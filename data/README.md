# Data guide

The authoritative archive is `monthly/YYYY-MM.json`. Each file is self-contained and records:

- raw OpenAlex and locally curated profile metrics;
- changes from the most recent snapshot in the preceding month;
- every publication and its citation count at retrieval;
- citation gains for works present in both months;
- newly indexed publications, corrections and removals;
- the OpenAlex counts-by-year series, curation rules and provenance.

`history.json` is a compact month-by-month index. `current.json` always mirrors the latest monthly record. CSV files are convenience exports rather than the primary archive.

## Python example

```python
import json
from pathlib import Path

record = json.loads(Path("data/monthly/2026-09.json").read_text())
print(record["metrics"]["curated"])

for paper in record["publications"]["citation_gains"]:
    print(paper["title"], paper["citation_change"])
```

## R example

```r
library(jsonlite)

record <- fromJSON("data/monthly/2026-09.json", simplifyVector = TRUE)
record$metrics$curated
record$publications$citation_gains[, c("title", "citation_change")]
```

The top-level `schema_version` field permits future format changes to be handled explicitly.
