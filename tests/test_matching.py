from shuttle_s3.matching import fuzzy_matches

BUCKETS = [
    "company-analytics-prod",
    "company-analytics-dev",
    "financial-reports",
    "prod-archive",
]


def test_exact_substrings_rank_before_subsequence_matches() -> None:
    assert fuzzy_matches("prod", BUCKETS) == [
        "prod-archive",
        "company-analytics-prod",
    ]


def test_non_contiguous_characters_match_bucket_name() -> None:
    assert fuzzy_matches("analyticsprod", BUCKETS) == ["company-analytics-prod"]


def test_unmatched_query_returns_empty_list() -> None:
    assert fuzzy_matches("xyz", BUCKETS) == []
