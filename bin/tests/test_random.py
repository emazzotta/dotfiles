import pytest

SAMPLES = 60
ONE_BYTE_CEILING = 255


def draw(run_cli, *args):
    result = run_cli("random", list(args))
    assert result.returncode == 0, result.stderr
    return int(result.stdout)


class TestRandom:
    def test_should_stay_below_the_default_maximum_of_100(self, run_cli):
        values = [draw(run_cli) for _ in range(SAMPLES)]

        assert all(0 <= value < 100 for value in values)

    def test_should_reach_values_beyond_one_byte_for_a_large_maximum(self, run_cli):
        values = [draw(run_cli, "1000") for _ in range(SAMPLES)]

        assert all(0 <= value < 1000 for value in values)
        assert max(values) > ONE_BYTE_CEILING

    def test_should_return_zero_for_a_maximum_of_one(self, run_cli):
        assert draw(run_cli, "1") == 0

    @pytest.mark.parametrize("maximum", ["0", "abc", "-5", "1.5"])
    def test_should_reject_a_maximum_that_is_not_a_positive_integer(self, run_cli, maximum):
        result = run_cli("random", [maximum])

        assert result.returncode == 1
        assert "usage:" in result.stderr
