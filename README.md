# OpenAlex Monitor

[![Update OpenAlex metrics](https://github.com/Dr-Joe-Roberts/openalex-monitor/actions/workflows/openalex-monitor.yml/badge.svg)](https://github.com/Dr-Joe-Roberts/openalex-monitor/actions/workflows/openalex-monitor.yml)

Reproducible monthly monitoring of [Joe M. Roberts's OpenAlex profile](https://openalex.org/A5060369592). The project records both the unmodified OpenAlex metrics and a curated view that removes confirmed author-disambiguation errors.

<!-- MONITOR:START -->
## Latest snapshot

Retrieved **2026-08-31**; comparison: **baseline**.

[Monthly report](reports/latest.md) · [Monthly JSON](data/monthly/2026-08.json) · [Full history](data/history.json)

| Metric | Curated | Change | OpenAlex raw | Raw change |
|---|---:|---:|---:|---:|
| Works | 50 | — | 54 | — |
| Citations | 386 | — | 431 | — |
| h-index | 9 | — | 11 | — |
| i10-index | 9 | — | 12 | — |

### Citation changes by publication

This baseline establishes the starting point for the next monthly comparison.

![Monthly citation history](plots/citation_history.png)
<!-- MONITOR:END -->

## Repository data

JSON is the primary archival format:

- `data/monthly/YYYY-MM.json` is the complete, self-contained record for each month. It contains raw and curated metrics, changes from the preceding month, the full publication list, paper-level citation gains, newly indexed works, corrections, exclusions and provenance.
- `data/history.json` is a compact index of all monthly metrics and changes.
- `data/current.json` is the latest complete monthly record.
- `data/snapshots/YYYY-MM-DD.json` preserves the dated record used for reproducibility.
- `reports/YYYY-MM.md` provides the corresponding human-readable monthly change report.

CSV files are also retained as convenient tabular exports for R, Python or spreadsheets. The curation rules remain transparent in `config/author.json`.

## Schedule

GitHub Actions runs the monitor at **06:17 UTC on the first day of every month**. It can also be run manually from the Actions tab. When the API returns changed data, the workflow commits the new snapshot and regenerated outputs to `main`.

## Local use

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest -q
python monitor.py
```

The OpenAlex API does not require a login for this low-volume workflow. If an API key is added later, expose it through the optional `OPENALEX_API_KEY` environment variable; never commit it to the repository.

## Interpretation

Citation totals are specific to OpenAlex and should be reported with the database name and retrieval date. The curated metrics are calculated locally from the works retained in `config/author.json`; they do not change the public OpenAlex record.

## Licence

Code is released under the MIT Licence. OpenAlex data are provided under their applicable terms and licences.
