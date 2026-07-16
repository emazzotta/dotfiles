import pytest


@pytest.fixture
def mod(load_script):
    return load_script("transcript-title")


@pytest.fixture
def transcript():
    return ('<html><head><title>Claude Transcript - -workspace</title></head>'
            '<body><h1 id="title">Claude Transcript - -workspace</h1></body></html>')


class TestSetTitle:
    def should_rewrite_document_title(self, mod, transcript):
        result, _ = mod.set_title(transcript, "Fixing the case-save corruption")

        assert "<title>Fixing the case-save corruption</title>" in result

    def should_rewrite_page_header(self, mod, transcript):
        result, _ = mod.set_title(transcript, "Fixing the case-save corruption")

        assert '<h1 id="title">Fixing the case-save corruption</h1>' in result

    def should_report_both_replacements(self, mod, transcript):
        _, replacements = mod.set_title(transcript, "New title")

        assert replacements == 2

    def should_escape_html_in_title(self, mod, transcript):
        result, _ = mod.set_title(transcript, 'Debug <script> & "quotes"')

        assert "<title>Debug &lt;script&gt; &amp; &quot;quotes&quot;</title>" in result
        assert "<script>" not in result

    def should_treat_replacement_text_literally(self, mod, transcript):
        result, _ = mod.set_title(transcript, r"a \g<1> backref \\ and $dollar")

        assert r"<title>a \g&lt;1&gt; backref \\ and $dollar</title>" in result

    def should_be_repeatable(self, mod, transcript):
        once, _ = mod.set_title(transcript, "Same title")
        twice, replacements = mod.set_title(once, "Same title")

        assert once == twice
        assert replacements == 2

    def should_replace_only_the_first_title_element(self, mod):
        html = "<head><title>a</title></head><body><title>b</title></body>"

        result, _ = mod.set_title(html, "new")

        assert "<title>new</title>" in result
        assert "<title>b</title>" in result

    def should_leave_multiline_title_content_behind(self, mod):
        html = "<head><title>\n  Claude\n  Transcript\n</title></head>"

        result, _ = mod.set_title(html, "new")

        assert "<title>new</title>" in result

    def should_match_header_regardless_of_attribute_order(self, mod):
        html = '<h1 class="x" id="title" data-a="1">old</h1>'

        result, replacements = mod.set_title(html, "new")

        assert '<h1 class="x" id="title" data-a="1">new</h1>' in result
        assert replacements == 1

    def should_ignore_headers_that_are_not_the_title(self, mod):
        html = '<h1 id="other">keep</h1><h1 id="title">old</h1>'

        result, _ = mod.set_title(html, "new")

        assert '<h1 id="other">keep</h1>' in result
        assert '<h1 id="title">new</h1>' in result

    def should_report_no_replacements_when_no_title_present(self, mod):
        result, replacements = mod.set_title("<body><p>hi</p></body>", "new")

        assert replacements == 0
        assert result == "<body><p>hi</p></body>"


class TestProcessFile:
    def should_write_the_new_title_to_disk(self, mod, tmp_path, transcript):
        html = tmp_path / "t.html"
        html.write_text(transcript, encoding="utf-8")

        replacements = mod.process_file(html, "Session recap")

        assert replacements == 2
        assert "<title>Session recap</title>" in html.read_text(encoding="utf-8")

    def should_leave_file_untouched_when_no_title_present(self, mod, tmp_path):
        html = tmp_path / "t.html"
        html.write_text("<body>hi</body>", encoding="utf-8")

        assert mod.process_file(html, "Session recap") == 0
        assert html.read_text(encoding="utf-8") == "<body>hi</body>"


class TestMain:
    def should_fail_when_file_is_missing(self, mod, tmp_path, capsys):
        assert mod.main([str(tmp_path / "nope.html"), "t"]) == 1

    def should_fail_when_title_is_blank(self, mod, tmp_path, transcript):
        html = tmp_path / "t.html"
        html.write_text(transcript, encoding="utf-8")

        assert mod.main([str(html), "   "]) == 2

    def should_fail_when_no_title_element_found(self, mod, tmp_path):
        html = tmp_path / "t.html"
        html.write_text("<body>hi</body>", encoding="utf-8")

        assert mod.main([str(html), "Session recap"]) == 1

    def should_succeed_on_a_generated_transcript(self, mod, tmp_path, transcript):
        html = tmp_path / "t.html"
        html.write_text(transcript, encoding="utf-8")

        assert mod.main([str(html), "Session recap"]) == 0
        assert "<title>Session recap</title>" in html.read_text(encoding="utf-8")
