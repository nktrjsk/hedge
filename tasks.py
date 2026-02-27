import asyncio
import time

from lnbits.core.crud import get_payments
from lnbits.core.models import Payment
from lnbits.tasks import register_invoice_listener
from loguru import logger

from .crud import (
    create_event,
    get_all_enabled_hedged_wallet_ids,
    get_config,
    get_hedged_wallet,
    update_config_sync,
)
from .lnmarkets import LNMarketsClient, LNMarketsError

RECONCILE_INTERVAL_SEC = 60

# Globální lock — hedge má jeden LNM účet, operace musí být serializované
_global_lock = asyncio.Lock()

# Unix timestamp posledního prověření odchozích plateb
_last_outgoing_check: int = 0


async def wait_for_paid_invoices():
    invoice_queue: asyncio.Queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_hedge")
    logger.info("Hedge: invoice listener spuštěn")
    while True:
        payment: Payment = await invoice_queue.get()
        asyncio.create_task(on_payment(payment))


async def on_payment(payment: Payment) -> None:
    wallet_id = payment.wallet_id

    hw = await get_hedged_wallet(wallet_id)
    if not hw or not hw.enabled:
        return

    config = await get_config()
    if not config:
        return

    sats_delta = payment.amount // 1000
    logger.info(f"Hedge: příchozí platba wallet={wallet_id[:8]}… +{sats_delta} sats")

    async with _global_lock:
        await adjust_hedge(
            wallet_id=wallet_id,
            sats_delta=sats_delta,
            payment_hash=payment.checking_id,
            event_type="payment_received",
        )


async def reconciliation_loop():
    """
    Každých 60 s zachytí odchozí platby z hedgovaných walletů a sníží short.
    Příchozí platby jsou zpracovány okamžitě přes invoice listener.
    Sanity check logika bude doplněna.
    """
    global _last_outgoing_check
    _last_outgoing_check = int(time.time())
    logger.info("Hedge: reconciliation loop spuštěna")
    while True:
        await asyncio.sleep(RECONCILE_INTERVAL_SEC)
        try:
            await check_outgoing_payments()
        except Exception as e:
            logger.error(f"Hedge: check_outgoing_payments chyba: {e}")


async def check_outgoing_payments() -> None:
    global _last_outgoing_check

    config = await get_config()
    if not config:
        return

    wallet_ids = await get_all_enabled_hedged_wallet_ids()
    if not wallet_ids:
        return

    since = _last_outgoing_check
    _last_outgoing_check = int(time.time())

    for wallet_id in wallet_ids:
        payments = await get_payments(
            wallet_id=wallet_id,
            outgoing=True,
            complete=True,
            since=since,
        )
        for payment in payments:
            sats = abs(payment.amount) // 1000
            if sats == 0:
                continue
            logger.info(f"Hedge: odchozí platba wallet={wallet_id[:8]}… -{sats} sats")
            async with _global_lock:
                await adjust_hedge(
                    wallet_id=wallet_id,
                    sats_delta=-sats,
                    payment_hash=payment.checking_id,
                    event_type="payment_sent",
                )


async def manual_sync() -> None:
    """
    Ruční sync: porovná reálný zůstatek hedgovaných walletů (v sats)
    s aktuální short pozicí na LNM a dorovná rozdíl.
    Volá se ze sync tlačítka — není závislé na pohybu ceny,
    slouží k opravě driftu způsobeného zmeškanými platbami.
    """
    config = await get_config()
    if not config:
        return

    wallet_ids = await get_all_enabled_hedged_wallet_ids()
    if not wallet_ids:
        return

    async with _global_lock:
        try:
            from lnbits.core.crud import get_wallet

            client = LNMarketsClient(
                key=config.lnm_key,
                secret=config.lnm_secret,
                passphrase=config.lnm_passphrase,
                testnet=config.testnet,
            )

            price   = await client.get_price()
            summary = await client.get_account_summary()

            total_sats = 0
            for wid in wallet_ids:
                w = await get_wallet(wid)
                if w:
                    total_sats += w.balance_msat // 1000

            target_usd      = total_sats / 100_000_000 * price
            current_short   = summary.total_short_usd
            drift_usd       = target_usd - current_short

            logger.info(
                f"Manual sync: wallet={target_usd:.2f} USD, "
                f"short={current_short:.2f} USD, drift={drift_usd:+.2f} USD"
            )

            # Prázdný wallet → zavřít celou pozici najednou (obejde double rounding)
            if total_sats == 0 and current_short > 0:
                logger.info("Manual sync: wallet prázdný, zavírám celou pozici")
                await client.close_position()
                await update_config_sync(last_error=None)
                return

            if abs(drift_usd) < 1.0:
                await update_config_sync(last_error=None)
                return

            sats_delta = int(abs(drift_usd) / price * 100_000_000)
            if drift_usd < 0:
                sats_delta = -sats_delta

            await adjust_hedge(
                wallet_id=wallet_ids[0],
                sats_delta=sats_delta,
                payment_hash=None,
                event_type="manual_sync",
                _price_override=price,
                _client=client,
            )

        except Exception as e:
            logger.error(f"Manual sync selhalo: {e}")
            await update_config_sync(last_error=str(e))


# Stub zachován pro zpětnou kompatibilitu
async def reconcile_wallet(wallet_id: str) -> None:
    pass


async def adjust_hedge(
    wallet_id: str,
    sats_delta: int,
    payment_hash: str | None,
    event_type: str,
    _price_override: float | None = None,
    _client: LNMarketsClient | None = None,
) -> None:
    config = await get_config()
    if not config:
        return

    try:
        client = _client or LNMarketsClient(
            key=config.lnm_key,
            secret=config.lnm_secret,
            passphrase=config.lnm_passphrase,
            testnet=config.testnet,
        )

        price        = _price_override or await client.get_price()
        usd_notional = abs(sats_delta) / 100_000_000 * price

        if usd_notional < 1.0:
            logger.info(
                f"Hedge: {sats_delta} sats = {usd_notional:.4f} USD "
                f"— pod minimem LNM, přeskakuji"
            )
            await create_event(
                wallet_id=wallet_id, event_type=event_type,
                sats_delta=sats_delta, usd_price=price,
                usd_notional_delta=0.0, status="skipped",
                payment_hash=payment_hash,
                error_msg="Pod minimem LNM (1 USD)",
            )
            return

        if sats_delta > 0:
            order_id = await client.open_short(usd_quantity=usd_notional, leverage=config.leverage)
        else:
            order_id = await client.reduce_short(usd_quantity=usd_notional)

        await create_event(
            wallet_id=wallet_id, event_type=event_type,
            sats_delta=sats_delta, usd_price=price,
            usd_notional_delta=usd_notional if sats_delta > 0 else -usd_notional,
            status="success", payment_hash=payment_hash, lnm_trade_id=order_id,
        )
        await update_config_sync(last_error=None)

    except LNMarketsError as e:
        logger.error(f"Hedge LNM chyba wallet={wallet_id[:8]}: {e}")
        await create_event(
            wallet_id=wallet_id, event_type=event_type,
            sats_delta=sats_delta, usd_price=0.0,
            usd_notional_delta=0.0, status="failed",
            payment_hash=payment_hash, error_msg=str(e),
        )
        await update_config_sync(last_error=str(e))

    except Exception as e:
        logger.error(f"Hedge neočekávaná chyba wallet={wallet_id[:8]}: {e}")
        await update_config_sync(last_error=f"Neočekávaná chyba: {e}")
