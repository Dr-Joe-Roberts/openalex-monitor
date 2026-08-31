from monitor import calculate_metrics, excluded_ids, h_index


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
