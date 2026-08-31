from monitor import (
    build_metric_change,
    build_paper_changes,
    calculate_metrics,
    excluded_ids,
    h_index,
)


def test_h_index():
    assert h_index([20, 10, 4, 4, 1]) == 4
    assert h_index([]) == 0


def test_excluded_ids_accepts_full_and_short_ids():
    config = {
        "excluded_works": [
            {"id": "W1", "reason": "test"},
            {"id": "https://openalex.org/W2", "reason": "test"},
        ]
    }
    assert excluded_ids(config) == {"W1", "W2"}


def test_calculate_curated_metrics():
    author = {
        "works_count": 4,
        "cited_by_count": 40,
        "summary_stats": {"h_index": 4, "i10_index": 2},
    }
    works = [
        {"id": "https://openalex.org/W1", "title": "A", "cited_by_count": 20},
        {"id": "https://openalex.org/W2", "title": "B", "cited_by_count": 10},
        {"id": "https://openalex.org/W3", "title": "C", "cited_by_count": 6},
        {"id": "https://openalex.org/W4", "title": "D", "cited_by_count": 4},
    ]
    config = {"excluded_works": [{"id": "W1", "reason": "test"}]}
    metrics, rows = calculate_metrics(author, works, config, "2026-08-31T08:00:00+00:00")

    assert metrics["raw_citations"] == 40
    assert metrics["curated_work_count"] == 3
    assert metrics["curated_citations"] == 20
    assert metrics["curated_h_index"] == 3
    assert metrics["curated_i10_index"] == 1
    assert sum(row["included_in_curated"] for row in rows) == 3


def test_metric_changes_are_month_to_month_differences():
    current = {
        "date": "2026-09-01",
        "raw_work_count": 12,
        "raw_citations": 105,
        "raw_h_index": 6,
        "raw_i10_index": 5,
        "curated_work_count": 10,
        "curated_citations": 90,
        "curated_h_index": 5,
        "curated_i10_index": 4,
    }
    previous = {
        "date": "2026-08-01",
        "raw_work_count": "11",
        "raw_citations": "100",
        "raw_h_index": "6",
        "raw_i10_index": "4",
        "curated_work_count": "9",
        "curated_citations": "86",
        "curated_h_index": "5",
        "curated_i10_index": "3",
    }
    change = build_metric_change(current, previous)
    assert change["previous_date"] == "2026-08-01"
    assert change["raw_citations_change"] == 5
    assert change["curated_citations_change"] == 4
    assert change["curated_h_index_change"] == 0


def test_paper_changes_separate_gains_new_indexing_and_removals():
    previous = [
        {"work_id": "W1", "title": "Established", "citations": "4", "included_in_curated": "True"},
        {"work_id": "W2", "title": "Newly cited", "citations": "0", "included_in_curated": "True"},
        {"work_id": "W3", "title": "Removed", "citations": "2", "included_in_curated": "True"},
    ]
    current = [
        {"work_id": "W1", "title": "Established", "citations": 7, "included_in_curated": True},
        {"work_id": "W2", "title": "Newly cited", "citations": 1, "included_in_curated": True},
        {"work_id": "W4", "title": "Newly indexed", "citations": 8, "included_in_curated": True},
    ]
    changes = build_paper_changes(current, previous, "2026-09-01", "2026-08-01")
    by_id = {row["work_id"]: row for row in changes}
    assert by_id["W1"]["change_type"] == "citation_gain"
    assert by_id["W1"]["citation_change"] == 3
    assert by_id["W2"]["change_type"] == "newly_cited"
    assert by_id["W4"]["change_type"] == "new_curated_work"
    assert by_id["W4"]["citation_change"] == ""
    assert by_id["W3"]["change_type"] == "removed_from_curated"
