# OpenAlex Monthly Monitor

[![Update OpenAlex metrics](https://github.com/Dr-Joe-Roberts/openalex-monitor/actions/workflows/openalex-monitor.yml/badge.svg)](https://github.com/Dr-Joe-Roberts/openalex-monitor/actions/workflows/openalex-monitor.yml)

Tracks month-to-month changes in [Joe M. Roberts's OpenAlex record](https://openalex.org/A5060369592), including profile metrics, citation gains by publication and indexing changes.

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

## Archive

| Path | Contents |
|---|---|
| [`data/monthly/`](data/monthly) | Complete self-contained JSON record for each month |
| [`data/history.json`](data/history.json) | Compact longitudinal index of metrics and changes |
| [`reports/`](reports) | Human-readable monthly change reports |
| [`data/current.json`](data/current.json) | Latest complete record |
| [`data/snapshots/`](data/snapshots) | Dated reproducibility snapshots |

JSON is the primary archive; CSV files are retained for convenient analysis in R, Python and spreadsheets. See the [data guide](data/README.md) and [JSON schema](data/schema.json).

## Automation

The workflow runs at **06:17 UTC on the first day of every month** and can also be started from the [Actions page](https://github.com/Dr-Joe-Roberts/openalex-monitor/actions). Changed data, reports and figures are committed directly to `main`.

<details>
<summary>Run locally</summary>

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest -q
python monitor.py
```

</details>

## Method

Raw metrics reproduce OpenAlex. Curated metrics exclude confirmed author-disambiguation errors listed in [`config/author.json`](config/author.json). Citation gains are calculated only for works present in consecutive monthly records; citations attached to newly indexed works are reported separately.

Code is released under the MIT Licence. OpenAlex data remain subject to their applicable terms and licences.
