import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def cl(load_script):
    return load_script("cl")


class TestFindGitCryptRoot:
    def test_returns_same_dir_when_git_crypt_present(self, cl, tmp_path):
        (tmp_path / ".git-crypt").mkdir()
        assert cl._find_git_crypt_root(tmp_path) == tmp_path

    def test_walks_up_to_find_root(self, cl, tmp_path):
        (tmp_path / ".git-crypt").mkdir()
        subdir = tmp_path / "src" / "main" / "deep"
        subdir.mkdir(parents=True)
        assert cl._find_git_crypt_root(subdir) == tmp_path

    def test_returns_none_when_absent(self, cl, tmp_path):
        subdir = tmp_path / "no-crypt"
        subdir.mkdir()
        assert cl._find_git_crypt_root(subdir) is None

    def test_finds_nearest_root(self, cl, tmp_path):
        (tmp_path / ".git-crypt").mkdir()
        inner = tmp_path / "inner"
        inner.mkdir()
        (inner / ".git-crypt").mkdir()
        subdir = inner / "child"
        subdir.mkdir()
        assert cl._find_git_crypt_root(subdir) == inner


class TestLockGitCrypt:
    @pytest.fixture(autouse=True)
    def _mock_which(self, cl):
        with patch.object(cl.shutil, "which", return_value="/usr/bin/git-crypt"):
            yield

    def test_skips_when_no_git_crypt_dir(self, cl, tmp_path):
        with patch.object(cl, "run") as mock_run:
            cl.lock_git_crypt(tmp_path)
        mock_run.assert_not_called()

    def test_locks_when_git_crypt_dir_exists(self, cl, tmp_path):
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git-crypt").mkdir()
        with patch.object(cl, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            cl.lock_git_crypt(tmp_path)
        lock_calls = [c for c in mock_run.call_args_list if c[0][0][:2] == ["git-crypt", "lock"]]
        assert len(lock_calls) == 1

    def test_already_locked(self, cl, tmp_path, capsys):
        (tmp_path / ".git-crypt").mkdir()
        with patch.object(cl, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 1, "stdout": "", "stderr": "already locked"})()
            cl.lock_git_crypt(tmp_path)
        assert "already locked" in capsys.readouterr().out

    def test_locks_at_repo_root_from_subdir(self, cl, tmp_path):
        (tmp_path / ".git-crypt").mkdir()
        subdir = tmp_path / "src" / "main"
        subdir.mkdir(parents=True)
        with patch.object(cl, "run") as mock_run:
            mock_run.return_value = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            cl.lock_git_crypt(subdir)
        lock_calls = [c for c in mock_run.call_args_list if c[0][0][:2] == ["git-crypt", "lock"]]
        assert len(lock_calls) == 1
        assert lock_calls[0][1]["cwd"] == tmp_path


class TestLockGitCryptMultiplePaths:
    @pytest.fixture(autouse=True)
    def _mock_which(self, cl):
        with patch.object(cl.shutil, "which", return_value="/usr/bin/git-crypt"):
            yield

    @pytest.fixture(autouse=True)
    def _no_leonardo_commons(self, cl, monkeypatch, tmp_path):
        monkeypatch.setattr(cl, "LEONARDO_COMMONS", tmp_path / "nonexistent")

    @pytest.fixture
    def mock_cl_run(self, cl, monkeypatch):
        captured = []
        def mock_run(cmd, **kwargs):
            captured.append((cmd, kwargs.get("cwd")))
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        monkeypatch.setattr(cl, "run", mock_run)
        return captured

    def test_no_paths_locks_pwd(self, cl, monkeypatch, mock_cl_run, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".git-crypt").mkdir()
        monkeypatch.setattr(sys, "argv", ["cl"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        lock_calls = [c for c in mock_cl_run if c[0][:2] == ["git-crypt", "lock"]]
        assert len(lock_calls) == 1
        assert lock_calls[0][1] == tmp_path

    def test_paths_lock_each_repo(self, cl, monkeypatch, mock_cl_run, tmp_path):
        dir1, dir2 = tmp_path / "dir1", tmp_path / "dir2"
        for d in (dir1, dir2):
            d.mkdir()
            (d / ".git-crypt").mkdir()
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(dir1), "-p", str(dir2)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        lock_calls = [c for c in mock_cl_run if c[0][:2] == ["git-crypt", "lock"]]
        locked_dirs = {c[1] for c in lock_calls}
        assert locked_dirs == {dir1, dir2}

    def test_paths_without_git_crypt_skipped(self, cl, monkeypatch, mock_cl_run, tmp_path):
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        (dir1 / ".git-crypt").mkdir()
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(dir1), "-p", str(dir2)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        lock_calls = [c for c in mock_cl_run if c[0][:2] == ["git-crypt", "lock"]]
        assert len(lock_calls) == 1
        assert lock_calls[0][1] == dir1

    def test_subdirs_of_same_repo_lock_once(self, cl, monkeypatch, mock_cl_run, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git-crypt").mkdir()
        sub1 = repo / "src" / "main"
        sub2 = repo / "src" / "test"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(sub1), "-p", str(sub2)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        lock_calls = [c for c in mock_cl_run if c[0][:2] == ["git-crypt", "lock"]]
        assert len(lock_calls) == 1
        assert lock_calls[0][1] == repo

    def test_subdirs_of_different_repos_lock_each(self, cl, monkeypatch, mock_cl_run, tmp_path):
        repo1 = tmp_path / "repo1"
        repo2 = tmp_path / "repo2"
        for r in (repo1, repo2):
            r.mkdir()
            (r / ".git-crypt").mkdir()
        sub1 = repo1 / "src"
        sub2 = repo2 / "src"
        sub1.mkdir()
        sub2.mkdir()
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(sub1), "-p", str(sub2)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        lock_calls = [c for c in mock_cl_run if c[0][:2] == ["git-crypt", "lock"]]
        locked_dirs = {c[1] for c in lock_calls}
        assert locked_dirs == {repo1, repo2}


class TestContainerPath:
    def test_path_within_pwd(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        subdir = pwd / "repo" / "src" / "main"
        subdir.mkdir(parents=True)
        assert cl._container_path(subdir, pwd) == "repo/src/main"

    def test_path_is_pwd_uses_name(self, cl, tmp_path):
        assert cl._container_path(tmp_path, tmp_path) == tmp_path.name

    def test_path_outside_pwd_falls_back_to_name(self, cl, tmp_path):
        outside = tmp_path / "other" / "project"
        outside.mkdir(parents=True)
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        assert cl._container_path(outside, pwd) == "project"


class TestParsePath:
    def test_success(self, cl, tmp_path):
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        assert cl.parse_path(str(test_dir)) == test_dir.resolve()

    def test_nonexistent_raises(self, cl, tmp_path):
        with pytest.raises(argparse.ArgumentTypeError):
            cl.parse_path(str(tmp_path / "nonexistent"))

    def test_file_raises(self, cl, tmp_path):
        test_file = tmp_path / "file.txt"
        test_file.write_text("content")
        with pytest.raises(argparse.ArgumentTypeError):
            cl.parse_path(str(test_file))

    def test_resolves_relative(self, cl, tmp_path, monkeypatch):
        test_dir = tmp_path / "testdir"
        test_dir.mkdir()
        monkeypatch.chdir(tmp_path)
        assert cl.parse_path("testdir") == test_dir


class TestValidateFileInPwd:
    @pytest.mark.parametrize("relative_path", ["file.txt", "subdir/file.txt", "."])
    def test_success(self, cl, relative_path, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        file_path = pwd / relative_path if relative_path != "." else pwd
        if relative_path != ".":
            file_path.parent.mkdir(parents=True, exist_ok=True)
        from pathlib import Path
        assert cl.validate_file_in_pwd(file_path, pwd, relative_path) == Path(relative_path)

    def test_outside_exits(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        with pytest.raises(SystemExit, match="1"):
            cl.validate_file_in_pwd(tmp_path / "outside.txt", pwd, "../outside.txt")


class TestBuildVolumeArgs:
    def test_no_args(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        assert cl.build_volume_args([], [], pwd) == ["-v", f"{pwd}:/workspace/code/{pwd.name}"]

    def test_with_files(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        for name in ("file1.txt", "file2.txt"):
            (pwd / name).write_text("content")
        result = cl.build_volume_args(["file1.txt", "file2.txt"], [], pwd)
        assert ["-v", f"{pwd / 'file1.txt'}:/workspace/code/file1.txt"] == result[:2]

    @pytest.mark.parametrize("file_path,expected_container_path", [
        ("subdir/file.txt", "subdir/file.txt"),
        ("./file.txt", "file.txt"),
        ("a/b/c/file.txt", "a/b/c/file.txt"),
    ])
    def test_nested_paths(self, cl, file_path, expected_container_path, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        full_path = pwd / expected_container_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text("content")
        result = cl.build_volume_args([file_path], [], pwd)
        assert result == ["-v", f"{pwd / expected_container_path}:/workspace/code/{expected_container_path}"]

    def test_absolute_path(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        test_file = pwd / "file.txt"
        test_file.write_text("content")
        result = cl.build_volume_args([str(test_file)], [], pwd)
        assert result == ["-v", f"{pwd / 'file.txt'}:/workspace/code/file.txt"]

    def test_nonexistent_file_exits(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        with pytest.raises(SystemExit, match="1"):
            cl.build_volume_args(["missing.txt"], [], pwd)

    def test_outside_pwd_exits(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        (tmp_path / "outside.txt").write_text("content")
        with pytest.raises(SystemExit, match="1"):
            cl.build_volume_args(["../outside.txt"], [], pwd)

    def test_single_path_within_pwd(self, cl, tmp_path):
        path_a = tmp_path / "project_a"
        path_a.mkdir()
        result = cl.build_volume_args([], [path_a], tmp_path)
        assert result == ["-v", f"{path_a}:/workspace/code/project_a"]

    def test_single_path_outside_pwd(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        path_a = tmp_path / "project_a"
        path_a.mkdir()
        result = cl.build_volume_args([], [path_a], pwd)
        assert result == ["-v", f"{path_a}:/workspace/code/{path_a.name}"]

    def test_multiple_paths(self, cl, tmp_path):
        path_a = tmp_path / "project_a"
        path_b = tmp_path / "project_b"
        path_a.mkdir()
        path_b.mkdir()
        result = cl.build_volume_args([], [path_a, path_b], tmp_path)
        assert len(result) == 4
        assert f"{path_a}:/workspace/code/project_a" in result[1]

    def test_mixed_files_and_paths(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        path_a = tmp_path / "project_a"
        path_a.mkdir()
        test_file = pwd / "file.txt"
        test_file.write_text("content")
        result = cl.build_volume_args(["file.txt"], [path_a], pwd)
        assert f"{path_a}:/workspace/code/{path_a.name}" in " ".join(result)
        assert f"{test_file}:/workspace/code/file.txt" in " ".join(result)

    def test_same_leaf_names_preserve_relative_structure(self, cl, tmp_path):
        r1 = tmp_path / "repo1" / "src" / "mac-installer"
        r2 = tmp_path / "repo2" / "src" / "mac-installer"
        r3 = tmp_path / "repo3" / "pkg" / "mac-installer"
        for d in (r1, r2, r3):
            d.mkdir(parents=True)
        result = cl.build_volume_args([], [r1, r2, r3], tmp_path)
        container_paths = [v.split(":")[-1] for v in result if v.startswith("/")]
        assert "/workspace/code/repo1/src/mac-installer" in container_paths
        assert "/workspace/code/repo2/src/mac-installer" in container_paths
        assert "/workspace/code/repo3/pkg/mac-installer" in container_paths


class TestMain:
    @pytest.fixture(autouse=True)
    def _no_leonardo_commons(self, cl, monkeypatch, tmp_path):
        monkeypatch.setattr(cl, "LEONARDO_COMMONS", tmp_path / "nonexistent")

    @pytest.fixture
    def mock_cl_run(self, cl, monkeypatch):
        captured = []
        def mock_run(cmd, **kwargs):
            captured.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        monkeypatch.setattr(cl, "run", mock_run)
        return captured

    def test_custom_path_only(self, cl, monkeypatch, mock_cl_run, tmp_path):
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(custom_dir)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        assert f"{custom_dir}:/workspace/code/{custom_dir.name}" in mock_cl_run[-1]

    def test_custom_path_and_files(self, cl, monkeypatch, mock_cl_run, tmp_path):
        custom_dir = tmp_path / "custom"
        custom_dir.mkdir()
        test_file = custom_dir / "file.txt"
        test_file.write_text("content")
        monkeypatch.chdir(custom_dir)
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(custom_dir), "-f", "file.txt"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert f"{custom_dir}:/workspace/code/{custom_dir.name}" in cmd
        assert f"{test_file}:/workspace/code/file.txt" in cmd

    def test_nonexistent_path_exits(self, cl, monkeypatch, tmp_path):
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(tmp_path / "nonexistent")])
        with pytest.raises(SystemExit, match="2"):
            cl.main()

    def test_missing_argument_exits(self, cl, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["cl", "-p"])
        with pytest.raises(SystemExit, match="2"):
            cl.main()

    def test_passthrough_args(self, cl, monkeypatch, mock_cl_run):
        monkeypatch.setattr(sys, "argv", ["cl", "--model", "opus"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert "--model" in cmd
        assert "opus" in cmd

    def test_default_includes_skip_permissions(self, cl, monkeypatch, mock_cl_run):
        monkeypatch.setattr(sys, "argv", ["cl"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert "--dangerously-skip-permissions" in cmd
        assert cmd.index("--dangerously-skip-permissions") > cmd.index("claude")

    def test_no_skip_flag(self, cl, monkeypatch, mock_cl_run):
        monkeypatch.setattr(sys, "argv", ["cl", "--no-skip"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        assert "--dangerously-skip-permissions" not in mock_cl_run[-1]

    def test_files_outside_cwd_exits(self, cl, monkeypatch, tmp_path):
        pwd = tmp_path / "pwd"
        pwd.mkdir()
        (tmp_path / "outside.txt").write_text("content")
        monkeypatch.chdir(pwd)
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(tmp_path / "custom"), "-f", "../outside.txt"])
        # -p with nonexistent dir fails at argparse
        with pytest.raises(SystemExit):
            cl.main()

    def test_multiple_paths(self, cl, monkeypatch, mock_cl_run, tmp_path):
        dir1, dir2 = tmp_path / "dir1", tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(dir1), "-p", str(dir2)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert f"{dir1}:/workspace/code/dir1" in cmd
        assert f"{dir2}:/workspace/code/dir2" in cmd
