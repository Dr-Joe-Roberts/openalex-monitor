"""Create reproducible monthly snapshots of an OpenAlex author profile."""

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
SNAPSHOT_DIR = DATA_DIR / "snapshots"
PLOTS_DIR = ROOT / "plots"
README_PATH = ROOT / "README.md"

METRIC_FIELDS = [
    "date",
    "fetched_at",
    "raw_work_count",
    "raw_citations",
    "raw_h_index",
    "raw_i10_index",
    "curated_work_count",
    "curated_citations",
    "curated_h_index",
    "curated_i10_index",
]

PAPER_FIELDS = [
    "date",
    "work_id",
    "doi",
    "title",
    "publication_year",
    "type",
    "source",
    "citations",
    "included_in_curated",
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
        {
            "User-Agent": (
                "openalex-monitor/1.0 "
                "(https://github.com/Dr-Joe-Roberts/openalex-monitor)"
            )
        }
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
        f"https://api.openalex.org/authors/{author_id}",
        params=api_params(),
        timeout=60,
    )
    author_response.raise_for_status()
    author = author_response.json()

    works: list[dict[str, Any]] = []
    cursor: str | None = "*"
    while cursor:
        response = session.get(
            "https://api.openalex.org/works",
            params=api_params(
                {
                    "filter": f"author.id:{author_id}",
                    "per-page": 100,
                    "cursor": cursor,
                }
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
    location = work.get("primary_location") or {}
    source = location.get("source") or {}
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
        "raw_i10_index": int(summary.get("i10_index") or sum(r["citations"] >= 10 for r in rows)),
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


def replace_date_rows(path: Path, new_rows: list[dict[str, Any]], fields: list[str], date: str) -> None:
    retained = [row for row in read_csv(path) if row.get("date") != date]
    combined = retained + new_rows
    combined.sort(key=lambda row: (row.get("date", ""), row.get("work_id", "")))
    write_csv(path, combined, fields)


def save_data(
    author: dict[str, Any],
    works: list[dict[str, Any]],
    metrics: dict[str, Any],
    paper_rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    snapshot_works = [
        {
            "id": work.get("id"),
            "doi": work.get("doi"),
            "title": work.get("title") or work.get("display_name"),
            "publication_date": work.get("publication_date"),
            "publication_year": work.get("publication_year"),
            "type": work.get("type"),
            "cited_by_count": work.get("cited_by_count"),
            "counts_by_year": work.get("counts_by_year"),
            "source": work_source(work),
            "updated_date": work.get("updated_date"),
        }
        for work in works
    ]
    snapshot = {
        "fetched_at": metrics["fetched_at"],
        "author": {
            "id": author.get("id"),
            "orcid": author.get("orcid"),
            "display_name": author.get("display_name"),
            "works_count": author.get("works_count"),
            "cited_by_count": author.get("cited_by_count"),
            "summary_stats": author.get("summary_stats"),
            "counts_by_year": author.get("counts_by_year"),
            "updated_date": author.get("updated_date"),
        },
        "works": snapshot_works,
        "monitor": {
            "metrics": metrics,
            "excluded_works": config.get("excluded_works", []),
        },
    }
    snapshot_path = SNAPSHOT_DIR / f"{metrics['date']}.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    current = {
        "fetched_at": metrics["fetched_at"],
        "author_id": author.get("id"),
        "display_name": author.get("display_name"),
        "orcid": author.get("orcid"),
        "metrics": metrics,
        "works": sorted(paper_rows, key=lambda row: (-row["citations"], row["title"])),
    }
    (DATA_DIR / "current.json").write_text(
        json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    replace_date_rows(DATA_DIR / "metrics.csv", [metrics], METRIC_FIELDS, metrics["date"])
    replace_date_rows(DATA_DIR / "paper_history.csv", paper_rows, PAPER_FIELDS, metrics["date"])
    write_csv(
        DATA_DIR / "papers.csv",
        sorted(paper_rows, key=lambda row: (-row["citations"], row["title"])),
        PAPER_FIELDS[1:],
    )


def plot_metrics() -> None:
    rows = read_csv(DATA_DIR / "metrics.csv")
    if not rows:
        return
    dates = [datetime.fromisoformat(row["date"]) for row in rows]
    raw = [int(row["raw_citations"]) for row in rows]
    curated = [int(row["curated_citations"]) for row in rows]

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(dates, raw, marker="o", linewidth=2, label="OpenAlex raw")
    ax.plot(dates, curated, marker="o", linewidth=2, label="Curated record")
    ax.set(title="Citation history", xlabel="Snapshot date", ylabel="Citations")
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


def markdown_summary(
    author: dict[str, Any], metrics: dict[str, Any], paper_rows: list[dict[str, Any]], config: dict[str, Any]
) -> str:
    top = sorted(
        (row for row in paper_rows if row["included_in_curated"]),
        key=lambda row: row["citations"],
        reverse=True,
    )[:10]
    lines = [
        f"*Last updated: {metrics['fetched_at'].replace('+00:00', ' UTC')}*",
        "",
        "| Metric | OpenAlex raw | Curated |",
        "|---|---:|---:|",
        f"| Works | {metrics['raw_work_count']} | {metrics['curated_work_count']} |",
        f"| Citations | {metrics['raw_citations']} | {metrics['curated_citations']} |",
        f"| h-index | {metrics['raw_h_index']} | {metrics['curated_h_index']} |",
        f"| i10-index | {metrics['raw_i10_index']} | {metrics['curated_i10_index']} |",
        "",
        f"The curated view excludes {len(excluded_ids(config))} confirmed misattributions listed in "
        "[`config/author.json`](config/author.json). It does not automatically discard preprints or other legitimate versions.",
        "",
        "![Citation history](plots/citation_history.png)",
        "",
        "![Most cited publications](plots/top_papers.png)",
        "",
        "### Most cited publications",
        "",
        "| Rank | Publication | Year | Citations |",
        "|---:|---|---:|---:|",
    ]
    for rank, row in enumerate(top, 1):
        title = str(row["title"]).replace("|", "\\|")
        lines.append(
            f"| {rank} | [{title}](https://openalex.org/{row['work_id']}) | "
            f"{row['publication_year']} | {row['citations']} |"
        )
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
    save_data(author, works, metrics, paper_rows, config)
    plot_metrics()
    plot_top_papers(paper_rows)
    update_readme(markdown_summary(author, metrics, paper_rows, config))
    print(
        f"Updated {author.get('display_name')}: "
        f"{metrics['curated_citations']} curated citations, h-index {metrics['curated_h_index']}"
    )


if __name__ == "__main__":
    main()
