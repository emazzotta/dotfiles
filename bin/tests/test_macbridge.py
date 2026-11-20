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
FAKEOWNER_MOUNTINFO = MOUNTINFO.replace(
    " - virtiofs virtiofs0 rw", " - fakeowner /run/host_mark/Users rw,fakeowner"
).replace(" - virtiofs virtiofs2 rw", " - fakeowner /run/host_mark/private rw,fakeowner")


@pytest.fixture
def macbridge(load_module):
    return load_module("macbridge")


class TestMacPathMapping:
    @pytest.fixture(params=[MOUNTINFO, FAKEOWNER_MOUNTINFO], ids=["virtiofs", "fakeowner"])
    def mounts(self, macbridge, request):
        return macbridge.parse_users_mounts(request.param)

    @pytest.mark.use_case("UC-001", scenario="A4: No docker daemon: the Mac pushes")
    def should_map_through_the_longest_matching_mount(self, macbridge, mounts):
        mac_path = macbridge.to_mac_path(Path("/home/opencode/dotfiles/bin/envify"), mounts)

        assert mac_path == Path("/Users/someone/Projects/private/dotfiles/bin/envify")

    @pytest.mark.use_case("UC-001", scenario="A4: No docker daemon: the Mac pushes")
    def should_decode_escaped_spaces_in_mount_roots(self, macbridge, mounts):
        mac_path = macbridge.to_mac_path(Path("/workspace/code/my-files/a.txt"), mounts)

        assert mac_path == Path("/Users/someone/My Files/a.txt")

    @pytest.mark.parametrize("path", ["/tmp/scratch.txt", "/proc/self/status", "/etc/passwd"])
    @pytest.mark.use_case("UC-001", scenario="A4: No docker daemon: the Mac pushes")
    def should_not_map_paths_outside_the_users_share(self, macbridge, mounts, path):
        assert macbridge.to_mac_path(Path(path), mounts) is None


class TestReadUsersMounts:
    @pytest.mark.use_case("UC-001", scenario="A4: No docker daemon: the Mac pushes")
    def should_read_the_users_share_from_a_mountinfo_file(self, macbridge, tmp_path):
        mountinfo = tmp_path / "mountinfo"
        mountinfo.write_text(MOUNTINFO)

        mounts = macbridge.read_users_mounts(mountinfo)

        assert (Path("/workspace/code/Desktop"), Path("/Users/someone/Desktop")) in mounts

    @pytest.mark.use_case("UC-001", scenario="A4: No docker daemon: the Mac pushes")
    def should_find_no_mounts_outside_a_container(self, macbridge, tmp_path):
        assert macbridge.read_users_mounts(tmp_path / "no-mountinfo") == []
