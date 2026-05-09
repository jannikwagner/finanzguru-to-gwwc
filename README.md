# finanzguru-to-gwwc

Automate importing donation transactions from a Finanzguru export into the Giving What We Can / EffectiveAltruism.org **My Giving** dashboard via browser automation.

## Status

This repository is currently in the planning and scaffolding phase.

The intended first version will:
- Parse Finanzguru CSV/XLSX exports.
- Identify donation transactions, including recurring donations where possible.
- Normalize them into a common donation model.
- Use Playwright to automate entry into the EA.org / GWWC donation form.
- Support a safe dry-run mode before any live submissions.

## Goals

- Run locally first as a CLI tool.
- Keep a strict separation between:
  - data ingestion/parsing
  - website automation/submission
- Make future support for other financial data sources possible.
- Avoid dependence on any unofficial backend API.

## Planned architecture

### Data module
Responsible for:
- reading Finanzguru exports
- filtering donation rows
- marking recurring vs one-off donations
- mapping source rows into a normalized `Donation` model

### Submission module
Responsible for:
- authenticating to the EffectiveAltruism.org / My Giving dashboard
- navigating to the donation entry form
- filling fields from normalized donation objects
- supporting dry-run and live submission modes
- tracking submitted source transactions to reduce duplicates

## Planned CLI

Example target usage:

```bash
python -m gwwc_import \
  --input path/to/finanzguru_export.xlsx \
  --source finanzguru \
  --mode dry-run
```

## Privacy

This project is developed against dummy/anonymized data only. **Never commit a real Finanzguru export.**

Real financial exports contain highly sensitive personal information: full transaction history, payee names, categories, dates, and amounts.

**Safe handling of your real export file:**
1. Store it in the `data/` directory at the root of this repo (gitignored entirely) **or** outside the repo completely.
2. Pass the path via `--input` at runtime — the file never needs to be inside the repo tree.
3. Do not rename the file to match a pattern you think `.gitignore` will catch — rely on the `data/` directory, not pattern matching.

At `INFO`/`WARNING`/`ERROR` log level the tool refers to donations only by the first 8 characters of their `source_id` hash — no payee names or amounts are logged unless you explicitly pass `--log-level DEBUG`.

## Notes

- The target website and form structure may change over time.
- Browser automation selectors will likely need maintenance if the site changes.
- If Giving What We Can / Effective Altruism ever exposes an official API for this workflow, the project should prefer that over UI automation.

## Next steps

1. Add a dummy Finanzguru export for parser development.
2. Implement the normalized donation data model.
3. Build the Finanzguru parsing module.
4. Add Playwright login/session handling.
5. Implement dry-run donation form automation.
6. Add duplicate-prevention and state tracking.

## License

TBD.
