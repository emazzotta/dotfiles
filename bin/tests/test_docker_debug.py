from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "docker-debug"

MOCK_DOCKER = r"""
if [ "$1" = "debug" ] && [ "$2" = "--help" ]; then
    exit 0
elif [ "$1" = "ps" ]; then
    printf 'myapp\tnginx:latest\tUp 5 min'
elif [ "$1" = "container" ]; then
    case "$3" in myapp|30cdd596c31a) echo "{}" ;; *) exit 1 ;; esac
elif [ "$1" = "debug" ]; then
    shift
    echo "debug: $*"
fi
"""


class TestHelpFlag:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def should_show_usage(self, create_mock_bin, run_script, flag):
        create_mock_bin("docker", "true")
        result = run_script(SCRIPT, [flag])
        assert result.returncode == 0
        assert "Usage:" in result.stdout


class TestDockerValidation:
    def should_reject_a_docker_without_the_debug_subcommand(self, create_mock_bin, run_script):
        create_mock_bin("docker", 'if [ "$1" = "debug" ]; then exit 1; fi')
        result = run_script(SCRIPT, ["-c", "myapp"])
        assert result.returncode == 1
        assert "'docker debug' not available" in result.stderr

    def should_reject_an_unknown_container(self, create_mock_bin, run_script):
        create_mock_bin("docker", MOCK_DOCKER)
        result = run_script(SCRIPT, ["-c", "ghost"])
        assert result.returncode == 1
        assert "container 'ghost' not found" in result.stderr


class TestContainerSelection:
    def should_debug_a_container_given_by_id(self, create_mock_bin, run_script):
        create_mock_bin("docker", MOCK_DOCKER)
        result = run_script(SCRIPT, ["30cdd596c31a"])
        assert result.returncode == 0
        assert "debug: 30cdd596c31a" in result.stdout

    def should_debug_the_container_given_after_c(self, create_mock_bin, run_script):
        create_mock_bin("docker", MOCK_DOCKER)
        result = run_script(SCRIPT, ["-c", "myapp"])
        assert result.returncode == 0
        assert "debug: myapp" in result.stdout

    def should_forward_leading_flags_and_auto_select_the_container(self, create_mock_bin, run_script):
        create_mock_bin("docker", MOCK_DOCKER)
        result = run_script(SCRIPT, ["--shell", "bash"])
        assert result.returncode == 0
        assert "debug: --shell bash myapp" in result.stdout
