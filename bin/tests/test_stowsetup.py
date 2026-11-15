from pathlib import Path

import pytest

STOWSETUP = Path(__file__).parent.parent.parent / "stowsetup"
INSTALLER_CONFIG = "sdkman_auto_answer=false\n"
GIT_CLONE_MOCK = 'for last; do :; done\nmkdir -p "$last"'
SUDO_MOCK = "exit 0"
UNAME_MOCK = "echo Darwin"
STOW_MOCK = """\
while [ $# -gt 0 ]; do
    case "$1" in
        -d) dir=$2; shift 2 ;;
        -t) target=$2; shift 2 ;;
        *) package=$1; shift ;;
    esac
done
config="$target/.sdkman/etc/config"
if [ "$package" = sdkman ]; then
    if [ -e "$config" ] && [ ! -L "$config" ]; then
        echo "WARNING! stowing sdkman would cause conflicts" >&2
        exit 1
    fi
    mkdir -p "${config%/*}"
    ln -sfn "$dir/sdkman/.sdkman/etc/config" "$config"
fi
echo "$package" >> "$STOW_LOG"
"""


@pytest.fixture
def stowsetup(run_script, create_mock_bin, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    stow_log = tmp_path / "stow.log"
    for name, body in {"git": GIT_CLONE_MOCK, "stow": STOW_MOCK, "sudo": SUDO_MOCK, "uname": UNAME_MOCK}.items():
        create_mock_bin(name, body)

    def _run(*args):
        return run_script(
            STOWSETUP, list(args),
            env_extra={"HOME": str(home), "ZDOTDIR": "", "STOW_LOG": str(stow_log)},
        )
    _run.config = home / ".sdkman" / "etc" / "config"
    _run.stowed = lambda: stow_log.read_text().split() if stow_log.exists() else []
    return _run


def _install_sdkman(config: Path):
    config.parent.mkdir(parents=True)
    config.write_text(INSTALLER_CONFIG)


class TestSdkmanConfig:
    def test_should_move_the_installer_config_aside_and_stow_sdkman(self, stowsetup):
        _install_sdkman(stowsetup.config)

        result = stowsetup()

        assert result.returncode == 0, result.stderr
        assert stowsetup.config.is_symlink()
        assert stowsetup.config.with_name("config.pre-stow").read_text() == INSTALLER_CONFIG

    def test_should_leave_a_stowed_config_link_alone_on_a_rerun(self, stowsetup):
        _install_sdkman(stowsetup.config)
        stowsetup()

        result = stowsetup()

        assert result.returncode == 0, result.stderr
        assert stowsetup.config.is_symlink()
        assert stowsetup.config.with_name("config.pre-stow").read_text() == INSTALLER_CONFIG

    def test_should_stow_sdkman_when_the_installer_has_not_run(self, stowsetup):
        result = stowsetup()

        assert result.returncode == 0, result.stderr
        assert stowsetup.config.is_symlink()
        assert not stowsetup.config.with_name("config.pre-stow").exists()

    def test_should_not_touch_the_installer_config_with_minimal(self, stowsetup):
        _install_sdkman(stowsetup.config)

        result = stowsetup("--minimal")

        assert result.returncode == 0, result.stderr
        assert stowsetup.config.read_text() == INSTALLER_CONFIG
        assert not stowsetup.config.is_symlink()
        assert "sdkman" not in stowsetup.stowed()
