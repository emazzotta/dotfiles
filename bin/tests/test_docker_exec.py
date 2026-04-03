from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "docker-exec"


class TestHelpFlag:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def test_shows_usage(self, create_mock_bin, run_script, flag):
        create_mock_bin("docker", "true")
        result = run_script(SCRIPT, [flag])
        assert result.returncode == 0
        assert "Usage:" in result.stdout


class TestDockerValidation:
    def test_missing_docker_exits_with_error(self, tmp_path):
        import os, subprocess
        bash_path = subprocess.check_output(["which", "bash"], text=True).strip()
        env = os.environ.copy()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        env["PATH"] = str(bin_dir)
        result = subprocess.run(
            [bash_path, str(SCRIPT), "-c", "nginx"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1
        assert "docker not found" in result.stderr


class TestContainerFlag:
    def test_missing_container_name(self, create_mock_bin, run_script):
        create_mock_bin("docker", "true")
        result = run_script(SCRIPT, ["-c"])
        assert result.returncode == 1
        assert "-c requires a container name" in result.stderr

    def test_nonexistent_container(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "inspect" ]; then
    echo "Error: no such container" >&2
    exit 1
fi
""")
        result = run_script(SCRIPT, ["-c", "ghost"])
        assert result.returncode == 1
        assert "container 'ghost' not found" in result.stderr


class TestShellDetection:
    def test_bash_available(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "inspect" ]; then
    echo "{}"
elif [ "$1" = "exec" ] && [ "$2" = "myapp" ] && [ "$3" = "test" ]; then
    exit 0
elif [ "$1" = "exec" ] && [ "$2" = "-it" ]; then
    echo "shell: $4"
fi
""")
        result = run_script(SCRIPT, ["-c", "myapp"])
        assert "shell: /bin/bash" in result.stdout

    def test_bash_not_available_falls_back_to_sh(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "inspect" ]; then
    echo "{}"
elif [ "$1" = "exec" ] && [ "$2" = "myapp" ] && [ "$3" = "test" ]; then
    exit 1
elif [ "$1" = "exec" ] && [ "$2" = "-it" ]; then
    echo "shell: $4"
fi
""")
        result = run_script(SCRIPT, ["-c", "myapp"])
        assert "shell: /bin/sh" in result.stdout


class TestCustomCommand:
    def test_explicit_command(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "inspect" ]; then
    echo "{}"
elif [ "$1" = "exec" ] && [ "$2" = "-it" ]; then
    shift 2
    container="$1"; shift
    echo "container=$container cmd=$*"
fi
""")
        result = run_script(SCRIPT, ["-c", "myapp", "ls", "-la"])
        assert "container=myapp cmd=ls -la" in result.stdout

    def test_command_without_container_flag(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "ps" ]; then
    printf 'myapp\tnginx:latest\tUp 5 min'
elif [ "$1" = "inspect" ]; then
    echo "{}"
elif [ "$1" = "exec" ] && [ "$2" = "-it" ]; then
    shift 2
    container="$1"; shift
    echo "container=$container cmd=$*"
fi
""")
        result = run_script(SCRIPT, ["python3", "-c", "print('hi')"])
        assert "container=myapp cmd=python3 -c print('hi')" in result.stdout


class TestAutoSelectSingleContainer:
    def test_single_running_container(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "ps" ]; then
    printf 'myapp\tnginx:latest\tUp 5 minutes'
elif [ "$1" = "inspect" ]; then
    echo "{}"
elif [ "$1" = "exec" ] && [ "$2" = "myapp" ] && [ "$3" = "test" ]; then
    exit 0
elif [ "$1" = "exec" ] && [ "$2" = "-it" ]; then
    echo "shell: $4"
fi
""")
        result = run_script(SCRIPT)
        assert result.returncode == 0
        assert "shell: /bin/bash" in result.stdout


class TestNoRunningContainers:
    def test_shows_error(self, create_mock_bin, run_script):
        create_mock_bin("docker", 'if [ "$1" = "ps" ]; then echo -n ""; fi')
        result = run_script(SCRIPT)
        assert result.returncode == 1
        assert "no running containers found" in result.stderr


class TestGumSelection:
    def test_multiple_containers_without_gum(self, tmp_path):
        import os, subprocess
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)

        docker_mock = bin_dir / "docker"
        docker_mock.write_text("""#!/bin/bash
if [ "$1" = "ps" ]; then
    printf 'nginx\\tnginx:latest\\tUp 5 min\\npostgres\\tpostgres:16\\tUp 3 min'
fi
""")
        docker_mock.chmod(0o755)

        bash_path = subprocess.check_output(["which", "bash"], text=True).strip()
        env = os.environ.copy()
        env["PATH"] = str(bin_dir) + ":/usr/bin:/bin"
        result = subprocess.run(
            [bash_path, str(SCRIPT)],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1
        assert "gum not found" in result.stderr
        assert "brew install gum" in result.stderr

    def test_gum_selection(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "ps" ]; then
    printf 'nginx\tnginx:latest\tUp 5 min\npostgres\tpostgres:16\tUp 3 min'
elif [ "$1" = "inspect" ]; then
    echo "{}"
elif [ "$1" = "exec" ] && [ "$2" = "nginx" ] && [ "$3" = "test" ]; then
    exit 0
elif [ "$1" = "exec" ] && [ "$2" = "-it" ]; then
    echo "exec: $3 $4"
fi
""")
        create_mock_bin("gum", """
while IFS= read -r line; do lines+=("$line"); done
echo "${lines[0]}"
""")
        result = run_script(SCRIPT)
        assert result.returncode == 0
        assert "exec: nginx /bin/bash" in result.stdout

    def test_gum_empty_selection_exits(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "ps" ]; then
    printf 'nginx\tnginx:latest\tUp 5 min\npostgres\tpostgres:16\tUp 3 min'
fi
""")
        create_mock_bin("gum", "echo -n ''")
        result = run_script(SCRIPT)
        assert result.returncode == 1
        assert "No container selected" in result.stderr
