import asyncio

from fastapi import APIRouter
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .crud import db
from .tasks import wait_for_paid_invoices
from .views import hedgesats_generic_router
from .views_api import hedgesats_api_router
from .views_lnurl import hedgesats_lnurl_router

logger.debug(
    "This logged message is from hedgesats/__init__.py, you can debug in your "
    "extension using 'import logger from loguru' and 'logger.debug(<thing-to-log>)'."
)


hedgesats_ext: APIRouter = APIRouter(prefix="/hedgesats", tags=["Hedgesats"])
hedgesats_ext.include_router(hedgesats_generic_router)
hedgesats_ext.include_router(hedgesats_api_router)
hedgesats_ext.include_router(hedgesats_lnurl_router)

hedgesats_static_files = [
    {
        "path": "/hedgesats/static",
        "name": "hedgesats_static",
    }
]

scheduled_tasks: list[asyncio.Task] = []


def hedgesats_stop():
    for task in scheduled_tasks:
        try:
            task.cancel()
        except Exception as ex:
            logger.warning(ex)


def hedgesats_start():
    task = create_permanent_unique_task("ext_hedgesats", wait_for_paid_invoices)
    scheduled_tasks.append(task)


__all__ = [
    "db",
    "hedgesats_ext",
    "hedgesats_start",
    "hedgesats_static_files",
    "hedgesats_stop",
]
