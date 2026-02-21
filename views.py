# views.py
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from lnbits.core.models import User
from lnbits.decorators import check_user_exists
from lnbits.helpers import template_renderer

hedge_generic_router = APIRouter()


def hedge_renderer():
    return template_renderer(["hedge/templates"])


@hedge_generic_router.get("/", response_class=HTMLResponse)
async def index(req: Request, user: User = Depends(check_user_exists)):
    return hedge_renderer().TemplateResponse(
        "hedge/index.html", {"request": req, "user": user.json()}
    )
