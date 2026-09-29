import io
import os
import subprocess
from pathlib import Path

import pytest

MOUNTINFO = (
    "154 132 0:44 /someone/Desktop /workspace/code/Desktop rw,relatime"
    " - virtiofs virtiofs0 rw\n"
    "161 132 0:44 /someone/Projects/private/dotfiles /home/opencode/dotfiles rw"
    " - virtiofs virtiofs0 rw\n"
    "162 132 0:44 /someone/Projects/private/dotfiles/bin /home/opencode/dotfiles/bin rw"
    " - virtiofs virtiofs0 rw\n"
    "170 132 0:44 /someone/My\\040Files /workspace/code/my-files rw"
    " - virtiofs virtiofs0 rw\n"
    "180 132 0:45 /tmp/opencode /tmp rw - virtiofs virtiofs2 rw\n"
    "100 90 0:22 / /proc rw,nosuid - proc proc rw\n"
)


@pytest.fixture
def mac_trash(load_script):
    return load_script("mac-trash")


@pytest.fixture
def home(tmp_path):
    home = tmp_path / "home"
    for name in ("Desktop", "Downloads", "Projects", "Documents"):
        (home / name).mkdir(parents=True)
    return home


@pytest.fixture
def roots(home):
    return [(home / name).resolve() for name in ("Desktop", "Downloads", "Projects")]


class TestMacPathMapping:
    @pytest.fixture
    def mounts(self, mac_trash):
        return mac_trash.parse_users_mounts(MOUNTINFO)

    def should_map_through_the_longest_matching_mount(self, mac_trash, mounts):
        mac_path = mac_trash.to_mac_path(Path("/home/opencode/dotfiles/bin/envify"), mounts)

        assert mac_path == Path("/Users/someone/Projects/private/dotfiles/bin/envify")

    def should_decode_escaped_spaces_in_mount_roots(self, mac_trash, mounts):
        mac_path = mac_trash.to_mac_path(Path("/workspace/code/my-files/a.txt"), mounts)

        assert mac_path == Path("/Users/someone/My Files/a.txt")

    @pytest.mark.parametrize("path", ["/tmp/scratch.txt", "/proc/self/status", "/etc/passwd"])
    def should_not_map_paths_outside_the_users_share(self, mac_trash, mounts, path):
        assert mac_trash.to_mac_path(Path(path), mounts) is None


class TestRefusalReason:
    def should_accept_an_existing_file_inside_an_allowed_root(self, mac_trash, home, roots):
        target = home / "Desktop" / "notes.txt"
        target.write_text("x")

        assert mac_trash.refusal_reason(str(target), roots) is None

    def should_accept_a_dangling_symlink_so_the_link_itself_is_trashed(self, mac_trash, home, roots):
        link = home / "Downloads" / "stale-link"
        link.symlink_to(home / "Downloads" / "gone")

        assert mac_trash.refusal_reason(str(link), roots) is None

    @pytest.mark.parametrize("relative, reason", [
        ("Desktop", "outside ~/Desktop, ~/Downloads and ~/Projects"),
        ("Documents/secret.txt", "outside ~/Desktop, ~/Downloads and ~/Projects"),
        ("Desktop/../Documents/secret.txt", "outside ~/Desktop, ~/Downloads and ~/Projects"),
        ("Desktop/missing.txt", "does not exist"),
        ("Desktop/..", "not a file or folder name"),
    ])
    def should_refuse_paths_the_endpoint_must_not_touch(self, mac_trash, home, roots, relative, reason):
        (home / "Documents" / "secret.txt").write_text("x")

        assert mac_trash.refusal_reason(str(home / relative), roots) == reason

    def should_refuse_a_path_that_escapes_through_a_symlinked_folder(self, mac_trash, home, roots):
        (home / "Documents" / "secret.txt").write_text("x")
        (home / "Desktop" / "shortcut").symlink_to(home / "Documents")

        reason = mac_trash.refusal_reason(str(home / "Desktop" / "shortcut" / "secret.txt"), roots)

        assert reason == "outside ~/Desktop, ~/Downloads and ~/Projects"

    def should_refuse_a_relative_path(self, mac_trash, roots):
        assert mac_trash.refusal_reason("Desktop/notes.txt", roots) == "not an absolute path"


class TestTrashPaths:
    @pytest.fixture
    def trashed(self, mac_trash, monkeypatch, tmp_path):
        calls = []
        monkeypatch.setattr(mac_trash, "trash_with_finder", lambda path: calls.append(path))
        monkeypatch.setattr(mac_trash, "LOG_FILE", tmp_path / "logs" / "mac-trash.log")
        return calls

    def should_trash_allowed_paths_and_report_each_refusal(self, mac_trash, home, trashed, capsys):
        keep = home / "Documents" / "keep.txt"
        drop = home / "Desktop" / "drop.txt"
        for path in (keep, drop):
            path.write_text("x")

        exit_code = mac_trash.trash_paths([str(drop), str(keep)], home)

        assert (exit_code, trashed) == (1, [drop.resolve()])
        assert capsys.readouterr().out.splitlines() == [
            f"trashed {drop.resolve()}",
            f"refused {keep}: outside ~/Desktop, ~/Downloads and ~/Projects",
        ]

    def should_log_every_trashed_path(self, mac_trash, home, trashed):
        drop = home / "Projects" / "build.log"
        drop.write_text("x")

        mac_trash.trash_paths([str(drop)], home)

        assert mac_trash.LOG_FILE.read_text().rstrip().endswith(str(drop.resolve()))

    def should_refuse_a_request_with_too_many_paths(self, mac_trash, home, trashed):
        raw_paths = [str(home / "Desktop" / f"f{i}") for i in range(mac_trash.MAX_PATHS + 1)]

        assert (mac_trash.trash_paths(raw_paths, home), trashed) == (1, [])


class TestTrashWithFinder:
    def should_pass_the_path_as_an_argument_never_inside_the_script(self, mac_trash, monkeypatch):
        captured = {}

        def fake_run(command, **kwargs):
            captured["command"] = command
            return subprocess.CompletedProcess(command, 0, "", "")

        monkeypatch.setattr(mac_trash.subprocess, "run", fake_run)
        path = Path('/Users/me/Desktop/a" & do shell script "x')

        assert mac_trash.trash_with_finder(path) is None
        command = captured["command"]
        assert command[-1] == str(path)
        assert all(str(path) not in part for part in command[:-1])


class TestTrashViaBridge:
    @pytest.fixture
    def bridge_calls(self, mac_trash, monkeypatch, tmp_path):
        mountinfo = tmp_path / "mountinfo"
        mountinfo.write_text(MOUNTINFO)
        monkeypatch.setattr(mac_trash, "MOUNTINFO", mountinfo)
        calls = []

        def fake_run(command, **kwargs):
            calls.append((command, kwargs["input"]))
            return subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(mac_trash.subprocess, "run", fake_run)
        return calls

    def should_send_the_mac_paths_to_the_endpoint_one_per_line(self, mac_trash, bridge_calls):
        exit_code = mac_trash.trash_via_bridge(
            ["/workspace/code/Desktop/a.sh", "/workspace/code/Desktop/b.txt"])

        assert exit_code == 0
        assert bridge_calls == [(
            ["envify", "--bridge", "mac-trash", "--stdin"],
            "/Users/someone/Desktop/a.sh\n/Users/someone/Desktop/b.txt\n",
        )]

    @pytest.mark.parametrize("path", ["/tmp/scratch.txt", "/workspace/code/Desktop/a\nb"])
    def should_refuse_before_any_bridge_call(self, mac_trash, bridge_calls, path):
        assert (mac_trash.trash_via_bridge([path]), bridge_calls) == (2, [])


class TestMain:
    def should_read_paths_from_stdin_on_the_mac(self, mac_trash, monkeypatch, home):
        received = []
        monkeypatch.setattr(mac_trash, "IS_MAC", True)
        monkeypatch.setattr(mac_trash.sys, "stdin", io.StringIO("/a\n\n/b\n"))
        monkeypatch.setattr(mac_trash, "trash_paths", lambda paths, _home: received.append(paths) or 0)

        assert (mac_trash.main([]), received) == (0, [["/a", "/b"]])

    def should_print_usage_for_help(self, run_cli):
        result = run_cli("mac-trash", ["--help"])

        assert (result.returncode, result.stdout.splitlines()[0]) == (0, "Usage: mac-trash PATH...")

    @pytest.mark.skipif(os.uname().sysname == "Darwin", reason="container branch only")
    def should_exit_with_usage_when_given_no_paths_in_the_container(self, run_cli):
        result = run_cli("mac-trash")

        assert (result.returncode, "Usage: mac-trash" in result.stderr) == (2, True)
