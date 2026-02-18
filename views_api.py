# Description: This file contains the extensions API endpoints.

from http import HTTPStatus

from fastapi import APIRouter, Depends, Request
from lnbits.core.crud import get_user
from lnbits.core.models import WalletTypeInfo
from lnbits.core.services import create_invoice
from lnbits.decorators import require_admin_key, require_invoice_key
from starlette.exceptions import HTTPException

from .crud import (
    create_hedgesats,
    delete_hedgesats,
    get_hedgesats,
    get_hedgesatss,
    update_hedgesats,
)
from .helpers import lnurler
from .models import CreateHedgesatsData, CreatePayment, Hedgesats

hedgesats_api_router = APIRouter()

# Note: we add the lnurl params to returns so the links
# are generated in the Hedgesats model in models.py

## Get all the records belonging to the user


@hedgesats_api_router.get("/api/v1/myex")
async def api_hedgesatss(
    req: Request,  # Withoutthe lnurl stuff this wouldnt be needed
    wallet: WalletTypeInfo = Depends(require_invoice_key),
) -> list[Hedgesats]:
    wallet_ids = [wallet.wallet.id]
    user = await get_user(wallet.wallet.user)
    wallet_ids = user.wallet_ids if user else []
    hedgesatss = await get_hedgesatss(wallet_ids)

    # Populate lnurlpay and lnurlwithdraw for each instance.
    # Without the lnurl stuff this wouldnt be needed.
    for myex in hedgesatss:
        myex.lnurlpay = lnurler(myex.id, "hedgesats.api_lnurl_pay", req)
        myex.lnurlwithdraw = lnurler(myex.id, "hedgesats.api_lnurl_withdraw", req)

    return hedgesatss


## Get a single record


@hedgesats_api_router.get(
    "/api/v1/myex/{hedgesats_id}",
    dependencies=[Depends(require_invoice_key)],
)
async def api_hedgesats(hedgesats_id: str, req: Request) -> Hedgesats:
    myex = await get_hedgesats(hedgesats_id)
    if not myex:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedgesats does not exist."
        )
    # Populate lnurlpay and lnurlwithdraw.
    # Without the lnurl stuff this wouldnt be needed.
    myex.lnurlpay = lnurler(myex.id, "hedgesats.api_lnurl_pay", req)
    myex.lnurlwithdraw = lnurler(myex.id, "hedgesats.api_lnurl_withdraw", req)

    return myex


## Create a new record


@hedgesats_api_router.post("/api/v1/myex", status_code=HTTPStatus.CREATED)
async def api_hedgesats_create(
    req: Request,  # Withoutthe lnurl stuff this wouldnt be needed
    data: CreateHedgesatsData,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Hedgesats:
    myex = await create_hedgesats(data)

    # Populate lnurlpay and lnurlwithdraw.
    # Withoutthe lnurl stuff this wouldnt be needed.
    myex.lnurlpay = lnurler(myex.id, "hedgesats.api_lnurl_pay", req)
    myex.lnurlwithdraw = lnurler(myex.id, "hedgesats.api_lnurl_withdraw", req)

    return myex


## update a record


@hedgesats_api_router.put("/api/v1/myex/{hedgesats_id}")
async def api_hedgesats_update(
    req: Request,  # Withoutthe lnurl stuff this wouldnt be needed
    data: CreateHedgesatsData,
    hedgesats_id: str,
    wallet: WalletTypeInfo = Depends(require_admin_key),
) -> Hedgesats:
    myex = await get_hedgesats(hedgesats_id)
    if not myex:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedgesats does not exist."
        )

    if wallet.wallet.id != myex.wallet:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your Hedgesats."
        )

    for key, value in data.dict().items():
        setattr(myex, key, value)

    myex = await update_hedgesats(data)

    # Populate lnurlpay and lnurlwithdraw.
    # Without the lnurl stuff this wouldnt be needed.
    myex.lnurlpay = lnurler(myex.id, "hedgesats.api_lnurl_pay", req)
    myex.lnurlwithdraw = lnurler(myex.id, "hedgesats.api_lnurl_withdraw", req)

    return myex


## Delete a record


@hedgesats_api_router.delete("/api/v1/myex/{hedgesats_id}")
async def api_hedgesats_delete(
    hedgesats_id: str, wallet: WalletTypeInfo = Depends(require_admin_key)
):
    myex = await get_hedgesats(hedgesats_id)

    if not myex:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedgesats does not exist."
        )

    if myex.wallet != wallet.wallet.id:
        raise HTTPException(
            status_code=HTTPStatus.FORBIDDEN, detail="Not your Hedgesats."
        )

    await delete_hedgesats(hedgesats_id)
    return


# ANY OTHER ENDPOINTS YOU NEED

## This endpoint creates a payment


@hedgesats_api_router.post("/api/v1/myex/payment", status_code=HTTPStatus.CREATED)
async def api_hedgesats_create_invoice(data: CreatePayment) -> dict:
    hedgesats = await get_hedgesats(data.hedgesats_id)

    if not hedgesats:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedgesats does not exist."
        )

    # we create a payment and add some tags,
    # so tasks.py can grab the payment once its paid

    payment = await create_invoice(
        wallet_id=hedgesats.wallet,
        amount=data.amount,
        memo=(
            f"{data.memo} to {hedgesats.name}" if data.memo else f"{hedgesats.name}"
        ),
        extra={
            "tag": "hedgesats",
            "amount": data.amount,
        },
    )

    return {"payment_hash": payment.payment_hash, "payment_request": payment.bolt11}
