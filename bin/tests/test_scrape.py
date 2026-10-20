import pytest

from .scrape_support import (
    PAGE_URL,
)

AUDIO_URN = "urn:srf:audio:7a1af3be-b996-3602-b224-27d0f9a2edb0"


@pytest.fixture
def cli(load_script):
    return load_script("scrape")


def should_list_its_flags_and_expert_choices_in_help(cli, capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_args(["--help"])

    out = capsys.readouterr().out
    assert exit_info.value.code == 0
    assert "--out DIR" in out
    assert "--expert {generic,srf}" in out


def should_reject_a_url_that_is_not_a_web_url(cli, capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_args(["file:///etc/hosts"])

    assert exit_info.value.code == 2
    assert "not a web URL: file:///etc/hosts" in capsys.readouterr().err


def should_exit_1_with_the_reason_when_the_page_cannot_be_fetched(
    cli, monkeypatch, capsys, tmp_path
):
    class UnreachableFetcher:
        def fetch_html(self, url):
            raise OSError("Name or service not known")

    monkeypatch.setattr(cli, "Fetcher", UnreachableFetcher)

    code = cli.main([PAGE_URL, "-o", str(tmp_path)])

    assert code == 1
    assert (
        f"Could not scrape {PAGE_URL}: Name or service not known"
        in capsys.readouterr().err
    )
