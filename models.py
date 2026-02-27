from datetime import datetime
from typing import Optional

from pydantic import BaseModel


# ── Původní template modely (zachováno) ──────────────────────────────────────

class CreateHedgeData(BaseModel):
    id: str | None = ""
    name: str
    lnurlpayamount: int
    lnurlwithdrawamount: int
    wallet: str
    total: int = 0


class Hedge(BaseModel):
    id: str
    name: str
    lnurlpayamount: int
    lnurlwithdrawamount: int
    wallet: str
    total: int
    lnurlpay: str | None = ""
    lnurlwithdraw: str | None = ""


class CreatePayment(BaseModel):
    hedge_id: str
    amount: int
    memo: str


# ── Globální LNM konfigurace ──────────────────────────────────────────────────

class HedgeConfigData(BaseModel):
    """Data pro uložení globálního LNM nastavení."""
    lnm_key: str
    lnm_secret: str
    lnm_passphrase: str
    leverage: int = 2
    testnet: bool = False


class HedgeConfig(HedgeConfigData):
    """Plný model z DB."""
    last_synced: Optional[datetime] = None
    last_error: Optional[str] = None


# ── Hedgované peněženky ───────────────────────────────────────────────────────

class HedgedWallet(BaseModel):
    wallet_id: str
    enabled: bool = True


# ── Hedge events ──────────────────────────────────────────────────────────────

class HedgeEvent(BaseModel):
    id: str
    wallet_id: str
    created_at: datetime
    event_type: str
    payment_hash: Optional[str] = None
    sats_delta: int = 0
    usd_price: float = 0.0
    usd_notional_delta: float = 0.0
    lnm_trade_id: Optional[str] = None
    status: str = "pending"
    error_msg: Optional[str] = None


# ── LNMarkets API modely ──────────────────────────────────────────────────────

class LNMAccountSummary(BaseModel):
    balance: int
    free_collateral_sats: int = 0
    unrealized_pl: int
    total_short_usd: float
    liquidation_price: float = 0.0


class HedgeStatus(BaseModel):
    """Celkový stav hedgu — agregát přes všechny hedgované wallety."""
    configured: bool
    lnm_account_balance_sats: int
    lnm_free_collateral_usd: float = 0.0
    lnm_free_collateral_sats: int = 0
    lnm_liquidation_price: float = 0.0
    btc_price: float
    total_wallet_sats: int
    total_wallet_usd: float
    lnm_short_usd: float
    drift_usd: float
    drift_pct: float
    hedged_wallets: list[str]
    last_synced: Optional[datetime] = None
    last_error: Optional[str] = None


class WalletStatus(BaseModel):
    """Stav jedné hedgované peněženky."""
    wallet_id: str
    wallet_name: str
    balance_sats: int
    balance_usd: float
    enabled: bool
