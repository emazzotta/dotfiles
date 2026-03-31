import sys
from pathlib import Path
from types import ModuleType

sys.path.insert(0, str(Path(__file__).parent.parent))

ags_path = Path(__file__).parent.parent / "ags"
ags = ModuleType("ags")
with open(ags_path) as f:
    exec(f.read(), ags.__dict__)


def test_filter_output_no_patterns():
    output = "line1\nline2\nline3"
    result = ags._filter_output(output, [])
    assert result == output


def test_filter_output_single_pattern():
    output = "line1\nline2 ERROR\nline3"
    result = ags._filter_output(output, ["ERROR"])
    assert "line1" in result
    assert "line3" in result
    assert "ERROR" not in result


def test_filter_output_multiple_patterns():
    output = "line1\nline2 ERROR\nline3 WARN\nline4"
    result = ags._filter_output(output, ["ERROR", "WARN"])
    assert "line1" in result
    assert "line4" in result
    assert "ERROR" not in result
    assert "WARN" not in result


def test_filter_output_empty_string():
    result = ags._filter_output("", ["pattern"])
    assert result == ""


def test_filter_output_no_matches():
    output = "line1\nline2\nline3"
    result = ags._filter_output(output, ["NOTFOUND"])
    assert result == output


def test_filter_output_all_filtered():
    output = "ERROR\nERROR\nERROR"
    result = ags._filter_output(output, ["ERROR"])
    assert result == ""


def test_filter_output_partial_match():
    output = "This is an ERROR message\nThis is fine\nAnother ERROR here"
    result = ags._filter_output(output, ["ERROR"])
    assert "This is fine" in result
    assert "ERROR" not in result


def test_filter_output_case_sensitive():
    output = "line with ERROR\nline with error\nclean line"
    result = ags._filter_output(output, ["ERROR"])
    assert "line with error" in result
    assert "clean line" in result
    assert "line with ERROR" not in result


def test_wrap_glob_plain_string_adds_wildcards():
    assert ags._wrap_glob("foo") == "*foo*"


def test_wrap_glob_with_star_passes_through():
    assert ags._wrap_glob("**/foo/bar") == "**/foo/bar"


def test_wrap_glob_with_question_mark_passes_through():
    assert ags._wrap_glob("foo?bar") == "foo?bar"


def test_wrap_glob_with_bracket_passes_through():
    assert ags._wrap_glob("[Ff]oo") == "[Ff]oo"


def test_wrap_glob_trailing_star_passes_through():
    assert ags._wrap_glob("*.log") == "*.log"


def test_ag_exclude_strips_double_star_path():
    assert ags._ag_exclude("**/commons/**") == "commons"


def test_ag_exclude_strips_leading_double_star():
    assert ags._ag_exclude("**/target") == "target"


def test_ag_exclude_strips_trailing_double_star():
    assert ags._ag_exclude("build/**") == "build"


def test_ag_exclude_plain_name_unchanged():
    assert ags._ag_exclude("node_modules") == "node_modules"


def test_ag_exclude_glob_pattern_stripped():
    assert ags._ag_exclude("*.log") == ".log"


def test_ag_exclude_nested_path():
    assert ags._ag_exclude("**/foo/bar/**") == "foo/bar"
