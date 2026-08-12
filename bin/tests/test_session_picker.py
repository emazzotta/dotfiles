from types import SimpleNamespace

import pytest

HEADER = "#test-index v1"
NOW = 1_700_000_000


@pytest.fixture
def picker(load_script, monkeypatch):
    """Freeze the clock: ages are relative, and a slow suite must not drift them."""
    module = load_script("session_picker.py")
    monkeypatch.setattr(module, "time", SimpleNamespace(time=lambda: NOW))
    return module


@pytest.fixture
def cache_file(tmp_path):
    return tmp_path / "index.tsv"


class TestCache:
    def test_should_round_trip_entries_through_the_cache_file(self, picker, cache_file):
        entries = {"a": picker.CacheEntry(10, "First", "body one"), "b": picker.CacheEntry(20, "Second", "body two")}

        picker.save_cache(cache_file, HEADER, entries)

        assert picker.load_cache(cache_file, HEADER) == entries

    def test_should_return_nothing_when_cache_file_is_absent(self, picker, tmp_path):
        assert picker.load_cache(tmp_path / "missing.tsv", HEADER) == {}

    def test_should_discard_cache_written_by_an_older_format(self, picker, cache_file):
        picker.save_cache(cache_file, "#test-index v0", {"a": picker.CacheEntry(1, "t", "c")})

        assert picker.load_cache(cache_file, HEADER) == {}

    def test_should_flatten_tabs_so_columns_stay_aligned(self, picker, cache_file):
        picker.save_cache(cache_file, HEADER, {"a": picker.CacheEntry(1, "ti\ttle", "con\ntent")})

        assert picker.load_cache(cache_file, HEADER)["a"] == picker.CacheEntry(1, "ti tle", "con tent")

    def test_should_create_parent_directory_when_missing(self, picker, tmp_path):
        nested = tmp_path / "cache" / "index.tsv"

        picker.save_cache(nested, HEADER, {"a": picker.CacheEntry(1, "t", "c")})

        assert nested.exists()


class TestFormatAgo:
    @pytest.mark.parametrize("seconds_ago,expected", [
        (5, "just now"),
        (90, "1m ago"),
        (7200, "2h ago"),
        (86400 + 60, "yesterday"),
        (5 * 86400, "5d ago"),
        (60 * 86400, "2mo ago"),
        (800 * 86400, "2y ago"),
    ])
    def test_should_describe_age_in_the_largest_useful_unit(self, picker, seconds_ago, expected):
        assert picker.format_ago(NOW - seconds_ago) == expected


class TestFormatDisplay:
    def test_should_pad_title_to_a_fixed_width(self, picker):
        display = picker.format_display("short", NOW)

        assert display.startswith("short" + " " * (picker.TITLE_WIDTH - len("short")))

    def test_should_truncate_title_that_exceeds_the_column(self, picker):
        display = picker.format_display("x" * 200, NOW)

        assert display.startswith("x" * (picker.TITLE_WIDTH - 1) + picker.ELLIPSIS)

    def test_should_append_project_column_when_given(self, picker):
        assert picker.format_display("title", NOW, "my-project").endswith("my-project")

    def test_should_omit_project_column_when_empty(self, picker):
        assert picker.format_display("title", NOW).rstrip().endswith("just now")


class TestFormatRow:
    def test_should_separate_display_from_id_with_a_tab(self, picker):
        assert picker.format_row("display", "abc123").split("\t") == ["display", "abc123"]

    def test_should_strip_tabs_from_display_so_the_id_stays_field_two(self, picker):
        assert picker.format_row("a\tb", "abc123").split("\t") == ["a b", "abc123"]


class TestHighlightMatches:
    def test_should_wrap_each_token_in_highlight_codes(self, picker):
        assert picker.highlight_matches("run docker now", ["docker"]) == f"run {picker.HIGHLIGHT_ON}docker{picker.RESET} now"

    def test_should_highlight_regardless_of_case(self, picker):
        assert picker.HIGHLIGHT_ON + "Docker" in picker.highlight_matches("run Docker now", ["docker"])

    def test_should_return_text_unchanged_when_no_tokens(self, picker):
        assert picker.highlight_matches("run docker now", []) == "run docker now"

    def test_should_treat_tokens_as_literals_not_patterns(self, picker):
        assert picker.highlight_matches("a.b and axb", ["a.b"]) == f"{picker.HIGHLIGHT_ON}a.b{picker.RESET} and axb"


class TestBuildFzfArgs:
    @pytest.fixture
    def args(self, picker):
        commands = picker.PickerCommands(preview="preview {2}", reload="reload {q}")
        return picker.build_fzf_args("docker", "header text", commands)

    def test_should_disable_fzf_matching_so_ranking_is_ours(self, args):
        assert "--disabled" in args

    def test_should_rerun_the_ranked_search_on_every_keystroke(self, args):
        assert "change:reload:reload {q}" in args

    def test_should_pass_the_initial_query_through(self, args):
        assert args[args.index("--query") + 1] == "docker"

    def test_should_select_the_id_field_for_the_preview(self, args):
        assert args[args.index("--preview") + 1] == "preview {2}"


class TestSplitArgs:
    def test_should_split_forwarded_args_at_the_separator(self, picker):
        assert picker.split_args(["a", "--", "b", "c"]) == (["a"], ["b", "c"])

    def test_should_forward_nothing_when_separator_is_absent(self, picker):
        assert picker.split_args(["a", "b"]) == (["a", "b"], [])
