from http import HTTPStatus
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from lnbits.core.crud import get_user, get_wallet
from lnbits.core.models import WalletTypeInfo
from lnbits.decorators import require_admin_key, require_invoice_key

from .crud import (
    create_event,
    delete_config,
    get_all_enabled_hedged_wallet_ids,
    get_config,
    get_events,
    get_hedged_wallets,
    save_config,
    set_hedged_wallets,
)
from .lnmarkets import LNMarketsClient, LNMarketsError
from .models import HedgeConfig, HedgeConfigData, HedgeEvent, HedgeStatus, WalletStatus

hedge_api_router = APIRouter()


# ── Config (globální LNM nastavení) ──────────────────────────────────────────

@hedge_api_router.get("/api/v1/config")
async def api_get_config(
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Optional[dict]:
    config = await get_config()
    if not config:
        return None
    return {
        "lnm_key": config.lnm_key[:6] + "..." if config.lnm_key else "",
        "lnm_secret": "***",
        "lnm_passphrase": "***",
        "leverage": config.leverage,
        "testnet": config.testnet,
        "last_synced": config.last_synced,
        "last_error": config.last_error,
    }


@hedge_api_router.post("/api/v1/config", status_code=HTTPStatus.CREATED)
async def api_save_config(
    data: HedgeConfigData,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    if data.leverage < 1 or data.leverage > 10:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Leverage musí být mezi 1 a 10",
        )
    try:
        client = LNMarketsClient(
            key=data.lnm_key,
            secret=data.lnm_secret,
            passphrase=data.lnm_passphrase,
            testnet=data.testnet,
        )
        await client.get_user()
    except LNMarketsError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Nepodařilo se ověřit LNMarkets API klíče: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail=f"Chyba připojení k LNMarkets: {e}",
        )

    await save_config(data)
    return {"status": "ok"}


@hedge_api_router.delete("/api/v1/config", status_code=HTTPStatus.NO_CONTENT)
async def api_delete_config(
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> None:
    await delete_config()


# ── Hedgované peněženky ───────────────────────────────────────────────────────

@hedge_api_router.get("/api/v1/wallets")
async def api_get_wallets(
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> list[str]:
    """Vrátí seznam wallet_id které jsou momentálně hedgovány."""
    return await get_all_enabled_hedged_wallet_ids()


@hedge_api_router.put("/api/v1/wallets")
async def api_set_wallets(
    wallet_ids: list[str],
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    """Nahradí celý seznam hedgovaných walletů."""
    config = await get_config()
    if not config:
        raise HTTPException(
            status_code=HTTPStatus.BAD_REQUEST,
            detail="Nejprve nastavte LNMarkets API klíče",
        )
    await set_hedged_wallets(wallet_ids)
    return {"status": "ok", "hedged_wallets": wallet_ids}


# ── Status ───────────────────────────────────────────────────────────────────

@hedge_api_router.get("/api/v1/status")
async def api_get_status(
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> HedgeStatus:
    config = await get_config()
    if not config:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Hedge není nakonfigurován",
        )

    hedged_ids = await get_all_enabled_hedged_wallet_ids()

    try:
        client = LNMarketsClient(
            key=config.lnm_key,
            secret=config.lnm_secret,
            passphrase=config.lnm_passphrase,
            testnet=config.testnet,
        )
        price   = await client.get_price()
        summary = await client.get_account_summary()
    except LNMarketsError as e:
        raise HTTPException(
            status_code=HTTPStatus.BAD_GATEWAY,
            detail=f"LNMarkets API nedostupné: {e}",
        )

    total_sats = 0
    for wid in hedged_ids:
        w = await get_wallet(wid)
        if w:
            total_sats += w.balance_msat // 1000

    total_usd = total_sats / 100_000_000 * price
    drift_usd = total_usd - summary.total_short_usd
    drift_pct = (drift_usd / total_usd * 100) if total_usd > 0 else 0.0

    return HedgeStatus(
        configured=True,
        lnm_account_balance_sats=summary.balance,
        lnm_free_collateral_usd=round(summary.free_collateral_sats / 100_000_000 * price, 2),
        lnm_free_collateral_sats=summary.free_collateral_sats,
        lnm_liquidation_price=summary.liquidation_price,
        btc_price=price,
        total_wallet_sats=total_sats,
        total_wallet_usd=round(total_usd, 2),
        lnm_short_usd=round(summary.total_short_usd, 2),
        drift_usd=round(drift_usd, 2),
        drift_pct=round(drift_pct, 2),
        hedged_wallets=hedged_ids,
        last_synced=config.last_synced,
        last_error=config.last_error,
    )


@hedge_api_router.get("/api/v1/wallet-statuses")
async def api_wallet_statuses(
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[WalletStatus]:
    """Vrátí balance každé hedgované peněženky."""
    config = await get_config()
    if not config:
        return []

    hedged_ids = await get_all_enabled_hedged_wallet_ids()

    try:
        client = LNMarketsClient(
            key=config.lnm_key,
            secret=config.lnm_secret,
            passphrase=config.lnm_passphrase,
            testnet=config.testnet,
        )
        price = await client.get_price()
    except Exception:
        price = 0.0

    result = []
    for wid in hedged_ids:
        w = await get_wallet(wid)
        if w:
            sats = w.balance_msat // 1000
            result.append(WalletStatus(
                wallet_id=wid,
                wallet_name=w.name,
                balance_sats=sats,
                balance_usd=round(sats / 100_000_000 * price, 2) if price else 0.0,
                enabled=True,
            ))
    return result


# ── Manual sync ───────────────────────────────────────────────────────────────

@hedge_api_router.post("/api/v1/sync")
async def api_manual_sync(
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> dict:
    from .tasks import reconcile_wallet
    import asyncio

    config = await get_config()
    if not config:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND,
            detail="Hedge není nakonfigurován",
        )

    hedged_ids = await get_all_enabled_hedged_wallet_ids()
    for wid in hedged_ids:
        asyncio.create_task(reconcile_wallet(wid))
    return {"status": "ok"}


# ── Events ────────────────────────────────────────────────────────────────────

@hedge_api_router.get("/api/v1/events")
async def api_get_events(
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[HedgeEvent]:
    return await get_events(limit=100)
