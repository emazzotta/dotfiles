import pytest


@pytest.fixture
def search(load_script):
    return load_script("session_search.py")


@pytest.fixture
def make_session(search):
    def _make(sid="s", updated_at=0, title="", content=""):
        return search.Session(sid=sid, updated_at=updated_at, title=title, content_lower=content.lower())
    return _make


class TestParseQuery:
    def test_should_split_whitespace_into_separate_terms(self, search):
        query = search.parse_query("docker compose")

        assert [term.alternatives[0].text for term in query.terms] == ["docker", "compose"]

    def test_should_lowercase_terms_when_query_has_uppercase(self, search):
        query = search.parse_query("Docker COMPOSE")

        assert [term.alternatives[0].text for term in query.terms] == ["docker", "compose"]

    def test_should_mark_term_as_negated_when_prefixed_with_bang(self, search):
        query = search.parse_query("docker !compose")

        assert [term.negated for term in query.terms] == [False, True]

    def test_should_split_pipe_into_alternatives(self, search):
        query = search.parse_query("docker|podman")

        assert [alt.text for alt in query.terms[0].alternatives] == ["docker", "podman"]

    def test_should_strip_anchor_markers_from_term_text(self, search):
        query = search.parse_query("^docker compose$")

        start, end = query.terms
        assert (start.alternatives[0].text, start.alternatives[0].anchor_start) == ("docker", True)
        assert (end.alternatives[0].text, end.alternatives[0].anchor_end) == ("compose", True)

    def test_should_drop_terms_that_are_only_operator_characters(self, search):
        query = search.parse_query("! docker")

        assert [term.alternatives[0].text for term in query.terms] == ["docker"]

    def test_should_return_no_terms_when_query_is_blank(self, search):
        assert search.parse_query("   ").terms == ()

    def test_should_expose_positive_terms_in_query_order_as_phrase_words(self, search):
        query = search.parse_query("docker !swarm compose")

        assert query.phrase_words == ("docker", "compose")


class TestMatches:
    def test_should_match_when_every_term_is_present(self, search, make_session):
        session = make_session(title="deploy", content="docker and compose")

        assert search.matches(session, search.parse_query("docker compose")) is True

    def test_should_not_match_when_one_term_is_missing(self, search, make_session):
        session = make_session(title="deploy", content="docker only")

        assert search.matches(session, search.parse_query("docker compose")) is False

    def test_should_match_term_found_in_title_only(self, search, make_session):
        session = make_session(title="Compose notes", content="unrelated")

        assert search.matches(session, search.parse_query("compose")) is True

    def test_should_not_match_when_negated_term_is_present(self, search, make_session):
        session = make_session(content="docker compose")

        assert search.matches(session, search.parse_query("docker !compose")) is False

    def test_should_match_when_negated_term_is_absent(self, search, make_session):
        session = make_session(content="docker only")

        assert search.matches(session, search.parse_query("docker !compose")) is True

    def test_should_match_when_any_alternative_is_present(self, search, make_session):
        session = make_session(content="podman run")

        assert search.matches(session, search.parse_query("docker|podman")) is True

    def test_should_anchor_prefix_term_to_title_start(self, search, make_session):
        matching = make_session(title="docker notes", content="")
        trailing = make_session(title="notes about docker", content="")
        query = search.parse_query("^docker")

        assert search.matches(matching, query) is True
        assert search.matches(trailing, query) is False

    def test_should_anchor_suffix_term_to_title_end(self, search, make_session):
        matching = make_session(title="notes about docker", content="")
        leading = make_session(title="docker notes", content="")
        query = search.parse_query("docker$")

        assert search.matches(matching, query) is True
        assert search.matches(leading, query) is False

    def test_should_match_every_session_when_query_is_blank(self, search, make_session):
        session = make_session(title="anything", content="")

        assert search.matches(session, search.parse_query("")) is True


class TestRanking:
    def test_should_rank_adjacent_words_above_scattered_words(self, search, make_session):
        adjacent = make_session(sid="adjacent", updated_at=1, content="deploy the docker compose stack")
        scattered = make_session(sid="scattered", updated_at=2, content="docker is fine but we compose later")

        ranked = search.search([scattered, adjacent], search.parse_query("docker compose"))

        assert [session.sid for session in ranked] == ["adjacent", "scattered"]

    def test_should_rank_longer_run_above_shorter_run(self, search, make_session):
        three = make_session(sid="three", updated_at=1, content="run git crypt lock now")
        two = make_session(sid="two", updated_at=2, content="run git crypt then lock it")
        one = make_session(sid="one", updated_at=3, content="git and crypt and lock separately")

        ranked = search.search([one, two, three], search.parse_query("git crypt lock"))

        assert [session.sid for session in ranked] == ["three", "two", "one"]

    def test_should_treat_punctuation_between_words_as_adjacent(self, search, make_session):
        hyphenated = make_session(sid="hyphenated", updated_at=1, content="we ran docker-compose up")
        scattered = make_session(sid="scattered", updated_at=2, content="docker is fine but we compose later")

        ranked = search.search([scattered, hyphenated], search.parse_query("docker compose"))

        assert [session.sid for session in ranked] == ["hyphenated", "scattered"]

    def test_should_not_treat_widely_separated_words_as_adjacent(self, search, make_session):
        far_apart = make_session(sid="far", updated_at=1, content="docker" + " " * 8 + "compose")
        query = search.parse_query("docker compose")

        assert search.rank_key(far_apart, query)[0] == 1

    def test_should_require_query_order_for_a_run(self, search, make_session):
        reversed_order = make_session(sid="reversed", updated_at=1, content="compose docker")
        query = search.parse_query("docker compose")

        assert search.rank_key(reversed_order, query)[0] == 1

    def test_should_rank_title_match_above_content_match_for_equal_runs(self, search, make_session):
        in_title = make_session(sid="title", updated_at=1, title="docker compose setup", content="filler")
        in_content = make_session(sid="content", updated_at=2, title="filler", content="docker compose setup")

        ranked = search.search([in_content, in_title], search.parse_query("docker compose"))

        assert [session.sid for session in ranked] == ["title", "content"]

    def test_should_fall_back_to_recency_when_runs_are_equal(self, search, make_session):
        older = make_session(sid="older", updated_at=1, content="docker compose up")
        newer = make_session(sid="newer", updated_at=2, content="docker compose down")

        ranked = search.search([older, newer], search.parse_query("docker compose"))

        assert [session.sid for session in ranked] == ["newer", "older"]

    def test_should_keep_recency_order_when_query_is_a_single_word(self, search, make_session):
        older = make_session(sid="older", updated_at=1, content="docker")
        newer = make_session(sid="newer", updated_at=2, content="docker docker docker")

        ranked = search.search([older, newer], search.parse_query("docker"))

        assert [session.sid for session in ranked] == ["newer", "older"]

    def test_should_ignore_negated_terms_when_scoring_runs(self, search, make_session):
        session = make_session(content="docker compose up")
        query = search.parse_query("docker !swarm compose")

        assert search.rank_key(session, query)[0] == 2


class TestSearch:
    def test_should_drop_sessions_that_do_not_match(self, search, make_session):
        matching = make_session(sid="hit", content="docker compose")
        other = make_session(sid="miss", content="something else")

        ranked = search.search([matching, other], search.parse_query("docker"))

        assert [session.sid for session in ranked] == ["hit"]

    def test_should_return_every_session_in_recency_order_when_query_is_blank(self, search, make_session):
        older = make_session(sid="older", updated_at=1, content="a")
        newer = make_session(sid="newer", updated_at=2, content="b")

        ranked = search.search([older, newer], search.parse_query(""))

        assert [session.sid for session in ranked] == ["newer", "older"]


class TestHighlightTokens:
    def test_should_return_positive_tokens_without_operator_syntax(self, search):
        tokens = search.highlight_tokens(search.parse_query("^docker compose$ !swarm podman|nerdctl"))

        assert tokens == ["docker", "compose", "podman", "nerdctl"]
