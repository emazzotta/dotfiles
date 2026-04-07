from base64 import b64encode

import pytest


@pytest.fixture
def jcr(load_script):
    return load_script("jcr")


class TestBuildAuthHeader:
    def test_encodes_credentials(self, jcr, monkeypatch):
        monkeypatch.setenv("JIRA_EMAIL", "user@example.com")
        monkeypatch.setenv("JIRA_TOKEN", "secret123")
        expected = b64encode(b"user@example.com:secret123").decode()
        assert jcr.build_auth_header() == f"Basic {expected}"

    def test_empty_credentials(self, jcr, monkeypatch):
        monkeypatch.delenv("JIRA_EMAIL", raising=False)
        monkeypatch.delenv("JIRA_TOKEN", raising=False)
        header = jcr.build_auth_header()
        assert header.startswith("Basic ")
        expected = b64encode(b":").decode()
        assert header == f"Basic {expected}"


class TestExtractError:
    @pytest.mark.parametrize("result,expected_substr", [
        ({"errorMessages": ["Something went wrong"], "errors": {}}, "Something went wrong"),
        ({"errorMessages": [], "errors": {"summary": "Required"}}, "Required"),
        ({"errorMessages": ["msg1"], "errors": {"field": "msg2"}}, "msg1"),
    ])
    def test_extracts_messages(self, jcr, result, expected_substr):
        assert expected_substr in jcr.extract_error(result)

    def test_combined_includes_both(self, jcr):
        error = jcr.extract_error({"errorMessages": ["msg1"], "errors": {"field": "msg2"}})
        assert "msg1" in error
        assert "msg2" in error

    def test_empty_returns_str_repr(self, jcr):
        result = {"errorMessages": [], "errors": {}}
        assert jcr.extract_error(result) == str(result)


class TestExtractAdfText:
    def test_text_node(self, jcr):
        assert jcr.extract_adf_text({"type": "text", "text": "hello"}) == "hello"

    def test_none_returns_empty(self, jcr):
        assert jcr.extract_adf_text(None) == ""

    def test_paragraph_with_text(self, jcr):
        node = {"type": "paragraph", "content": [{"type": "text", "text": "hello"}]}
        assert "hello" in jcr.extract_adf_text(node)

    def test_nested_nodes(self, jcr):
        node = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "first"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "second"}]},
            ],
        }
        result = jcr.extract_adf_text(node)
        assert "first" in result
        assert "second" in result

    def test_empty_content(self, jcr):
        assert jcr.extract_adf_text({"type": "doc", "content": []}) == ""

    def test_missing_text_field(self, jcr):
        assert jcr.extract_adf_text({"type": "text"}) == ""


class TestToAdf:
    def test_single_paragraph(self, jcr):
        result = jcr.to_adf("Hello world")
        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) >= 1
        assert result["content"][0]["type"] == "paragraph"

    def test_multiple_paragraphs(self, jcr):
        result = jcr.to_adf("First\n\nSecond")
        assert len(result["content"]) == 2

    def test_empty_string(self, jcr):
        result = jcr.to_adf("")
        assert result["type"] == "doc"
        assert result["version"] == 1
        assert len(result["content"]) == 1

    @pytest.mark.parametrize("heading,level", [
        ("# Title", 1),
        ("## Section", 2),
        ("### Subsection", 3),
    ])
    def test_heading_levels(self, jcr, heading, level):
        result = jcr.to_adf(heading)
        node = result["content"][0]
        assert node["type"] == "heading"
        assert node["attrs"]["level"] == level
        assert node["content"][0]["text"] == heading.lstrip("# ")

    def test_bullet_list(self, jcr):
        result = jcr.to_adf("- First item\n- Second item\n- Third item")
        node = result["content"][0]
        assert node["type"] == "bulletList"
        assert len(node["content"]) == 3
        assert node["content"][0]["type"] == "listItem"
        assert node["content"][0]["content"][0]["content"][0]["text"] == "First item"

    def test_bullet_list_asterisk(self, jcr):
        result = jcr.to_adf("* Alpha\n* Beta")
        node = result["content"][0]
        assert node["type"] == "bulletList"
        assert len(node["content"]) == 2

    def test_table(self, jcr):
        table_md = "| Name | Value |\n| --- | --- |\n| foo | bar |\n| baz | qux |"
        result = jcr.to_adf(table_md)
        node = result["content"][0]
        assert node["type"] == "table"
        rows = node["content"]
        assert len(rows) == 3
        assert rows[0]["content"][0]["type"] == "tableHeader"
        assert rows[1]["content"][0]["type"] == "tableCell"

    def test_table_without_separator(self, jcr):
        table_md = "| Name | Value |\n| foo | bar |"
        result = jcr.to_adf(table_md)
        node = result["content"][0]
        assert node["type"] == "table"
        rows = node["content"]
        assert len(rows) == 2
        assert rows[0]["content"][0]["type"] == "tableHeader"
        assert rows[1]["content"][0]["type"] == "tableCell"

    def test_mixed_content(self, jcr):
        md = "### Problem\n\nSome description.\n\n- Item one\n- Item two\n\n| A | B |\n| --- | --- |\n| 1 | 2 |"
        result = jcr.to_adf(md)
        types = [node["type"] for node in result["content"]]
        assert types == ["heading", "paragraph", "bulletList", "table"]

    def test_heading_followed_by_paragraph(self, jcr):
        result = jcr.to_adf("### Title\n\nBody text here.")
        assert result["content"][0]["type"] == "heading"
        assert result["content"][1]["type"] == "paragraph"

    def test_multiline_paragraph_uses_hard_breaks(self, jcr):
        result = jcr.to_adf("Line one\nLine two\nLine three")
        node = result["content"][0]
        assert node["type"] == "paragraph"
        texts = [c for c in node["content"] if c["type"] == "text"]
        breaks = [c for c in node["content"] if c["type"] == "hardBreak"]
        assert len(texts) == 3
        assert len(breaks) == 2
