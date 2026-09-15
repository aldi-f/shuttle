from __future__ import annotations

from collections.abc import Iterable


def _fuzzy_score(query: str, candidate: str) -> tuple[int, int, int, int] | None:
    """Rank exact substrings before ordered, non-contiguous character matches."""
    query = query.casefold().strip()
    candidate = candidate.casefold()
    if not query:
        return (0, 0, 0, len(candidate))

    substring_index = candidate.find(query)
    if substring_index >= 0:
        return (0, substring_index, 0, len(candidate))

    positions: list[int] = []
    search_from = 0
    for character in query:
        position = candidate.find(character, search_from)
        if position < 0:
            return None
        positions.append(position)
        search_from = position + 1
    gaps = positions[-1] - positions[0] + 1 - len(query)
    return (1, gaps, positions[0], len(candidate))


def fuzzy_matches(query: str, candidates: Iterable[str], *, limit: int = 50) -> list[str]:
    scored = [
        (score, candidate)
        for candidate in candidates
        if (score := _fuzzy_score(query, candidate)) is not None
    ]
    scored.sort(key=lambda item: (item[0], item[1].casefold()))
    return [candidate for _score, candidate in scored[:limit]]

