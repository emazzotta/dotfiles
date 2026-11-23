import pytest

NOW = 1_800_000_000


@pytest.fixture
def presence(load_module):
    return load_module("presence")


def _line(age, kind):
    return f"{NOW - age} {kind}"


class TestClassify:
    @pytest.mark.parametrize("lines, expected", [
        (None, "unknown"),
        ([], "away"),
        ([_line(5, "computer")], "computer"),
        ([_line(5, "phone")], "phone"),
        ([_line(5, "phone"), _line(30, "computer")], "computer"),
        ([_line(500, "computer"), _line(5, "phone")], "phone"),
        ([_line(500, "computer"), _line(121, "phone")], "away"),
        ([_line(119, "computer")], "computer"),
        ([_line(120, "computer")], "away"),
        ([_line(-30, "phone")], "phone"),
    ], ids=["no-folder", "empty-folder", "computer", "phone", "computer-beats-phone", "stale-computer-then-phone",
            "everything-stale", "one-second-inside-the-window", "exactly-at-the-window", "clock-ahead"])
    def should_name_the_kind_that_is_present(self, presence, lines, expected):
        assert presence.classify(lines, NOW) == presence.Presence(expected)

    @pytest.mark.parametrize("line", [
        "", "   ", "garbage", f"{NOW}", "computer", f"computer {NOW}", f"{NOW} tablet", f"{NOW} computer extra",
        f"{NOW} Computer", "-5 computer", f"{NOW}.5 computer", f"{NOW}computer",
    ])
    def should_ignore_a_line_in_a_bad_format(self, presence, line):
        assert presence.classify([line], NOW) == presence.Presence.AWAY

    def should_still_count_a_good_line_beside_a_bad_one(self, presence):
        assert presence.classify(["garbage", _line(5, "phone")], NOW) == presence.Presence.PHONE

    @pytest.mark.parametrize("line", [f"{NOW - 5}\tcomputer", f"  {NOW - 5}   computer  ", f"{NOW - 5} computer\r"])
    def should_accept_any_white_space_around_and_between_the_fields(self, presence, line):
        assert presence.classify([line], NOW) == presence.Presence.COMPUTER

    @pytest.mark.parametrize("kind, attended", [("computer", True), ("phone", True), ("away", False),
                                                  ("unknown", False)])
    def should_count_only_a_computer_or_a_phone_as_attended(self, presence, kind, attended):
        assert presence.Presence(kind).attended is attended


class TestFolderLines:
    def should_collect_the_lines_of_every_instance_file(self, presence, tmp_path):
        (tmp_path / "terminal-a").write_text("1 computer\n2 phone\n")
        (tmp_path / "terminal-b").write_text("3 computer\n")

        assert sorted(presence.folder_lines(tmp_path)) == ["1 computer", "2 phone", "3 computer"]

    def should_give_no_lines_for_an_empty_folder(self, presence, tmp_path):
        assert presence.folder_lines(tmp_path) == []

    def should_give_none_when_the_folder_is_missing(self, presence, tmp_path):
        assert presence.folder_lines(tmp_path / "missing") is None

    def should_give_none_when_the_folder_is_a_file(self, presence, tmp_path):
        (tmp_path / "presence").write_text("1 computer\n")

        assert presence.folder_lines(tmp_path / "presence") is None

    def should_skip_every_file_whose_name_starts_with_a_dot(self, presence, tmp_path):
        (tmp_path / ".terminal.tmp").write_text(f"{NOW} computer\n")
        (tmp_path / ".hidden").write_text(f"{NOW} computer\n")
        (tmp_path / "terminal").write_text(f"{NOW} phone\n")

        lines = presence.folder_lines(tmp_path)

        assert lines == [f"{NOW} phone"]
        assert presence.classify(lines, NOW) == presence.Presence.PHONE

    def should_count_a_normal_file_beside_a_temporary_write(self, presence, tmp_path):
        (tmp_path / ".terminal.tmp").write_text(f"{NOW} phone\n")
        (tmp_path / "terminal").write_text(f"{NOW} computer\n")

        assert presence.classify(presence.folder_lines(tmp_path), NOW) == presence.Presence.COMPUTER

    def should_give_away_when_only_a_temporary_write_is_there(self, presence, tmp_path):
        (tmp_path / ".terminal.tmp").write_text(f"{NOW} computer\n")

        assert presence.classify(presence.folder_lines(tmp_path), NOW) == presence.Presence.AWAY

    def should_merge_equal_lines_from_several_files(self, presence, tmp_path):
        (tmp_path / "terminal-a").write_text(f"{NOW} phone\n{NOW} phone\n")
        (tmp_path / "terminal-b").write_text(f"{NOW} phone\n")

        lines = presence.folder_lines(tmp_path)

        assert lines == [f"{NOW} phone"] * 3
        assert presence.classify(lines, NOW) == presence.Presence.PHONE

    def should_skip_a_subfolder(self, presence, tmp_path):
        (tmp_path / "nested").mkdir()
        (tmp_path / "terminal").write_text("1 phone\n")

        assert presence.folder_lines(tmp_path) == ["1 phone"]

    @pytest.mark.parametrize("failure", [PermissionError, FileNotFoundError], ids=["unreadable", "vanished"])
    def should_skip_a_file_it_cannot_read_and_keep_the_others(self, presence, tmp_path, monkeypatch, failure):
        (tmp_path / "locked").write_text("1 computer\n")
        (tmp_path / "open").write_text("2 phone\n")
        read_text = type(tmp_path).read_text

        def read_unless_locked(path, *args, **kwargs):
            if path.name == "locked":
                raise failure(path)
            return read_text(path, *args, **kwargs)

        monkeypatch.setattr(type(tmp_path), "read_text", read_unless_locked)

        assert presence.folder_lines(tmp_path) == ["2 phone"]

    def should_survive_bytes_that_are_not_utf8(self, presence, tmp_path):
        (tmp_path / "terminal").write_bytes(b"\xff\xfe\n" + f"{NOW} phone\n".encode())

        lines = presence.folder_lines(tmp_path)

        assert presence.classify(lines, NOW) == presence.Presence.PHONE


class TestCurrent:
    @pytest.fixture
    def folder(self, presence, tmp_path, monkeypatch):
        monkeypatch.setattr(presence, "PRESENCE_DIR", tmp_path / "presence")
        return tmp_path / "presence"

    def should_read_the_presence_folder_at_the_given_time(self, presence, folder):
        folder.mkdir()
        (folder / "terminal").write_text(_line(10, "computer") + "\n")

        assert presence.current(clock=lambda: NOW) == presence.Presence.COMPUTER
        assert presence.current(clock=lambda: NOW + 600) == presence.Presence.AWAY

    def should_be_unknown_when_the_folder_does_not_exist(self, presence, folder):
        assert presence.current(clock=lambda: NOW) == presence.Presence.UNKNOWN

    def should_read_the_folder_under_the_claude_home(self, presence):
        assert presence.PRESENCE_DIR.parts[-2:] == (".claude", "presence")
