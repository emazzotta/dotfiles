import pytest

SOPS_ENCRYPTS = 'echo "ENC[$(cat "$2")]"'
SOPS_FAILS = "echo 'config file not found' >&2; exit 1"


@pytest.fixture
def seal(run_cli, tmp_path):
    source = tmp_path / "secret.yaml"
    source.write_text("token: abc\n")
    target = tmp_path / "apps" / "secret.enc.yaml"

    def _run(sops_body):
        return run_cli("sops-seal", [str(source), str(target)], mock_bins={"sops": sops_body})
    _run.target = target
    return _run


class TestSopsSeal:
    def test_should_write_the_encrypted_output_to_the_target(self, seal):
        result = seal(SOPS_ENCRYPTS)

        assert result.returncode == 0, result.stderr
        assert seal.target.read_text() == "ENC[token: abc]\n"
        assert f"sealed: {seal.target}" in result.stdout

    def test_should_leave_no_temp_files_beside_the_target(self, seal):
        seal(SOPS_ENCRYPTS)

        assert [path.name for path in seal.target.parent.iterdir()] == ["secret.enc.yaml"]

    def test_should_keep_an_existing_target_when_sops_fails(self, seal):
        seal.target.parent.mkdir()
        seal.target.write_text("previous ciphertext\n")

        result = seal(SOPS_FAILS)

        assert result.returncode != 0
        assert seal.target.read_text() == "previous ciphertext\n"
        assert "sealed:" not in result.stdout

    def test_should_not_create_the_target_when_sops_fails(self, seal):
        result = seal(SOPS_FAILS)

        assert result.returncode != 0
        assert [path.name for path in seal.target.parent.iterdir()] == []
