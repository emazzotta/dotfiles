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


class TestRemoveReport:
    @pytest.fixture
    def remove(self, run_cli):
        def _remove(report):
            mocks = {"kubectl": f'printf "%s\\n" "{report}"'}
            return run_cli("fileserver", ["remove", "clip.mp4"], mock_bins=mocks, isolate_path=True)
        return _remove

    def should_say_how_long_cloudflare_serves_a_removed_file(self, remove):
        result = remove("removed:clip.mp4")

        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines() == ["✓ removed clip.mp4", "  Cloudflare may serve cached copies for up to 1h"]

    def should_not_mention_the_cache_when_nothing_was_removed(self, remove):
        result = remove("missing:clip.mp4")

        assert result.stdout == ""
        assert "not on the server: clip.mp4" in result.stderr


class TestPodServiceAccount:
    """On the devbox, kubectl has no kubeconfig and the SSH session lacks the pod's API server variables."""

    @pytest.fixture
    def list_files(self, run_cli, tmp_path):
        def _list(token_exists=True, kubeconfig_exists=False):
            token = tmp_path / "token"
            if token_exists:
                token.write_text("t")
            kubeconfig = tmp_path / "personal-infra.yaml"
            if kubeconfig_exists:
                kubeconfig.write_text("apiVersion: v1\n")
            env = {"HOME": str(tmp_path), "KUBECONFIG": str(kubeconfig), "FILESERVER_SERVICE_ACCOUNT_TOKEN": str(token)}
            mocks = {"kubectl": 'echo "api=${KUBERNETES_SERVICE_HOST:-none}:${KUBERNETES_SERVICE_PORT:-none}"'}
            return run_cli("fileserver", ["list"], mock_bins=mocks, isolate_path=True, env_extra=env)
        return _list

    def should_point_kubectl_at_the_api_server_when_the_named_kubeconfig_is_missing(self, list_files):
        result = list_files()

        assert "api=kubernetes.default.svc:443" in result.stdout

    def should_leave_kubectl_alone_when_a_kubeconfig_exists(self, list_files):
        result = list_files(kubeconfig_exists=True)

        assert "api=none:none" in result.stdout

    def should_leave_kubectl_alone_outside_a_pod(self, list_files):
        result = list_files(token_exists=False)

        assert "api=none:none" in result.stdout
