import shutil

import pytest


class TestSlugify:
    @pytest.mark.parametrize("input_val,expected", [
        ("Hello World", "hello-world"),
        ("Hello, World! How's it?", "hello-world-how-s-it-"),
        ("ALLCAPS", "allcaps"),
        ("hello---world", "hello-world"),
        ("already-slugified", "already-slugified"),
        ("  spaces  ", "-spaces-"),
        ("CamelCaseTitle", "camelcasetitle"),
    ])
    def test_slugify(self, run_bash, input_val, expected):
        result = run_bash("slugify", [input_val])
        assert result.stdout.strip() == expected

    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("slugify")
        assert "usage" in result.stdout.lower()


class TestCtof:
    @pytest.mark.parametrize("celsius,expected_f", [
        ("0", "32"),
        ("100", "212"),
        ("-40", "-40"),
        ("37", "98.6"),
    ])
    def test_conversion(self, run_bash, celsius, expected_f):
        result = run_bash("ctof", [celsius])
        assert expected_f in result.stdout

    def test_no_args_shows_usage(self, run_bash):
        assert "usage" in run_bash("ctof").stdout.lower()


class TestFtoc:
    @pytest.mark.parametrize("fahrenheit,expected_c", [
        ("32", "0.0"),
        ("212", "100"),
        ("-40", "-40"),
    ])
    def test_conversion(self, run_bash, fahrenheit, expected_c):
        result = run_bash("ftoc", [fahrenheit])
        assert expected_c in result.stdout

    def test_no_args_shows_usage(self, run_bash):
        assert "usage" in run_bash("ftoc").stdout.lower()


class TestKmtom:
    @pytest.mark.parametrize("km,expected_miles", [
        ("1", "0.62"),
        ("10", "6.21"),
    ])
    def test_conversion(self, run_bash, km, expected_miles):
        assert expected_miles in run_bash("kmtom", [km]).stdout

    def test_no_args_shows_usage(self, run_bash):
        assert "usage" in run_bash("kmtom").stdout.lower()


class TestMtokm:
    @pytest.mark.parametrize("miles,expected_km", [
        ("1", "1.61"),
        ("10", "16.09"),
    ])
    def test_conversion(self, run_bash, miles, expected_km):
        assert expected_km in run_bash("mtokm", [miles]).stdout

    def test_no_args_shows_usage(self, run_bash):
        assert "usage" in run_bash("mtokm").stdout.lower()


class TestSizefmt:
    @pytest.mark.parametrize("bytes_val,expected", [
        ("500", "500"),
        ("1024", "KiB"),
        ("1048576", "MiB"),
    ])
    def test_formats(self, run_bash, bytes_val, expected):
        assert expected in run_bash("sizefmt", [bytes_val]).stdout

    def test_no_args_shows_message(self, run_bash):
        output = run_bash("sizefmt").stdout.lower()
        assert "number" in output or "human" in output


class TestFirstCapitalize:
    @pytest.mark.parametrize("input_val,expected", [
        ("hello", "Hello"),
        ("Hello", "Hello"),
        ("a", "A"),
    ])
    def test_capitalizes(self, run_bash, input_val, expected):
        assert run_bash("first_capitalize", [input_val]).stdout.strip() == expected

    def test_no_args_exits_nonzero(self, run_bash):
        assert run_bash("first_capitalize").returncode == 1


class TestTldify:
    def test_generates_all_tlds(self, run_bash):
        result = run_bash("tldify", ["example"])
        lines = result.stdout.strip().split("\n")
        expected = {"example.ch", "example.com", "example.io", "example.me", "example.net", "example.gmbh"}
        assert set(lines) == expected


class TestProgressbar:
    @pytest.fixture(autouse=True)
    def _require_bc(self):
        if not shutil.which("bc"):
            pytest.skip("bc not available")

    def test_half_progress(self, run_bash):
        result = run_bash("progressbar", ["5", "10", "10"])
        assert result.returncode == 0
        assert "◼" in result.stdout

    def test_full_progress(self, run_bash):
        result = run_bash("progressbar", ["10", "10", "10"])
        assert result.returncode == 0
        assert "◻" not in result.stdout

    def test_no_args_shows_usage(self, run_bash):
        assert "usage" in run_bash("progressbar").stdout.lower()
