import os
import time


class TestRmOldGitlabBuilds:
    def should_print_usage_for_help_and_delete_nothing(self, run_cli, tmp_path):
        old_build = tmp_path / "builds" / "old"
        old_build.mkdir(parents=True)
        two_hours_ago = time.time() - 7200
        os.utime(old_build, (two_hours_ago, two_hours_ago))

        result = run_cli("rm_old_gitlab_builds", ["--help"], env_extra={"HOME": str(tmp_path)})

        assert result.returncode == 0
        assert "--dry-run" in result.stdout
        assert old_build.exists()
