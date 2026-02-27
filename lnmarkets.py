# lnmarkets.py
# LNMarkets API v3 klient
# Spec: https://api.lnmarkets.com/v3/
# Závislosti: pouze httpx (součást LNbits)

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from loguru import logger

from .models import LNMAccountSummary

LNM_BASE_URL    = "https://api.lnmarkets.com"
LNM_TESTNET_URL = "https://api.testnet4.lnmarkets.com"

LNM_MIN_QUANTITY_USD = 1.0


class LNMarketsError(Exception):
    pass


class LNMarketsClient:
    """
    LNMarkets API v3 klient postavený na httpx.
    httpx je součástí LNbits — žádná externí závislost.

    Autentizace dle spec:
      signature = base64( hmac_sha256(secret, timestamp + method_lower + path + data) )

    kde:
      - method je lowercase ("get", "post", ...)
      - path je celá cesta včetně /v3 prefix (např. "/v3/account")
      - data je pro GET/DELETE query string (např. "?key=val"), pro POST/PUT JSON body bez mezer
    """

    def __init__(
        self,
        key: str,
        secret: str,
        passphrase: str,
        testnet: bool = False,
    ):
        self.key        = key
        self.secret     = secret
        self.passphrase = passphrase
        self.base_url   = LNM_TESTNET_URL if testnet else LNM_BASE_URL

    # ── Autentizace ───────────────────────────────────────────────────────────

    def _sign(self, timestamp: str, method: str, path: str, data: str = "") -> str:
        """
        HMAC-SHA256 podpis zakódovaný v Base64.
        Vstup: timestamp + method_lowercase + path + data
        """
        message = timestamp + method.lower() + path + data
        raw = hmac.new(
            self.secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        return base64.b64encode(raw).decode("utf-8")

    def _auth_headers(
        self,
        method: str,
        path: str,           # např. "/v3/futures/cross/order"
        data: str = "",      # query string nebo JSON body
        with_content_type: bool = False,
    ) -> dict:
        timestamp = str(int(time.time() * 1000))
        headers = {
            "LNM-ACCESS-KEY":        self.key,
            "LNM-ACCESS-PASSPHRASE": self.passphrase,
            "LNM-ACCESS-TIMESTAMP":  timestamp,
            "LNM-ACCESS-SIGNATURE":  self._sign(timestamp, method, path, data),
        }
        if with_content_type:
            headers["Content-Type"] = "application/json"
        return headers

    # ── HTTP ──────────────────────────────────────────────────────────────────

    async def _request(
        self,
        method: str,
        endpoint: str,                    # např. "/futures/cross/order"
        params: Optional[dict] = None,    # pro GET/DELETE
        payload: Optional[dict] = None,   # pro POST/PUT
    ) -> Any:
        method_upper = method.upper()
        path = f"/v3{endpoint}"           # cesta pro podpis

        # data pro podpis
        if method_upper in ("GET", "DELETE") and params:
            query_string = "?" + urlencode(params)
            data_for_sign = query_string
        elif payload is not None:
            data_for_sign = json.dumps(payload, separators=(",", ":"))
        else:
            data_for_sign = ""

        has_body = method_upper in ("POST", "PUT") and payload is not None
        headers = self._auth_headers(
            method_upper, path, data_for_sign, with_content_type=has_body
        )

        url = self.base_url + path

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.request(
                method=method_upper,
                url=url,
                headers=headers,
                params=params if method_upper in ("GET", "DELETE") else None,
                content=data_for_sign.encode() if has_body else None,
            )

        if not resp.is_success:
            try:
                err_body = resp.json()
                err_msg = err_body.get("message") or err_body.get("error") or resp.text
            except Exception:
                err_msg = resp.text
            err_lower = err_msg.lower()
            if any(k in err_lower for k in ("insufficient", "margin", "balance", "funds", "collateral")):
                raise LNMarketsError(
                    f"Nedostatečný kolaterál na LNMarkets — vložte více BTC do cross margin účtu. ({err_msg})"
                )
            raise LNMarketsError(
                f"LNM {method_upper} {endpoint} → HTTP {resp.status_code}: {err_msg}"
            )

        # Prázdná odpověď (204 apod.)
        if not resp.content:
            return {}

        return resp.json()

    # ── Cena ─────────────────────────────────────────────────────────────────

    async def get_price(self) -> float:
        """
        Aktuální BTC/USD cena z /futures/ticker.
        Endpoint je veřejný — voláme bez auth hlaviček aby nedošlo k interferenci.
        Preferujeme `lastPrice` (skutečná cena posledního obchodu na platformě),
        fallback na `index` (agregát burz).
        """
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                self.base_url + "/v3/futures/ticker",
                headers={"Accept": "application/json"},
            )
        if not resp.is_success:
            raise LNMarketsError(
                f"LNM GET /futures/ticker → HTTP {resp.status_code}: {resp.text}"
            )
        data = resp.json()
        # lastPrice = poslední skutečný obchod na platformě
        # index     = agregát z externích burz (obvykle velmi podobný)
        price = float(data.get("lastPrice") or data.get("index") or 0)
        if price <= 0:
            raise LNMarketsError(f"LNM vrátil neplatnou cenu: {data}")
        logger.debug(f"LNM cena: {price} USD (lastPrice={data.get('lastPrice')}, index={data.get('index')})")
        return price

    # ── Účet ─────────────────────────────────────────────────────────────────

    async def get_user(self) -> dict:
        """
        GET /account — vrátí info o účtu.
        Slouží i pro ověření platnosti API klíčů.
        Odpověď: {username, balance, syntheticUsdBalance, feeTier, email, id, ...}
        """
        return await self._request("GET", "/account")

    async def get_account_summary(self) -> LNMAccountSummary:
        """
        Kombinuje GET /account a GET /futures/cross/position.

        /account vrátí celkový balance (sats).
        /futures/cross/position vrátí aktuální cross margin pozici:
          - margin: cross margin balance (sats)
          - quantity: USD notional pozice (+ = long, záporné hodnoty nejsou, ale
                      side se určuje znaménkem quantity nebo polem side)
          - totalPl, deltaPl: P&L v sats
        """
        account  = await self._request("GET", "/account")
        balance  = int(account.get("balance", 0) or 0)

        try:
            pos = await self._request("GET", "/futures/cross/position")
        except LNMarketsError as e:
            # Pokud není žádná pozice, API může vrátit chybu nebo prázdný objekt
            logger.debug(f"LNM: get_position selhalo (asi žádná pozice): {e}")
            pos = {}

        total_short_usd      = 0.0
        free_collateral_sats = 0
        unrealized_pl        = 0
        liquidation_price    = 0.0

        if pos:
            # quantity: záporné = short (sell), kladné = long (buy)
            quantity = float(pos.get("quantity", 0) or 0)
            if quantity < 0:
                total_short_usd = abs(quantity)
            # margin            = celkový margin v cross účtu (sats)
            # maintenanceMargin = minimum pro udržení pozice před likvidací (sats)
            # volný kolaterál   = buffer před likvidací
            total_margin       = int(pos.get("margin", 0) or 0)
            running_margin     = int(pos.get("runningMargin", 0) or 0)
            maintenance_margin = int(pos.get("maintenanceMargin", 0) or 0)
            free_collateral_sats = max(0, total_margin - (running_margin + maintenance_margin))
            unrealized_pl = int(pos.get("totalPl", 0) or 0)
            liquidation_price = float(pos.get("liquidation", 0) or 0)

        return LNMAccountSummary(
            balance=balance,
            free_collateral_sats=free_collateral_sats,
            unrealized_pl=unrealized_pl,
            total_short_usd=total_short_usd,
            liquidation_price=liquidation_price,
        )

    # ── Cross futures ─────────────────────────────────────────────────────────

    async def open_short(self, usd_quantity: float, leverage: int = 2) -> str:
        """
        POST /futures/cross/order — market sell order (short).

        Body dle spec:
          { "type": "market", "side": "sell", "quantity": <int USD> }

        Před otevřením nastaví leverage přes PUT /futures/cross/leverage.
        LNM agreguje do sdílené cross pozice automaticky.

        Returns: order UUID
        """
        if usd_quantity < LNM_MIN_QUANTITY_USD:
            raise LNMarketsError(
                f"Minimum je {LNM_MIN_QUANTITY_USD} USD, požadováno {usd_quantity:.4f} USD"
            )

        quantity_int = int(usd_quantity)  # LNM bere celé USD

        # Nastav leverage (PUT /futures/cross/leverage)
        await self._set_leverage(leverage)

        payload = {"type": "market", "side": "sell", "quantity": quantity_int}
        logger.info(f"LNM: open short {quantity_int} USD (leverage {leverage}x)")

        data     = await self._request("POST", "/futures/cross/order", payload=payload)
        order_id = str(data.get("id", ""))
        logger.info(f"LNM: short otevřen id={order_id}")
        return order_id

    async def reduce_short(self, usd_quantity: float) -> str:
        """
        POST /futures/cross/order — market buy order (uzavírá část short pozice).

        U cross margin LNM nettuje buy order proti existující short pozici.

        Body: { "type": "market", "side": "buy", "quantity": <int USD> }

        Returns: order UUID
        """
        if usd_quantity < LNM_MIN_QUANTITY_USD:
            raise LNMarketsError(
                f"Minimum je {LNM_MIN_QUANTITY_USD} USD, požadováno {usd_quantity:.4f} USD"
            )

        quantity_int = int(usd_quantity)
        payload = {"type": "market", "side": "buy", "quantity": quantity_int}
        logger.info(f"LNM: reduce short o {quantity_int} USD")

        data     = await self._request("POST", "/futures/cross/order", payload=payload)
        order_id = str(data.get("id", ""))
        logger.info(f"LNM: short zmenšen id={order_id}")
        return order_id

    async def close_position(self) -> None:
        """
        POST /futures/cross/position/close — uzavře celou cross pozici.
        Interně pošle market order opačného směru k celé pozici.
        """
        logger.warning("LNM: zavírám celou cross pozici")
        await self._request("POST", "/futures/cross/position/close")

    async def _set_leverage(self, leverage: int) -> None:
        """
        PUT /futures/cross/leverage
        Body: { "leverage": <number 1-100> }
        """
        await self._request(
            "PUT",
            "/futures/cross/leverage",
            payload={"leverage": leverage},
        )

    async def deposit_to_cross(self, amount_sats: int) -> None:
        """
        POST /futures/cross/deposit
        Body: { "amount": <sats> }
        Přesune sats z hlavního LNM balance do cross margin účtu.
        """
        await self._request(
            "POST",
            "/futures/cross/deposit",
            payload={"amount": amount_sats},
        )
