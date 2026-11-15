GS_MOCK = 'printf "%s\\n" "$@" > "$GS_LOG"'


def run_pdfmerge(run_cli, tmp_path, *args):
    log = tmp_path / "gs.log"
    result = run_cli("pdfmerge", list(args), env_extra={"GS_LOG": str(log)}, mock_bins={"gs": GS_MOCK})
    return result, (log.read_text().splitlines() if log.exists() else [])


class TestPdfmerge:
    def test_should_hand_ghostscript_the_output_and_the_inputs(self, run_cli, tmp_path):
        result, call = run_pdfmerge(run_cli, tmp_path, "out.pdf", "a.pdf", "b.pdf")

        assert result.returncode == 0, result.stderr
        assert "-sOutputFile=out.pdf" in call
        assert call[-2:] == ["a.pdf", "b.pdf"]

    def test_should_keep_names_with_spaces_whole(self, run_cli, tmp_path):
        result, call = run_pdfmerge(run_cli, tmp_path, "merged scan.pdf", "page 1.pdf", "page 2.pdf")

        assert result.returncode == 0, result.stderr
        assert "-sOutputFile=merged scan.pdf" in call
        assert call[-2:] == ["page 1.pdf", "page 2.pdf"]

    def test_should_print_usage_when_only_one_argument_is_given(self, run_cli, tmp_path):
        result, call = run_pdfmerge(run_cli, tmp_path, "out.pdf")

        assert "usage:" in result.stdout
        assert call == []
