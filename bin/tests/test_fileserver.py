from pathlib import Path

import pytest

SITE = "https://emanuelemazzotta.com"
MOCK_BINS = {
    "kubectl": 'case "$*" in *containers*) echo "caddy rsync" ;; *) echo file-server-0 ;; esac',
    "rsync": "exit 0",
}

pytestmark = pytest.mark.skipif(
    Path("/.dockerenv").is_file(),
    reason="inside a container fileserver forwards uploads to the Mac over the keyguard bridge",
)


@pytest.fixture
def upload(run_cli, tmp_path):
    def _upload(name):
        shared = tmp_path / name
        shared.touch()
        return run_cli("fileserver", ["upload", str(shared)], mock_bins=MOCK_BINS, isolate_path=True)
    return _upload


class TestUploadReport:
    @pytest.mark.parametrize("name,page", [
        ("mix.flac", "listen"),
        ("voice.M4A", "listen"),
        ("clip.mp4", "watch"),
        ("phone.MOV", "watch"),
    ])
    def should_list_the_player_page_before_the_share_link(self, upload, name, page):
        result = upload(name)

        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[1:] == [f"  {SITE}/{page}/{name}", f"  {SITE}/share/{name}"]

    def should_print_only_the_share_link_for_formats_browsers_do_not_stream(self, upload):
        result = upload("notes.pdf")

        assert result.stdout.splitlines()[1:] == [f"  {SITE}/share/notes.pdf"]

    def should_url_encode_the_player_link(self, upload):
        result = upload("am i in.flac")

        assert f"  {SITE}/listen/am%20i%20in.flac" in result.stdout.splitlines()
