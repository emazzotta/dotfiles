import pytest


@pytest.fixture
def markup(load_module):
    return load_module("scrapelib.markup")


@pytest.fixture
def soup_of(load_module):
    bs4 = load_module("bs4")
    return lambda html: bs4.BeautifulSoup(html, "html5lib")


def should_escape_text_and_keep_only_allowed_inline_tags(markup, soup_of):
    paragraph = soup_of(
        '<p>a &lt;b&gt; <strong>bold</strong> <span class="x">plain</span>'
        "<script>alert(1)</script></p>"
    ).p

    result = markup.inline_html(paragraph)

    assert result == "a &lt;b&gt; <strong>bold</strong> plain"


def should_drop_links_that_are_not_web_urls(markup, soup_of):
    paragraph = soup_of(
        '<p><a href="javascript:alert(1)">bad</a> '
        '<a href="https://example.org/a?x=1&amp;y=2">good</a></p>'
    ).p

    result = markup.inline_html(paragraph)

    assert result == 'bad <a href="https://example.org/a?x=1&amp;y=2">good</a>'


def should_leave_screen_reader_labels_out_of_visible_text(markup, soup_of):
    cite = soup_of(
        '<cite><span class="h-offscreen">Autor:</span> Erika <b>Muster</b></cite>'
    ).cite

    assert markup.text_of(cite) == "Erika Muster"


def should_pick_the_widest_srcset_candidate(markup):
    assert (
        markup.largest_srcset_candidate("a.jpg 320w, c.jpg 1280w, b.jpg 640w")
        == "c.jpg"
    )


def should_read_semantic_html_into_blocks(load_module, markup, soup_of):
    article = load_module("scrapelib.article")
    body = soup_of(
        '<h1>Kapitel</h1><p>Text <em>kursiv</em><img src="/a.jpg" alt="Alt"></p>'
        "<ul><li>eins</li><li>zwei</li></ul><ol><li>erstens</li></ol>"
        "<blockquote>Zitat</blockquote>"
        '<figure><img srcset="/s.jpg 320w, /l.jpg 1280w"><figcaption>Legende</figcaption></figure>'
        "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
    ).body

    blocks = markup.SemanticReader(
        "https://example.org/news/x", article.AssetNamer()
    ).blocks(body)

    names = [type(block).__name__ for block in blocks]
    assert names == [
        "Heading",
        "Paragraph",
        "Figure",
        "ListBlock",
        "ListBlock",
        "Quote",
        "Figure",
        "Table",
    ]
    heading, paragraph, image, bullets, numbers, quote, figure, table = blocks
    assert (heading.level, heading.text) == (2, "Kapitel")
    assert paragraph.html == "Text <em>kursiv</em>"
    assert (image.image.url, image.alt) == ("https://example.org/a.jpg", "Alt")
    assert (bullets.items, bullets.ordered, numbers.ordered) == (
        ("eins", "zwei"),
        False,
        True,
    )
    assert quote.html == "Zitat"
    assert (figure.image.url, figure.caption) == (
        "https://example.org/l.jpg",
        "Legende",
    )
    assert (table.rows, table.header) == ((("A", "B"), ("1", "2")), True)
