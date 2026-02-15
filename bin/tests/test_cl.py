from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

cl_path = Path(__file__).parent.parent / "cl"
cl = SourceFileLoader("cl_module", str(cl_path)).load_module()

normalize_file_path = cl.normalize_file_path
resolve_absolute_path = cl.resolve_absolute_path
validate_file_exists = cl.validate_file_exists
validate_file_in_pwd = cl.validate_file_in_pwd
build_volume_args_for_pwd = cl.build_volume_args_for_pwd
build_volume_args_for_files = cl.build_volume_args_for_files
build_volume_args = cl.build_volume_args


class TestNormalizeFilePath:
    def test_normalize_file_path_with_relative_path_without_prefix(self):
        result = normalize_file_path("file.txt")
        assert result == "./file.txt"

    def test_normalize_file_path_with_subdirectory_without_prefix(self):
        result = normalize_file_path("subdir/file.txt")
        assert result == "./subdir/file.txt"

    def test_normalize_file_path_with_dot_slash_prefix(self):
        result = normalize_file_path("./file.txt")
        assert result == "./file.txt"

    def test_normalize_file_path_with_absolute_path(self):
        result = normalize_file_path("/absolute/path/file.txt")
        assert result == "/absolute/path/file.txt"


class TestResolveAbsolutePath:
    def test_resolve_absolute_path_with_relative_path(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()

        result = resolve_absolute_path("./file.txt", pwd)

        assert result == pwd / "file.txt"

    def test_resolve_absolute_path_with_subdirectory(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()

        result = resolve_absolute_path("./subdir/file.txt", pwd)

        assert result == pwd / "subdir" / "file.txt"

    def test_resolve_absolute_path_with_absolute_input(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        absolute_input = tmp_path / "other" / "file.txt"

        result = resolve_absolute_path(str(absolute_input), pwd)

        assert result == absolute_input

    def test_resolve_absolute_path_resolves_symlinks_and_dots(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        (pwd / "subdir").mkdir()

        result = resolve_absolute_path("./subdir/../file.txt", pwd)

        assert result == pwd / "file.txt"


class TestValidateFileExists:
    def test_validate_file_exists_with_existing_file(self, tmp_path):
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")

        validate_file_exists(test_file, "file.txt")

    def test_validate_file_exists_with_nonexistent_file_exits(self, tmp_path):
        test_file = tmp_path / "missing.txt"

        with pytest.raises(SystemExit) as exc_info:
            validate_file_exists(test_file, "missing.txt")

        assert exc_info.value.code == 1

    def test_validate_file_exists_with_directory(self, tmp_path):
        test_dir = tmp_path / "dir"
        test_dir.mkdir()

        validate_file_exists(test_dir, "dir")


class TestValidateFileInPwd:
    def test_validate_file_in_pwd_with_file_in_pwd(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        file_path = pwd / "file.txt"

        result = validate_file_in_pwd(file_path, pwd, "file.txt")

        assert result == Path("file.txt")

    def test_validate_file_in_pwd_with_file_in_subdirectory(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        file_path = pwd / "subdir" / "file.txt"

        result = validate_file_in_pwd(file_path, pwd, "subdir/file.txt")

        assert result == Path("subdir/file.txt")

    def test_validate_file_in_pwd_with_file_outside_pwd_exits(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        outside_file = tmp_path / "outside.txt"

        with pytest.raises(SystemExit) as exc_info:
            validate_file_in_pwd(outside_file, pwd, "../outside.txt")

        assert exc_info.value.code == 1

    def test_validate_file_in_pwd_with_pwd_itself(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()

        result = validate_file_in_pwd(pwd, pwd, ".")

        assert result == Path(".")


class TestBuildVolumeArgsForPwd:
    def test_build_volume_args_for_pwd_returns_correct_format(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()

        result = build_volume_args_for_pwd(pwd)

        assert result == ["-v", f"{pwd}:/workspace/code"]

    def test_build_volume_args_for_pwd_with_absolute_path(self):
        pwd = Path("/home/user/project")

        result = build_volume_args_for_pwd(pwd)

        assert result == ["-v", "/home/user/project:/workspace/code"]


class TestBuildVolumeArgsForFiles:
    def test_build_volume_args_for_files_with_single_file(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        test_file = pwd / "file.txt"
        test_file.write_text("content")

        result = build_volume_args_for_files(["file.txt"], pwd)

        assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]

    def test_build_volume_args_for_files_with_multiple_files(self, tmp_path):
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

    def test_build_volume_args_for_files_with_subdirectory_file(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        subdir = pwd / "subdir"
        subdir.mkdir()
        test_file = subdir / "file.txt"
        test_file.write_text("content")

        result = build_volume_args_for_files(["subdir/file.txt"], pwd)

        assert result == ["-v", f"{pwd / 'subdir' / 'file.txt'}:/workspace/code/subdir/file.txt"]

    def test_build_volume_args_for_files_with_dot_slash_prefix(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        test_file = pwd / "file.txt"
        test_file.write_text("content")

        result = build_volume_args_for_files(["./file.txt"], pwd)

        assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]

    def test_build_volume_args_for_files_with_absolute_path_in_pwd(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        test_file = pwd / "file.txt"
        test_file.write_text("content")

        result = build_volume_args_for_files([str(test_file)], pwd)

        assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]

    def test_build_volume_args_for_files_with_nonexistent_file_exits(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()

        with pytest.raises(SystemExit) as exc_info:
            build_volume_args_for_files(["missing.txt"], pwd)

        assert exc_info.value.code == 1

    def test_build_volume_args_for_files_with_file_outside_pwd_exits(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        outside_file = tmp_path / "outside.txt"
        outside_file.write_text("content")

        with pytest.raises(SystemExit) as exc_info:
            build_volume_args_for_files(["../outside.txt"], pwd)

        assert exc_info.value.code == 1

    def test_build_volume_args_for_files_with_nested_subdirectories(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        nested_dir = pwd / "a" / "b" / "c"
        nested_dir.mkdir(parents=True)
        test_file = nested_dir / "file.txt"
        test_file.write_text("content")

        result = build_volume_args_for_files(["a/b/c/file.txt"], pwd)

        expected_path = "a/b/c/file.txt"
        assert result == ["-v", f"{pwd / expected_path}:/workspace/code/{expected_path}"]

    def test_build_volume_args_for_files_normalizes_paths_without_prefix(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        test_file = pwd / "file.txt"
        test_file.write_text("content")

        result = build_volume_args_for_files(["file.txt"], pwd)

        assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]


class TestBuildVolumeArgs:
    def test_build_volume_args_with_no_files_mounts_pwd(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()

        result = build_volume_args([], pwd)

        assert result == ["-v", f"{pwd}:/workspace/code"]

    def test_build_volume_args_with_empty_list_mounts_pwd(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()

        result = build_volume_args([], pwd)

        assert result == ["-v", f"{pwd}:/workspace/code"]

    def test_build_volume_args_with_single_file(self, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        test_file = pwd / "file.txt"
        test_file.write_text("content")

        result = build_volume_args(["file.txt"], pwd)

        assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]

    def test_build_volume_args_with_multiple_files(self, tmp_path):
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
