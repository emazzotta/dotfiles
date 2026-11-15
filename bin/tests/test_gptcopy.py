import pytest

PBCOPY_MOCK = 'cat > "$CLIPBOARD"'
ESCAPES = 'print("a\\n")\n\\cite{key} and \\color{red}\n'
LAST_FILE = "after the cut\n"


@pytest.fixture
def gptcopy(run_bash, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    clipboard = tmp_path / "clipboard"

    def _run(answer):
        return run_bash("gptcopy", stdin=answer, cwd=work, env_extra={"CLIPBOARD": str(clipboard)},
                        mock_bins={"pbcopy": PBCOPY_MOCK})
    _run.work = work
    _run.clipboard = clipboard
    return _run


class TestGptcopy:
    def should_print_file_contents_with_backslashes_untouched(self, gptcopy):
        (gptcopy.work / "code.py").write_text(ESCAPES)
        (gptcopy.work / "z-last.txt").write_text(LAST_FILE)

        result = gptcopy("n\n")

        assert ESCAPES.rstrip("\n") in result.stdout
        assert LAST_FILE.rstrip("\n") in result.stdout

    def should_copy_the_same_text_to_the_clipboard(self, gptcopy):
        (gptcopy.work / "code.py").write_text(ESCAPES)
        (gptcopy.work / "z-last.txt").write_text(LAST_FILE)

        result = gptcopy("y\n")

        assert result.returncode == 0, result.stderr
        copied = gptcopy.clipboard.read_text()
        assert ESCAPES.rstrip("\n") in copied
        assert LAST_FILE.rstrip("\n") in copied
        assert copied in result.stdout

    def should_fence_each_file_under_a_heading_with_its_path(self, gptcopy):
        (gptcopy.work / "notes.txt").write_text("plain\n")

        result = gptcopy("n\n")

        assert result.stdout.startswith("```\n# ./notes.txt\nplain\n```\n\n")
