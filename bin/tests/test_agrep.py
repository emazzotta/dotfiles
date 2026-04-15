import importlib.machinery
import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

import pytest

AGREP = Path(__file__).parent.parent / "agrep"

requires_rg = pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep not installed")


def _load(path: Path):
    loader = importlib.machinery.SourceFileLoader("agrep_mod", str(path))
    spec = importlib.util.spec_from_loader("agrep_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


agrep = _load(AGREP)


class TestColorize:
    def test_wraps_substring(self):
        out = agrep.colorize("foo bar", "bar", exact=False)
        assert "bar" in out and "\033[" in out

    def test_case_insensitive(self):
        out = agrep.colorize("FoO", "foo", exact=False)
        assert "\033[" in out

    def test_exact_word_boundary(self):
        assert "\033[" in agrep.colorize("pwc here", "pwc", exact=True)
        assert "\033[" not in agrep.colorize("mpcpwcompress", "pwc", exact=True)


class TestFilenameMatches:
    def test_substring(self, tmp_path):
        (tmp_path / "pwcompress").touch()
        (tmp_path / "mpcpwcompress").touch()
        (tmp_path / "unrelated").touch()
        names = [p.name for p in agrep.filename_matches("pwc", tmp_path, exact=False)]
        assert set(names) == {"pwcompress", "mpcpwcompress"}

    def test_exact_word(self, tmp_path):
        (tmp_path / "pwc").touch()
        (tmp_path / "mpcpwcompress").touch()
        names = [p.name for p in agrep.filename_matches("pwc", tmp_path, exact=True)]
        assert names == ["pwc"]


class TestBashrcMatches:
    def test_matches_alias_export_function_only(self, tmp_path, monkeypatch):
        d = tmp_path / ".bashrc.d"
        d.mkdir()
        (d / "10-x.sh").write_text(
            "# foo comment\n"
            "alias foo='echo hi'\n"
            "export BAR=1\n"
            "baz() { echo foo; }\n"
            "echo foo  # not a def line\n"
        )
        monkeypatch.setattr(agrep, "BASHRC_DIR", d)
        hits = agrep.bashrc_matches("foo", exact=False)
        assert len(hits) == 2  # alias line + function (body contains foo)
        assert all(h.path == d / "10-x.sh" for h in hits)

    def test_ignores_non_numeric_files(self, tmp_path, monkeypatch):
        d = tmp_path / ".bashrc.d"
        d.mkdir()
        (d / "10-x.sh").write_text("alias foo=1\n")
        (d / "readme.sh").write_text("alias foo=1\n")
        monkeypatch.setattr(agrep, "BASHRC_DIR", d)
        hits = agrep.bashrc_matches("foo", exact=False)
        assert [h.path.name for h in hits] == ["10-x.sh"]


@requires_rg
class TestRgContent:
    def test_finds_content_and_filenames(self, tmp_path):
        (tmp_path / "a").write_text("hello world\n")
        (tmp_path / "b").write_text("no match here\n")
        hits = agrep.rg_content("hello", tmp_path, exact=False)
        assert len(hits) == 1
        assert hits[0].path.name == "a"
        assert hits[0].line_no == 1

    def test_respects_exact(self, tmp_path):
        (tmp_path / "a").write_text("pwcompress\n")
        assert not agrep.rg_content("pwc", tmp_path, exact=True)
        assert agrep.rg_content("pwc", tmp_path, exact=False)


class TestIntegration:
    @requires_rg
    def test_cli_finds_filename_and_content(self, tmp_path, monkeypatch):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        (bin_dir / "pwcompress").write_text("#!/bin/bash\necho ok\n")
        (bin_dir / "gsheet_backup").write_text("#!/bin/bash\npwcompress foo\n")
        (bin_dir / "unrelated").write_text("#!/bin/bash\necho bye\n")

        env = {**os.environ, "CUSTOM_BIN_DIR": str(bin_dir), "HOME": str(tmp_path)}
        r = subprocess.run([str(AGREP), "pwc"], capture_output=True, text=True, env=env)
        assert r.returncode == 0
        # Strip ANSI before asserting plain-text content
        import re as _re
        plain = _re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", r.stdout)
        assert "pwcompress" in plain
        assert "gsheet_backup" in plain
        assert "filename match" in plain

    def test_cli_help(self):
        r = subprocess.run([str(AGREP), "-h"], capture_output=True, text=True)
        assert r.returncode == 0
        assert "aliases" in r.stdout.lower() or "search" in r.stdout.lower()

    @pytest.mark.parametrize("args", [[], ["--unknown"]])
    def test_cli_rejects_bad_args(self, args):
        r = subprocess.run([str(AGREP), *args], capture_output=True, text=True)
        assert r.returncode != 0
