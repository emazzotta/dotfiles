import subprocess

import pytest

from bin.tests.conftest import BIN_DIR

DOTFILES = BIN_DIR.parent


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    (home / "dotfiles").symlink_to(DOTFILES)
    (home / ".bashrc").symlink_to(DOTFILES / "bash" / ".bashrc")
    (home / ".bashrc.d").symlink_to(DOTFILES / "bash" / ".bashrc.d")
    (home / ".sshrc").write_text('echo loaded >> "$HOME/sshrc-loads"\n')
    return home


def sshrc_loaded(home, bash_args, **env_extra):
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin", "TERM": "dumb", **env_extra}
    subprocess.run(["bash", *bash_args], env=env, capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    return (home / "sshrc-loads").exists()


class TestSshrcLoading:
    def should_not_load_the_sshrc_into_a_cron_job(self, home):
        loaded = sshrc_loaded(home, ["-c", "true"], BASH_ENV=str(home / ".bashrc"))

        assert not loaded

    def should_not_load_the_sshrc_into_an_interactive_local_bash(self, home):
        loaded = sshrc_loaded(home, ["-i", "-c", "true"])

        assert not loaded
