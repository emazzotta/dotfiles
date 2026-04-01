import pytest


@pytest.fixture
def mod(load_script):
    return load_script("fix-html-charset")


class TestHasCharsetDeclaration:
    @pytest.mark.parametrize("html,expected", [
        ('<meta charset="UTF-8">', True),
        ('<meta charset="ISO-8859-1">', True),
        ('<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">', True),
        ("<html><head></head></html>", False),
        ("", False),
    ])
    def test_detection(self, mod, html, expected):
        assert mod.has_charset_declaration(html) is expected


class TestNormalizeCharsetMeta:
    def test_already_utf8(self, mod):
        html = '<meta charset="UTF-8">'
        result, changed = mod.normalize_charset_meta(html)
        assert changed is False
        assert result == html

    @pytest.mark.parametrize("charset", ["ISO-8859-1", "windows-1252", "us-ascii"])
    def test_normalizes_to_utf8(self, mod, charset):
        html = f'<meta charset="{charset}">'
        result, changed = mod.normalize_charset_meta(html)
        assert changed is True
        assert 'charset="UTF-8"' in result


class TestNormalizeCharsetContent:
    def test_already_utf8(self, mod):
        html = '<meta http-equiv="Content-Type" content="text/html; charset=UTF-8">'
        result, changed = mod.normalize_charset_content(html)
        assert changed is False

    def test_normalizes_latin1(self, mod):
        html = '<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1">'
        result, changed = mod.normalize_charset_content(html)
        assert changed is True
        assert "charset=UTF-8" in result


class TestAddCharsetDeclaration:
    def test_adds_before_title(self, mod):
        html = "<html><head>\n    <title>Test</title>\n</head></html>"
        result = mod.add_charset_declaration(html)
        assert "charset=UTF-8" in result
        assert result.index("charset") < result.index("<title>")

    def test_adds_after_doctype(self, mod):
        html = "<!DOCTYPE html>\n<html><head></head></html>"
        result = mod.add_charset_declaration(html)
        assert "charset=UTF-8" in result
        assert result.index("charset") > result.index("DOCTYPE")

    def test_adds_at_beginning_when_no_markers(self, mod):
        html = "<html><head></head></html>"
        result = mod.add_charset_declaration(html)
        assert result.startswith('<meta http-equiv="Content-Type"')


class TestFixHtmlCharset:
    def test_no_charset_adds_one(self, mod):
        html = "<!DOCTYPE html>\n<html><head><title>Test</title></head></html>"
        result, changes = mod.fix_html_charset(html)
        assert len(changes) == 1
        assert "added" in changes[0]
        assert "charset" in result.lower()

    def test_existing_utf8_no_changes(self, mod):
        html = '<html><head><meta charset="UTF-8"><title>T</title></head></html>'
        result, changes = mod.fix_html_charset(html)
        assert not any("normalized" in c for c in changes)

    def test_normalizes_latin1(self, mod):
        html = '<html><head><meta charset="ISO-8859-1"><title>T</title></head></html>'
        result, changes = mod.fix_html_charset(html)
        assert any("normalized" in c for c in changes)
        assert 'charset="UTF-8"' in result

    def test_removes_duplicates(self, mod):
        html = '<html><head><meta charset="UTF-8"><meta charset="UTF-8"><title>T</title></head></html>'
        result, changes = mod.fix_html_charset(html)
        assert any("duplicate" in c for c in changes)
        assert result.count('charset="UTF-8"') == 1

    def test_mixed_types_keeps_first(self, mod):
        html = '<html><head><meta charset="ISO-8859-1"><meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"><title>T</title></head></html>'
        result, changes = mod.fix_html_charset(html)
        assert 'charset="UTF-8"' in result


class TestProcessFile:
    def test_fixes_file(self, mod, tmp_path):
        f = tmp_path / "test.html"
        f.write_text('<html><head><meta charset="ISO-8859-1"><title>T</title></head></html>')
        result = mod.process_file(f, dry_run=False)
        assert result.status == mod.ProcessingStatus.FIXED
        assert 'charset="UTF-8"' in f.read_text()

    def test_skips_correct_file(self, mod, tmp_path):
        f = tmp_path / "test.html"
        f.write_text('<html><head><meta charset="UTF-8"><title>T</title></head></html>')
        result = mod.process_file(f, dry_run=False)
        assert result.status == mod.ProcessingStatus.SKIPPED

    def test_dry_run_does_not_modify(self, mod, tmp_path):
        f = tmp_path / "test.html"
        original = '<html><head><meta charset="ISO-8859-1"><title>T</title></head></html>'
        f.write_text(original)
        result = mod.process_file(f, dry_run=True)
        assert result.status == mod.ProcessingStatus.FIXED
        assert f.read_text() == original

    def test_non_utf8_file_fails(self, mod, tmp_path):
        f = tmp_path / "test.html"
        f.write_bytes(b"\xff\xfe invalid utf8 content")
        result = mod.process_file(f, dry_run=False)
        assert result.status == mod.ProcessingStatus.FAILED
