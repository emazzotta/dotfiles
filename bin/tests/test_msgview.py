import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

ZURICH_SUMMER = timezone(timedelta(hours=2))
SENT = datetime(2020, 4, 21, 9, 24, tzinfo=ZURICH_SUMMER)


class FakeMsgError(Exception):
    pass


class FakeAttachment:
    def __init__(self, name, data):
        self.name = name
        self.data = data

    def getFilename(self):
        return self.name

    def save(self, customPath, extractEmbedded):
        target = Path(customPath) / self.name
        target.write_bytes(self.data)
        return "FILE", str(target)


class FakeMessage:
    def __init__(self, **overrides):
        fields = dict(
            subject="Patch 19.2", sender="Team <team@example.com>",
            to="customer@example.com", cc=None, bcc=None, date=SENT,
            receivedTime=None, body="Hello", attachments=[],
        )
        fields.update(overrides)
        self.__dict__.update(fields)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def fake_extract_msg(message=None, error=None):
    def open_msg(path):
        if error:
            raise error
        return message

    return SimpleNamespace(
        openMsg=open_msg,
        exceptions=SimpleNamespace(ExMsgBaseException=FakeMsgError),
    )


@pytest.fixture
def cli(load_script):
    return load_script("msgview", mock_modules={"extract_msg": fake_extract_msg()})


@pytest.fixture
def msg_file(tmp_path):
    path = tmp_path / "mail.msg"
    path.write_bytes(b"ole")
    return path


def open_as(cli, monkeypatch, message=None, error=None):
    monkeypatch.setattr(cli, "extract_msg", fake_extract_msg(message, error))


def should_show_subject_sender_date_and_attachment_sizes(cli, monkeypatch, msg_file, capsys):
    attachments = [FakeAttachment("report.pdf", b"x" * 1536)]
    open_as(cli, monkeypatch, FakeMessage(attachments=attachments))

    code = cli.main([str(msg_file)])

    out = capsys.readouterr().out
    assert code == 0
    assert "Patch 19.2" in out
    assert "Team <team@example.com>" in out
    assert "Tue 21 Apr 2020 09:24 +0200" in out
    assert "report.pdf" in out
    assert "1.5 KB" in out
    assert out.rstrip().endswith("Hello")


def should_leave_out_header_rows_the_message_does_not_carry(cli):
    email = cli.read_email(FakeMessage(sender=None, cc=None, attachments=[]))

    labels = [label for label, _ in cli.header_rows(email)]

    assert labels == ["To", "Date"]


def should_show_the_received_time_when_the_message_has_no_date(cli):
    received = SENT + timedelta(minutes=3)

    email = cli.read_email(FakeMessage(date=None, receivedTime=received))

    assert email.date == received


def should_reduce_whitespace_only_lines_to_single_blank_lines(cli):
    body = "Dear all\r\n \r\n\xa0\r\n\r\nPatch ready.  \r\n\r\n"

    assert cli.clean_body(body) == "Dear all\n\nPatch ready."


@pytest.mark.parametrize("size,expected", [
    (512, "512 B"),
    (1536, "1.5 KB"),
    (5 * 1024 * 1024, "5.0 MB"),
    (3 * 1024 ** 4, "3072.0 GB"),
])
def should_format_attachment_sizes_in_binary_units(cli, size, expected):
    assert cli.format_size(size) == expected


def should_name_an_embedded_message_without_a_size(cli):
    attachment = cli.read_attachment(FakeAttachment("forwarded.msg", FakeMessage()))

    assert cli.describe(attachment) == "forwarded.msg"


def should_save_every_attachment_into_a_new_directory(cli, monkeypatch, msg_file, tmp_path):
    attachments = [FakeAttachment("a.pdf", b"a"), FakeAttachment("b.png", b"b")]
    open_as(cli, monkeypatch, FakeMessage(attachments=attachments))
    target = tmp_path / "out" / "attachments"

    code = cli.main([str(msg_file), "-a", str(target)])

    assert code == 0
    assert sorted(p.name for p in target.iterdir()) == ["a.pdf", "b.png"]


def should_exit_1_naming_an_attachment_the_library_cannot_save(
    cli, monkeypatch, msg_file, tmp_path, capsys
):
    unsupported = FakeAttachment("link.url", b"")
    unsupported.save = lambda customPath, extractEmbedded: ("NONE", None)
    attachments = [FakeAttachment("a.pdf", b"a"), unsupported]
    open_as(cli, monkeypatch, FakeMessage(attachments=attachments))
    target = tmp_path / "out"

    code = cli.main([str(msg_file), "-a", str(target)])

    assert code == 1
    assert [p.name for p in target.iterdir()] == ["a.pdf"]
    assert "Could not save link.url: unsupported attachment type" in capsys.readouterr().err


def should_exit_1_with_the_reason_when_the_file_is_not_an_outlook_message(
    cli, monkeypatch, msg_file, capsys
):
    open_as(cli, monkeypatch, error=FakeMsgError("not an OLE2 structured storage file"))

    code = cli.main([str(msg_file)])

    assert code == 1
    assert "not an OLE2 structured storage file" in capsys.readouterr().err


def should_exit_1_when_the_file_does_not_exist(cli, tmp_path, capsys):
    missing = tmp_path / "gone.msg"

    code = cli.main([str(missing)])

    assert code == 1
    assert f"No such file: {missing}" in capsys.readouterr().err


def should_read_the_file_pickfile_resolves_when_none_is_given(cli, monkeypatch, msg_file, capsys):
    open_as(cli, monkeypatch, FakeMessage(subject="Picked"))
    monkeypatch.setattr(
        cli.subprocess, "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 0, f"{msg_file}\n"),
    )

    code = cli.main([])

    assert code == 0
    assert "Picked" in capsys.readouterr().out


def should_exit_1_when_pickfile_finds_no_msg_file(cli, monkeypatch):
    monkeypatch.setattr(
        cli.subprocess, "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 1, ""),
    )

    assert cli.main([]) == 1


def should_list_the_attachments_flag_in_help(cli, capsys):
    with pytest.raises(SystemExit) as exit_info:
        cli.parse_args(["--help"])

    assert exit_info.value.code == 0
    assert "--attachments DIR" in capsys.readouterr().out
