# Description: Add your page endpoints here.

from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer
from lnbits.settings import settings

from .crud import get_hedgesats
from .helpers import lnurler

hedgesats_generic_router = APIRouter()


def hedgesats_renderer():
    return template_renderer(["hedgesats/templates"])


#######################################
##### ADD YOUR PAGE ENDPOINTS HERE ####
#######################################


# Backend admin page


@hedgesats_generic_router.get("/", response_class=HTMLResponse)
async def index(req: Request, user: User = Depends(check_user_exists)):
    return hedgesats_renderer().TemplateResponse(
        "hedgesats/index.html", {"request": req, "user": user.json()}
    )


# Frontend shareable page


@hedgesats_generic_router.get("/{hedgesats_id}")
async def hedgesats(req: Request, hedgesats_id):
    myex = await get_hedgesats(hedgesats_id)
    if not myex:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedgesats does not exist."
        )
    return hedgesats_renderer().TemplateResponse(
        "hedgesats/hedgesats.html",
        {
            "request": req,
            "hedgesats_id": hedgesats_id,
            "lnurlpay": lnurler(myex.id, "hedgesats.api_lnurl_pay", req),
            "web_manifest": f"/hedgesats/manifest/{hedgesats_id}.webmanifest",
        },
    )


# Manifest for public page, customise or remove manifest completely


@hedgesats_generic_router.get("/manifest/{hedgesats_id}.webmanifest")
async def manifest(hedgesats_id: str):
    hedgesats = await get_hedgesats(hedgesats_id)
    if not hedgesats:
        raise HTTPException(
            status_code=HTTPStatus.NOT_FOUND, detail="Hedgesats does not exist."
        )

    return {
        "short_name": settings.lnbits_site_title,
        "name": hedgesats.name + " - " + settings.lnbits_site_title,
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
        "start_url": "/hedgesats/" + hedgesats_id,
        "background_color": "#1F2234",
        "description": "Minimal extension to build on",
        "display": "standalone",
        "scope": "/hedgesats/" + hedgesats_id,
        "theme_color": "#1F2234",
        "shortcuts": [
            {
                "name": hedgesats.name + " - " + settings.lnbits_site_title,
                "short_name": hedgesats.name,
                "description": hedgesats.name + " - " + settings.lnbits_site_title,
                "url": "/hedgesats/" + hedgesats_id,
            }
        ],
    }
