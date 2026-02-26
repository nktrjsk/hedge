from datetime import datetime
from typing import Optional

from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import (
    CreateHedgeData,
    Hedge,
    HedgeConfig,
    HedgeConfigData,
    HedgeEvent,
    HedgedWallet,
)

db = Database("ext_hedge")


# ── Původní template CRUD (zachováno) ────────────────────────────────────────

async def create_hedge(data: CreateHedgeData) -> Hedge:
    data.id = urlsafe_short_hash()
    await db.insert("hedge.maintable", data)
    return Hedge(**data.dict())


async def get_hedge(hedge_id: str) -> Optional[Hedge]:
    return await db.fetchone(
        "SELECT * FROM hedge.maintable WHERE id = :id",
        {"id": hedge_id},
        Hedge,
    )


async def get_hedges(wallet_ids: str | list[str]) -> list[Hedge]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{w}'" for w in wallet_ids])
    return await db.fetchall(
        f"SELECT * FROM hedge.maintable WHERE wallet IN ({q}) ORDER BY id",
        model=Hedge,
    )


async def update_hedge(data: CreateHedgeData) -> Hedge:
    await db.update("hedge.maintable", data)
    return Hedge(**data.dict())


async def delete_hedge(hedge_id: str) -> None:
    await db.execute(
        "DELETE FROM hedge.maintable WHERE id = :id", {"id": hedge_id}
    )


# ── Globální LNM konfigurace ──────────────────────────────────────────────────

async def get_config() -> Optional[HedgeConfig]:
    return await db.fetchone(
        "SELECT * FROM hedge.config WHERE id = 1",
        {},
        HedgeConfig,
    )


async def save_config(data: HedgeConfigData) -> HedgeConfig:
    existing = await get_config()
    if existing:
        await db.execute(
            """
            UPDATE hedge.config
            SET lnm_key = :lnm_key,
                lnm_secret = :lnm_secret,
                lnm_passphrase = :lnm_passphrase,
                leverage = :leverage,
                testnet = :testnet
            WHERE id = 1
            """,
            {
                "lnm_key": data.lnm_key,
                "lnm_secret": data.lnm_secret,
                "lnm_passphrase": data.lnm_passphrase,
                "leverage": data.leverage,
                "testnet": data.testnet,
            },
        )
    else:
        await db.execute(
            """
            INSERT INTO hedge.config
                (id, lnm_key, lnm_secret, lnm_passphrase, leverage, testnet)
            VALUES
                (1, :lnm_key, :lnm_secret, :lnm_passphrase, :leverage, :testnet)
            """,
            {
                "lnm_key": data.lnm_key,
                "lnm_secret": data.lnm_secret,
                "lnm_passphrase": data.lnm_passphrase,
                "leverage": data.leverage,
                "testnet": data.testnet,
            },
        )
    result = await get_config()
    assert result
    return result


async def update_config_sync(
    last_synced: Optional[datetime] = None,
    last_error: Optional[str] = None,
) -> None:
    await db.execute(
        """
        UPDATE hedge.config
        SET last_synced = :last_synced, last_error = :last_error
        WHERE id = 1
        """,
        {
            "last_synced": last_synced or datetime.utcnow(),
            "last_error": last_error,
        },
    )


async def delete_config() -> None:
    await db.execute("DELETE FROM hedge.config WHERE id = 1", {})


# ── Hedgované peněženky ───────────────────────────────────────────────────────

async def get_hedged_wallets() -> list[HedgedWallet]:
    return await db.fetchall(
        "SELECT * FROM hedge.hedged_wallets ORDER BY wallet_id",
        model=HedgedWallet,
    )


async def get_hedged_wallet(wallet_id: str) -> Optional[HedgedWallet]:
    return await db.fetchone(
        "SELECT * FROM hedge.hedged_wallets WHERE wallet_id = :wallet_id",
        {"wallet_id": wallet_id},
        HedgedWallet,
    )


async def set_hedged_wallets(wallet_ids: list[str]) -> None:
    """Nahradí celý seznam hedgovaných walletů."""
    await db.execute("DELETE FROM hedge.hedged_wallets", {})
    for wid in wallet_ids:
        await db.execute(
            "INSERT INTO hedge.hedged_wallets (wallet_id, enabled) VALUES (:wallet_id, TRUE)",
            {"wallet_id": wid},
        )


async def get_all_enabled_hedged_wallet_ids() -> list[str]:
    rows = await db.fetchall(
        "SELECT wallet_id FROM hedge.hedged_wallets WHERE enabled = TRUE",
        model=HedgedWallet,
    )
    return [r.wallet_id for r in rows]


# ── HedgeEvents CRUD ─────────────────────────────────────────────────────────

async def create_event(
    wallet_id: str,
    event_type: str,
    sats_delta: int,
    usd_price: float,
    usd_notional_delta: float,
    status: str = "success",
    payment_hash: Optional[str] = None,
    lnm_trade_id: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> HedgeEvent:
    event_id = urlsafe_short_hash()
    now = datetime.utcnow()
    await db.execute(
        """
        INSERT INTO hedge.events
            (id, wallet_id, created_at, event_type, payment_hash,
             sats_delta, usd_price, usd_notional_delta, lnm_trade_id, status, error_msg)
        VALUES
            (:id, :wallet_id, :created_at, :event_type, :payment_hash,
             :sats_delta, :usd_price, :usd_notional_delta, :lnm_trade_id, :status, :error_msg)
        """,
        {
            "id": event_id, "wallet_id": wallet_id, "created_at": now,
            "event_type": event_type, "payment_hash": payment_hash,
            "sats_delta": sats_delta, "usd_price": usd_price,
            "usd_notional_delta": usd_notional_delta,
            "lnm_trade_id": lnm_trade_id, "status": status, "error_msg": error_msg,
        },
    )
    return HedgeEvent(
        id=event_id, wallet_id=wallet_id, created_at=now,
        event_type=event_type, payment_hash=payment_hash,
        sats_delta=sats_delta, usd_price=usd_price,
        usd_notional_delta=usd_notional_delta,
        lnm_trade_id=lnm_trade_id, status=status, error_msg=error_msg,
    )


async def get_events(wallet_id: Optional[str] = None, limit: int = 100) -> list[HedgeEvent]:
    if wallet_id:
        return await db.fetchall(
            "SELECT * FROM hedge.events WHERE wallet_id = :wallet_id ORDER BY created_at DESC LIMIT :limit",
            {"wallet_id": wallet_id, "limit": limit},
            HedgeEvent,
        )
    return await db.fetchall(
        "SELECT * FROM hedge.events ORDER BY created_at DESC LIMIT :limit",
        {"limit": limit},
        HedgeEvent,
    )
