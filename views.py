# Description: Add your page endpoints here.

from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from lnbits.settings import settings

from .crud import get_hedge
from .helpers import lnurler

hedge_generic_router = APIRouter()


def hedge_renderer():
    return template_renderer(["hedge/templates"])


#######################################
##### ADD YOUR PAGE ENDPOINTS HERE ####
#######################################


# Backend admin page


@hedge_generic_router.get("/", response_class=HTMLResponse)
async def index(req: Request, user: User = Depends(check_user_exists)):
    return hedge_renderer().TemplateResponse(
        "hedge/index.html", {"request": req, "user": user.json()}
    )


# Frontend shareable page


@hedge_generic_router.get("/{hedge_id}")
async def hedge(req: Request, hedge_id):
    myex = await get_hedge(hedge_id)
    if not myex:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedge does not exist."
        )
    return hedge_renderer().TemplateResponse(
        "hedge/hedge.html",
        {
            "request": req,
            "hedge_id": hedge_id,
            "lnurlpay": lnurler(myex.id, "hedge.api_lnurl_pay", req),
            "web_manifest": f"/hedge/manifest/{hedge_id}.webmanifest",
        },
    )


# Manifest for public page, customise or remove manifest completely


@hedge_generic_router.get("/manifest/{hedge_id}.webmanifest")
async def manifest(hedge_id: str):
    hedge = await get_hedge(hedge_id)
    if not hedge:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedge does not exist."
        )

    return {
        "short_name": settings.lnbits_site_title,
        "name": hedge.name + " - " + settings.lnbits_site_title,
        "icons": [
            {
                "src": (
                    settings.lnbits_custom_logo
                    if settings.lnbits_custom_logo
                    else "https://cdn.jsdelivr.net/gh/lnbits/lnbits@0.3.0/docs/logos/lnbits.png"
                ),
                "type": "image/png",
                "sizes": "900x900",
            }
        ],
        "start_url": "/hedge/" + hedge_id,
        "background_color": "#1F2234",
        "description": "Minimal extension to build on",
        "display": "standalone",
        "scope": "/hedge/" + hedge_id,
        "theme_color": "#1F2234",
        "shortcuts": [
            {
                "name": hedge.name + " - " + settings.lnbits_site_title,
                "short_name": hedge.name,
                "description": hedge.name + " - " + settings.lnbits_site_title,
                "url": "/hedge/" + hedge_id,
            }
        ],
    }
