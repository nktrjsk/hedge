# Description: Extensions that use LNURL usually have a few endpoints in views_lnurl.py.

from http import HTTPStatus

import shortuuid
from fastapi import APIRouter, Query, Request
from lnbits.core.services import create_invoice, pay_invoice
from loguru import logger

from .crud import get_hedge

#################################################
########### A very simple LNURLpay ##############
# https://github.com/lnurl/luds/blob/luds/06.md #
#################################################
#################################################

hedge_lnurl_router = APIRouter()


@hedge_lnurl_router.get(
    "/api/v1/lnurl/pay/{hedge_id}",
    status_code=HTTPStatus.OK,
    name="hedge.api_lnurl_pay",
)
async def api_lnurl_pay(
    request: Request,
    hedge_id: str,
):
    hedge = await get_hedge(hedge_id)
    if not hedge:
        return {"status": "ERROR", "reason": "No hedge found"}
    return {
        "callback": str(
            request.url_for(
                "hedge.api_lnurl_pay_callback", hedge_id=hedge_id
            )
        ),
        "maxSendable": hedge.lnurlpayamount * 1000,
        "minSendable": hedge.lnurlpayamount * 1000,
        "metadata": '[["text/plain", "' + hedge.name + '"]]',
        "tag": "payRequest",
    }


@hedge_lnurl_router.get(
    "/api/v1/lnurl/paycb/{hedge_id}",
    status_code=HTTPStatus.OK,
    name="hedge.api_lnurl_pay_callback",
)
async def api_lnurl_pay_cb(
    request: Request,
    hedge_id: str,
    amount: int = Query(...),
):
    hedge = await get_hedge(hedge_id)
    logger.debug(hedge)
    if not hedge:
        return {"status": "ERROR", "reason": "No hedge found"}

    payment = await create_invoice(
        wallet_id=hedge.wallet,
        amount=int(amount / 1000),
        memo=hedge.name,
        unhashed_description=f'[["text/plain", "{hedge.name}"]]'.encode(),
        extra={
            "tag": "Hedge",
            "hedgeId": hedge_id,
            "extra": request.query_params.get("amount"),
        },
    )
    return {
        "pr": payment.bolt11,
        "routes": [],
        "successAction": {"tag": "message", "message": f"Paid {hedge.name}"},
    }


#################################################
######## A very simple LNURLwithdraw ############
# https://github.com/lnurl/luds/blob/luds/03.md #
#################################################
## withdraw is unlimited, look at withdraw ext ##
## for more advanced withdraw options          ##
#################################################


@hedge_lnurl_router.get(
    "/api/v1/lnurl/withdraw/{hedge_id}",
    status_code=HTTPStatus.OK,
    name="hedge.api_lnurl_withdraw",
)
async def api_lnurl_withdraw(
    request: Request,
    hedge_id: str,
):
    hedge = await get_hedge(hedge_id)
    if not hedge:
        return {"status": "ERROR", "reason": "No hedge found"}
    k1 = shortuuid.uuid(name=hedge.id)
    return {
        "tag": "withdrawRequest",
        "callback": str(
            request.url_for(
                "hedge.api_lnurl_withdraw_callback", hedge_id=hedge_id
            )
        ),
        "k1": k1,
        "defaultDescription": hedge.name,
        "maxWithdrawable": hedge.lnurlwithdrawamount * 1000,
        "minWithdrawable": hedge.lnurlwithdrawamount * 1000,
    }


@hedge_lnurl_router.get(
    "/api/v1/lnurl/withdrawcb/{hedge_id}",
    status_code=HTTPStatus.OK,
    name="hedge.api_lnurl_withdraw_callback",
)
async def api_lnurl_withdraw_cb(
    hedge_id: str,
    pr: str | None = None,
    k1: str | None = None,
):
    assert k1, "k1 is required"
    assert pr, "pr is required"
    hedge = await get_hedge(hedge_id)
    if not hedge:
        return {"status": "ERROR", "reason": "No hedge found"}

    k1_check = shortuuid.uuid(name=hedge.id)
    if k1_check != k1:
        return {"status": "ERROR", "reason": "Wrong k1 check provided"}

    await pay_invoice(
        wallet_id=hedge.wallet,
        payment_request=pr,
        max_sat=int(hedge.lnurlwithdrawamount * 1000),
        extra={
            "tag": "Hedge",
            "hedgeId": hedge_id,
            "lnurlwithdraw": True,
        },
    )
    return {"status": "OK"}
