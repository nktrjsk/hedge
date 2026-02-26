# migrations.py
# Poznámka: migration file je jako blockchain - nikdy needituj, pouze přidávej!


async def m001_initial(db):
    """
    Původní maintable z template - zachováváme pro kompatibilitu.
    """
    await db.execute(
        """
        CREATE TABLE hedge.maintable (
            id TEXT PRIMARY KEY NOT NULL,
            wallet TEXT NOT NULL,
            name TEXT NOT NULL,
            total INTEGER DEFAULT 0,
            lnurlpayamount INTEGER DEFAULT 0,
            lnurlwithdrawamount INTEGER DEFAULT 0
        );
    """
    )


async def m002_add_timestamp(db):
    """
    Add timestamp to maintable.
    """
    await db.execute(
        f"""
        ALTER TABLE hedge.maintable
        ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now};
    """
    )


async def m003_hedge_settings(db):
    """
    Tabulka s nastavením hedgu per wallet.
    Ukládá LNMarkets API klíče a konfiguraci.
    """
    await db.execute(
        """
        CREATE TABLE hedge.settings (
            wallet_id TEXT PRIMARY KEY NOT NULL,
            lnm_key TEXT NOT NULL,
            lnm_secret TEXT NOT NULL,
            lnm_passphrase TEXT NOT NULL,
            leverage INTEGER NOT NULL DEFAULT 2,
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            last_synced TIMESTAMP,
            last_error TEXT
        );
    """
    )


async def m004_hedge_events(db):
    """
    Audit log všech hedge operací.
    """
    await db.execute(
        f"""
        CREATE TABLE hedge.events (
            id TEXT PRIMARY KEY NOT NULL,
            wallet_id TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT {db.timestamp_now},
            event_type TEXT NOT NULL,
            payment_hash TEXT,
            sats_delta INTEGER NOT NULL DEFAULT 0,
            usd_price REAL NOT NULL DEFAULT 0,
            usd_notional_delta REAL NOT NULL DEFAULT 0,
            lnm_trade_id TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            error_msg TEXT
        );
    """
    )


async def m005_add_testnet(db):
    """
    Přidá sloupec testnet do settings tabulky.
    """
    await db.execute(
        """
        ALTER TABLE hedge.settings
        ADD COLUMN testnet BOOLEAN NOT NULL DEFAULT FALSE;
    """
    )


async def m006_global_settings(db):
    """
    Refaktoring: settings přestávají být per-wallet a stávají se globálními.
    Nová tabulka hedge.config pro globální LNM nastavení (jeden řádek).
    Nová tabulka hedge.hedged_wallets pro seznam hedgovaných walletů.
    """
    await db.execute(
        """
        CREATE TABLE hedge.config (
            id INTEGER PRIMARY KEY DEFAULT 1,
            lnm_key TEXT NOT NULL,
            lnm_secret TEXT NOT NULL,
            lnm_passphrase TEXT NOT NULL,
            leverage INTEGER NOT NULL DEFAULT 2,
            testnet BOOLEAN NOT NULL DEFAULT FALSE,
            last_synced TIMESTAMP,
            last_error TEXT
        );
        """
    )
    await db.execute(
        """
        CREATE TABLE hedge.hedged_wallets (
            wallet_id TEXT PRIMARY KEY NOT NULL,
            enabled BOOLEAN NOT NULL DEFAULT TRUE
        );
        """
    )
