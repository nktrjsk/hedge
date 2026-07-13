# Hedge — Architecture

> **Status:** Draft for review. Design-first; no implementation committed against it yet.
> **Branch:** `redesign` (ground-up rethink; ignores the previous `claude`-branch implementation).
> **Verified:** LNMarkets v3 exposes both `futures.isolated.*` (per-trade margin, `addMargin`/
> `cashIn`) and `futures.cross.*` (pooled). This design uses **isolated** (§5, §13).

## 1. What we're building

A **provider-agnostic, always-on hedge engine** that gives wallet users a **per-wallet USD
balance** backed by their Bitcoin plus an offsetting short position on a futures venue.

A user flips a **hedge toggle** on a wallet. From then on that wallet reads as a USD balance;
the sats and the short that back it are an implementation detail the user never touches. The
promise:

> **The $100 you deposited reads $100 later — minus honest, itemized funding — and you never
> touch collateral, leverage, or an exchange.**

Three requirements drove every decision:

1. **Seamless** — the user deals with USD, not satoshis, collateral, or leverage.
2. **No silent bleed** — value only changes for reasons we can name (deposits, spends, funding).
3. **Custody-conscious** — minimize the trust the user must place in the trading venue.

## 2. The one invariant everything serves

The user's **total sats** (buffer held wallet-side + margin posted at the venue) *are* the spot
that backs the short. If BTC pumps, the short loses USD but those same sats gain the same USD —
net flat. So the hedged position is **self-collateralizing**, and:

> **The only way the user loses money is if the short is liquidated before margin can be topped
> up. Liquidation is a latency problem, not a solvency problem.**

Every mechanism below exists to keep that latency safe. This is the sentence to re-read whenever
a design question feels ambiguous.

## 3. Topology

The hedge engine is an **always-on server**, independent of any wallet.

```
        ┌─────────────────────┐         ┌──────────────────────────┐
        │  Wallet client       │  API    │  Hedge engine (server)    │
        │  - LNbits (now)      │◄───────►│  - event-sourced ledger   │
        │  - Linky/Cashu (later)│        │  - margin mgmt loop        │
        │  shows USD balance   │         │  - reconciliation loop     │
        └─────────────────────┘         │  - provider abstraction    │
                                         └───────────┬──────────────┘
                                                     │ provider adapter
                                            ┌────────▼─────────┐
                                            │ Venue (LNMarkets) │
                                            │ inverse perp short│
                                            └───────────────────┘
```

**Why a standalone service and not "just an LNbits extension":** the safety model (§6) depends on
a loop that runs 24/7 and can shuttle margin to the venue within seconds of a price move. A
client that only runs while the app is open (any local-first / PWA wallet, e.g. Linky) **cannot**
host that loop — a pump while the phone is asleep would liquidate the position. The engine must
outlive any client session.

LNbits is the first client because it hands us a server for free — custodial balances, a
background-task framework, and an invoice listener. Linky is a **later** client of the same
wallet-agnostic API; its Cashu/mint custody and Nostr identity will need bridging at that point.

### 3.1 Responsibility split (the trust boundary)

| | Holds | Decides / does |
|---|---|---|
| **Engine** | venue API keys | when/how much to hedge, margin, deleverage; the ledger; reconciliation |
| **Client** (e.g. LNbits ext) | wallet custody keys | executes sat movements **on the engine's instruction**; renders USD balance |

The engine **never holds wallet custody credentials.** When margin must move, the engine instructs
(*"pay X sats to this venue deposit invoice"* / *"expect a withdrawal"*) and the client performs
the payment with its own keys and reports back. This keeps wallet custody on the wallet side and
venue custody on the engine side.

### 3.2 Client ↔ engine contract

- **Transport:** **REST** for commands (open / adjust / close / quote / status); **WebSocket push**
  from engine → client for balance, health, and alert updates (no polling). LNbits already speaks
  WebSocket, which the client relays to the user UI.
- **Auth:** a **per-deployment credential** authenticates the client; every request carries a
  **per-user scoped token/ID** so a compromised client can't act across users it shouldn't.
  Requests are HMAC-signed. (Fits the operator-runs-both deployment.)

## 4. Custody model — an operator choice

Custody has two legs, and they are decided independently:

- **Wallet-side custody** is inherent to the client. LNbits is custodial: the operator already
  holds the buffer sats. This is unavoidable and out of scope to change.
- **Venue-side custody** is what we minimize, and it is the operator's deployment-time choice:

| Mode | Who holds the venue account | Trade-off |
|------|-----------------------------|-----------|
| **Shared** | Operator runs one venue account for all users | Fully seamless; operator becomes venue custodian (**Risk B**, §13); margin contagion avoided via isolated positions (§5) |
| **Bring-your-own** | Each user links their own venue account | Non-custodial at the venue; user must onboard to the venue (least seamless) |

The engine supports both so **the operator is never locked into liability they didn't choose.**
The client API and ledger are identical across modes; only the credential source and settlement
routing differ.

**Key scope (both modes):** automation keys are **trade-only**, and withdrawals are **hard-locked
to the user's own wallet node address**. A compromised key or DB can move positions but cannot
exfiltrate funds to an attacker's address.

## 5. Collateral & margining

- **Isolated margin, one position per hedged wallet.** Each hedged wallet maps to its **own
  isolated-margin trade** with its own margin and its own liquidation price. This is the core
  primitive in **both** custody modes. On LNMarkets this is the `futures.isolated.*` product
  (individual trades, per-trade `addMargin` / `cashIn`), **not** the pooled `futures.cross.*`
  product. The previous implementation's "one shared cross-margin account" is explicitly rejected:
  see §13.
- **Minimal margin at the venue + a wallet-side buffer** as the shock absorber. Most sats stay
  wallet-side; only the margin the short needs is posted at the venue; the buffer feeds top-ups
  during volatility and reclaims margin when volatility subsides. Top-ups target the *specific*
  trade (`addMargin`/`cashIn`), never a shared pool.
- **Dynamic margining to a health ratio.** A safe **default** ships out of the box; a **hidden
  advanced control** lets power users adjust; a **hard floor** exists that no user can cross, so
  nobody can configure themselves into guaranteed liquidation. Most users never see this.
- **Default parameters (Balanced, ~3x effective):**
  - **Target:** keep the liquidation price **~+33%** above spot.
  - **Top-up trigger:** add margin when the move-to-liquidation narrows to **~+22%**; **reclaim**
    margin back to the buffer once it widens past **~+28%** (hysteresis to avoid churn).
  - **Hard floor:** **+15%** — no user config may place liquidation closer than this.

  Note the trade-off this encodes: a farther liquidation point means more margin parked at the
  venue, so this default *is* the steady-state venue custody exposure (~1/3 of the hedged sats).
- **Cadence / triggers.** Adjust the hedge **immediately** on deposit/spend; monitor margin health
  on **every price tick** and act on the trigger above; run a full ledger **reconcile every ~60s**
  (§9). Only trade when drift exceeds **max($1, 1% of wallet)** to avoid dust churn (§10).

## 6. Liquidation backstop

Defense in depth, in order:

1. **Headroom.** The default health ratio is sized to survive a realistic pump within top-up
   latency.
2. **Fast top-ups.** Buffer → venue over Lightning (seconds, not on-chain confirmations).
3. **Auto-deleverage (last resort).** If health goes critical and a top-up can't land, the engine
   **shrinks that wallet's short** rather than risk liquidation. Because each wallet is its own
   isolated trade (§5), the backstop acts on exactly one user's position and never touches
   another's. The wallet is flagged **under-hedged** (temporary, disclosed BTC exposure) until
   margin is restored and the hedge is rebuilt.

Losing the hedge temporarily (deleverage) is recoverable; a liquidation is not. We always pick the
recoverable failure.

## 7. Value integrity — no silent bleed

- **Funding floats to the user, itemized.** The USD balance reflects funding actually paid or
  received, shown as a distinct line (`funding: −$3.40`). When funding favors shorts the balance
  can even earn carry. Nothing about funding is hidden or smoothed over.
- **Erosion policy.** When cumulative funding erosion crosses a threshold, the engine **alerts the
  user and lets them decide** whether to unwind. It never silently auto-closes a user's hedge —
  re-exposing them to BTC price is their call, not ours. Defaults: first alert at **−2%** of
  principal, escalated alert + unwind prompt at **−5%**. (BTC perps are often in contango, so shorts
  frequently *earn* funding; sustained erosion is the rarer backwardation case.)
- **Event-sourced ledger.** Every deposit, spend, trade, and funding payment is an append-only
  event; balances are *derived*, never mutated in place. This ledger *is* the no-bleed guarantee:
  any deviation from the promised USD must be fully explained by named events. An unexplained
  delta is a bug, and we treat it as one (§9).
- **Multi-asset from day one.** The ledger's settlement-asset model is generic (BTC now,
  stablecoin-capable schema) so adding a linear/USDT-margined venue later is an adapter, not a
  migration.

## 8. Price & oracle

- **An independent, aggregated oracle is the source of truth** for accounting and the displayed
  balance — not gameable by any single venue, and provider-agnostic by construction. Default:
  **median of 3–4 major spot venues** (e.g. Coinbase, Kraken, Bitstamp, Binance).
- The **venue mark price is used only to size and settle** the actual trade.
- **Divergence handling:** if the venue mark diverges **>~1%** from the oracle, **trading halts**
  (the price-sanity check) rather than acting on a bad or manipulated price. If the oracle's own
  sources disagree by **>~0.5%**, drop outliers before taking the median.

## 9. Reconciliation & safe-mode

A loop continuously compares the **derived ledger expectation** against **actual venue + wallet
state**.

- On a discrepancy, the engine **attempts to auto-heal** toward the reconciled truth.
- If auto-heal fails, it enters **safe-mode**: stop opening/adjusting positions, stop deriving new
  balances from suspect state, and page the operator. The user sees *"hedge paused,"* never silent
  drift.

## 10. Settlement flows

- **Deposit / receive:** sats arrive → engine opens/increases the short for the USD-equivalent →
  wallet displays updated USD. USD value is locked at the oracle price at settlement time.
- **Spend / withdraw:** reduce the short by the spent USD amount at market and **release sats
  instantly over Lightning**. The user never waits on the venue.
- **Toggle off:** unwind the short fully at market; the wallet returns to plain BTC exposure.
- **Dust:** hedge to the nearest size the venue minimum allows; carry the sub-minimum remainder as
  **explicitly tracked, disclosed unhedged dust**. No silent unhedged exposure.

## 11. Provider abstraction

A provider adapter is the only venue-specific code. The abstraction must paper over:

- **Perp type** — inverse / BTC-margined (now) vs. linear / stablecoin-margined (later).
- **Settlement asset** — BTC (now) vs. stablecoin (later).
- **Deposit rail** — Lightning (now) vs. on-chain / bridged (later).

Scope now: **BTC-margined, Lightning-capable venues only** (LNMarkets-like), keeping the system
sat-native. The multi-asset ledger (§7) is what lets us widen this later without a rewrite.

A provider adapter must expose **per-position isolated margin** (own margin + own liquidation
price per trade) and the ability to **add margin to a specific position**. This is the primitive
§5/§6 rely on; a venue that only offers pooled cross-margin cannot safely host multiple users and
is out of scope.

## 12. Open questions (to resolve during implementation)

Parameters and interfaces are now specified inline (§3.1–3.2, §5, §7, §8). Genuinely still open:

- **Business model for shared mode** — does the operator charge a spread/fee to cover its capital,
  funding variance, and operational risk? (Bring-your-own has no operator capital at stake.)
- **Exact oracle venue list** and failover behaviour when a source is down or rate-limited.
- **Linky bridging** — how Cashu/mint custody and Nostr identity map onto the client contract
  (§3.1) when Linky becomes a client.
- **Onboarding for bring-your-own** — the UX of linking a venue account and issuing trade-only,
  withdrawal-whitelisted keys with the least friction.
- **Test/validation strategy** — how we exercise the margin/liquidation logic against realistic
  price paths before touching real funds (e.g. against LNMarkets testnet4).

## 13. Biggest risks

1. **Shared-account risk — split into two, one solved, one inherent.** Bundling "shared account"
   into a single risk is a mistake; it is two distinct problems:

   - **Risk A — margin contagion (SOLVED).** *Would* be severe in a pooled cross-margin account:
     every user's position is the same trade (a BTC short), so a pump puts all users underwater at
     once, all drawing on one collateral pool — one user's shortfall could liquidate another's. The
     fix is the §5 primitive: **isolated-margin trade per wallet.** LNMarkets v3 offers this
     (`futures.isolated.*` with per-trade `addMargin`/`cashIn`), so one user's liquidation is
     confined to their own margin. With isolated positions, contagion does not arise — in **either**
     custody mode.
   - **Risk B — custodial concentration (INHERENT to shared mode).** Isolated margin walls off
     *liquidation*, not *custody*. In shared mode the operator still holds one account, one key set,
     and one venue's solvency for all users; a key/DB compromise, exit-scam, or venue insolvency
     takes everyone down together. No margin model fixes this. The trade-only + whitelisted-
     withdrawal keys (§4) blunt the *theft* vector but not insolvency or exit-scam. Only
     **bring-your-own** (custody is the user's) or **multi-venue spreading** (caps blast radius)
     address Risk B.

   **Conclusion:** shared mode is defensible on the margin axis (Risk A solved via isolated), so it
   is a reasonable *convenience* option. **Bring-your-own remains the recommended safe default**
   for custody-conscious deployers, now purely on Risk B grounds — not because shared mode is
   unsafe to operate.
2. **Always-on reliability.** The engine being down during a pump is the failure mode that costs
   real money. It needs the same rigor as the trading logic (supervision, alerting, fast restart,
   state recovery from the event log).
3. **Top-up latency under stress.** Venue deposits must actually clear in seconds when volatility
   spikes and Lightning routing is congested. If they can't, headroom (§6) must be wide enough to
   cover the worst realistic case.
