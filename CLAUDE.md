# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

**Hedge** is an [LNbits](https://github.com/lnbits/lnbits) extension that automatically delta-hedges Bitcoin holdings. When a hedged wallet receives a Lightning payment, the extension opens an equivalent USD short position on [LNMarkets](https://lnmarkets.com) (cross-margin perpetual futures). A periodic reconciliation loop keeps the short position aligned with the total wallet balance.

## Commands

All commands use `uv` as the package manager (not pip/poetry).

```bash
make test          # Run tests (sets PYTHONUNBUFFERED=1 DEBUG=true)
make format        # Format: prettier (JS) + black + ruff --fix (Python)
make check         # Check: mypy + pyright + black --check + ruff + prettier --check
make pre-commit    # Run all pre-commit hooks on all files

# Individual tools:
uv run pytest tests/test_init.py   # Run a single test file
uv run ruff check . --fix
uv run black .
uv run mypy .
```

## Architecture

This is a standard LNbits extension. LNbits loads it by importing `__init__.py`, which exports `hedge_ext` (APIRouter), `hedge_start`, `hedge_stop`, `hedge_static_files`, and `db`.

### File roles

| File | Role |
|------|------|
| `__init__.py` | Extension entry point — registers routers, starts background tasks |
| `models.py` | All Pydantic models |
| `crud.py` | All DB operations via `db = Database("ext_hedge")` |
| `migrations.py` | DB schema — **append-only, never edit existing migrations** |
| `views.py` | Single HTML page route (`/hedge/`) |
| `views_api.py` | REST API (`/hedge/api/v1/...`) |
| `lnmarkets.py` | LNMarkets API v3 client (HMAC-SHA256 auth over httpx) |
| `tasks.py` | Two background tasks: invoice listener + reconciliation loop |
| `helpers.py` | Small utilities |
| `templates/hedge/` | Jinja2 HTML templates |
| `static/` | Frontend JS and images |

### Data flow

1. `wait_for_paid_invoices` (task) listens on LNbits invoice queue
2. On payment → `on_payment` checks if receiving wallet is in `hedge.hedged_wallets`
3. If hedged → `adjust_hedge` opens an LNM short for the BTC-equivalent USD value
4. `reconciliation_loop` runs every 60 s → `reconcile_all` compares total wallet sats vs current LNM short, calls `adjust_hedge` if drift > $1 USD

All LNM operations go through a single `_global_lock` (asyncio.Lock) because there is one shared cross-margin account on LNMarkets — operations must be serialized.

### Database tables (schema prefix `hedge.`)

- `hedge.config` — single-row global LNM credentials + status (leverage, testnet flag, last_synced, last_error)
- `hedge.hedged_wallets` — list of LNbits wallet IDs to hedge
- `hedge.events` — append-only audit log of every hedge operation
- `hedge.maintable` — original template table (kept for compatibility)

### LNMarkets client (`lnmarkets.py`)

Auth: `HMAC-SHA256(secret, timestamp + method_lower + path + data)` encoded as base64. The `path` must include the `/v3` prefix. For GET/DELETE, `data` is the query string (`?key=val`); for POST/PUT it is compact JSON.

Key constants: min trade = `$1 USD` (`LNM_MIN_QUANTITY_USD`), reconcile tolerance = `$1 USD` (`RECONCILE_TOLERANCE_USD`), reconcile interval = `60 s`.

### API endpoints (all under `/hedge/api/v1/`)

| Method | Path | Auth required |
|--------|------|---------------|
| GET/POST/DELETE | `/config` | admin key |
| GET/PUT | `/wallets` | admin key |
| GET | `/status` | invoice key |
| GET | `/wallet-statuses` | invoice key |
| POST | `/sync` | admin key |
| GET | `/events` | invoice key |

### Installing / developing

**Production install**: LNbits installs the extension from GitHub via `manifest.json`. Add the manifest URL (`https://raw.githubusercontent.com/<org>/<repo>/main/manifest.json`) in LNbits Settings → Extensions, then install from Extensions → ALL. A GitHub release must exist for the extension to appear there.

**Local development**: Symlink the repo into the LNbits extensions directory (`ln -s /path/to/hedge /path/to/lnbits/lnbits/extensions/hedge`) and restart LNbits. DB migrations take effect after a full restart; other code changes take effect after a reload/restart.

## Code style

- Line length: 88 (black/ruff)
- Type annotations required (mypy strict with pydantic plugin, pyright)
- Ruff rule sets: F, E, W, I, A, C, N, UP, RUF, B (see `pyproject.toml`)
- `classmethod` decorators `validator` and `root_validator` are treated as pydantic class methods by ruff
