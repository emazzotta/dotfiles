import argparse
import subprocess
import sys
from base64 import b64encode
from pathlib import Path

import pytest

BIN_DIR = Path(__file__).parent.parent


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


class TestBuildPayload:
    def _call(self, jcr, **overrides):
        defaults = dict(
            summary="S", description="", fix_version="25.3.0",
            issue_type="Task", sprint_id="", account_id="acct",
        )
        defaults.update(overrides)
        return jcr.build_payload(**defaults)

    def test_omits_parent_by_default(self, jcr):
        payload = self._call(jcr)
        assert "parent" not in payload["fields"]

    def test_omits_parent_when_none(self, jcr):
        payload = self._call(jcr, parent_key=None)
        assert "parent" not in payload["fields"]

    def test_omits_parent_when_empty_string(self, jcr):
        payload = self._call(jcr, parent_key="")
        assert "parent" not in payload["fields"]

    def test_sets_parent_when_provided(self, jcr):
        payload = self._call(jcr, parent_key="LEO-2305")
        assert payload["fields"]["parent"] == {"key": "LEO-2305"}

    def test_parent_coexists_with_other_fields(self, jcr):
        payload = self._call(jcr, parent_key="LEO-2305", sprint_id="461", description="body")
        fields = payload["fields"]
        assert fields["parent"] == {"key": "LEO-2305"}
        assert fields[jcr.SPRINT_FIELD] == 461
        assert fields["description"]["type"] == "doc"


class TestBuildUpdateFields:
    def _ns(self, **overrides):
        defaults = dict(
            issue_type=None, summary=None, description=None,
            fix_version=None, no_fix_version=False,
            assignee=None, parent=None,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_empty_namespace_produces_empty_dict(self, jcr):
        assert jcr.build_update_fields(self._ns()) == {}

    def test_parent_included_when_set(self, jcr):
        fields = jcr.build_update_fields(self._ns(parent="LEO-2305"))
        assert fields == {"parent": {"key": "LEO-2305"}}

    def test_parent_omitted_when_none(self, jcr):
        fields = jcr.build_update_fields(self._ns(summary="new"))
        assert "parent" not in fields

    def test_parent_with_other_updates(self, jcr):
        ns = self._ns(parent="LEO-2305", summary="new", fix_version="25.4.0")
        fields = jcr.build_update_fields(ns)
        assert fields["parent"] == {"key": "LEO-2305"}
        assert fields["summary"] == "new"
        assert fields["fixVersions"] == [{"name": "25.4.0"}]


class TestParseArgsParent:
    """Verify --parent wires into the argparse namespace and reaches build_payload."""

    def test_parent_flag_sets_namespace_attr(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "--summary", "S", "--parent", "LEO-2305"])
        args = jcr.parse_args()
        assert args.parent == "LEO-2305"

    def test_parent_defaults_to_none(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "--summary", "S"])
        args = jcr.parse_args()
        assert args.parent is None

    def test_parent_available_on_update(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-100", "--update", "--parent", "LEO-2305"])
        args = jcr.parse_args()
        assert args.parent == "LEO-2305"
        assert args.update is True

    def test_help_output_mentions_parent(self):
        result = subprocess.run(
            [sys.executable, str(BIN_DIR / "jcr"), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "--parent" in result.stdout
