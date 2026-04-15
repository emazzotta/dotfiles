from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "docker-inspect"


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
            [bash_path, str(SCRIPT), "nginx"],
            capture_output=True, text=True, env=env,
        )
        assert result.returncode == 1
        assert "docker not found" in result.stderr


class TestExplicitContainers:
    def test_single_named_container(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /nginx"
    echo "Image: nginx:latest"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        result = run_script(SCRIPT, ["nginx"])
        assert result.returncode == 0
        assert "Container: /nginx" in result.stdout

    def test_multiple_named_containers(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
name="${@: -1}"
if [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /$name"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        result = run_script(SCRIPT, ["nginx", "postgres"])
        assert result.returncode == 0
        assert "Container: /nginx" in result.stdout
        assert "Container: /postgres" in result.stdout

    def test_nonexistent_container_continues(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
name="${@: -1}"
if [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    if [ "$name" = "ghost" ]; then exit 1; fi
    echo "Container: /$name"
    echo "---"
elif [ "$1" = "inspect" ]; then
    if [ "$name" = "ghost" ]; then exit 1; fi
    echo "{}"
fi
""")
        result = run_script(SCRIPT, ["ghost", "nginx"])
        assert "container 'ghost' not found" in result.stderr
        assert "Container: /nginx" in result.stdout


class TestAutoSelectSingleContainer:
    def test_single_running_container(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "ps" ]; then
    printf 'myapp\tnginx:latest\tUp 5 minutes'
elif [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /myapp"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        result = run_script(SCRIPT)
        assert result.returncode == 0
        assert "Container: /myapp" in result.stdout


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
        assert "no interactive picker backend found" in result.stderr
        assert "brew install fzf" in result.stderr

    def test_gum_selection_single_choice(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "ps" ]; then
    printf 'nginx\tnginx:latest\tUp 5 min\npostgres\tpostgres:16\tUp 3 min'
elif [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /nginx"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        create_mock_bin("picker", 'cat >/dev/null; echo "nginx  nginx:latest  Up 5 min"')
        result = run_script(SCRIPT)
        assert result.returncode == 0
        assert "Container: /nginx" in result.stdout

    def test_gum_selection_multiple_choices(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
name="${@: -1}"
if [ "$1" = "ps" ]; then
    printf 'nginx\tnginx:latest\tUp 5 min\npostgres\tpostgres:16\tUp 3 min\nredis\tredis:7\tUp 1 min'
elif [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /$name"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        create_mock_bin("picker", 'cat >/dev/null; printf "nginx  nginx:latest  Up 5 min\\nredis  redis:7  Up 1 min\\n"')
        result = run_script(SCRIPT)
        assert result.returncode == 0
        assert "Container: /nginx" in result.stdout
        assert "Container: /redis" in result.stdout

    def test_gum_empty_selection_exits(self, create_mock_bin, run_script):
        create_mock_bin("docker", """
if [ "$1" = "ps" ]; then
    printf 'nginx\tnginx:latest\tUp 5 min\npostgres\tpostgres:16\tUp 3 min'
fi
""")
        create_mock_bin("picker", 'cat >/dev/null; echo -n ""')
        result = run_script(SCRIPT)
        assert result.returncode == 1
        assert "No containers selected" in result.stderr
