DIG_STAND_IN = """
case "$*" in
    "example.test TXT +short") echo '"google-site-verification=abc"' ;;
    "example.test MX +short") echo '10 mail.example.test.' ;;
    *) echo "answer for $*" ;;
esac
"""


class TestDnscheckemail:
    def should_run_every_check_for_a_domain_without_an_spf_record(self, run_bash):
        result = run_bash("dnscheckemail", ["example.test"], mock_bins={"dig": DIG_STAND_IN})

        assert result.returncode == 0, result.stderr
        assert "answer for _autodiscover._tcp.example.test SRV +short" in result.stdout

    def should_show_the_spf_record_when_there_is_one(self, run_bash):
        dig = DIG_STAND_IN.replace('"google-site-verification=abc"', '"v=spf1 -all"')

        result = run_bash("dnscheckemail", ["example.test"], mock_bins={"dig": dig})

        assert '"v=spf1 -all"' in result.stdout
        assert result.returncode == 0, result.stderr

    def should_show_usage_without_a_domain(self, run_bash):
        result = run_bash("dnscheckemail")

        assert result.returncode == 1
        assert "Usage:" in result.stdout
