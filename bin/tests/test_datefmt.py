TIMESTAMP = "1700000000"
FORMATTED = "2023-11-14 22:13:20"
DATE_STAND_IN = """
if [ "$1" = -j ]; then exit "${BSD_DATE:-1}"; fi
echo "$*"
"""


class TestDatefmt:
    def should_format_a_timestamp_with_the_real_date(self, run_bash):
        result = run_bash("datefmt", [TIMESTAMP], env_extra={"TZ": "UTC"})

        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == FORMATTED

    def should_read_the_timestamp_with_dash_r_on_bsd_date(self, run_bash):
        result = run_bash("datefmt", [TIMESTAMP], env_extra={"BSD_DATE": "0"}, mock_bins={"date": DATE_STAND_IN})

        assert result.stdout.strip() == f"-r {TIMESTAMP} +%Y-%m-%d %H:%M:%S"

    def should_read_the_timestamp_as_an_epoch_on_gnu_date(self, run_bash):
        result = run_bash("datefmt", [TIMESTAMP], env_extra={"BSD_DATE": "1"}, mock_bins={"date": DATE_STAND_IN})

        assert result.stdout.strip() == f"-d @{TIMESTAMP} +%Y-%m-%d %H:%M:%S"

    def should_show_usage_without_a_timestamp(self, run_bash):
        result = run_bash("datefmt")

        assert "usage: datefmt" in result.stdout
