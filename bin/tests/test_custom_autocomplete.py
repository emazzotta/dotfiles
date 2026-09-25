import os
import shlex
import subprocess
from pathlib import Path

import pytest

from bin.tests.conftest import BIN_DIR

AUTOCOMPLETE = BIN_DIR.parent / "autocomplete" / "custom_autocomplete"
HELP_COMPLETERS = ("_complete_help_flags", "_complete_help_subcommands", "_complete_script_words")

ARGPARSE_HELP = """usage: fake [-h] [-o OUTPUT] [--mode {fast,slow}] [--dry-run] input

options:
  -h, --help            show this help message and exit
  -o OUTPUT, --output OUTPUT
  --mode {fast,slow}
  --dry-run
"""

ARGPARSE_SUBCOMMANDS = """if [ "$1" = start ]; then
    echo "usage: fakesub start [-h] [--force]"
else
    printf 'usage: fakesub [-h] {start,stop} ...\\n\\npositional arguments:\\n  {start,stop}\\n'
fi"""

GPG_PUBLIC = """pub:u:255:22:AAAA:1:::u:::scESC:::::ed25519:::0:
uid:u::::1::HASH::Emanuele Mazzotta <me@example.com>::::::::::0:
pub:f:255:22:BBBB:1:::f:::scESC:::::ed25519:::0:
uid:f::::1::HASH::Friend <friend@example.com>::::::::::0:
uid:f::::1::HASH::No Email::::::::::0:
"""

GPG_SECRET = """sec:u:255:22:AAAA:1:::u:::scESC:::::ed25519:::0:
uid:u::::1::HASH::Emanuele Mazzotta <me@example.com>::::::::::0:
"""

DISKUTIL_EXTERNAL = """/dev/disk4 (external, physical):
   #:                       TYPE NAME                    SIZE       IDENTIFIER
   0:     FDisk_partition_scheme                        *31.9 GB    disk4
   1:             Windows_FAT_32 boot                    268.4 MB   disk4s1
   2:                      Linux                         31.6 GB    disk4s2
"""


def run_bash(script, cwd, path_prefix, env_extra=None):
    env = {**os.environ, "PATH": f"{path_prefix}:{os.environ['PATH']}", **(env_extra or {})}
    result = subprocess.run(["bash", "-c", f'source "{AUTOCOMPLETE}"\n{script}'],
                            capture_output=True, text=True, cwd=cwd, env=env)
    assert result.returncode == 0, result.stderr
    return result.stdout


@pytest.fixture
def commands(tmp_path):
    directory = tmp_path / "commands"
    directory.mkdir()
    return directory


@pytest.fixture
def mock(commands):
    def _mock(name, body):
        script = commands / name
        script.write_text(f"#!/bin/bash\n{body}\n")
        script.chmod(0o755)
    return _mock


@pytest.fixture
def home(tmp_path):
    directory = tmp_path / "home"
    directory.mkdir()
    return directory


@pytest.fixture
def fake_command(tmp_path, mock):
    help_text = tmp_path / "help.txt"
    help_text.write_text(ARGPARSE_HELP)
    calls = tmp_path / "calls"
    mock("fake", f'echo call >> "{calls}"\ncat "{help_text}"')
    return {"help": help_text, "calls": calls}


@pytest.fixture
def complete(commands, home, tmp_path):
    def _complete(function, *words, cwd=None, times=1, env=None):
        script = (f"COMP_WORDS=({' '.join(shlex.quote(word) for word in words)}); "
                  f"COMP_CWORD={len(words) - 1}\n"
                  + f"{function}\n" * times
                  + 'printf "%s\\n" "${COMPREPLY[@]}"')
        output = run_bash(script, cwd or tmp_path, commands, {"HOME": str(home), **(env or {})})
        return [line for line in output.splitlines() if line]
    return _complete


@pytest.fixture
def repo(tmp_path):
    gitconfig = tmp_path / "gitconfig"
    gitconfig.write_text("[user]\n\tname = Test\n\temail = test@example.com\n"
                         "[init]\n\tdefaultBranch = main\n[safe]\n\tdirectory = *\n")
    env = {**os.environ, "GIT_CONFIG_GLOBAL": str(gitconfig), "GIT_CONFIG_NOSYSTEM": "1"}
    directory = tmp_path / "repo"

    def git(*args):
        result = subprocess.run(["git", "-C", str(directory), *args], capture_output=True,
                                text=True, env=env)
        assert result.returncode == 0, result.stderr
        return result.stdout.strip()

    directory.mkdir()
    git("init", "-q")
    git("commit", "-q", "--allow-empty", "-m", "Initial commit")
    return {"dir": directory, "git": git, "env": {"GIT_CONFIG_GLOBAL": str(gitconfig)}}


class TestCompleteHelp:
    def should_offer_every_flag_the_help_lists(self, complete, fake_command):
        candidates = complete("_complete_help_flags", "fake", "-")

        assert sorted(candidates) == ["--dry-run", "--help", "--mode", "--output", "-h", "-o"]

    def should_offer_the_choices_the_help_lists_after_a_flag(self, complete, fake_command):
        candidates = complete("_complete_help_flags", "fake", "--mode", "")

        assert candidates == ["fast", "slow"]

    def should_leave_a_word_that_is_no_flag_to_the_shell(self, complete, fake_command, tmp_path):
        (tmp_path / "notes.txt").touch()

        candidates = complete("_complete_help_flags", "fake", "no")

        assert candidates == []

    def should_run_the_help_once_per_shell(self, complete, fake_command):
        complete("_complete_help_flags", "fake", "-", times=2)

        assert fake_command["calls"].read_text().split() == ["call"]

    def should_find_flags_in_colored_help(self, complete, fake_command):
        fake_command["help"].write_text("\033[1m--color-flag\033[0m  paints the output\n")

        candidates = complete("_complete_help_flags", "fake", "--c")

        assert candidates == ["--color-flag"]

    def should_ignore_flags_in_example_lines(self, complete, fake_command):
        fake_command["help"].write_text("Usage: fake [-c CONTAINER]\n\nExamples:\n"
                                        "  fake nginx ls -la\n")

        candidates = complete("_complete_help_flags", "fake", "-")

        assert candidates == ["-c"]

    def should_offer_the_flags_of_the_wrapped_leorun_to_wleorun(self, complete, mock):
        mock("leorun", 'echo "Usage: leorun [-f|--fast] [-q|--quick]"')

        candidates = complete("_wleorun", "wleorun", "-")

        assert sorted(candidates) == ["--fast", "--quick", "-f", "-q"]


class TestScriptLists:
    def should_relay_the_words_typed_so_far_to_the_script(self, complete, mock):
        mock("fakewords", '[ "$1" = --complete ] && shift && echo "after-$*"')

        candidates = complete("_complete_script_words", "fakewords", "first", "")

        assert candidates == ["after-first"]

    def should_offer_the_subcommands_of_an_argparse_script(self, complete, mock):
        mock("fakesub", ARGPARSE_SUBCOMMANDS)

        candidates = complete("_complete_help_subcommands", "fakesub", "")

        assert candidates == ["start", "stop"]

    def should_offer_the_flags_of_the_chosen_subcommand(self, complete, mock):
        mock("fakesub", ARGPARSE_SUBCOMMANDS)

        candidates = complete("_complete_help_subcommands", "fakesub", "start", "--")

        assert candidates == ["--force"]

    def should_not_ask_an_unknown_subcommand_for_help(self, complete, mock, tmp_path):
        mock("fakesub", f'echo "$*" >> "{tmp_path / "asked"}"\n{ARGPARSE_SUBCOMMANDS}')

        complete("_complete_help_subcommands", "fakesub", "bogus", "--")

        assert (tmp_path / "asked").read_text().split("\n") == ["--help", ""]

    def should_offer_the_formats_of_audiotox_after_the_format_of_audiomerge(self, complete, mock):
        mock("audiotox", 'echo "  -f {mp3,wav}, --format {mp3,wav}"')
        mock("audiomerge", 'echo "  -f, --format FORMAT"')

        candidates = complete("_audiomerge", "audiomerge", "-f", "")

        assert candidates == ["mp3", "wav"]

    def should_offer_the_short_names_of_host_resolver(self, complete, mock):
        mock("host-resolver", '[ "$*" = "--complete hosts" ] && echo ci-macmini')

        candidates = complete("_host_resolver", "host-resolver", "")

        assert candidates == ["ci-macmini"]

    def should_offer_nothing_as_the_value_of_a_host_resolver_flag(self, complete, mock):
        mock("host-resolver", '[ "$*" = "--complete hosts" ] && echo ci-macmini')

        candidates = complete("_host_resolver", "host-resolver", "--timeout", "")

        assert candidates == []


class TestGitCompletions:
    def should_offer_the_tags_of_the_repository_to_gretag(self, complete, repo):
        repo["git"]("tag", "v1.0")
        repo["git"]("tag", "v1.1")

        candidates = complete("_gretag", "gretag", "v", cwd=repo["dir"], env=repo["env"])

        assert candidates == ["v1.0", "v1.1"]

    def should_offer_branches_first_to_git_squash_commits_x_y(self, complete, repo):
        repo["git"]("branch", "feature")

        candidates = complete("_git_squash_commits_x_y", "git_squash_commits_x_y", "",
                              cwd=repo["dir"], env=repo["env"])

        assert candidates == ["feature", "main"]

    def should_offer_the_commits_of_the_branch_after_it(self, complete, repo):
        head = repo["git"]("rev-parse", "--short", "HEAD")

        candidates = complete("_git_squash_commits_x_y", "git_squash_commits_x_y", "main", "",
                              cwd=repo["dir"], env=repo["env"])

        assert candidates == [head]

    def should_offer_only_staged_files_to_gunstage(self, complete, repo):
        (repo["dir"] / "staged.txt").touch()
        (repo["dir"] / "untracked.txt").touch()
        repo["git"]("add", "staged.txt")

        candidates = complete("_gunstage", "gunstage", "", cwd=repo["dir"], env=repo["env"])

        assert candidates == ["staged.txt"]


class TestExternalLists:
    def should_offer_public_key_emails_to_gpgpub(self, complete, mock):
        mock("gpg", f"cat <<'EOF'\n{GPG_PUBLIC}EOF")

        candidates = complete("_gpgpub", "gpgpub", "")

        assert candidates == ["friend@example.com", "me@example.com"]

    def should_offer_secret_key_emails_as_the_signing_key_of_gpgsign(self, complete, mock):
        mock("gpg", f'[ "$1" = --list-secret-keys ] && cat <<\'EOF\'\n{GPG_SECRET}EOF')

        candidates = complete("_gpgsign", "gpgsign", "some text", "")

        assert candidates == ["me@example.com"]

    def should_leave_the_file_after_the_recipient_of_gpgencrypt_to_the_shell(self, complete, mock,
                                                                             tmp_path):
        mock("gpg", f"cat <<'EOF'\n{GPG_PUBLIC}EOF")
        (tmp_path / "secret.txt").touch()

        candidates = complete("_gpgencrypt", "gpgencrypt", "me@example.com", "sec")

        assert candidates == []

    def should_offer_running_process_names_to_killgrep(self, complete, mock):
        mock("ps", "printf '%s\\n' /usr/sbin/cron bash /Applications/Zoom.app/Contents/MacOS/zoom")

        candidates = complete("_process_names", "killgrep", "")

        assert candidates == ["bash", "cron", "zoom"]

    def should_offer_tmux_sessions_to_tma(self, complete, mock):
        mock("tmux", "printf '%s\\n' main work")

        candidates = complete("_tma", "tma", "")

        assert candidates == ["main", "work"]

    def should_match_a_name_typed_with_an_escaped_space(self, complete, mock):
        mock("tmux", "printf '%s\\n' main 'dj set'")

        candidates = complete("_tma", "tma", "dj\\ s")

        assert candidates == ["dj set"]

    def should_keep_the_spaces_in_time_machine_destinations(self, complete, mock):
        mock("timemachine", "[ \"$*\" = '--complete destinations' ] && printf '%s\\n' 'Backup Disk' 'Travel SSD'")

        candidates = complete("_timemachine", "timemachine", "prune", "")

        assert candidates == ["Backup Disk", "Travel SSD"]

    def should_offer_only_external_whole_disks_to_flash_disk_with_zeros(self, complete, mock):
        mock("diskutil", f"cat <<'EOF'\n{DISKUTIL_EXTERNAL}EOF")

        candidates = complete("_external_disks", "flash_disk_with_zeros", "")

        assert candidates == ["disk4"]

    def should_offer_external_partitions_to_mount_ext(self, complete, mock):
        mock("diskutil", f"cat <<'EOF'\n{DISKUTIL_EXTERNAL}EOF")

        candidates = complete("_external_partitions", "mount_ext", "")

        assert candidates == ["disk4s1", "disk4s2"]


class TestDockerScripts:
    @pytest.fixture(autouse=True)
    def containers(self, mock, home):
        mock("docker", "printf '%s\\n' web db")
        mock("docker-exec", 'echo "Usage: docker-exec [-s SERVER] [-c CONTAINER] [CONTAINER]"')
        ssh = home / ".ssh"
        (ssh / "config.d").mkdir(parents=True)
        (ssh / "config").write_text("Include ~/.ssh/config.d/*.conf\n"
                                    "Host dev devserver\n  HostName 10.0.0.1\nHost 10.0.0.*\n")
        (ssh / "config.d" / "extra.conf").write_text("Host nas\n")

    def should_offer_running_containers_as_the_first_word(self, complete):
        candidates = complete("_docker_script", "docker-exec", "")

        assert candidates == ["db", "web"]

    def should_offer_nothing_once_the_container_is_given(self, complete):
        candidates = complete("_docker_script", "docker-exec", "web", "")

        assert candidates == []

    def should_offer_a_container_for_every_word_of_docker_inspect(self, complete):
        candidates = complete("_docker_script", "docker-inspect", "web", "")

        assert candidates == ["db", "web"]

    def should_offer_the_ssh_hosts_after_the_server_flag(self, complete):
        candidates = complete("_docker_script", "docker-exec", "--server", "")

        assert candidates == ["dev", "devserver", "nas"]

    def should_offer_no_local_containers_for_a_remote_server(self, complete):
        candidates = complete("_docker_script", "docker-exec", "-s", "dev", "")

        assert candidates == []

    def should_offer_the_flags_the_help_lists(self, complete):
        candidates = complete("_docker_script", "docker-exec", "-")

        assert sorted(candidates) == ["-c", "-s"]


class TestFileserver:
    @pytest.fixture(autouse=True)
    def server(self, mock):
        mock("fileserver", f'exec "{BIN_DIR / "fileserver"}" "$@"')
        mock("kubectl", "printf '%s\\n' 'rick ross - hustlin1.wav' 'mix set.mp3'")

    def should_offer_remote_names_whole(self, complete):
        candidates = complete("_fileserver", "fileserver", "rm", "")

        assert candidates == ["rick ross - hustlin1.wav", "mix set.mp3"]

    def should_match_a_remote_name_typed_with_escaped_spaces(self, complete):
        candidates = complete("_fileserver", "fget", "rick\\ ross")

        assert candidates == ["rick ross - hustlin1.wav"]

    def should_leave_local_files_to_the_shell_on_upload(self, complete, tmp_path):
        (tmp_path / "notes.txt").touch()

        candidates = complete("_fileserver", "fileserver", "upload", "no")

        assert candidates == []


class TestKeyguard:
    @pytest.fixture(autouse=True)
    def subcommands(self, mock):
        mock("keyguard", "[ \"$*\" = '--complete commands' ] && printf '%s\\n' get set import")

    def should_offer_a_file_name_with_spaces_whole_to_import(self, complete, tmp_path):
        (tmp_path / "rick ross.env").touch()

        candidates = complete("_keyguard", "keyguard", "import", "ri")

        assert candidates == ["rick ross.env"]

    def should_offer_nothing_where_set_expects_a_secret(self, complete, tmp_path):
        (tmp_path / "notes.txt").touch()

        candidates = complete("_keyguard", "keyguard", "set", "API_KEY", "")

        assert candidates == []


class TestRegistrations:
    def should_register_the_help_completers_only_for_bin_scripts(self, tmp_path, commands):
        specs = run_bash("complete -p", tmp_path, commands).splitlines()

        registered = [spec.split()[-1] for spec in specs
                      if any(f"-F {completer} " in spec for completer in HELP_COMPLETERS)]

        assert registered
        assert [name for name in registered if not os.access(BIN_DIR / name, os.X_OK)] == []

    def should_leave_the_native_sudo_completion_alone(self, tmp_path, commands):
        specs = run_bash("complete -p", tmp_path, commands).splitlines()

        assert [spec for spec in specs if spec.endswith(" sudo")] == []

    @pytest.mark.parametrize("command", ["ags", "audiomerge", "audiotox", "backup_restore_util",
                                         "captions", "cl", "compressvideo", "dcp", "fileserver",
                                         "gpgencrypt"])
    def should_leave_file_arguments_to_the_shell(self, tmp_path, commands, command):
        spec = run_bash(f"complete -p {command}", tmp_path, commands)

        assert "-o default" in spec

    @pytest.mark.parametrize("command", ["json_format", "keyguard"])
    def should_not_fall_back_to_files(self, tmp_path, commands, command):
        spec = run_bash(f"complete -p {command}", tmp_path, commands)

        assert "-o default" not in spec

    @pytest.mark.parametrize("command", ["fileserver", "gunstage", "keyguard", "killgrep",
                                         "timemachine", "tma"])
    def should_let_bash_quote_names_with_spaces(self, tmp_path, commands, command):
        spec = run_bash(f"complete -p {command}", tmp_path, commands)

        assert "-o filenames" in spec
