import asyncio

from lnbits.core.models import Payment
from lnbits.core.services import websocket_updater
from lnbits.tasks import register_invoice_listener

from .crud import get_hedge, update_hedge
from .models import CreateHedgeData

#######################################
########## RUN YOUR TASKS HERE ########
#######################################

# The usual task is to listen to invoices related to this extension


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_hedge")
    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


# Do somethhing when an invoice related top this extension is paid


async def on_invoice_paid(payment: Payment) -> None:
    if payment.extra.get("tag") != "Hedge":
        return

    hedge_id = payment.extra.get("hedgeId")
    assert hedge_id, "hedgeId not set in invoice"
    hedge = await get_hedge(hedge_id)
    assert hedge, "Hedge does not exist"

    # update something in the db
    if payment.extra.get("lnurlwithdraw"):
        total = hedge.total - payment.amount
    else:
        total = hedge.total + payment.amount

    hedge.total = total
    await update_hedge(CreateHedgeData(**hedge.dict()))

    # here we could send some data to a websocket on
    # wss://<your-lnbits>/api/v1/ws/<hedge_id> and then listen to it on

    some_payment_data = {
        "name": hedge.name,
        "amount": payment.amount,
        "fee": payment.fee,
        "checking_id": payment.checking_id,
    }

    await websocket_updater(hedge_id, str(some_payment_data))
