from pathlib import Path
from types import ModuleType
import argparse
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

cl_path = Path(__file__).parent.parent / "cl"
cl = ModuleType("cl")
with open(cl_path) as f:
    exec(f.read(), cl.__dict__)

parse_path = cl.parse_path
validate_file_in_pwd = cl.validate_file_in_pwd
build_volume_args = cl.build_volume_args


def test_parse_path_success(tmp_path):
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()

    result = parse_path(str(test_dir))
    assert result == test_dir.resolve()


def test_parse_path_nonexistent_raises(tmp_path):
    nonexistent = tmp_path / "nonexistent"

    with pytest.raises(argparse.ArgumentTypeError):
        parse_path(str(nonexistent))


def test_parse_path_file_raises(tmp_path):
    test_file = tmp_path / "file.txt"
    test_file.write_text("content")

    with pytest.raises(argparse.ArgumentTypeError):
        parse_path(str(test_file))


def test_parse_path_resolves_relative(tmp_path, monkeypatch):
    test_dir = tmp_path / "testdir"
    test_dir.mkdir()
    monkeypatch.chdir(tmp_path)

    result = parse_path("testdir")
    assert result == test_dir


@pytest.mark.parametrize("relative_path", [
    "file.txt",
    "subdir/file.txt",
    ".",
])
def test_validate_file_in_pwd_success(relative_path, tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    if relative_path != ".":
        file_path = pwd / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        file_path = pwd

    result = validate_file_in_pwd(file_path, pwd, relative_path)
    assert result == Path(relative_path)


def test_validate_file_in_pwd_outside_exits(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    outside_file = tmp_path / "outside.txt"

    with pytest.raises(SystemExit) as exc_info:
        validate_file_in_pwd(outside_file, pwd, "../outside.txt")
    assert exc_info.value.code == 1


def test_build_volume_args_no_files(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()

    result = build_volume_args([], pwd)
    assert result == ["-v", f"{pwd}:/workspace/code"]


def test_build_volume_args_with_files(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    file1 = pwd / "file1.txt"
    file2 = pwd / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")

    result = build_volume_args(["file1.txt", "file2.txt"], pwd)
    expected = [
        "-v", f"{pwd / 'file1.txt'}:/workspace/code/file1.txt",
        "-v", f"{pwd / 'file2.txt'}:/workspace/code/file2.txt",
    ]
    assert result == expected


@pytest.mark.parametrize("file_path,expected_container_path", [
    ("subdir/file.txt", "subdir/file.txt"),
    ("./file.txt", "file.txt"),
    ("a/b/c/file.txt", "a/b/c/file.txt"),
])
def test_build_volume_args_with_nested_paths(file_path, expected_container_path, tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()

    full_path = pwd / expected_container_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text("content")

    result = build_volume_args([file_path], pwd)
    assert result == ["-v", f"{pwd / expected_container_path}:/workspace/code/{expected_container_path}"]


def test_build_volume_args_absolute_path(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    test_file = pwd / "file.txt"
    test_file.write_text("content")

    result = build_volume_args([str(test_file)], pwd)
    assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]


def test_build_volume_args_nonexistent_file_exits(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        build_volume_args(["missing.txt"], pwd)
    assert exc_info.value.code == 1


def test_build_volume_args_outside_pwd_exits(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("content")

    with pytest.raises(SystemExit) as exc_info:
        build_volume_args(["../outside.txt"], pwd)
    assert exc_info.value.code == 1


def test_main_with_custom_path_only(tmp_path, monkeypatch):
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()

    monkeypatch.setattr(sys, "argv", ["cl", "-p", str(custom_dir)])

    captured_command = []
    def mock_run(cmd):
        captured_command.append(cmd)
        return type('obj', (), {'returncode': 0})()
    monkeypatch.setattr(cl, "run", mock_run)

    with pytest.raises(SystemExit) as exc_info:
        cl.main()
    assert exc_info.value.code == 0

    volume_arg = f"{custom_dir}:/workspace/code"
    assert volume_arg in captured_command[0]


def test_main_with_custom_path_and_files(tmp_path, monkeypatch):
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    test_file = custom_dir / "file.txt"
    test_file.write_text("content")

    monkeypatch.setattr(sys, "argv", ["cl", "-p", str(custom_dir), "-f", "file.txt"])

    captured_command = []
    def mock_run(cmd):
        captured_command.append(cmd)
        return type('obj', (), {'returncode': 0})()
    monkeypatch.setattr(cl, "run", mock_run)

    with pytest.raises(SystemExit) as exc_info:
        cl.main()
    assert exc_info.value.code == 0

    volume_arg = f"{test_file}:/workspace/code/file.txt"
    assert volume_arg in captured_command[0]


def test_main_custom_path_nonexistent_exits(tmp_path, monkeypatch):
    nonexistent = tmp_path / "nonexistent"

    monkeypatch.setattr(sys, "argv", ["cl", "-p", str(nonexistent)])

    with pytest.raises(SystemExit) as exc_info:
        cl.main()
    assert exc_info.value.code == 2


def test_main_custom_path_missing_argument_exits(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cl", "-p"])

    with pytest.raises(SystemExit) as exc_info:
        cl.main()
    assert exc_info.value.code == 2


def test_main_custom_path_with_files_relative_to_custom(tmp_path, monkeypatch):
    pwd = tmp_path / "pwd"
    pwd.mkdir()
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()
    subdir = custom_dir / "subdir"
    subdir.mkdir()
    test_file = subdir / "file.txt"
    test_file.write_text("content")

    monkeypatch.chdir(pwd)
    monkeypatch.setattr(sys, "argv", ["cl", "-p", str(custom_dir), "-f", "subdir/file.txt"])

    captured_command = []
    def mock_run(cmd):
        captured_command.append(cmd)
        return type('obj', (), {'returncode': 0})()
    monkeypatch.setattr(cl, "run", mock_run)

    with pytest.raises(SystemExit) as exc_info:
        cl.main()
    assert exc_info.value.code == 0

    volume_arg = f"{test_file}:/workspace/code/subdir/file.txt"
    assert volume_arg in captured_command[0]


def test_main_custom_path_with_files_outside_custom_exits(tmp_path, monkeypatch):
    pwd = tmp_path / "pwd"
    pwd.mkdir()
    pwd_file = pwd / "file.txt"
    pwd_file.write_text("content")
    custom_dir = tmp_path / "custom"
    custom_dir.mkdir()

    monkeypatch.chdir(pwd)
    monkeypatch.setattr(sys, "argv", ["cl", "-p", str(custom_dir), "-f", "file.txt"])

    with pytest.raises(SystemExit) as exc_info:
        cl.main()
    assert exc_info.value.code == 1


def test_main_passthrough_args_included_in_command(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["cl", "--resume"])

    captured_command = []
    def mock_run(cmd):
        captured_command.append(cmd)
        return type('obj', (), {'returncode': 0})()
    monkeypatch.setattr(cl, "run", mock_run)

    with pytest.raises(SystemExit) as exc_info:
        cl.main()
    assert exc_info.value.code == 0

    assert "--resume" in captured_command[0]
