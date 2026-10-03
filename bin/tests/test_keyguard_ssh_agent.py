import base64

import pytest

KEY_B64 = base64.b64encode(b"not a real key").decode()


@pytest.fixture
def agent_run(run_bash, tmp_path):
    calls = tmp_path / "ssh-add.calls"
    sourced = tmp_path / "envify.sourced"

    def _run(agent_has_key=False, cache_timeout=None, envify=None):
        mocks = {
            "ssh-add": (
                f'echo "$*" >> "{calls}"\n'
                f'if [ "$1" = "-l" ]; then exit {0 if agent_has_key else 1}; fi\n'
                "cat >/dev/null"
            ),
            "ssh-agent": "true",
            "envify": envify or f'echo yes >> "{sourced}"\nexport TEST_KEY_B64={KEY_B64}',
        }
        env = {"HOME": str(tmp_path)}
        if cache_timeout is not None:
            env["ENVIFY_CACHE_TIMEOUT"] = cache_timeout
        result = run_bash("keyguard-ssh-agent", ["TEST_KEY_B64", ""],
                          env_extra=env, mock_bins=mocks, isolate_path=True)
        logged = calls.read_text().splitlines() if calls.exists() else []
        return result, logged, sourced.exists()
    return _run


class TestKeyguardSshAgent:
    def test_should_load_the_key_for_envifys_default_cache_window(self, agent_run):
        result, logged, _ = agent_run()

        assert result.returncode == 0
        assert logged == ["-l", "-t 120 -"]
        assert "export SSH_AUTH_SOCK=" in result.stdout

    def test_should_follow_envify_cache_timeout_when_set(self, agent_run):
        _, logged, _ = agent_run(cache_timeout="45")

        assert logged[-1] == "-t 45 -"

    def test_should_reuse_a_key_the_agent_still_holds_without_asking(self, agent_run):
        result, logged, asked = agent_run(agent_has_key=True)

        assert (result.returncode, logged, asked) == (0, ["-l"], False)

    @pytest.mark.parametrize("value", ["2m", "0", "-5"])
    def test_should_refuse_a_cache_timeout_that_is_not_seconds_before_asking(self, agent_run, value):
        result, logged, asked = agent_run(cache_timeout=value)

        assert (result.returncode, logged, asked) == (2, [], False)

    def test_should_pass_on_what_envify_said_when_the_key_comes_back_empty(self, agent_run):
        approve = "Approve on your phone: https://unlock.example/approve?id=Ab12"

        result, _, _ = agent_run(envify=f'echo "{approve}" >&2')

        assert result.returncode == 1
        assert approve in result.stderr
