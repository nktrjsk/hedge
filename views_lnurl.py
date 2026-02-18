# Description: Extensions that use LNURL usually have a few endpoints in views_lnurl.py.

from http import HTTPStatus

import shortuuid
from fastapi import APIRouter, Query, Request
from lnbits.core.services import create_invoice, pay_invoice
from loguru import logger

from .crud import get_hedgesats

#################################################
########### A very simple LNURLpay ##############
# https://github.com/lnurl/luds/blob/luds/06.md #
#################################################
#################################################

hedgesats_lnurl_router = APIRouter()


@hedgesats_lnurl_router.get(
    "/api/v1/lnurl/pay/{hedgesats_id}",
    status_code=HTTPStatus.OK,
    name="hedgesats.api_lnurl_pay",
)
async def api_lnurl_pay(
    request: Request,
    hedgesats_id: str,
):
    hedgesats = await get_hedgesats(hedgesats_id)
    if not hedgesats:
        return {"status": "ERROR", "reason": "No hedgesats found"}
    return {
        "callback": str(
            request.url_for(
                "hedgesats.api_lnurl_pay_callback", hedgesats_id=hedgesats_id
            )
        ),
        "maxSendable": hedgesats.lnurlpayamount * 1000,
        "minSendable": hedgesats.lnurlpayamount * 1000,
        "metadata": '[["text/plain", "' + hedgesats.name + '"]]',
        "tag": "payRequest",
    }


@hedgesats_lnurl_router.get(
    "/api/v1/lnurl/paycb/{hedgesats_id}",
    status_code=HTTPStatus.OK,
    name="hedgesats.api_lnurl_pay_callback",
)
async def api_lnurl_pay_cb(
    request: Request,
    hedgesats_id: str,
    amount: int = Query(...),
):
    hedgesats = await get_hedgesats(hedgesats_id)
    logger.debug(hedgesats)
    if not hedgesats:
        return {"status": "ERROR", "reason": "No hedgesats found"}

    payment = await create_invoice(
        wallet_id=hedgesats.wallet,
        amount=int(amount / 1000),
        memo=hedgesats.name,
        unhashed_description=f'[["text/plain", "{hedgesats.name}"]]'.encode(),
        extra={
            "tag": "Hedgesats",
            "hedgesatsId": hedgesats_id,
            "extra": request.query_params.get("amount"),
        },
    )
    return {
        "pr": payment.bolt11,
        "routes": [],
        "successAction": {"tag": "message", "message": f"Paid {hedgesats.name}"},
    }


#################################################
######## A very simple LNURLwithdraw ############
# https://github.com/lnurl/luds/blob/luds/03.md #
#################################################
## withdraw is unlimited, look at withdraw ext ##
## for more advanced withdraw options          ##
#################################################


@hedgesats_lnurl_router.get(
    "/api/v1/lnurl/withdraw/{hedgesats_id}",
    status_code=HTTPStatus.OK,
    name="hedgesats.api_lnurl_withdraw",
)
async def api_lnurl_withdraw(
    request: Request,
    hedgesats_id: str,
):
    hedgesats = await get_hedgesats(hedgesats_id)
    if not hedgesats:
        return {"status": "ERROR", "reason": "No hedgesats found"}
    k1 = shortuuid.uuid(name=hedgesats.id)
    return {
        "tag": "withdrawRequest",
        "callback": str(
            request.url_for(
                "hedgesats.api_lnurl_withdraw_callback", hedgesats_id=hedgesats_id
            )
        ),
        "k1": k1,
        "defaultDescription": hedgesats.name,
        "maxWithdrawable": hedgesats.lnurlwithdrawamount * 1000,
        "minWithdrawable": hedgesats.lnurlwithdrawamount * 1000,
    }


@hedgesats_lnurl_router.get(
    "/api/v1/lnurl/withdrawcb/{hedgesats_id}",
    status_code=HTTPStatus.OK,
    name="hedgesats.api_lnurl_withdraw_callback",
)
async def api_lnurl_withdraw_cb(
    hedgesats_id: str,
    pr: str | None = None,
    k1: str | None = None,
):
    assert k1, "k1 is required"
    assert pr, "pr is required"
    hedgesats = await get_hedgesats(hedgesats_id)
    if not hedgesats:
        return {"status": "ERROR", "reason": "No hedgesats found"}

    k1_check = shortuuid.uuid(name=hedgesats.id)
    if k1_check != k1:
        return {"status": "ERROR", "reason": "Wrong k1 check provided"}

    await pay_invoice(
        wallet_id=hedgesats.wallet,
        payment_request=pr,
        max_sat=int(hedgesats.lnurlwithdrawamount * 1000),
        extra={
            "tag": "Hedgesats",
            "hedgesatsId": hedgesats_id,
            "lnurlwithdraw": True,
        },
    )
    return {"status": "OK"}
