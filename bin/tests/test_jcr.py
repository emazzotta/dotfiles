import argparse
import json
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

    def test_inline_code_in_paragraph(self, jcr):
        result = jcr.to_adf("Use `foo` to enable it.")
        nodes = result["content"][0]["content"]
        assert nodes[0] == {"type": "text", "text": "Use "}
        assert nodes[1] == {"type": "text", "text": "foo", "marks": [{"type": "code"}]}
        assert nodes[2] == {"type": "text", "text": " to enable it."}

    def test_inline_code_in_heading(self, jcr):
        result = jcr.to_adf("## Property `enableFoo`")
        heading = result["content"][0]
        assert heading["type"] == "heading"
        assert heading["content"][0] == {"type": "text", "text": "Property "}
        assert heading["content"][1] == {"type": "text", "text": "enableFoo", "marks": [{"type": "code"}]}

    def test_inline_code_in_bullet(self, jcr):
        result = jcr.to_adf("- Set `debug=true` to see more")
        item_content = result["content"][0]["content"][0]["content"][0]["content"]
        assert item_content[0] == {"type": "text", "text": "Set "}
        assert item_content[1] == {"type": "text", "text": "debug=true", "marks": [{"type": "code"}]}
        assert item_content[2] == {"type": "text", "text": " to see more"}

    def test_inline_code_in_table_cell(self, jcr):
        result = jcr.to_adf("| Key | Value |\n| --- | --- |\n| `foo` | bar |")
        body_row = result["content"][0]["content"][1]
        first_cell_para = body_row["content"][0]["content"][0]
        assert first_cell_para["content"][0] == {"type": "text", "text": "foo", "marks": [{"type": "code"}]}

    def test_inline_code_adjacent(self, jcr):
        result = jcr.to_adf("`a` `b`")
        nodes = result["content"][0]["content"]
        assert nodes[0] == {"type": "text", "text": "a", "marks": [{"type": "code"}]}
        assert nodes[1] == {"type": "text", "text": " "}
        assert nodes[2] == {"type": "text", "text": "b", "marks": [{"type": "code"}]}

    def test_unmatched_backtick_is_literal(self, jcr):
        result = jcr.to_adf("before ` after")
        nodes = result["content"][0]["content"]
        assert len(nodes) == 1
        assert nodes[0] == {"type": "text", "text": "before ` after"}

    def test_fenced_code_block_not_treated_as_inline(self, jcr):
        result = jcr.to_adf("```\nfoo = `bar`\n```")
        block = result["content"][0]
        assert block["type"] == "codeBlock"
        assert block["content"][0] == {"type": "text", "text": "foo = `bar`"}


class TestInlineNodes:
    def test_plain_text(self, jcr):
        assert jcr._inline_nodes("hello world") == [{"type": "text", "text": "hello world"}]

    def test_empty_string_falls_back_to_single_text_node(self, jcr):
        assert jcr._inline_nodes("") == [{"type": "text", "text": ""}]

    def test_only_code(self, jcr):
        assert jcr._inline_nodes("`only`") == [
            {"type": "text", "text": "only", "marks": [{"type": "code"}]},
        ]

    def test_code_at_start(self, jcr):
        nodes = jcr._inline_nodes("`head` rest")
        assert nodes == [
            {"type": "text", "text": "head", "marks": [{"type": "code"}]},
            {"type": "text", "text": " rest"},
        ]

    def test_code_at_end(self, jcr):
        nodes = jcr._inline_nodes("rest `tail`")
        assert nodes == [
            {"type": "text", "text": "rest "},
            {"type": "text", "text": "tail", "marks": [{"type": "code"}]},
        ]

    def test_multiple_code_spans(self, jcr):
        nodes = jcr._inline_nodes("`a` and `b` and `c`")
        code_texts = [n["text"] for n in nodes if n.get("marks")]
        assert code_texts == ["a", "b", "c"]


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


class TestParseArgsAttach:
    def test_should_collect_attach_paths_into_list(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-1", "--attach", "a.xml", "--attach", "b.xml"])
        args = jcr.parse_args()
        assert args.attach == ["a.xml", "b.xml"]

    def test_should_default_attach_to_none(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-1"])
        args = jcr.parse_args()
        assert args.attach is None

    def test_should_set_yes_flag_with_short_option(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-1", "--attach", "a.xml", "-y"])
        args = jcr.parse_args()
        assert args.yes is True

    def test_should_default_yes_to_false(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-1", "--attach", "a.xml"])
        args = jcr.parse_args()
        assert args.yes is False

    def test_should_mention_attach_in_help(self):
        result = subprocess.run(
            [sys.executable, str(BIN_DIR / "jcr"), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "--attach" in result.stdout


class TestRunAttach:
    def _ns(self, **overrides):
        defaults = dict(keys=["LEO-1"], attach=["f.xml"], dry_run=False, yes=True, output_json=False)
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_should_exit_when_more_than_one_key(self, jcr):
        with pytest.raises(SystemExit):
            jcr.run_attach(self._ns(keys=["LEO-1", "LEO-2"]))

    def test_should_exit_when_file_missing(self, jcr, tmp_path):
        with pytest.raises(SystemExit):
            jcr.run_attach(self._ns(attach=[str(tmp_path / "nope.xml")]))

    def test_should_not_upload_on_dry_run(self, jcr, tmp_path, monkeypatch, capsys):
        target = tmp_path / "f.xml"
        target.write_text("<x/>")

        def boom(*args, **kwargs):
            raise AssertionError("upload must not run on dry-run")

        monkeypatch.setattr(jcr, "upload_attachments", boom)
        jcr.run_attach(self._ns(attach=[str(target)], dry_run=True))
        assert "f.xml" in capsys.readouterr().out

    def test_should_upload_when_file_exists_and_confirmed(self, jcr, tmp_path, monkeypatch, capsys):
        target = tmp_path / "f.xml"
        target.write_text("<x/>")
        captured: dict = {}

        def fake_upload(key, paths):
            captured["key"] = key
            captured["paths"] = paths
            return [{"id": "42", "filename": "f.xml", "size": 4}]

        monkeypatch.setattr(jcr, "upload_attachments", fake_upload)
        jcr.run_attach(self._ns(attach=[str(target)], yes=True))
        out = capsys.readouterr().out
        assert captured["key"] == "LEO-1"
        assert "Attached f.xml" in out
        assert "id 42" in out


class TestConfirmAttachments:
    def test_should_return_without_prompt_when_yes(self, jcr, tmp_path, monkeypatch):
        target = tmp_path / "f.xml"
        target.write_text("x")

        def boom(_message):
            raise AssertionError("must not prompt when --yes")

        monkeypatch.setattr(jcr, "gum_confirm", boom)
        jcr.confirm_attachments("LEO-1", [target], assume_yes=True)

    def test_should_exit_when_no_tty_and_not_yes(self, jcr, tmp_path, monkeypatch):
        target = tmp_path / "f.xml"
        target.write_text("x")
        monkeypatch.setattr(jcr.sys.stdin, "isatty", lambda: False)
        with pytest.raises(SystemExit):
            jcr.confirm_attachments("LEO-1", [target], assume_yes=False)


class TestUploadAttachments:
    def _result(self, stdout, returncode=0):
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout)

    def test_should_return_parsed_list_on_http_200(self, jcr, monkeypatch):
        monkeypatch.setattr(
            jcr.subprocess, "run",
            lambda cmd, **kwargs: self._result('[{"id":"9","filename":"f.xml","size":3}]\n200'),
        )
        result = jcr.upload_attachments("LEO-1", [Path("f.xml")])
        assert result == [{"id": "9", "filename": "f.xml", "size": 3}]

    def test_should_send_no_check_token_and_file_field(self, jcr, monkeypatch):
        captured: dict = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            return self._result("[]\n200")

        monkeypatch.setattr(jcr.subprocess, "run", fake_run)
        jcr.upload_attachments("LEO-1", [Path("/x/f.xml")])
        assert "X-Atlassian-Token: no-check" in captured["cmd"]
        assert "file=@/x/f.xml" in captured["cmd"]
        assert captured["cmd"][-1].endswith("/issue/LEO-1/attachments")

    def test_should_exit_on_non_200(self, jcr, monkeypatch):
        monkeypatch.setattr(jcr.subprocess, "run", lambda cmd, **kwargs: self._result("nope\n401"))
        with pytest.raises(SystemExit):
            jcr.upload_attachments("LEO-1", [Path("f.xml")])


class TestReportAndDescribeAttachments:
    def test_should_describe_file_name_size_and_key(self, jcr, tmp_path):
        target = tmp_path / "f.xml"
        target.write_text("abcd")
        desc = jcr.describe_attachments("LEO-1", [target])
        assert "LEO-1" in desc
        assert "f.xml" in desc
        assert "4 bytes" in desc

    def test_should_emit_json_when_requested(self, jcr, capsys):
        jcr.report_attachments("LEO-1", [{"id": "7", "filename": "f.xml", "size": 4}], output_json=True)
        assert json.loads(capsys.readouterr().out) == [{"id": "7", "filename": "f.xml", "size": 4}]


class TestParseArgsComment:
    def test_should_capture_comment_text(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-1", "--comment", "hello"])
        args = jcr.parse_args()
        assert args.comment == "hello"

    def test_should_default_comment_to_none(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-1"])
        args = jcr.parse_args()
        assert args.comment is None

    def test_should_mention_comment_in_help(self):
        result = subprocess.run(
            [sys.executable, str(BIN_DIR / "jcr"), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "--comment" in result.stdout


class TestAddComment:
    def test_should_post_adf_body_to_comment_endpoint(self, jcr, monkeypatch):
        captured: dict = {}

        def fake_request(method, path, data=None):
            captured.update(method=method, path=path, data=data)
            return {"id": "555"}

        monkeypatch.setattr(jcr, "jira_request", fake_request)
        result = jcr.add_comment("LEO-1", "Use `x` now")
        assert captured["method"] == "POST"
        assert captured["path"] == "api/3/issue/LEO-1/comment"
        assert captured["data"]["body"]["type"] == "doc"
        assert result == {"id": "555"}


class TestRunComment:
    def _ns(self, **overrides):
        defaults = dict(keys=["LEO-1"], comment="hi", dry_run=False, yes=True, output_json=False)
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_should_exit_when_more_than_one_key(self, jcr):
        with pytest.raises(SystemExit):
            jcr.run_comment(self._ns(keys=["LEO-1", "LEO-2"]))

    def test_should_not_post_on_dry_run(self, jcr, monkeypatch, capsys):
        def boom(*args, **kwargs):
            raise AssertionError("must not post on dry-run")

        monkeypatch.setattr(jcr, "add_comment", boom)
        jcr.run_comment(self._ns(dry_run=True))
        assert '"type": "doc"' in capsys.readouterr().out

    def test_should_post_when_confirmed(self, jcr, monkeypatch, capsys):
        captured: dict = {}

        def fake_add(key, text):
            captured.update(key=key, text=text)
            return {"id": "777"}

        monkeypatch.setattr(jcr, "add_comment", fake_add)
        jcr.run_comment(self._ns(comment="body text", yes=True))
        out = capsys.readouterr().out
        assert captured["key"] == "LEO-1"
        assert captured["text"] == "body text"
        assert "Comment 777 posted" in out

    def test_should_exit_when_no_tty_and_not_yes(self, jcr, monkeypatch):
        monkeypatch.setattr(jcr.sys.stdin, "isatty", lambda: False)
        with pytest.raises(SystemExit):
            jcr.confirm_comment("LEO-1", "text", assume_yes=False)


class TestParseArgsDeleteComment:
    def test_should_capture_delete_comment_id(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-1", "--delete-comment", "999"])
        args = jcr.parse_args()
        assert args.delete_comment == "999"

    def test_should_default_delete_comment_to_none(self, jcr, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["jcr", "LEO-1"])
        args = jcr.parse_args()
        assert args.delete_comment is None

    def test_should_mention_delete_comment_in_help(self):
        result = subprocess.run(
            [sys.executable, str(BIN_DIR / "jcr"), "--help"],
            capture_output=True, text=True, timeout=30,
        )
        assert result.returncode == 0
        assert "--delete-comment" in result.stdout


class TestDeleteComment:
    def test_should_call_delete_endpoint(self, jcr, monkeypatch):
        captured: dict = {}

        def fake_request(method, path, data=None):
            captured.update(method=method, path=path)
            return {}

        monkeypatch.setattr(jcr, "jira_request", fake_request)
        jcr.delete_comment("LEO-1", "555")
        assert captured["method"] == "DELETE"
        assert captured["path"] == "api/3/issue/LEO-1/comment/555"


class TestRunDeleteComment:
    def _ns(self, **overrides):
        defaults = dict(keys=["LEO-1"], delete_comment="555", dry_run=False, yes=True, output_json=False)
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_should_exit_when_more_than_one_key(self, jcr):
        with pytest.raises(SystemExit):
            jcr.run_delete_comment(self._ns(keys=["LEO-1", "LEO-2"]))

    def test_should_not_delete_on_dry_run(self, jcr, monkeypatch, capsys):
        def boom(*args, **kwargs):
            raise AssertionError("must not delete on dry-run")

        monkeypatch.setattr(jcr, "delete_comment", boom)
        jcr.run_delete_comment(self._ns(dry_run=True))
        assert "555" in capsys.readouterr().out

    def test_should_delete_when_confirmed(self, jcr, monkeypatch, capsys):
        captured: dict = {}

        def fake_delete(key, comment_id):
            captured.update(key=key, comment_id=comment_id)

        monkeypatch.setattr(jcr, "delete_comment", fake_delete)
        jcr.run_delete_comment(self._ns(delete_comment="555", yes=True))
        assert captured == {"key": "LEO-1", "comment_id": "555"}
        assert "deleted" in capsys.readouterr().out

    def test_should_exit_when_no_tty_and_not_yes(self, jcr, monkeypatch):
        monkeypatch.setattr(jcr.sys.stdin, "isatty", lambda: False)
        with pytest.raises(SystemExit):
            jcr.confirm_delete_comment("LEO-1", "555", assume_yes=False)
