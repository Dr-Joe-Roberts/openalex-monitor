"""Archive, compare, and report monthly OpenAlex author data."""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config" / "author.json"
DATA_DIR = ROOT / "data"
MONTHLY_DIR = DATA_DIR / "monthly"
SNAPSHOT_DIR = DATA_DIR / "snapshots"
REPORTS_DIR = ROOT / "reports"
PLOTS_DIR = ROOT / "plots"
README_PATH = ROOT / "README.md"

METRIC_FIELDS = [
    "date", "fetched_at", "raw_work_count", "raw_citations", "raw_h_index",
    "raw_i10_index", "curated_work_count", "curated_citations",
    "curated_h_index", "curated_i10_index",
]

PAPER_FIELDS = [
    "date", "work_id", "doi", "title", "publication_year", "type", "source",
    "citations", "included_in_curated",
]

METRIC_CHANGE_FIELDS = [
    "date", "previous_date", "raw_work_count_change", "raw_citations_change",
    "raw_h_index_change", "raw_i10_index_change", "curated_work_count_change",
    "curated_citations_change", "curated_h_index_change",
    "curated_i10_index_change",
]

PAPER_CHANGE_FIELDS = [
    "date", "previous_date", "work_id", "doi", "title", "publication_year",
    "change_type", "previous_citations", "current_citations", "citation_change",
]

METRICS = [
    ("Works", "raw_work_count", "curated_work_count"),
    ("Citations", "raw_citations", "curated_citations"),
    ("h-index", "raw_h_index", "curated_h_index"),
    ("i10-index", "raw_i10_index", "curated_i10_index"),
]


def load_config(path: Path = CONFIG_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def api_session() -> requests.Session:
    retry = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers.update(
        {"User-Agent": "openalex-monitor/2.0 (https://github.com/Dr-Joe-Roberts/openalex-monitor)"}
    )
    return session


def api_params(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(extra or {})
    api_key = os.getenv("OPENALEX_API_KEY")
    if api_key:
        params["api_key"] = api_key
    return params


def fetch_openalex(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    author_id = config["author_id"].removeprefix("https://openalex.org/")
    session = api_session()
    author_response = session.get(
        f"https://api.openalex.org/authors/{author_id}", params=api_params(), timeout=60
    )
    author_response.raise_for_status()
    author = author_response.json()

    works: list[dict[str, Any]] = []
    cursor: str | None = "*"
    while cursor:
        response = session.get(
            "https://api.openalex.org/works",
            params=api_params(
                {"filter": f"author.id:{author_id}", "per-page": 100, "cursor": cursor}
            ),
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        works.extend(payload.get("results", []))
        cursor = payload.get("meta", {}).get("next_cursor")
    return author, works


def h_index(citations: Iterable[int]) -> int:
    ordered = sorted((int(value or 0) for value in citations), reverse=True)
    return max((rank for rank, value in enumerate(ordered, 1) if value >= rank), default=0)


def excluded_ids(config: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for item in config.get("excluded_works", []):
        work_id = item["id"] if isinstance(item, dict) else item
        result.add(str(work_id).removeprefix("https://openalex.org/"))
    return result


def short_id(value: str | None) -> str:
    return (value or "").removeprefix("https://openalex.org/")


def work_source(work: dict[str, Any]) -> str:
    source = (work.get("primary_location") or {}).get("source") or {}
    return source.get("display_name") or ""


def work_row(work: dict[str, Any], date: str, excluded: set[str]) -> dict[str, Any]:
    work_id = short_id(work.get("id"))
    return {
        "date": date,
        "work_id": work_id,
        "doi": work.get("doi") or "",
        "title": work.get("title") or work.get("display_name") or "Untitled",
        "publication_year": work.get("publication_year") or "",
        "type": work.get("type") or "",
        "source": work_source(work),
        "citations": int(work.get("cited_by_count") or 0),
        "included_in_curated": work_id not in excluded,
    }


def calculate_metrics(
    author: dict[str, Any], works: list[dict[str, Any]], config: dict[str, Any], fetched_at: str
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    date = fetched_at[:10]
    excluded = excluded_ids(config)
    rows = [work_row(work, date, excluded) for work in works]
    curated = [row for row in rows if row["included_in_curated"]]
    summary = author.get("summary_stats") or {}
    metrics = {
        "date": date,
        "fetched_at": fetched_at,
        "raw_work_count": int(author.get("works_count") or len(rows)),
        "raw_citations": int(author.get("cited_by_count") or 0),
        "raw_h_index": int(summary.get("h_index") or h_index(r["citations"] for r in rows)),
        "raw_i10_index": int(
            summary.get("i10_index") or sum(r["citations"] >= 10 for r in rows)
        ),
        "curated_work_count": len(curated),
        "curated_citations": sum(row["citations"] for row in curated),
        "curated_h_index": h_index(row["citations"] for row in curated),
        "curated_i10_index": sum(row["citations"] >= 10 for row in curated),
    }
    return metrics, rows


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def replace_date_rows(
    path: Path, new_rows: list[dict[str, Any]], fields: list[str], date: str
) -> None:
    retained = [row for row in read_csv(path) if row.get("date") != date]
    combined = retained + new_rows
    combined.sort(key=lambda row: (row.get("date", ""), row.get("work_id", "")))
    write_csv(path, combined, fields)


def as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def previous_state(current_date: str) -> tuple[dict[str, str] | None, list[dict[str, str]]]:
    """Use the latest snapshot from a month preceding the current month."""
    current_period = current_date[:7]
    candidates = [
        row for row in read_csv(DATA_DIR / "metrics.csv") if row["date"][:7] < current_period
    ]
    if not candidates:
        return None, []
    previous_metrics = max(candidates, key=lambda row: row["date"])
    previous_date = previous_metrics["date"]
    previous_papers = [
        row for row in read_csv(DATA_DIR / "paper_history.csv") if row["date"] == previous_date
    ]
    return previous_metrics, previous_papers


def build_metric_change(
    metrics: dict[str, Any], previous_metrics: dict[str, Any] | None
) -> dict[str, Any]:
    change: dict[str, Any] = {
        "date": metrics["date"],
        "previous_date": previous_metrics["date"] if previous_metrics else "",
    }
    for _, raw_key, curated_key in METRICS:
        for key in (raw_key, curated_key):
            change[f"{key}_change"] = (
                int(metrics[key]) - int(previous_metrics[key]) if previous_metrics else ""
            )
    return change


def build_paper_changes(
    paper_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    date: str,
    previous_date: str,
) -> list[dict[str, Any]]:
    """Compare curated works without treating newly indexed citations as new gains."""
    if not previous_date:
        return []
    current = {row["work_id"]: row for row in paper_rows}
    previous = {row["work_id"]: row for row in previous_rows}
    changes: list[dict[str, Any]] = []

    def add(
        row: dict[str, Any],
        change_type: str,
        old_count: int | str,
        new_count: int | str,
        difference: int | str,
    ) -> None:
        changes.append(
            {
                "date": date,
                "previous_date": previous_date,
                "work_id": row["work_id"],
                "doi": row.get("doi", ""),
                "title": row.get("title", "Untitled"),
                "publication_year": row.get("publication_year", ""),
                "change_type": change_type,
                "previous_citations": old_count,
                "current_citations": new_count,
                "citation_change": difference,
            }
        )

    for work_id, row in current.items():
        if not as_bool(row.get("included_in_curated")):
            continue
        old = previous.get(work_id)
        if old is None or not as_bool(old.get("included_in_curated")):
            add(row, "new_curated_work", "", int(row["citations"]), "")
            continue
        old_count = int(old["citations"])
        new_count = int(row["citations"])
        difference = new_count - old_count
        if difference > 0:
            add(
                row,
                "newly_cited" if old_count == 0 else "citation_gain",
                old_count,
                new_count,
                difference,
            )
        elif difference < 0:
            add(row, "citation_correction", old_count, new_count, difference)

    for work_id, old in previous.items():
        if not as_bool(old.get("included_in_curated")):
            continue
        new = current.get(work_id)
        if new is None or not as_bool(new.get("included_in_curated")):
            add(old, "removed_from_curated", int(old["citations"]), "", "")

    return sorted(
        changes, key=lambda row: (-int(row["citation_change"] or 0), str(row["title"]))
    )


def grouped_metrics(metrics: dict[str, Any]) -> dict[str, dict[str, int]]:
    return {
        "raw": {
            "works": metrics["raw_work_count"],
            "citations": metrics["raw_citations"],
            "h_index": metrics["raw_h_index"],
            "i10_index": metrics["raw_i10_index"],
        },
        "curated": {
            "works": metrics["curated_work_count"],
            "citations": metrics["curated_citations"],
            "h_index": metrics["curated_h_index"],
            "i10_index": metrics["curated_i10_index"],
        },
    }


def grouped_changes(metric_change: dict[str, Any]) -> dict[str, dict[str, int] | None]:
    if not metric_change["previous_date"]:
        return {"raw": None, "curated": None}
    return {
        "raw": {
            "works": metric_change["raw_work_count_change"],
            "citations": metric_change["raw_citations_change"],
            "h_index": metric_change["raw_h_index_change"],
            "i10_index": metric_change["raw_i10_index_change"],
        },
        "curated": {
            "works": metric_change["curated_work_count_change"],
            "citations": metric_change["curated_citations_change"],
            "h_index": metric_change["curated_h_index_change"],
            "i10_index": metric_change["curated_i10_index_change"],
        },
    }


def selected_work_json(work: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": short_id(work.get("id")),
        "doi": work.get("doi"),
        "title": work.get("title") or work.get("display_name"),
        "publication_date": work.get("publication_date"),
        "publication_year": work.get("publication_year"),
        "type": work.get("type"),
        "source": work_source(work),
        "cited_by_count": int(work.get("cited_by_count") or 0),
        "counts_by_year": work.get("counts_by_year") or [],
        "updated_date": work.get("updated_date"),
    }


def monthly_record(
    author: dict[str, Any],
    works: list[dict[str, Any]],
    metrics: dict[str, Any],
    metric_change: dict[str, Any],
    paper_rows: list[dict[str, Any]],
    paper_changes: list[dict[str, Any]],
    config: dict[str, Any],
) -> dict[str, Any]:
    gains = [
        row for row in paper_changes if row["change_type"] in {"citation_gain", "newly_cited"}
    ]
    new_works = [row for row in paper_changes if row["change_type"] == "new_curated_work"]
    corrections = [
        row
        for row in paper_changes
        if row["change_type"] in {"citation_correction", "removed_from_curated"}
    ]
    return {
        "schema_version": 1,
        "period": metrics["date"][:7],
        "snapshot_date": metrics["date"],
        "fetched_at": metrics["fetched_at"],
        "comparison": {
            "previous_snapshot_date": metric_change["previous_date"] or None,
            "metrics_change": grouped_changes(metric_change),
        },
        "profile": {
            "id": author.get("id"),
            "orcid": author.get("orcid"),
            "display_name": author.get("display_name"),
        },
        "metrics": grouped_metrics(metrics),
        "publications": {
            "all": sorted(paper_rows, key=lambda row: (-int(row["citations"]), row["title"])),
            "citation_gains": gains,
            "newly_indexed": new_works,
            "corrections_or_removals": corrections,
        },
        "openalex_snapshot": {
            "author": {
                "works_count": author.get("works_count"),
                "cited_by_count": author.get("cited_by_count"),
                "summary_stats": author.get("summary_stats"),
                "counts_by_year": author.get("counts_by_year") or [],
                "updated_date": author.get("updated_date"),
            },
            "works": [selected_work_json(work) for work in works],
        },
        "curation": {"excluded_works": config.get("excluded_works", [])},
        "provenance": {
            "source": "OpenAlex API",
            "author_endpoint": f"https://api.openalex.org/authors/{config['author_id']}",
            "works_filter": f"author.id:{config['author_id']}",
            "repository": "https://github.com/Dr-Joe-Roberts/openalex-monitor",
        },
    }


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def update_history(record: dict[str, Any]) -> None:
    path = DATA_DIR / "history.json"
    if path.exists():
        history = json.loads(path.read_text(encoding="utf-8"))
    else:
        history = {
            "schema_version": 1,
            "description": "Monthly OpenAlex monitoring index",
            "months": [],
        }
    summary = {
        "period": record["period"],
        "snapshot_date": record["snapshot_date"],
        "fetched_at": record["fetched_at"],
        "previous_snapshot_date": record["comparison"]["previous_snapshot_date"],
        "metrics": record["metrics"],
        "metrics_change": record["comparison"]["metrics_change"],
        "citation_gaining_publications": len(record["publications"]["citation_gains"]),
        "newly_indexed_publications": len(record["publications"]["newly_indexed"]),
        "data_file": f"monthly/{record['period']}.json",
        "report_file": f"../reports/{record['period']}.md",
    }
    months = [item for item in history.get("months", []) if item["period"] != record["period"]]
    history["months"] = sorted(months + [summary], key=lambda item: item["period"])
    save_json(path, history)


def save_data(
    author: dict[str, Any],
    works: list[dict[str, Any]],
    metrics: dict[str, Any],
    paper_rows: list[dict[str, Any]],
    config: dict[str, Any],
    metric_change: dict[str, Any],
    paper_changes: list[dict[str, Any]],
) -> dict[str, Any]:
    record = monthly_record(
        author, works, metrics, metric_change, paper_rows, paper_changes, config
    )
    save_json(MONTHLY_DIR / f"{record['period']}.json", record)
    save_json(SNAPSHOT_DIR / f"{metrics['date']}.json", record)
    save_json(DATA_DIR / "current.json", record)
    update_history(record)

    replace_date_rows(DATA_DIR / "metrics.csv", [metrics], METRIC_FIELDS, metrics["date"])
    replace_date_rows(DATA_DIR / "paper_history.csv", paper_rows, PAPER_FIELDS, metrics["date"])
    replace_date_rows(
        DATA_DIR / "metric_changes.csv", [metric_change], METRIC_CHANGE_FIELDS, metrics["date"]
    )
    replace_date_rows(
        DATA_DIR / "paper_changes.csv", paper_changes, PAPER_CHANGE_FIELDS, metrics["date"]
    )
    write_csv(
        DATA_DIR / "papers.csv",
        sorted(paper_rows, key=lambda row: (-row["citations"], row["title"])),
        PAPER_FIELDS[1:],
    )
    return record


def plot_metrics() -> None:
    path = DATA_DIR / "history.json"
    if not path.exists():
        return
    months = json.loads(path.read_text(encoding="utf-8")).get("months", [])
    if not months:
        return
    dates = [datetime.fromisoformat(item["snapshot_date"]) for item in months]
    raw = [item["metrics"]["raw"]["citations"] for item in months]
    curated = [item["metrics"]["curated"]["citations"] for item in months]
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(dates, raw, marker="o", linewidth=2, label="OpenAlex raw")
    ax.plot(dates, curated, marker="o", linewidth=2, label="Curated record")
    ax.set(title="Monthly citation history", xlabel="Snapshot month", ylabel="Citations")
    if len(dates) == 1:
        ax.set_xlim(dates[0] - timedelta(days=15), dates[0] + timedelta(days=15))
    ax.grid(alpha=0.25)
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "citation_history.png", dpi=180)
    plt.close(fig)


def plot_top_papers(paper_rows: list[dict[str, Any]]) -> None:
    top = sorted(
        (row for row in paper_rows if row["included_in_curated"]),
        key=lambda row: row["citations"],
        reverse=True,
    )[:10]
    if not top:
        return
    labels = [row["title"][:62] + ("…" if len(row["title"]) > 62 else "") for row in top]
    values = [row["citations"] for row in top]
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6.5))
    bars = ax.barh(labels[::-1], values[::-1], color="#2f6f8f")
    ax.bar_label(bars, padding=3)
    ax.set(title="Most cited publications (curated record)", xlabel="OpenAlex citations")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "top_papers.png", dpi=180, bbox_inches="tight")
    plt.close(fig)


def plot_monthly_gains(paper_changes: list[dict[str, Any]]) -> bool:
    gained = [
        row for row in paper_changes if row["change_type"] in {"citation_gain", "newly_cited"}
    ][:10]
    if not gained:
        return False
    labels = [row["title"][:62] + ("…" if len(row["title"]) > 62 else "") for row in gained]
    values = [int(row["citation_change"]) for row in gained]
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 6.5))
    bars = ax.barh(labels[::-1], values[::-1], color="#397367")
    ax.bar_label(bars, padding=3, fmt="+%g")
    ax.set(title="Citation gains since the preceding month", xlabel="Citations gained")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(PLOTS_DIR / "latest_citation_gains.png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    return True


def delta(value: Any) -> str:
    if value == "" or value is None:
        return "—"
    return f"{int(value):+d}"


def paper_table(rows: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Manuscript | Year | Previous | Current | Change |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        title = str(row["title"]).replace("|", "\\|")
        lines.append(
            f"| [{title}](https://openalex.org/{row['work_id']}) | "
            f"{row['publication_year']} | {row['previous_citations']} | "
            f"{row['current_citations']} | {delta(row['citation_change'])} |"
        )
    return lines


def change_report(record: dict[str, Any]) -> str:
    metrics = record["metrics"]
    changes = record["comparison"]["metrics_change"]
    previous_date = record["comparison"]["previous_snapshot_date"]
    lines = [
        f"# OpenAlex change report — {record['period']}",
        "",
        f"**Profile:** {record['profile']['display_name']}  ",
        f"**Retrieved:** {record['fetched_at'].replace('+00:00', ' UTC')}",
        "",
    ]
    if not previous_date:
        lines.extend(
            [
                "This is the baseline snapshot. Month-to-month changes will be calculated from the next scheduled run.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                f"**Comparison:** {previous_date} to {record['snapshot_date']}",
                "",
                "## Metric changes",
                "",
                "| Metric | OpenAlex raw | Change | Curated | Change |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for label, key in [
            ("Works", "works"), ("Citations", "citations"),
            ("h-index", "h_index"), ("i10-index", "i10_index"),
        ]:
            lines.append(
                f"| {label} | {metrics['raw'][key]} | {delta(changes['raw'][key])} | "
                f"{metrics['curated'][key]} | {delta(changes['curated'][key])} |"
            )

        gains = record["publications"]["citation_gains"]
        lines.extend(["", "## Manuscripts gaining citations", ""])
        lines.extend(
            paper_table(gains)
            if gains
            else ["No citation gains were detected among previously tracked curated works."]
        )

        new_works = record["publications"]["newly_indexed"]
        lines.extend(["", "## Newly indexed curated works", ""])
        if new_works:
            lines.extend(
                ["| Manuscript | Year | Citations when first observed |", "|---|---:|---:|"]
            )
            for row in new_works:
                title = str(row["title"]).replace("|", "\\|")
                lines.append(
                    f"| [{title}](https://openalex.org/{row['work_id']}) | "
                    f"{row['publication_year']} | {row['current_citations']} |"
                )
        else:
            lines.append("No newly indexed curated works were detected.")

        corrections = record["publications"]["corrections_or_removals"]
        if corrections:
            lines.extend(["", "## Corrections or removals", "", *paper_table(corrections)])

    lines.extend(
        [
            "", "---",
            "Citation gains are differences between works present in both monthly snapshots. Citations already attached to newly indexed works are reported separately and are not treated as citations gained during the interval.",
            "",
        ]
    )
    return "\n".join(lines)


def save_reports(report: str, period: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / f"{period}.md").write_text(report, encoding="utf-8")
    (REPORTS_DIR / "latest.md").write_text(report, encoding="utf-8")


def markdown_summary(record: dict[str, Any], has_gain_plot: bool) -> str:
    metrics = record["metrics"]
    changes = record["comparison"]["metrics_change"]
    previous_date = record["comparison"]["previous_snapshot_date"]
    lines = [
        "## Latest snapshot",
        "",
        f"Retrieved **{record['snapshot_date']}**; comparison: **{previous_date or 'baseline'}**.",
        "",
        f"[Monthly report](reports/latest.md) · [Monthly JSON](data/monthly/{record['period']}.json) · [Full history](data/history.json)",
        "",
        "| Metric | Curated | Change | OpenAlex raw | Raw change |",
        "|---|---:|---:|---:|---:|",
    ]
    for label, key in [
        ("Works", "works"), ("Citations", "citations"),
        ("h-index", "h_index"), ("i10-index", "i10_index"),
    ]:
        raw_change = changes["raw"][key] if changes["raw"] else None
        curated_change = changes["curated"][key] if changes["curated"] else None
        lines.append(
            f"| {label} | {metrics['curated'][key]} | {delta(curated_change)} | "
            f"{metrics['raw'][key]} | {delta(raw_change)} |"
        )

    gains = record["publications"]["citation_gains"]
    lines.extend(["", "### Citation changes by publication", ""])
    if previous_date and gains:
        lines.extend(paper_table(gains[:10]))
        if has_gain_plot:
            lines.extend(["", "![Latest citation gains](plots/latest_citation_gains.png)"])
    elif previous_date:
        lines.append("No citation gains were detected among previously tracked curated works.")
    else:
        lines.append("This baseline establishes the starting point for the next monthly comparison.")

    lines.extend(["", "![Monthly citation history](plots/citation_history.png)"])
    return "\n".join(lines)


def update_readme(summary: str) -> None:
    start = "<!-- MONITOR:START -->"
    end = "<!-- MONITOR:END -->"
    text = README_PATH.read_text(encoding="utf-8")
    replacement = f"{start}\n{summary}\n{end}"
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.DOTALL)
    if not pattern.search(text):
        raise ValueError("README monitoring markers are missing")
    README_PATH.write_text(pattern.sub(replacement, text), encoding="utf-8")


def main() -> None:
    config = load_config()
    fetched_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    author, works = fetch_openalex(config)
    metrics, paper_rows = calculate_metrics(author, works, config, fetched_at)
    old_metrics, old_papers = previous_state(metrics["date"])
    metric_change = build_metric_change(metrics, old_metrics)
    paper_changes = build_paper_changes(
        paper_rows, old_papers, metrics["date"], metric_change["previous_date"]
    )
    record = save_data(
        author, works, metrics, paper_rows, config, metric_change, paper_changes
    )
    plot_metrics()
    plot_top_papers(paper_rows)
    has_gain_plot = plot_monthly_gains(paper_changes)
    save_reports(change_report(record), record["period"])
    update_readme(markdown_summary(record, has_gain_plot))
    print(
        f"Updated {author.get('display_name')}: "
        f"{metrics['curated_citations']} curated citations, "
        f"{len(record['publications']['citation_gains'])} manuscripts gained citations"
    )


if __name__ == "__main__":
    main()
