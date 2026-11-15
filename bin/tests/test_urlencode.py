import pytest


class TestUrlencode:
    @pytest.mark.parametrize("args,encoded", [
        (["hello world"], "hello%20world"),
        (["a/b?c=d&e"], "a%2Fb%3Fc%3Dd%26e"),
        (["it's"], "it%27s"),
        (["C:\\temp"], "C%3A%5Ctemp"),
        (['say "hi"'], "say%20%22hi%22"),
        (["two", "words"], "two%20words"),
        (["gr\u00fcezi"], "gr%C3%BCezi"),
    ])
    def test_should_percent_encode_the_arguments(self, run_cli, args, encoded):
        result = run_cli("urlencode", args)

        assert result.returncode == 0, result.stderr
        assert result.stdout == encoded + "\n"

    def test_should_print_usage_without_arguments(self, run_cli):
        result = run_cli("urlencode")

        assert result.returncode == 0
        assert "usage:" in result.stdout
