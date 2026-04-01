import pytest


@pytest.fixture
def ags(load_script):
    return load_script("ags")


class TestFilterOutput:
    def test_no_patterns(self, ags):
        assert ags._filter_output("line1\nline2\nline3", []) == "line1\nline2\nline3"

    def test_single_pattern(self, ags):
        result = ags._filter_output("line1\nline2 ERROR\nline3", ["ERROR"])
        assert "line1" in result
        assert "line3" in result
        assert "ERROR" not in result

    def test_multiple_patterns(self, ags):
        result = ags._filter_output("line1\nline2 ERROR\nline3 WARN\nline4", ["ERROR", "WARN"])
        assert "line1" in result
        assert "line4" in result
        assert "ERROR" not in result
        assert "WARN" not in result

    def test_empty_string(self, ags):
        assert ags._filter_output("", ["pattern"]) == ""

    def test_no_matches(self, ags):
        output = "line1\nline2\nline3"
        assert ags._filter_output(output, ["NOTFOUND"]) == output

    def test_all_filtered(self, ags):
        assert ags._filter_output("ERROR\nERROR\nERROR", ["ERROR"]) == ""

    def test_partial_match(self, ags):
        result = ags._filter_output("This is an ERROR message\nThis is fine\nAnother ERROR here", ["ERROR"])
        assert "This is fine" in result
        assert "ERROR" not in result

    def test_case_sensitive(self, ags):
        result = ags._filter_output("line with ERROR\nline with error\nclean line", ["ERROR"])
        assert "line with error" in result
        assert "clean line" in result
        assert "line with ERROR" not in result


class TestWrapGlob:
    @pytest.mark.parametrize("input_val,expected", [
        ("foo", "*foo*"),
        ("**/foo/bar", "**/foo/bar"),
        ("foo?bar", "foo?bar"),
        ("[Ff]oo", "[Ff]oo"),
        ("*.log", "*.log"),
    ])
    def test_wrapping(self, ags, input_val, expected):
        assert ags._wrap_glob(input_val) == expected


class TestAgExclude:
    @pytest.mark.parametrize("input_val,expected", [
        ("**/commons/**", "commons"),
        ("**/target", "target"),
        ("build/**", "build"),
        ("node_modules", "node_modules"),
        ("*.log", ".log"),
        ("**/foo/bar/**", "foo/bar"),
    ])
    def test_exclusion(self, ags, input_val, expected):
        assert ags._ag_exclude(input_val) == expected
