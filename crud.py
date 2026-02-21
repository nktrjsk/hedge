# Description: This file contains the CRUD operations for talking to the database.


from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import CreateHedgeData, Hedge

db = Database("ext_hedge")


async def create_hedge(data: CreateHedgeData) -> Hedge:
    data.id = urlsafe_short_hash()
    await db.insert("hedge.maintable", data)
    return Hedge(**data.dict())


async def get_hedge(hedge_id: str) -> Hedge | None:
    return await db.fetchone(
        "SELECT * FROM hedge.maintable WHERE id = :id",
        {"id": hedge_id},
        Hedge,
    )


async def get_hedges(wallet_ids: str | list[str]) -> list[Hedge]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{w}'" for w in wallet_ids])
    return await db.fetchall(
        f"SELECT * FROM hedge.maintable WHERE wallet IN ({q}) ORDER BY id",
        model=Hedge,
    )


async def update_hedge(data: CreateHedgeData) -> Hedge:
    await db.update("hedge.maintable", data)
    return Hedge(**data.dict())


async def delete_hedge(hedge_id: str) -> None:
    await db.execute(
        "DELETE FROM hedge.maintable WHERE id = :id", {"id": hedge_id}
    )
