from __future__ import annotations

from pathlib import Path

MOCK_CODE_SERVER = """\
printf '%s\\n' "$*" >> "{calls}"
if [[ " $* " == *" --list-extensions "* ]]; then
    printf '%s\\n' {installed}
fi
"""


def code_server_mock(tmp_path: Path, installed: str = "") -> dict[str, str]:
    return {"code-server": MOCK_CODE_SERVER.format(calls=tmp_path / "calls", installed=installed)}


def calls(tmp_path: Path) -> list[str]:
    return (tmp_path / "calls").read_text().splitlines()


def test_should_print_usage_with_help(run_cli):
    result = run_cli("code-server-start", ["--help"])

    assert result.returncode == 0
    assert "Usage: code-server-start <address:port>" in result.stdout


def test_should_refuse_to_start_without_an_address(run_cli, tmp_path):
    result = run_cli("code-server-start", mock_bins=code_server_mock(tmp_path))

    assert result.returncode == 2
    assert "Usage:" in result.stderr
    assert not (tmp_path / "calls").exists()


def test_should_fail_when_code_server_is_missing(run_cli):
    result = run_cli("code-server-start", ["127.0.0.1:8125"], isolate_path=True)

    assert result.returncode == 127
    assert "code-server is not installed" in result.stderr


def test_should_install_a_missing_extension_then_start_without_a_password(run_cli, tmp_path):
    result = run_cli("code-server-start", ["127.0.0.1:8125"], mock_bins=code_server_mock(tmp_path),
                     env_extra={"HOME": str(tmp_path)})

    data = f"--user-data-dir {tmp_path}/.local/share/code-server --extensions-dir {tmp_path}/.local/share/code-server/extensions"
    assert result.returncode == 0
    assert calls(tmp_path) == [
        f"{data} --list-extensions",
        f"{data} --install-extension anthropic.claude-code",
        f"{data} --bind-addr 127.0.0.1:8125 --auth none --disable-telemetry --disable-update-check",
    ]


def test_should_skip_an_extension_that_is_installed(run_cli, tmp_path):
    result = run_cli("code-server-start", ["10.42.3.7:8080"],
                     mock_bins=code_server_mock(tmp_path, installed="Anthropic.claude-code"),
                     env_extra={"HOME": str(tmp_path)})

    assert result.returncode == 0
    assert not any("--install-extension" in call for call in calls(tmp_path))
    assert calls(tmp_path)[-1].endswith("--bind-addr 10.42.3.7:8080 --auth none --disable-telemetry --disable-update-check")


def test_should_start_even_when_an_extension_fails_to_install(run_cli, tmp_path):
    failing = code_server_mock(tmp_path)
    failing["code-server"] += '[[ " $* " == *" --install-extension "* ]] && exit 1\nexit 0\n'

    result = run_cli("code-server-start", ["127.0.0.1:8125"], mock_bins=failing, env_extra={"HOME": str(tmp_path)})

    assert result.returncode == 0
    assert "could not install anthropic.claude-code" in result.stderr
    assert "--bind-addr 127.0.0.1:8125" in calls(tmp_path)[-1]
