import pytest


class TestUrldecode:
    @pytest.mark.parametrize("args,decoded", [
        (["hello%20world"], "hello world"),
        (["a%2Fb%3Fc%3Dd%26e"], "a/b?c=d&e"),
        (["it%27s"], "it's"),
        (["C%3A%5Ctemp"], "C:\\temp"),
        (["it's%20ok"], "it's ok"),
        (["two%20", "words"], "two  words"),
        (["gr%C3%BCezi"], "gr\u00fcezi"),
    ])
    def test_should_decode_percent_encoded_arguments(self, run_cli, args, decoded):
        result = run_cli("urldecode", args)

        assert result.returncode == 0, result.stderr
        assert result.stdout == decoded + "\n"

    def test_should_print_usage_without_arguments(self, run_cli):
        result = run_cli("urldecode")

        assert result.returncode == 0
        assert "usage:" in result.stdout
