import argparse
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def cl(load_script):
    return load_script("cl")


class TestIsGitCryptRepo:
    def test_gpg_user_flow_detected_via_dot_git_crypt(self, cl, tmp_path):
        (tmp_path / ".git-crypt").mkdir()
        assert cl._is_git_crypt_repo(tmp_path) is True

    def test_single_user_flow_detected_via_dot_git_git_crypt(self, cl, tmp_path):
        (tmp_path / ".git" / "git-crypt").mkdir(parents=True)
        assert cl._is_git_crypt_repo(tmp_path) is True

    def test_plain_git_repo_not_detected(self, cl, tmp_path):
        (tmp_path / ".git").mkdir()
        assert cl._is_git_crypt_repo(tmp_path) is False

    def test_empty_dir_not_detected(self, cl, tmp_path):
        assert cl._is_git_crypt_repo(tmp_path) is False

    def test_dot_git_crypt_as_file_not_detected(self, cl, tmp_path):
        (tmp_path / ".git-crypt").write_text("not a directory")
        assert cl._is_git_crypt_repo(tmp_path) is False


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

    def test_detects_single_user_flow_via_dot_git_git_crypt(self, cl, tmp_path):
        (tmp_path / ".git" / "git-crypt").mkdir(parents=True)
        subdir = tmp_path / "src"
        subdir.mkdir()
        assert cl._find_git_crypt_root(subdir) == tmp_path


class TestFindGitCryptRootsDescending:
    def test_finds_gpg_flow_repo_under_root(self, cl, tmp_path):
        repo = tmp_path / "repo"
        (repo / ".git-crypt").mkdir(parents=True)
        (repo / ".git").mkdir()
        assert cl._find_git_crypt_roots_descending(tmp_path) == [repo]

    def test_finds_single_user_flow_repo_under_root(self, cl, tmp_path):
        repo = tmp_path / "repo"
        (repo / ".git" / "git-crypt").mkdir(parents=True)
        assert cl._find_git_crypt_roots_descending(tmp_path) == [repo]

    def test_ignores_plain_git_repo(self, cl, tmp_path):
        plain = tmp_path / "plain"
        (plain / ".git").mkdir(parents=True)
        assert cl._find_git_crypt_roots_descending(tmp_path) == []

    def test_skips_nonexistent_root(self, cl, tmp_path):
        assert cl._find_git_crypt_roots_descending(tmp_path / "nope") == []

    def test_respects_maxdepth(self, cl, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "d" / "repo"
        (deep / ".git-crypt").mkdir(parents=True)
        (deep / ".git").mkdir()
        assert cl._find_git_crypt_roots_descending(tmp_path, maxdepth=2) == []

    def test_skips_hidden_and_build_dirs(self, cl, tmp_path):
        for name in (".hidden", "node_modules", "target", "build", "dist", "vendor"):
            repo = tmp_path / name / "repo"
            (repo / ".git-crypt").mkdir(parents=True)
            (repo / ".git").mkdir()
        assert cl._find_git_crypt_roots_descending(tmp_path) == []


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


class TestLockGitCryptRoots:
    @pytest.fixture(autouse=True)
    def _mock_which(self, cl):
        with patch.object(cl.shutil, "which", return_value="/usr/bin/git-crypt"):
            yield

    @pytest.fixture
    def mock_cl_run(self, cl, monkeypatch):
        captured = []
        def mock_run(cmd, **kwargs):
            captured.append((cmd, kwargs.get("cwd")))
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        monkeypatch.setattr(cl, "run", mock_run)
        return captured

    def test_empty_targets_locks_nothing(self, cl, mock_cl_run):
        assert cl._lock_git_crypt_roots([]) == set()
        assert mock_cl_run == []

    def test_walk_up_discovers_ancestor_root(self, cl, tmp_path, mock_cl_run):
        repo = tmp_path / "repo"
        (repo / ".git-crypt").mkdir(parents=True)
        sub = repo / "src" / "main"
        sub.mkdir(parents=True)
        assert cl._lock_git_crypt_roots([sub]) == {repo}

    def test_descend_discovers_nested_roots(self, cl, tmp_path, mock_cl_run):
        r1 = tmp_path / "a" / "repo"
        r2 = tmp_path / "b" / "repo"
        for r in (r1, r2):
            (r / ".git-crypt").mkdir(parents=True)
            (r / ".git").mkdir()
        assert cl._lock_git_crypt_roots([tmp_path]) == {r1, r2}

    def test_deduplicates_across_targets(self, cl, tmp_path, mock_cl_run):
        repo = tmp_path / "repo"
        (repo / ".git-crypt").mkdir(parents=True)
        sub1 = repo / "src"
        sub2 = repo / "tests"
        sub1.mkdir()
        sub2.mkdir()
        assert cl._lock_git_crypt_roots([sub1, sub2]) == {repo}
        lock_calls = [c for c in mock_cl_run if c[0][:2] == ["git-crypt", "lock"]]
        assert len(lock_calls) == 1

    def test_single_user_flow_is_locked(self, cl, tmp_path, mock_cl_run):
        repo = tmp_path / "repo"
        (repo / ".git" / "git-crypt").mkdir(parents=True)
        assert cl._lock_git_crypt_roots([repo]) == {repo}
        lock_calls = [c for c in mock_cl_run if c[0][:2] == ["git-crypt", "lock"]]
        assert [c[1] for c in lock_calls] == [repo]


class TestRemoveSubmounts:
    def test_removes_file_within_directory(self, cl, tmp_path):
        directory = tmp_path / "leonardo-commons"
        volume_args = ["-v", f"{directory}/pom.xml:/workspace/code/leonardo-commons/pom.xml"]
        result = cl._remove_submounts(volume_args, directory)
        assert result == []

    def test_removes_nested_file_within_directory(self, cl, tmp_path):
        directory = tmp_path / "leonardo-commons"
        volume_args = [
            "-v", f"{directory}/java-commons/pom.xml:/workspace/code/leonardo-commons/java-commons/pom.xml",
        ]
        result = cl._remove_submounts(volume_args, directory)
        assert result == []

    def test_removes_multiple_subpath_mounts(self, cl, tmp_path):
        directory = tmp_path / "leonardo-commons"
        volume_args = [
            "-v", f"{directory}/pom.xml:/workspace/code/leonardo-commons/pom.xml",
            "-v", f"{directory}/.gitlab-ci.yml:/workspace/code/leonardo-commons/.gitlab-ci.yml",
            "-v", f"{directory}/java-commons/pom.xml:/workspace/code/leonardo-commons/java-commons/pom.xml",
        ]
        result = cl._remove_submounts(volume_args, directory)
        assert result == []

    def test_preserves_mounts_outside_directory(self, cl, tmp_path):
        directory = tmp_path / "leonardo-commons"
        other = tmp_path / "capitalisatorx"
        volume_args = [
            "-v", f"{other}/pom.xml:/workspace/code/capitalisatorx/pom.xml",
            "-v", f"{directory}/pom.xml:/workspace/code/leonardo-commons/pom.xml",
        ]
        result = cl._remove_submounts(volume_args, directory)
        assert result == ["-v", f"{other}/pom.xml:/workspace/code/capitalisatorx/pom.xml"]

    def test_preserves_sibling_directory_with_same_prefix(self, cl, tmp_path):
        directory = tmp_path / "leonardo-commons"
        sibling = tmp_path / "leonardo-commons-fork"
        volume_args = ["-v", f"{sibling}/pom.xml:/workspace/code/leonardo-commons-fork/pom.xml"]
        result = cl._remove_submounts(volume_args, directory)
        assert result == volume_args

    def test_empty_volume_args(self, cl, tmp_path):
        directory = tmp_path / "leonardo-commons"
        assert cl._remove_submounts([], directory) == []


class TestIsPathMounted:
    def test_true_when_path_is_mount_source(self, cl, tmp_path):
        host = tmp_path / "leonardo-commons"
        volume_args = ["-v", f"{host}:/workspace/code/leonardo-commons"]
        assert cl._is_path_mounted(volume_args, host) is True

    def test_false_on_sibling_name_prefix(self, cl, tmp_path):
        host = tmp_path / "leonardo-commons"
        sibling = tmp_path / "leonardo-commons-fork"
        volume_args = ["-v", f"{sibling}:/workspace/code/leonardo-commons-fork"]
        assert cl._is_path_mounted(volume_args, host) is False

    def test_false_when_path_absent(self, cl, tmp_path):
        host = tmp_path / "leonardo-commons"
        assert cl._is_path_mounted([], host) is False

    def test_ignores_container_target_matches(self, cl, tmp_path):
        host = tmp_path / "leonardo-commons"
        other = tmp_path / "other"
        volume_args = ["-v", f"{other}:/workspace/code/leonardo-commons"]
        assert cl._is_path_mounted(volume_args, host) is False


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
        assert result[:2] == ["-v", f"{pwd}:/workspace/code/{pwd.name}"]
        mounts = " ".join(result)
        assert f"{pwd / 'file1.txt'}:/workspace/code/file1.txt" in mounts
        assert f"{pwd / 'file2.txt'}:/workspace/code/file2.txt" in mounts

    def should_include_full_pwd_mount_when_files_only(self, cl, tmp_path):
        pwd = tmp_path / "myproject"
        pwd.mkdir()
        (pwd / "pom.xml").write_text("<project/>")
        result = cl.build_volume_args(["pom.xml"], [], pwd)
        assert result[:2] == ["-v", f"{pwd}:/workspace/code/myproject"]

    def should_not_include_full_pwd_mount_when_paths_and_files_combined(self, cl, tmp_path):
        pwd = tmp_path / "myproject"
        pwd.mkdir()
        (pwd / "pom.xml").write_text("<project/>")
        extra = tmp_path / "capitalisator-core"
        extra.mkdir()
        result = cl.build_volume_args(["pom.xml"], [extra], pwd)
        assert f"{pwd}:/workspace/code/myproject" not in " ".join(result)
        assert f"{extra}:/workspace/code/capitalisator-core" in " ".join(result)

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
        assert result[:2] == ["-v", f"{pwd}:/workspace/code/{pwd.name}"]
        assert f"{pwd / expected_container_path}:/workspace/code/{expected_container_path}" in " ".join(result)

    def test_absolute_path(self, cl, tmp_path):
        pwd = tmp_path / "workspace"
        pwd.mkdir()
        test_file = pwd / "file.txt"
        test_file.write_text("content")
        result = cl.build_volume_args([str(test_file)], [], pwd)
        assert result[:2] == ["-v", f"{pwd}:/workspace/code/{pwd.name}"]
        assert f"{pwd / 'file.txt'}:/workspace/code/file.txt" in " ".join(result)

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

    def should_mount_full_pwd_when_files_only(self, cl, monkeypatch, mock_cl_run, tmp_path):
        pwd = tmp_path / "myproject"
        pwd.mkdir()
        (pwd / "pom.xml").write_text("<project/>")
        monkeypatch.chdir(pwd)
        monkeypatch.setattr(sys, "argv", ["cl", "-f", "pom.xml"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert f"{pwd}:/workspace/code/myproject" in cmd

    def should_not_mount_full_pwd_when_files_and_explicit_paths_combined(self, cl, monkeypatch, mock_cl_run, tmp_path):
        pwd = tmp_path / "myproject"
        pwd.mkdir()
        (pwd / "pom.xml").write_text("<project/>")
        monkeypatch.chdir(pwd)
        cap_core = tmp_path / "capitalisator-core"
        cap_core.mkdir()
        monkeypatch.setattr(sys, "argv", ["cl", "-f", "pom.xml", "-p", str(cap_core)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert f"{pwd}:/workspace/code/myproject" not in cmd
        assert f"{cap_core}:/workspace/code/capitalisator-core" in cmd


class TestLeonardoCommonsAutoMount:
    @pytest.fixture(autouse=True)
    def _mock_which(self, cl):
        with patch.object(cl.shutil, "which", return_value="/usr/bin/git-crypt"):
            yield

    @pytest.fixture
    def mock_cl_run(self, cl, monkeypatch):
        captured = []
        def mock_run(cmd, **kwargs):
            captured.append(cmd)
            return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        monkeypatch.setattr(cl, "run", mock_run)
        return captured

    def test_sibling_name_does_not_suppress_auto_mount(self, cl, monkeypatch, mock_cl_run, tmp_path):
        leonardo_commons = tmp_path / "leonardo-commons"
        leonardo_commons.mkdir()
        sibling = tmp_path / "leonardo-commons-fork"
        sibling.mkdir()
        monkeypatch.setattr(cl, "LEONARDO_COMMONS", leonardo_commons)
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(sibling)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert f"{leonardo_commons}:/workspace/code/leonardo-commons" in cmd

    def should_remain_fully_mounted_when_files_only(self, cl, monkeypatch, mock_cl_run, tmp_path):
        leonardo_commons = tmp_path / "leonardo-commons"
        leonardo_commons.mkdir()
        monkeypatch.setattr(cl, "LEONARDO_COMMONS", leonardo_commons)
        pwd = tmp_path / "myproject"
        pwd.mkdir()
        (pwd / "pom.xml").write_text("<project/>")
        monkeypatch.chdir(pwd)
        monkeypatch.setattr(sys, "argv", ["cl", "-f", "pom.xml"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert f"{leonardo_commons}:/workspace/code/leonardo-commons" in cmd

    def should_remain_fully_mounted_when_files_and_paths_combined(self, cl, monkeypatch, mock_cl_run, tmp_path):
        leonardo_commons = tmp_path / "leonardo-commons"
        leonardo_commons.mkdir()
        monkeypatch.setattr(cl, "LEONARDO_COMMONS", leonardo_commons)
        pwd = tmp_path / "myproject"
        pwd.mkdir()
        (pwd / "pom.xml").write_text("<project/>")
        monkeypatch.chdir(pwd)
        cap_core = tmp_path / "capitalisator-core"
        cap_core.mkdir()
        monkeypatch.setattr(sys, "argv", ["cl", "-f", "pom.xml", "-p", str(cap_core)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert f"{leonardo_commons}:/workspace/code/leonardo-commons" in cmd

    def should_mount_commons_even_when_already_locked_by_parent_scan(self, cl, monkeypatch, mock_cl_run, tmp_path):
        # Reproduces the bug where running from a parent of leonardo-commons causes
        # _lock_git_crypt_roots to add it to locked_roots, which then skipped the mount entirely.
        parent = tmp_path / "leo-productions"
        parent.mkdir()
        leonardo_commons = parent / "leonardo-commons"
        leonardo_commons.mkdir()
        (leonardo_commons / ".git-crypt").mkdir()
        monkeypatch.setattr(cl, "LEONARDO_COMMONS", leonardo_commons)
        monkeypatch.chdir(parent)
        monkeypatch.setattr(sys, "argv", ["cl"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert f"{leonardo_commons}:/workspace/code/leonardo-commons" in cmd

    def should_strip_commons_file_submounts_before_directory_mount(self, cl, monkeypatch, mock_cl_run, tmp_path):
        leonardo_commons = tmp_path / "leonardo-commons"
        leonardo_commons.mkdir()
        (leonardo_commons / "pom.xml").write_text("<project/>")
        (leonardo_commons / ".gitlab-ci.yml").write_text("stages: []")
        monkeypatch.setattr(cl, "LEONARDO_COMMONS", leonardo_commons)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(sys, "argv", ["cl", "-f", "leonardo-commons/pom.xml", "-f", "leonardo-commons/.gitlab-ci.yml"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        full_mount = f"{leonardo_commons}:/workspace/code/leonardo-commons"
        assert full_mount in cmd
        individual_pom = f"{leonardo_commons}/pom.xml:"
        assert not any(arg.startswith(individual_pom) for arg in cmd)

    def test_explicit_leonardo_commons_path_is_not_double_mounted(self, cl, monkeypatch, mock_cl_run, tmp_path):
        leonardo_commons = tmp_path / "leonardo-commons"
        leonardo_commons.mkdir()
        monkeypatch.setattr(cl, "LEONARDO_COMMONS", leonardo_commons)
        monkeypatch.setattr(sys, "argv", ["cl", "-p", str(leonardo_commons)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        mount_spec = f"{leonardo_commons}:/workspace/code/leonardo-commons"
        assert cmd.count(mount_spec) == 1


class TestParseExclude:
    def test_should_return_resolved_path_for_absolute_input(self, cl, tmp_path):
        result = cl.parse_exclude(str(tmp_path / "secrets"))
        assert isinstance(result, Path)
        assert result == tmp_path / "secrets"

    def test_should_expand_tilde_to_absolute_path(self, cl):
        result = cl.parse_exclude("~/some/path")
        assert isinstance(result, Path)
        assert result == Path.home() / "some" / "path"

    def test_should_return_string_for_name_only_pattern(self, cl):
        result = cl.parse_exclude("secrets")
        assert result == "secrets"
        assert isinstance(result, str)

    def test_should_return_string_for_glob_pattern(self, cl):
        result = cl.parse_exclude("*.env")
        assert result == "*.env"
        assert isinstance(result, str)

    def test_should_return_string_for_relative_path(self, cl):
        result = cl.parse_exclude("src/generated")
        assert result == "src/generated"
        assert isinstance(result, str)


class TestEntryIsIgnored:
    def test_should_match_absolute_path_ignore_exact(self, cl, tmp_path):
        target = tmp_path / "secrets"
        assert cl._entry_is_ignored("secrets", target, [target]) is True

    def test_should_match_absolute_path_ignore_child(self, cl, tmp_path):
        parent = tmp_path / "secrets"
        child = parent / "key.pem"
        assert cl._entry_is_ignored("secrets/key.pem", child, [parent]) is True

    def test_should_not_match_sibling_of_absolute_ignore(self, cl, tmp_path):
        secrets = tmp_path / "secrets"
        other = tmp_path / "src"
        assert cl._entry_is_ignored("src", other, [secrets]) is False

    def test_should_match_name_only_pattern_anywhere(self, cl, tmp_path):
        entry = tmp_path / "src" / "node_modules"
        entry.mkdir(parents=True)
        assert cl._entry_is_ignored("src/node_modules", entry, ["node_modules"]) is True

    def test_should_match_name_only_glob(self, cl, tmp_path):
        entry = tmp_path / "app.pyc"
        entry.write_text("")
        assert cl._entry_is_ignored("app.pyc", entry, ["*.pyc"]) is True

    def test_should_not_match_name_only_wrong_name(self, cl, tmp_path):
        entry = tmp_path / "src"
        entry.mkdir()
        assert cl._entry_is_ignored("src", entry, ["node_modules"]) is False

    def test_should_match_relative_path_pattern_exact(self, cl, tmp_path):
        entry = tmp_path / "src" / "generated"
        entry.mkdir(parents=True)
        assert cl._entry_is_ignored("src/generated", entry, ["src/generated"]) is True

    def test_should_match_relative_path_pattern_child(self, cl, tmp_path):
        entry = tmp_path / "src" / "generated" / "Foo.java"
        entry.parent.mkdir(parents=True)
        entry.write_text("")
        assert cl._entry_is_ignored("src/generated/Foo.java", entry, ["src/generated"]) is True

    def test_should_match_relative_path_glob(self, cl, tmp_path):
        entry = tmp_path / "src" / "test" / "Foo.java"
        entry.parent.mkdir(parents=True)
        entry.write_text("")
        assert cl._entry_is_ignored("src/test/Foo.java", entry, ["src/test/*.java"]) is True

    def test_should_return_false_with_empty_ignores(self, cl, tmp_path):
        entry = tmp_path / "anything"
        assert cl._entry_is_ignored("anything", entry, []) is False


class TestAnyIgnoreTargetsInside:
    def test_should_detect_absolute_path_inside_dir(self, cl, tmp_path):
        parent = tmp_path / "myproject"
        parent.mkdir()
        child_ignore = parent / "secrets"
        assert cl._any_ignore_targets_inside("myproject", parent, [child_ignore]) is True

    def test_should_not_match_absolute_ignore_outside(self, cl, tmp_path):
        parent = tmp_path / "myproject"
        parent.mkdir()
        other = tmp_path / "other" / "secrets"
        assert cl._any_ignore_targets_inside("myproject", parent, [other]) is False

    def test_should_detect_relative_path_with_slash_inside(self, cl, tmp_path):
        parent = tmp_path / "src"
        parent.mkdir()
        assert cl._any_ignore_targets_inside("src", parent, ["src/generated"]) is True

    def test_should_not_match_relative_path_of_different_subtree(self, cl, tmp_path):
        parent = tmp_path / "src"
        parent.mkdir()
        assert cl._any_ignore_targets_inside("src", parent, ["tests/fixtures"]) is False

    def test_should_not_match_name_only_patterns(self, cl, tmp_path):
        parent = tmp_path / "src"
        parent.mkdir()
        assert cl._any_ignore_targets_inside("src", parent, ["node_modules"]) is False


class TestHasNameOnlyIgnores:
    def test_should_return_true_for_name_only_string(self, cl):
        assert cl._has_name_only_ignores(["secrets"]) is True

    def test_should_return_true_for_glob_without_slash(self, cl):
        assert cl._has_name_only_ignores(["*.pyc"]) is True

    def test_should_return_false_for_path_with_slash(self, cl):
        assert cl._has_name_only_ignores(["src/generated"]) is False

    def test_should_return_false_for_absolute_path(self, cl, tmp_path):
        assert cl._has_name_only_ignores([tmp_path / "secrets"]) is False

    def test_should_return_false_for_empty_list(self, cl):
        assert cl._has_name_only_ignores([]) is False

    def test_should_return_true_when_mixed_and_any_name_only(self, cl, tmp_path):
        assert cl._has_name_only_ignores(["src/ok", "secrets"]) is True


class TestBuildIgnoreAwareVolumeArgs:
    def test_should_mount_all_entries_with_no_ignores(self, cl, tmp_path):
        (tmp_path / "src").mkdir()
        (tmp_path / "README.md").write_text("")
        result = cl.build_ignore_aware_volume_args(tmp_path, "/workspace/code/proj", [])
        mounts = {v.split(":")[1] for v in result if v.startswith("/")}
        assert "/workspace/code/proj/src" in mounts
        assert "/workspace/code/proj/README.md" in mounts

    def test_should_exclude_absolute_path_ignore(self, cl, tmp_path):
        secrets = tmp_path / "secrets"
        secrets.mkdir()
        (tmp_path / "src").mkdir()
        result = cl.build_ignore_aware_volume_args(tmp_path, "/workspace/code/proj", [secrets])
        mounts = {v.split(":")[1] for v in result if v.startswith("/")}
        assert "/workspace/code/proj/secrets" not in mounts
        assert "/workspace/code/proj/src" in mounts

    def test_should_exclude_name_only_pattern_at_any_depth(self, cl, tmp_path):
        (tmp_path / "src" / "node_modules").mkdir(parents=True)
        (tmp_path / "src" / "index.js").write_text("")
        result = cl.build_ignore_aware_volume_args(tmp_path, "/workspace/code/proj", ["node_modules"])
        container_paths = [v.split(":")[1] for v in result if v.startswith("/")]
        assert not any("node_modules" in p for p in container_paths)
        assert any("src/index.js" in p for p in container_paths)

    def test_should_exclude_nested_absolute_path(self, cl, tmp_path):
        secrets = tmp_path / "config" / "secrets"
        secrets.mkdir(parents=True)
        (tmp_path / "config" / "app.conf").write_text("")
        result = cl.build_ignore_aware_volume_args(tmp_path, "/workspace/code/proj", [secrets])
        container_paths = [v.split(":")[1] for v in result if v.startswith("/")]
        assert not any("secrets" in p for p in container_paths)
        assert any("app.conf" in p for p in container_paths)

    def test_should_mount_dir_whole_when_no_ignores_inside(self, cl, tmp_path):
        src = tmp_path / "src"
        src.mkdir()
        (src / "main.py").write_text("")
        secrets = tmp_path / "secrets"
        secrets.mkdir()
        result = cl.build_ignore_aware_volume_args(tmp_path, "/workspace/code/proj", [secrets])
        mounts = {v.split(":")[1] for v in result if v.startswith("/")}
        assert "/workspace/code/proj/src" in mounts
        assert "/workspace/code/proj/src/main.py" not in mounts

    def test_should_exclude_relative_path_pattern(self, cl, tmp_path):
        generated = tmp_path / "src" / "generated"
        generated.mkdir(parents=True)
        (tmp_path / "src" / "main.py").write_text("")
        result = cl.build_ignore_aware_volume_args(tmp_path, "/workspace/code/proj", ["src/generated"])
        container_paths = [v.split(":")[1] for v in result if v.startswith("/")]
        assert not any("generated" in p for p in container_paths)
        assert any("main.py" in p for p in container_paths)

    def test_should_exclude_glob_pattern(self, cl, tmp_path):
        (tmp_path / "secret.env").write_text("")
        (tmp_path / "app.py").write_text("")
        result = cl.build_ignore_aware_volume_args(tmp_path, "/workspace/code/proj", ["*.env"])
        container_paths = [v.split(":")[1] for v in result if v.startswith("/")]
        assert not any(".env" in p for p in container_paths)
        assert any("app.py" in p for p in container_paths)


class TestBuildVolumeArgsWithIgnores:
    def test_should_switch_to_ignore_walk_when_ignores_present(self, cl, tmp_path):
        pwd = tmp_path / "project"
        pwd.mkdir()
        secrets = pwd / "secrets"
        secrets.mkdir()
        (pwd / "src").mkdir()
        result = cl.build_volume_args([], [], pwd, ignores=[secrets])
        mounts = {v.split(":")[1] for v in result if v.startswith("/")}
        assert not any("secrets" in p for p in mounts)
        assert any("src" in p for p in mounts)

    def test_should_mount_whole_dir_with_no_ignores(self, cl, tmp_path):
        pwd = tmp_path / "project"
        pwd.mkdir()
        result = cl.build_volume_args([], [], pwd, ignores=[])
        assert result == ["-v", f"{pwd}:/workspace/code/project"]

    def test_should_skip_ignored_path_from_paths_list(self, cl, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        secrets = tmp_path / "secrets"
        secrets.mkdir()
        result = cl.build_volume_args([], [project, secrets], tmp_path, ignores=[secrets])
        mounts = {v.split(":")[1] for v in result if v.startswith("/")}
        assert any("project" in p for p in mounts)
        assert not any("secrets" in p for p in mounts)

    def test_should_filter_ignored_files_from_file_list(self, cl, tmp_path):
        pwd = tmp_path / "project"
        pwd.mkdir()
        (pwd / "main.py").write_text("")
        (pwd / "secret.env").write_text("")
        result = cl.build_volume_args(["main.py", "secret.env"], [], pwd, ignores=["*.env"])
        mounts = {v for v in result if v.startswith("/")}
        assert any("main.py" in m for m in mounts)
        assert not any(".env" in m for m in mounts)

    def test_should_use_ignore_walk_for_path_with_nested_absolute_ignore(self, cl, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        secrets = project / "secrets"
        secrets.mkdir()
        (project / "src").mkdir()
        result = cl.build_volume_args([], [project], tmp_path, ignores=[secrets])
        container_paths = [v.split(":")[1] for v in result if v.startswith("/")]
        assert not any("secrets" in p for p in container_paths)


class TestMainWithIgnores:
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

    def test_should_exclude_path_via_x_flag(self, cl, monkeypatch, mock_cl_run, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        secrets = project / "secrets"
        secrets.mkdir()
        (project / "src").mkdir()
        monkeypatch.chdir(project)
        monkeypatch.setattr(sys, "argv", ["cl", "-x", str(secrets)])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert not any("secrets" in arg for arg in cmd)
        assert any("src" in arg for arg in cmd)

    def test_should_exclude_file_pattern_via_x_flag(self, cl, monkeypatch, mock_cl_run, tmp_path):
        pwd = tmp_path / "project"
        pwd.mkdir()
        (pwd / "main.py").write_text("")
        (pwd / "secret.env").write_text("")
        monkeypatch.chdir(pwd)
        monkeypatch.setattr(sys, "argv", ["cl", "-f", "main.py", "-f", "secret.env", "-x", "*.env"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert any("main.py" in arg for arg in cmd)
        assert not any(".env" in arg for arg in cmd)

    def test_should_support_multiple_x_flags(self, cl, monkeypatch, mock_cl_run, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        src = project / "src"
        src.mkdir()
        (src / "main.py").write_text("")
        (project / "secrets").mkdir()
        (project / "build").mkdir()
        monkeypatch.chdir(project)
        monkeypatch.setattr(sys, "argv", ["cl", "-x", str(project / "secrets"), "-x", "build"])
        with pytest.raises(SystemExit, match="0"):
            cl.main()
        cmd = mock_cl_run[-1]
        assert not any("secrets" in arg for arg in cmd)
        assert not any("build" in arg for arg in cmd)
        assert any("src" in arg for arg in cmd)
