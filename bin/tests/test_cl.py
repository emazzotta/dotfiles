from pathlib import Path
from types import ModuleType
import sys
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

cl_path = Path(__file__).parent.parent / "cl"
cl = ModuleType("cl")
with open(cl_path) as f:
    exec(f.read(), cl.__dict__)

normalize_file_path = cl.normalize_file_path
resolve_absolute_path = cl.resolve_absolute_path
validate_file_exists = cl.validate_file_exists
validate_file_in_pwd = cl.validate_file_in_pwd
build_volume_args_for_pwd = cl.build_volume_args_for_pwd
build_volume_args_for_files = cl.build_volume_args_for_files
build_volume_args = cl.build_volume_args


@pytest.mark.parametrize("input_path,expected", [
    ("file.txt", "./file.txt"),
    ("subdir/file.txt", "./subdir/file.txt"),
    ("./file.txt", "./file.txt"),
    ("/absolute/path/file.txt", "/absolute/path/file.txt"),
])
def test_normalize_file_path(input_path, expected):
    assert normalize_file_path(input_path) == expected


@pytest.mark.parametrize("file_path,expected_relative", [
    ("./file.txt", "file.txt"),
    ("./subdir/file.txt", "subdir/file.txt"),
    ("./subdir/../file.txt", "file.txt"),
])
def test_resolve_absolute_path(file_path, expected_relative, tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    if "subdir" in file_path:
        (pwd / "subdir").mkdir()

    result = resolve_absolute_path(file_path, pwd)
    assert result == pwd / expected_relative


def test_resolve_absolute_path_with_absolute_input(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    absolute_input = tmp_path / "other" / "file.txt"

    result = resolve_absolute_path(str(absolute_input), pwd)
    assert result == absolute_input


def test_validate_file_exists_success(tmp_path):
    test_file = tmp_path / "file.txt"
    test_file.write_text("content")
    validate_file_exists(test_file, "file.txt")


def test_validate_file_exists_with_directory(tmp_path):
    test_dir = tmp_path / "dir"
    test_dir.mkdir()
    validate_file_exists(test_dir, "dir")


def test_validate_file_exists_nonexistent_exits(tmp_path):
    test_file = tmp_path / "missing.txt"
    with pytest.raises(SystemExit) as exc_info:
        validate_file_exists(test_file, "missing.txt")
    assert exc_info.value.code == 1


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


@pytest.mark.parametrize("pwd_path", [
    "workspace",
    "/home/user/project",
])
def test_build_volume_args_for_pwd(pwd_path, tmp_path):
    if pwd_path.startswith("/"):
        pwd = Path(pwd_path)
    else:
        pwd = tmp_path / pwd_path
        pwd.mkdir()

    result = build_volume_args_for_pwd(pwd)
    assert result == ["-v", f"{pwd}:/workspace/code"]


def test_build_volume_args_for_files_single(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    test_file = pwd / "file.txt"
    test_file.write_text("content")

    result = build_volume_args_for_files(["file.txt"], pwd)
    assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]


def test_build_volume_args_for_files_multiple(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    file1 = pwd / "file1.txt"
    file2 = pwd / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")

    result = build_volume_args_for_files(["file1.txt", "file2.txt"], pwd)
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
def test_build_volume_args_for_files_paths(file_path, expected_container_path, tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()

    full_path = pwd / expected_container_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text("content")

    result = build_volume_args_for_files([file_path], pwd)
    assert result == ["-v", f"{pwd / expected_container_path}:/workspace/code/{expected_container_path}"]


def test_build_volume_args_for_files_absolute_path(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    test_file = pwd / "file.txt"
    test_file.write_text("content")

    result = build_volume_args_for_files([str(test_file)], pwd)
    assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]


def test_build_volume_args_for_files_nonexistent_exits(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        build_volume_args_for_files(["missing.txt"], pwd)
    assert exc_info.value.code == 1


def test_build_volume_args_for_files_outside_pwd_exits(tmp_path):
    pwd = tmp_path / "workspace"
    pwd.mkdir()
    outside_file = tmp_path / "outside.txt"
    outside_file.write_text("content")

    with pytest.raises(SystemExit) as exc_info:
        build_volume_args_for_files(["../outside.txt"], pwd)
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
