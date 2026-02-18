# Description: This file contains the CRUD operations for talking to the database.


from lnbits.db import Database
from lnbits.helpers import urlsafe_short_hash

from .models import CreateHedgesatsData, Hedgesats

db = Database("ext_hedgesats")


async def create_hedgesats(data: CreateHedgesatsData) -> Hedgesats:
    data.id = urlsafe_short_hash()
    await db.insert("hedgesats.maintable", data)
    return Hedgesats(**data.dict())


async def get_hedgesats(hedgesats_id: str) -> Hedgesats | None:
    return await db.fetchone(
        "SELECT * FROM hedgesats.maintable WHERE id = :id",
        {"id": hedgesats_id},
        Hedgesats,
    )


async def get_hedgesatss(wallet_ids: str | list[str]) -> list[Hedgesats]:
    if isinstance(wallet_ids, str):
        wallet_ids = [wallet_ids]
    q = ",".join([f"'{w}'" for w in wallet_ids])
    return await db.fetchall(
        f"SELECT * FROM hedgesats.maintable WHERE wallet IN ({q}) ORDER BY id",
        model=Hedgesats,
    )


async def update_hedgesats(data: CreateHedgesatsData) -> Hedgesats:
    await db.update("hedgesats.maintable", data)
    return Hedgesats(**data.dict())


async def delete_hedgesats(hedgesats_id: str) -> None:
    await db.execute(
        "DELETE FROM hedgesats.maintable WHERE id = :id", {"id": hedgesats_id}
    )
