import os
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "docker-inspect"


def create_mock_bin(tmp_path, name, body):
    mock = tmp_path / "bin" / name
    mock.parent.mkdir(exist_ok=True)
    mock.write_text(f"#!/bin/bash\n{body}\n")
    mock.chmod(mock.stat().st_mode | stat.S_IEXEC)
    return mock


def run_script(tmp_path, args=None, env_extra=None):
    env = os.environ.copy()
    env["PATH"] = str(tmp_path / "bin") + ":" + env["PATH"]
    if env_extra:
        env.update(env_extra)
    result = subprocess.run(
        ["bash", str(SCRIPT)] + (args or []),
        capture_output=True,
        text=True,
        env=env,
    )
    return result


class TestHelpFlag:
    def test_help_shows_usage(self, tmp_path):
        create_mock_bin(tmp_path, "docker", "true")
        result = run_script(tmp_path, ["-h"])
        assert result.returncode == 0
        assert "Usage:" in result.stdout

    def test_long_help_shows_usage(self, tmp_path):
        create_mock_bin(tmp_path, "docker", "true")
        result = run_script(tmp_path, ["--help"])
        assert result.returncode == 0
        assert "Usage:" in result.stdout


class TestDockerValidation:
    def test_missing_docker_exits_with_error(self, tmp_path):
        bash_path = subprocess.check_output(["which", "bash"], text=True).strip()
        env = os.environ.copy()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir(exist_ok=True)
        env["PATH"] = str(bin_dir)
        result = subprocess.run(
            [bash_path, str(SCRIPT), "nginx"],
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 1
        assert "docker not found" in result.stderr


class TestExplicitContainers:
    def test_inspect_single_named_container(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
if [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /nginx"
    echo "Image: nginx:latest"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        result = run_script(tmp_path, ["nginx"])
        assert result.returncode == 0
        assert "Container: /nginx" in result.stdout

    def test_inspect_multiple_named_containers(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
name="${@: -1}"
if [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /$name"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        result = run_script(tmp_path, ["nginx", "postgres"])
        assert result.returncode == 0
        assert "Container: /nginx" in result.stdout
        assert "Container: /postgres" in result.stdout

    def test_inspect_nonexistent_container_continues(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
name="${@: -1}"
if [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    if [ "$name" = "ghost" ]; then
        exit 1
    fi
    echo "Container: /$name"
    echo "---"
elif [ "$1" = "inspect" ]; then
    if [ "$name" = "ghost" ]; then
        exit 1
    fi
    echo "{}"
fi
""")
        result = run_script(tmp_path, ["ghost", "nginx"])
        assert "container 'ghost' not found" in result.stderr
        assert "Container: /nginx" in result.stdout


class TestAutoSelectSingleContainer:
    def test_single_running_container_auto_selected(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
if [ "$1" = "ps" ]; then
    printf 'myapp\tnginx:latest\tUp 5 minutes'
elif [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /myapp"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        result = run_script(tmp_path)
        assert result.returncode == 0
        assert "Container: /myapp" in result.stdout


class TestNoRunningContainers:
    def test_no_containers_shows_error(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
if [ "$1" = "ps" ]; then
    echo -n ""
fi
""")
        result = run_script(tmp_path)
        assert result.returncode == 1
        assert "no running containers found" in result.stderr


class TestGumSelection:
    def test_multiple_containers_without_gum_shows_error(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
if [ "$1" = "ps" ]; then
    printf 'nginx\tnginx:latest\tUp 5 min\npostgres\tpostgres:16\tUp 3 min'
fi
""")
        result = run_script(tmp_path)
        assert result.returncode == 1
        assert "gum not found" in result.stderr
        assert "brew install gum" in result.stderr

    def test_gum_selection_single_choice(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
if [ "$1" = "ps" ]; then
    printf 'nginx\tnginx:latest\tUp 5 min\npostgres\tpostgres:16\tUp 3 min'
elif [ "$1" = "inspect" ] && [[ "$2" == --format=* ]]; then
    echo "Container: /nginx"
    echo "---"
elif [ "$1" = "inspect" ]; then
    echo "{}"
fi
""")
        create_mock_bin(tmp_path, "gum", """
while IFS= read -r line; do
    lines+=("$line")
done
echo "${lines[0]}"
""")
        result = run_script(tmp_path)
        assert result.returncode == 0
        assert "Container: /nginx" in result.stdout

    def test_gum_selection_multiple_choices(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
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
        create_mock_bin(tmp_path, "gum", """
while IFS= read -r line; do
    lines+=("$line")
done
echo "${lines[0]}"
echo "${lines[2]}"
""")
        result = run_script(tmp_path)
        assert result.returncode == 0
        assert "Container: /nginx" in result.stdout
        assert "Container: /redis" in result.stdout

    def test_gum_empty_selection_exits(self, tmp_path):
        create_mock_bin(tmp_path, "docker", """
if [ "$1" = "ps" ]; then
    printf 'nginx\tnginx:latest\tUp 5 min\npostgres\tpostgres:16\tUp 3 min'
fi
""")
        create_mock_bin(tmp_path, "gum", "echo -n ''")
        result = run_script(tmp_path)
        assert result.returncode == 1
        assert "No containers selected" in result.stderr
