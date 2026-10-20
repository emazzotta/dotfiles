import pytest

from .scrape_support import PAGE_URL, srf_page


@pytest.fixture
def experts(load_module):
    return load_module("scrapelib.experts")


@pytest.fixture
def page_of(load_module):
    base = load_module("scrapelib.experts.base")
    bs4 = load_module("bs4")
    return lambda url, html: base.Page(url, html, bs4.BeautifulSoup(html, "html5lib"))


def should_pick_the_expert_by_site_unless_one_is_named(experts, page_of):
    srf = page_of(PAGE_URL, srf_page(""))
    elsewhere = page_of("https://news.example.org/x", srf_page(""))

    assert experts.expert_for(srf).name == "srf"
    assert experts.expert_for(elsewhere).name == "generic"
    assert experts.expert_for(srf, "generic").name == "generic"
    assert experts.expert_names() == ("generic", "srf")


def should_reject_an_unknown_expert_name(experts):
    with pytest.raises(ValueError, match="unknown expert 'nope', known: generic, srf"):
        experts.named_expert("nope")
