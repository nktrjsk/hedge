import asyncio

from lnbits.core.models import Payment
from lnbits.core.services import websocket_updater
from lnbits.tasks import register_invoice_listener

from .crud import get_hedgesats, update_hedgesats
from .models import CreateHedgesatsData

#######################################
########## RUN YOUR TASKS HERE ########
#######################################

# The usual task is to listen to invoices related to this extension


async def wait_for_paid_invoices():
    invoice_queue = asyncio.Queue()
    register_invoice_listener(invoice_queue, "ext_hedgesats")
    while True:
        payment = await invoice_queue.get()
        await on_invoice_paid(payment)


# Do somethhing when an invoice related top this extension is paid


async def on_invoice_paid(payment: Payment) -> None:
    if payment.extra.get("tag") != "Hedgesats":
        return

    hedgesats_id = payment.extra.get("hedgesatsId")
    assert hedgesats_id, "hedgesatsId not set in invoice"
    hedgesats = await get_hedgesats(hedgesats_id)
    assert hedgesats, "Hedgesats does not exist"

    # update something in the db
    if payment.extra.get("lnurlwithdraw"):
        total = hedgesats.total - payment.amount
    else:
        total = hedgesats.total + payment.amount

    hedgesats.total = total
    await update_hedgesats(CreateHedgesatsData(**hedgesats.dict()))

    # here we could send some data to a websocket on
    # wss://<your-lnbits>/api/v1/ws/<hedgesats_id> and then listen to it on

    some_payment_data = {
        "name": hedgesats.name,
        "amount": payment.amount,
        "fee": payment.fee,
        "checking_id": payment.checking_id,
    }

    await websocket_updater(hedgesats_id, str(some_payment_data))
