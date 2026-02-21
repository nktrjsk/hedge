import asyncio

from fastapi import APIRouter
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import hedge_generic_router
from .views_api import hedge_api_router
from .views_lnurl import hedge_lnurl_router

logger.debug(
    "This logged message is from hedge/__init__.py, you can debug in your "
    "extension using 'import logger from loguru' and 'logger.debug(<thing-to-log>)'."
)


hedge_ext: APIRouter = APIRouter(prefix="/hedge", tags=["Hedge"])
hedge_ext.include_router(hedge_generic_router)
hedge_ext.include_router(hedge_api_router)
hedge_ext.include_router(hedge_lnurl_router)

hedge_static_files = [
    {
        "path": "/hedge/static",
        "name": "hedge_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []


def hedge_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def hedge_start():
    task = create_permanent_unique_task("ext_hedge", wait_for_paid_invoices)
    scheduled_tasks.append(task)


__all__ = [
    "db",
    "hedge_ext",
    "hedge_start",
    "hedge_static_files",
    "hedge_stop",
]
