import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import ags


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
    assert result == "\n\n"


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
