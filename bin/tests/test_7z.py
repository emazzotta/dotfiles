RECORD = 'printf "%s %s\\n" "$(basename "$0")" "$*" >> "$CALLS_LOG"'


def run_wrapper(run_bash, tmp_path, mock_bins):
    mock_dir = tmp_path / "mock_bin"
    return run_bash(
        "7z",
        ["x", "a.7z"],
        env_extra={
            "PATH": f"{mock_dir}:/usr/bin:/bin",
            "KEKA_CLI": str(mock_dir / "keka"),
            "CALLS_LOG": str(tmp_path / "calls"),
        },
        mock_bins=mock_bins,
    )


def calls(tmp_path):
    return (tmp_path / "calls").read_text().splitlines()


def test_should_run_7zz_when_it_is_installed(run_bash, tmp_path):
    result = run_wrapper(run_bash, tmp_path, {"7zz": RECORD, "keka": RECORD})

    assert result.returncode == 0
    assert calls(tmp_path) == ["7zz x a.7z"]


def test_should_run_keka_when_7zz_is_missing(run_bash, tmp_path):
    result = run_wrapper(run_bash, tmp_path, {"keka": RECORD})

    assert result.returncode == 0
    assert calls(tmp_path) == ["keka --cli 7zz x a.7z"]
