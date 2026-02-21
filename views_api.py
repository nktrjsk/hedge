# Description: This file contains the extensions API endpoints.

from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from lnbits.core.crud import get_user
from lnbits.core.models import WalletTypeInfo
from lnbits.core.services import create_invoice
from lnbits.decorators import require_admin_key, require_invoice_key
from starlette.exceptions import HTTPException

from .crud import (
    create_hedge,
    delete_hedge,
    get_hedge,
    get_hedges,
    update_hedge,
)
from .helpers import lnurler
from .models import CreateHedgeData, CreatePayment, Hedge

hedge_api_router = APIRouter()

# Note: we add the lnurl params to returns so the links
# are generated in the Hedge model in models.py

## Get all the records belonging to the user


@hedge_api_router.get("/api/v1/myex")
async def api_hedges(
    req: Request,  # Withoutthe lnurl stuff this wouldnt be needed
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Hedge]:
    wallet_ids = [wallet.wallet.id]
    user = await get_user(wallet.wallet.user)
    wallet_ids = user.wallet_ids if user else []
    hedges = await get_hedges(wallet_ids)

    # Populate lnurlpay and lnurlwithdraw for each instance.
    # Without the lnurl stuff this wouldnt be needed.
    for myex in hedges:
        myex.lnurlpay = lnurler(myex.id, "hedge.api_lnurl_pay", req)
        myex.lnurlwithdraw = lnurler(myex.id, "hedge.api_lnurl_withdraw", req)

    return hedges


## Get a single record


@hedge_api_router.get(
    "/api/v1/myex/{hedge_id}",
    dependencies=[Depends(require_invoice_key)],
)
async def api_hedge(hedge_id: str, req: Request) -> Hedge:
    myex = await get_hedge(hedge_id)
    if not myex:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedge does not exist."
        )
    # Populate lnurlpay and lnurlwithdraw.
    # Without the lnurl stuff this wouldnt be needed.
    myex.lnurlpay = lnurler(myex.id, "hedge.api_lnurl_pay", req)
    myex.lnurlwithdraw = lnurler(myex.id, "hedge.api_lnurl_withdraw", req)

    return myex


## Create a new record


@hedge_api_router.post("/api/v1/myex", status_code=HTTPStatus.CREATED)
async def api_hedge_create(
    req: Request,  # Withoutthe lnurl stuff this wouldnt be needed
    data: CreateHedgeData,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Hedge:
    myex = await create_hedge(data)

    # Populate lnurlpay and lnurlwithdraw.
    # Withoutthe lnurl stuff this wouldnt be needed.
    myex.lnurlpay = lnurler(myex.id, "hedge.api_lnurl_pay", req)
    myex.lnurlwithdraw = lnurler(myex.id, "hedge.api_lnurl_withdraw", req)

    return myex


## update a record


@hedge_api_router.put("/api/v1/myex/{hedge_id}")
async def api_hedge_update(
    req: Request,  # Withoutthe lnurl stuff this wouldnt be needed
    data: CreateHedgeData,
    hedge_id: str,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Hedge:
    myex = await get_hedge(hedge_id)
    if not myex:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedge does not exist."
        )

    if wallet.wallet.id != myex.wallet:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your Hedge."
        )

    for key, value in data.dict().items():
        setattr(myex, key, value)

    myex = await update_hedge(data)

    # Populate lnurlpay and lnurlwithdraw.
    # Without the lnurl stuff this wouldnt be needed.
    myex.lnurlpay = lnurler(myex.id, "hedge.api_lnurl_pay", req)
    myex.lnurlwithdraw = lnurler(myex.id, "hedge.api_lnurl_withdraw", req)

    return myex


## Delete a record


@hedge_api_router.delete("/api/v1/myex/{hedge_id}")
async def api_hedge_delete(
    hedge_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
    myex = await get_hedge(hedge_id)

    if not myex:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedge does not exist."
        )

    if myex.wallet != wallet.wallet.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your Hedge."
        )

    await delete_hedge(hedge_id)
    return


# ANY OTHER ENDPOINTS YOU NEED

## This endpoint creates a payment


@hedge_api_router.post("/api/v1/myex/payment", status_code=HTTPStatus.CREATED)
async def api_hedge_create_invoice(data: CreatePayment) -> dict:
    hedge = await get_hedge(data.hedge_id)

    if not hedge:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedge does not exist."
        )

    # we create a payment and add some tags,
    # so tasks.py can grab the payment once its paid

    payment = await create_invoice(
        wallet_id=hedge.wallet,
        amount=data.amount,
        memo=(
            f"{data.memo} to {hedge.name}" if data.memo else f"{hedge.name}"
        ),
        extra={
            "tag": "hedge",
            "amount": data.amount,
        },
    )

    return {"payment_hash": payment.payment_hash, "payment_request": payment.bolt11}
