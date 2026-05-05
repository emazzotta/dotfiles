from pathlib import Path

import pytest


def _capture_expect(capture_file: str) -> str:
    return (
        f'printf "ENV_PASSWORD=%s\\n" "$PASSWORD" >> "{capture_file}"\n'
        f'printf "ENV_PROMPT=%s\\n" "$PROMPT" >> "{capture_file}"\n'
        f'printf "ENV_PROMPTS=%s\\n" "$PROMPTS" >> "{capture_file}"\n'
        f'printf "ENV_IS_KEKA=%s\\n" "$IS_KEKA" >> "{capture_file}"\n'
        f'printf "ARG:%s\\n" "$@" >> "{capture_file}"\n'
    )


def _mock_bins(capture_file: str, keka: bool = False) -> dict:
    fingerprint = "Modified by aone for Keka" if keka else "p7zip"
    return {
        "envify": "export PASSWORD_ZIPS=super_secret",
        "expect": _capture_expect(capture_file),
        "7z": f'echo "7-Zip version: {fingerprint}"',
    }


def _parse_capture(path: Path):
    lines = path.read_text().splitlines()
    def find(prefix):
        return next(
            (l.removeprefix(prefix) for l in lines if l.startswith(prefix)),
            None,
        )
    env = {
        "password": find("ENV_PASSWORD="),
        "prompt": find("ENV_PROMPT="),
        "prompts": find("ENV_PROMPTS="),
        "is_keka": find("ENV_IS_KEKA="),
    }
    args = [l.removeprefix("ARG:") for l in lines if l.startswith("ARG:")]
    return env, args


class TestPwcompress:
    def test_no_args_shows_usage(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        result = run_bash(
            "pwcompress",
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "usage" in combined.lower()

    def test_invalid_compression_level(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = run_bash(
            "pwcompress",
            args=["-c", "10", str(f)],
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        assert result.returncode != 0

    def test_password_in_env_not_args(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = run_bash(
            "pwcompress",
            args=[str(f)],
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        assert result.returncode == 0, result.stderr
        env, args = _parse_capture(tmp_path / "calls.txt")
        env_pw = env["password"]
        assert env_pw == "super_secret"
        assert not any("super_secret" in a for a in args)

    def test_p_flag_without_value(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        run_bash(
            "pwcompress",
            args=[str(f)],
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, args = _parse_capture(tmp_path / "calls.txt")
        assert "-p" in args
        assert not any(a.startswith("-p") and len(a) > 2 for a in args)

    def test_single_file_archive_name(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "myfile.txt"
        f.write_text("hello")
        run_bash(
            "pwcompress",
            args=[str(f)],
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, args = _parse_capture(tmp_path / "calls.txt")
        assert any("myfile.7z" in a for a in args)

    def test_compression_level_passed(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        run_bash(
            "pwcompress",
            args=["-c", "3", str(f)],
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, args = _parse_capture(tmp_path / "calls.txt")
        assert "-mx=3" in args

    def test_help_flag_exits_zero(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        envify_call_log = str(tmp_path / "envify_called.txt")
        result = run_bash(
            "pwcompress",
            args=["-h"],
            mock_bins={
                **_mock_bins(capture),
                "envify": f'echo called >> "{envify_call_log}"; export PASSWORD_ZIPS=super_secret',
            },
            env_extra={"DESKDIR": str(tmp_path)},
        )
        assert result.returncode == 0
        combined = result.stdout + result.stderr
        assert "usage" in combined.lower()
        assert not Path(envify_call_log).exists(), "envify must not be called for -h"

    def test_custom_password_overrides_env(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        result = run_bash(
            "pwcompress",
            args=["-p", "custom_pw", str(f)],
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "env_pw", "DESKDIR": str(tmp_path)},
        )
        assert result.returncode == 0, result.stderr
        env, args = _parse_capture(tmp_path / "calls.txt")
        env_pw = env["password"]
        assert env_pw == "custom_pw"
        assert not any("custom_pw" in a for a in args)


class TestPwuncompress:
    def _mock_bins(self, capture_file: str, keka: bool = False) -> dict:
        return _mock_bins(capture_file, keka=keka)

    def test_no_args_shows_usage(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        result = run_bash(
            "pwuncompress",
            mock_bins=self._mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        assert result.returncode != 0

    def test_nonexistent_archive(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        result = run_bash(
            "pwuncompress",
            args=["/nonexistent/archive.7z"],
            mock_bins=self._mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        assert result.returncode != 0

    def test_password_in_env_not_args(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        archive = tmp_path / "test.7z"
        archive.write_text("fake")
        result = run_bash(
            "pwuncompress",
            args=["-o", str(tmp_path), str(archive)],
            mock_bins=self._mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        assert result.returncode == 0, result.stderr
        env, args = _parse_capture(tmp_path / "calls.txt")
        env_pw = env["password"]
        assert env_pw == "super_secret"
        assert not any("super_secret" in a for a in args)

    def test_no_p_value_in_args(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        archive = tmp_path / "test.7z"
        archive.write_text("fake")
        run_bash(
            "pwuncompress",
            args=["-o", str(tmp_path), str(archive)],
            mock_bins=self._mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, args = _parse_capture(tmp_path / "calls.txt")
        assert not any(a.startswith("-p") and len(a) > 2 for a in args)

    def test_archive_path_passed_to_expect(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        archive = tmp_path / "myarchive.7z"
        archive.write_text("fake")
        run_bash(
            "pwuncompress",
            args=["-o", str(tmp_path), str(archive)],
            mock_bins=self._mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, args = _parse_capture(tmp_path / "calls.txt")
        assert any("myarchive.7z" in a for a in args)


class TestPromptDetection:
    def test_standard_7z_uses_enter_password_prompt(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        run_bash(
            "pwcompress",
            args=[str(f)],
            mock_bins=_mock_bins(capture, keka=False),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, _ = _parse_capture(tmp_path / "calls.txt")
        prompt = env["prompt"]
        assert prompt == "Enter password"

    def test_keka_7z_uses_keka_marker_prompt(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        run_bash(
            "pwcompress",
            args=[str(f)],
            mock_bins=_mock_bins(capture, keka=True),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, _ = _parse_capture(tmp_path / "calls.txt")
        prompt = env["prompt"]
        assert prompt == "___KEKA___PASSWORD___KEKA___"

    def test_keka_flag_propagated_to_expect(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        run_bash(
            "pwcompress",
            args=[str(f)],
            mock_bins=_mock_bins(capture, keka=True),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, _ = _parse_capture(tmp_path / "calls.txt")
        assert env["is_keka"] == "1"

    def test_standard_flag_propagated_to_expect(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        run_bash(
            "pwcompress",
            args=[str(f)],
            mock_bins=_mock_bins(capture, keka=False),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, _ = _parse_capture(tmp_path / "calls.txt")
        assert env["is_keka"] == "0"


class TestPromptCount:
    def test_compress_uses_two_prompts(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        f = tmp_path / "test.txt"
        f.write_text("hello")
        run_bash(
            "pwcompress",
            args=[str(f)],
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, _ = _parse_capture(tmp_path / "calls.txt")
        assert env["prompts"] == "2"

    def test_extract_uses_one_prompt(self, run_bash, tmp_path):
        capture = str(tmp_path / "calls.txt")
        archive = tmp_path / "test.7z"
        archive.write_text("fake")
        run_bash(
            "pwuncompress",
            args=["-o", str(tmp_path), str(archive)],
            mock_bins=_mock_bins(capture),
            env_extra={"PASSWORD_ZIPS": "super_secret", "DESKDIR": str(tmp_path)},
        )
        env, _ = _parse_capture(tmp_path / "calls.txt")
        assert env["prompts"] == "1"
