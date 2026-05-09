# Project Specification: finanzguru-to-gwwc

**Version:** 0.1 (draft)  
**Status:** Pre-implementation  
**Author:** jannikwagner  
**Last updated:** 2026-05-09

---

## 1. Overview

`finanzguru-to-gwwc` is a local-first Python CLI tool that reads donation transactions from a **Finanzguru** financial export and automatically submits them to the **Giving What We Can / EffectiveAltruism.org "My Giving"** dashboard using **Playwright** browser automation.

There is no official public API on the EffectiveAltruism.org side, so the tool drives the website form directly.

### Problem statement

GWWC members who track their finances in Finanzguru currently have to manually copy every donation into the EA.org My Giving dashboard. This is tedious, error-prone, and discourages consistent record-keeping.

### Solution

An automated pipeline that:
1. Reads a Finanzguru `.xlsx` or `.csv` export.
2. Identifies and normalizes all donation transactions (one-off and recurring).
3. Authenticates to EA.org and submits each donation via browser automation.
4. Tracks which transactions have already been submitted to prevent duplicates.
5. Supports a safe dry-run mode that shows what would be submitted without touching the website.

---

## 2. Goals and non-goals

### Goals

- Local CLI tool, runnable on macOS, Linux, and Windows.
- Clean modular architecture: data parsing is fully decoupled from browser automation.
- Future-proof: other banking apps / data sources can be plugged in with minimal effort.
- Privacy-first: no data leaves the local machine except to the EA.org website itself.
- Safe by default: dry-run mode is the default, live submission requires explicit opt-in.
- Duplicate-safe: a local state file records which donations have already been submitted.
- Configurable via a `.env` file for credentials and settings.

### Non-goals

- Not a general-purpose accounting or budgeting tool.
- Not a scraper of EA.org donation data (read-only from EA.org is out of scope).
- No cloud deployment in v1 (though the architecture should support it later).
- No GUI in v1.
- No support for multi-user / team use in v1.

---

## 3. Target platform

### Finanzguru (data source)

- German banking aggregator app, connects via FinTS/PSD2 to German bank accounts.
- Export formats: `.xlsx` (PLUS subscription) or `.csv`.
- Export includes all transactions across all connected accounts.
- Transactions can be tagged with categories (`Hauptkategorie`, `Unterkategorie`) and marked as belonging to a recurring contract (`Vertrag`).
- Donations are typically categorized under a category like `"Spenden"` (German for donations).

### EffectiveAltruism.org / My Giving (submission target)

- GWWC's "My Giving" functionality was migrated from `givingwhatwecan.org` to `effectivealtruism.org`.
- Logged-in members can manually log donations through a web form.
- No public API exists for programmatic submission.
- Authentication is handled via the EA.org login flow (email + password or OAuth).

---

## 4. Architecture

```
finanzguru-to-gwwc/
│
├── gwwc_import/
│   ├── __main__.py              # CLI entry point
│   ├── cli.py                   # Argument parsing and orchestration
│   ├── models.py                # Donation data model
│   │
│   ├── data_sources/
│   │   ├── __init__.py
│   │   ├── base.py              # DonationSource protocol / abstract base
│   │   └── finanzguru.py        # FinanzguruSource implementation
│   │
│   └── automation/
│       ├── __init__.py
│       ├── session.py           # Playwright login, session persistence
│       ├── submitter.py         # Donation form navigation and submission
│       └── state.py             # Submitted-donations state tracker
│
├── tests/
│   ├── fixtures/
│   │   └── finanzguru_dummy.csv # Dummy export for unit tests
│   ├── test_finanzguru_parser.py
│   └── test_submission_smoke.py
│
├── .env.example
├── .gitignore
├── pyproject.toml
├── README.md
└── PROJECT_SPEC.md
```

### Design principle: source / submission separation

The tool is deliberately split into two independent layers:

| Layer | Input | Output | Dependencies |
|---|---|---|---|
| **Data module** | Raw export file (CSV/XLSX) | List of `Donation` objects | `pandas`, `pydantic` |
| **Submission module** | List of `Donation` objects | EA.org form submissions | `playwright` |

Neither layer knows about the internals of the other. Adding a new data source (e.g. Revolut, N26) requires only implementing a new class in `data_sources/` — the automation layer remains untouched.

---

## 5. Data model

### `Donation`

Defined in `gwwc_import/models.py` using Pydantic v2.

```python
from pydantic import BaseModel
from datetime import date
from decimal import Decimal

class Donation(BaseModel):
    source_system: str          # e.g. "finanzguru"
    source_id: str              # Unique, deterministic key from the source
    date: date                  # Booking date of the transaction
    amount: Decimal             # Absolute positive value in source currency
    currency: str               # ISO 4217, e.g. "EUR"
    recipient_name: str         # Payee / charity name
    description: str            # Memo / Verwendungszweck
    is_recurring: bool          # True if contract/Vertrag-based recurring donation
    category: str | None        # Original category from source (optional)
    notes: str | None           # Any additional free-text notes (optional)
```

`amount` is `Decimal` (not `float`) so euro/cent values round-trip without
binary-float drift before being written into the EA.org form.

### `SubmissionState`

Defined in `gwwc_import/automation/state.py`. Tracks which `source_id` values have been submitted.

```python
class SubmissionRecord(BaseModel):
    source_id: str
    submitted_at: datetime
    dry_run: bool
    success: bool
    error: str | None
```

Stored as a local JSON file (default: `~/.gwwc_import_state.json`). Can be overridden via config.

---

## 6. Data sources

### `DonationSource` protocol

Defined in `gwwc_import/data_sources/base.py`.

```python
from pathlib import Path
from typing import Protocol
from gwwc_import.models import Donation

class DonationSource(Protocol):
    def load_donations(self, path: Path) -> list[Donation]:
        """Load and normalize donations from the given export file."""
        ...
```

### `FinanzguruSource`

Defined in `gwwc_import/data_sources/finanzguru.py`.

#### Expected Finanzguru export columns (German locale)

| Column | Description |
|---|---|
| `Name Referenzkonto` | Account name |
| `Buchungstag` | Booking date (DD.MM.YYYY or ISO format) |
| `Beguenstigter/Auftraggeber` | Payee / sender name |
| `Verwendungszweck` | Transaction memo / purpose |
| `Betrag` | Amount (negative = outgoing) |
| `Hauptkategorie` | Main category |
| `Unterkategorie` | Subcategory |
| `Vertrag` | Contract flag (present / non-empty = recurring) |

The exact column headers vary across export versions and locales (e.g.
`Beguenstigter/Auftraggeber` vs `Begünstigter/Zahlungspflichtiger`,
`Buchungstag` vs `Datum`). The parser keeps an explicit alias map per
logical field and raises a clear error listing the columns it actually
saw if no candidate matches, rather than silently producing empty fields.

The German Finanzguru CSV export typically uses `;` as the column
separator and `,` as the decimal separator. The parser auto-detects
this (via `csv.Sniffer` plus a fallback) and also accepts the standard
`,`-separated / `.`-decimal form for `.xlsx` exports converted to CSV.

#### Filtering logic

1. Filter rows where `Hauptkategorie` matches any value in the configured `donation_categories` list (default: `["Spenden"]`).
2. Optionally also check `Unterkategorie` for finer filtering.
3. Treat any row with a non-empty `Vertrag` field as `is_recurring = True`.
4. Derive `source_id` as a deterministic SHA-256 hash over a stable
   tuple of fields plus a per-file ordinal:
   `sha256(Buchungstag + Betrag + Beguenstigter + Verwendungszweck + ordinal)`.
   The ordinal is the row's position among rows that would otherwise hash
   identically within the same export, so two genuinely-distinct donations
   with the same date, amount, payee and memo still get distinct IDs.

#### Configuration

The `FinanzguruSource` accepts an optional config object:

```python
class FinanzguruConfig(BaseModel):
    donation_categories: list[str] = ["Spenden"]
    donation_subcategories: list[str] | None = None
    currency: str = "EUR"
    date_format: str = "%d.%m.%Y"
    payee_normalization: dict[str, str] = {}
    # Map raw payee strings to canonical names, e.g.:
    # {"GiveWell, Inc.": "GiveWell", "AMF": "Against Malaria Foundation"}
```

---

## 7. Automation module

### Session management (`session.py`)

- Uses Playwright's `browser_context.storage_state()` to persist cookies and localStorage.
- Default session file: `~/.gwwc_import_session.json`.
- On first run (or if session is expired), performs a full login via the EA.org login page.
- Login credentials are read from environment variables:
  - `GWWC_EMAIL`
  - `GWWC_PASSWORD`
- After login, the session state is saved for subsequent runs.

### Submission flow (`submitter.py`)

For each `Donation` in the list:

1. Navigate to the My Giving / donation entry page on EA.org.
2. Wait for the donation form to be visible.
3. Fill in:
   - Date field ← `donation.date`
   - Amount field ← `donation.amount`
   - Currency field (if selectable) ← `donation.currency`
   - Charity / recipient field ← `donation.recipient_name`
   - Description / notes field ← `donation.description` (if available)
   - One-off vs. recurring toggle ← `donation.is_recurring`
4. If `dry_run=True`: log the filled form state and stop. Do not click submit.
5. If `dry_run=False`: click submit, wait for success confirmation.
6. Record the outcome in the `SubmissionState`.

**Note:** Exact field names and selectors must be confirmed against the live EA.org donation form before implementation. The DOM structure may change over time and will require periodic maintenance.

### Error handling

- If form navigation fails: log error, skip donation, continue.
- If a required field is not found: raise a `FormStructureError` with instructions to update selectors.
- If submission fails: log the error and mark the record in state as `success=False`.
- Network errors: retry up to 3 times with exponential backoff.

---

## 8. CLI interface

Entry point: `python -m gwwc_import`

```
usage: gwwc_import [-h]
                   --input FILE
                   --source {finanzguru}
                   [--mode {dry-run,live}]
                   [--headless | --no-headless]
                   [--limit N]
                   [--from-date YYYY-MM-DD]
                   [--to-date YYYY-MM-DD]
                   [--only-recurring]
                   [--only-onetime]
                   [--force-resubmit]
                   [--state-file PATH]
                   [--session-file PATH]
                   [--log-level {DEBUG,INFO,WARNING,ERROR}]
```

| Flag | Default | Description |
|---|---|---|
| `--input` | required | Path to the export file |
| `--source` | required | Data source type (`finanzguru`) |
| `--mode` | `dry-run` | `dry-run` prints what would be submitted; `live` submits |
| `--headless` | `True` | Run browser headlessly (use `--no-headless` to watch) |
| `--limit N` | none | Only process the first N donations |
| `--from-date` | none | Only include donations on or after this date |
| `--to-date` | none | Only include donations on or before this date |
| `--only-recurring` | `False` | Only process recurring donations |
| `--only-onetime` | `False` | Only process one-time donations |
| `--force-resubmit` | `False` | Re-submit donations already in state file |
| `--state-file` | `~/.gwwc_import_state.json` | Override default state file location |
| `--session-file` | `~/.gwwc_import_session.json` | Override default session file location |
| `--log-level` | `INFO` | Logging verbosity |

---

## 9. Configuration (`.env`)

```dotenv
# EA.org credentials
GWWC_EMAIL=your@email.com
GWWC_PASSWORD=yourpassword

# Optional overrides
GWWC_STATE_FILE=~/.gwwc_import_state.json
GWWC_SESSION_FILE=~/.gwwc_import_session.json

# Finanzguru parser
FINANZGURU_DONATION_CATEGORIES=Spenden
FINANZGURU_CURRENCY=EUR
```

A `.env.example` file is committed to the repository. The actual `.env` file is `.gitignore`d.

---

## 10. Testing strategy

### Unit tests

- `test_finanzguru_parser.py`
  - Load `tests/fixtures/finanzguru_dummy.csv`.
  - Assert correct number of donations parsed.
  - Assert correct categorization (donation vs non-donation rows).
  - Assert correct `is_recurring` mapping.
  - Assert `source_id` is deterministic.
  - Assert payee normalization works.

### Integration / smoke tests

- `test_submission_smoke.py`
  - Requires `GWWC_EMAIL` and `GWWC_PASSWORD` to be set.
  - Launches Playwright in headless mode.
  - Logs in and navigates to the My Giving page.
  - Asserts the page title / key elements are present.
  - Does **not** submit any donation.
  - Saves session state for subsequent test runs.

### Manual testing checklist (before any live submission)

- [ ] Dry-run on a single known donation shows correct field mappings.
- [ ] `--limit 1 --mode live` submits exactly one donation correctly.
- [ ] Re-running with the same input does not re-submit (duplicate prevention).
- [ ] `--force-resubmit` correctly overrides duplicate prevention.

---

## 11. Privacy and security

- **Credentials** are stored only in `.env` (gitignored) or environment variables. Never hardcoded or logged.
- **Session state** is stored in a local JSON file outside the repo. It contains browser cookies — treat it like a password.
- **Transaction data** never leaves the machine except to EA.org during form submission. No telemetry. No analytics. No third-party services.
- **State file** records only `source_id` hashes, timestamps, and submission outcomes — not amounts or payee names.
- **Logging** uses a small redaction helper: error and info logs reference donations by the first 8 chars of `source_id`, never by full payee name or raw amount. Full payee/amount appear only at `DEBUG` level and only when the user has explicitly opted in via `--log-level DEBUG`.
- **Development** should be done against dummy/anonymized data. Real exports should never be committed to the repository.

---

## 12. Deployment (future)

While v1 is local-only, the architecture is designed to support deployment as a service later:

| Concern | v1 (local) | Future (service) |
|---|---|---|
| Scheduling | Manual CLI invocation | Cron / GitHub Actions / Cloud Scheduler |
| State storage | Local JSON file | Database (SQLite → PostgreSQL) |
| Session storage | Local JSON file | Secrets manager (e.g. AWS Secrets Manager) |
| Credentials | `.env` file | Environment secrets in CI / cloud |
| Logging | stdout | Structured logging → log aggregator |
| Notifications | None | Email / Slack on success or failure |

---

## 13. Extensibility: adding a new data source

To add support for a new banking app (e.g. Revolut, N26, Monzo):

1. Create `gwwc_import/data_sources/revolut.py` (or similar).
2. Implement the `DonationSource` protocol:
   ```python
   class RevolutSource:
       def load_donations(self, path: Path) -> list[Donation]:
           ...
   ```
3. Register the source in `cli.py`:
   ```python
   SOURCES = {
       "finanzguru": FinanzguruSource,
       "revolut": RevolutSource,
   }
   ```
4. Add unit tests under `tests/` with a corresponding dummy fixture.

No changes to the automation module are needed.

---

## 14. Open questions

These need to be resolved before or during Phase 3/4 implementation:

1. **EA.org form structure:** What are the exact field names and selectors on the My Giving donation entry form? Do they support free-text charity names or only a lookup from a predefined list?
2. **Recurring donations:** Does the EA.org form have a dedicated recurring/one-time toggle, or does it accept individual entries per transaction?
3. **Currency support:** Does the EA.org form support currencies other than USD/GBP by default?
4. **Exact Finanzguru column names:** May differ slightly depending on export locale and account type — needs to be validated against the user's actual export headers.
5. **Login method:** Does EA.org support email + password login, or does it require OAuth (Google / Facebook)? Token-based login via the API endpoint may be possible.

---

## 15. Phases and milestones

| Phase | Milestone | Deliverables |
|---|---|---|
| 1 | Data model and Finanzguru parser | `models.py`, `finanzguru.py`, dummy fixture, unit tests |
| 2 | Source abstraction and CLI skeleton | `base.py`, `cli.py`, `__main__.py`, dry-run JSON output |
| 3 | Playwright login and navigation | `session.py`, smoke test, session persistence |
| 4 | Donation form submission | `submitter.py`, full dry-run + live mode |
| 5 | Polish and duplicate prevention | `state.py`, README finalized, `--force-resubmit` |
| 6 | Open source release | License, CONTRIBUTING.md, EA Forum post |
