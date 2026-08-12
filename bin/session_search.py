"""Matching and ranking for session pickers.

Pure logic - no I/O. Shared by claude-resume and opencode-resume.

Matching keeps the fzf operator syntax the pickers used to delegate to fzf:
space separates AND terms, `|` separates alternatives, `!` negates, and
`^`/`$` anchor to the session title.

Ranking answers "which of these sessions did I mean": sessions whose query
words appear consecutively rank above sessions that merely contain all of
them somewhere.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Final, Iterable, Pattern, Sequence

MAX_SEPARATOR_CHARS: Final = 3
ALTERNATIVE_SEPARATOR: Final = "|"
NEGATION_PREFIX: Final = "!"
EXACT_PREFIX: Final = "'"
ANCHOR_START: Final = "^"
ANCHOR_END: Final = "$"


@dataclass(frozen=True)
class Alternative:
    text: str
    anchor_start: bool = False
    anchor_end: bool = False


@dataclass(frozen=True)
class Term:
    alternatives: tuple[Alternative, ...]
    negated: bool = False


@dataclass(frozen=True)
class Query:
    terms: tuple[Term, ...] = ()

    @property
    def phrase_words(self) -> tuple[str, ...]:
        """Positive term texts in query order - the words a run is measured over."""
        return tuple(
            term.alternatives[0].text
            for term in self.terms
            if not term.negated and term.alternatives
        )


@dataclass(frozen=True)
class Session:
    """An indexed session. Content arrives lowercased - matching runs per keystroke."""

    sid: str
    updated_at: int
    title: str
    content_lower: str
    project: str = ""
    title_lower: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "title_lower", self.title.lower())


def parse_query(raw: str) -> Query:
    terms = tuple(term for term in (_parse_term(word) for word in raw.split()) if term)
    return Query(terms)


def _parse_term(word: str) -> Term | None:
    negated = word.startswith(NEGATION_PREFIX)
    body = word[1:] if negated else word
    alternatives = tuple(
        alternative
        for alternative in (_parse_alternative(part) for part in body.split(ALTERNATIVE_SEPARATOR))
        if alternative
    )
    return Term(alternatives, negated) if alternatives else None


def _parse_alternative(part: str) -> Alternative | None:
    text = part.lstrip(EXACT_PREFIX)
    anchor_start = text.startswith(ANCHOR_START)
    if anchor_start:
        text = text[1:]
    anchor_end = text.endswith(ANCHOR_END)
    if anchor_end:
        text = text[:-1]
    return Alternative(text.lower(), anchor_start, anchor_end) if text else None


def highlight_tokens(query: Query) -> list[str]:
    """Literal substrings worth highlighting in a preview pane."""
    return [
        alternative.text
        for term in query.terms
        if not term.negated
        for alternative in term.alternatives
    ]


def matches(session: Session, query: Query) -> bool:
    return all(_term_matches(session, term) for term in query.terms)


def _term_matches(session: Session, term: Term) -> bool:
    found = any(_alternative_matches(session, alternative) for alternative in term.alternatives)
    return not found if term.negated else found


def _alternative_matches(session: Session, alternative: Alternative) -> bool:
    if alternative.anchor_start and alternative.anchor_end:
        return session.title_lower == alternative.text
    if alternative.anchor_start:
        return session.title_lower.startswith(alternative.text)
    if alternative.anchor_end:
        return session.title_lower.endswith(alternative.text)
    return alternative.text in session.title_lower or alternative.text in session.content_lower


@lru_cache(maxsize=512)
def _run_pattern(words: tuple[str, ...]) -> Pattern[str]:
    separator = rf"[^a-z0-9]{{0,{MAX_SEPARATOR_CHARS}}}"
    return re.compile(separator.join(re.escape(word) for word in words))


def longest_adjacent_run(haystack: str, words: Sequence[str]) -> int:
    """Longest count of query words appearing consecutively, in query order.

    Words may be separated by a little punctuation, so a query of
    "docker compose" scores 2 against "docker-compose" as well as
    against "docker compose". Returns 0 when no word is present at all.
    """
    for length in range(len(words), 1, -1):
        for start in range(len(words) - length + 1):
            if _run_pattern(tuple(words[start : start + length])).search(haystack):
                return length
    return 1 if any(word in haystack for word in words) else 0


def rank_key(session: Session, query: Query) -> tuple[int, int, int]:
    """Sort key, descending: longest run, then title over content, then recency."""
    words = query.phrase_words
    title_run = longest_adjacent_run(session.title_lower, words)
    content_run = longest_adjacent_run(session.content_lower, words)
    return max(title_run, content_run), title_run, session.updated_at


def search(sessions: Iterable[Session], query: Query) -> list[Session]:
    hits = [session for session in sessions if matches(session, query)]
    hits.sort(key=lambda session: rank_key(session, query), reverse=True)
    return hits
