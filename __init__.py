# __init__.py
import asyncio

from fastapi import APIRouter
from lnbits.tasks import create_permanent_unique_task
from loguru import logger

from .crud import db
from .tasks import reconciliation_loop, wait_for_paid_invoices
from .views import hedge_generic_router
from .views_api import hedge_api_router

hedge_ext: APIRouter = APIRouter(prefix="/hedge", tags=["Hedge"])
hedge_ext.include_router(hedge_generic_router)
hedge_ext.include_router(hedge_api_router)

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
    task1 = create_permanent_unique_task("ext_hedge_invoices", wait_for_paid_invoices)
    task2 = create_permanent_unique_task("ext_hedge_reconcile", reconciliation_loop)
    scheduled_tasks.extend([task1, task2])
    logger.info("Hedge extension: invoice listener a reconciliation loop spuštěny")


__all__ = [
    "db",
    "hedge_ext",
    "hedge_start",
    "hedge_static_files",
    "hedge_stop",
]
