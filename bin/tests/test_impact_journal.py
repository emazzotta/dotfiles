import re
from datetime import date, datetime, timezone

import pytest

from bin.tests.conftest import marker_mocks

ANSI = re.compile(r"\x1b\[[0-9;]*m")


@pytest.fixture
def journal(load_script):
    return load_script("impact-journal")


def gym_class(journal, title, day=date(2026, 10, 7), status="completed"):
    return journal.GymClass(day, title, "Coach", "Studio", status)


@pytest.mark.parametrize("title, expected", [
    ("BJJ (Gi) - All Levels", "BJJ Gi"),
    ("BJJ (No-Gi) - Basics", "BJJ No-Gi"),
    ("BJJ Sparring (Gi & No-Gi)", "BJJ Sparring Gi & No-Gi"),
    ("Muay Thai - Basics", "Muay Thai"),
    ("Fitness Kickboxing", "Fitness Kickboxing"),
])
def should_group_a_class_by_discipline_and_gi_variant(journal, title, expected):
    assert journal.discipline(title) == expected


@pytest.mark.parametrize("text", ["2026-04-01", "1.4.2026", "01.04.2026"])
def should_read_iso_and_swiss_dates(journal, text):
    assert journal.parse_day(text) == date(2026, 4, 1)


@pytest.mark.parametrize("text", ["31.2.2026", "2026/04/01", "april"])
def should_reject_a_date_it_cannot_read(journal, text):
    with pytest.raises(journal.argparse.ArgumentTypeError):
        journal.parse_day(text)


def should_cover_the_range_in_gapless_windows_of_at_most_thirty_days(journal):
    windows = list(journal.query_windows(date(2026, 4, 1), date(2026, 10, 12)))

    assert windows[0][0] == datetime(2026, 4, 1, tzinfo=journal.GYM_ZONE)
    assert windows[-1][1] == datetime(2026, 10, 13, tzinfo=journal.GYM_ZONE)
    assert all(earlier[1] == later[0] for earlier, later in zip(windows, windows[1:]))
    assert all(end - start <= journal.QUERY_WINDOW for start, end in windows)


def should_read_a_class_from_a_calendar_entry(journal):
    entry = {
        "date": int(datetime(2026, 10, 7, tzinfo=timezone.utc).timestamp()),
        "text": "BJJ (Gi) - All Levels",
        "data": {"trainer_name": "Coach", "location": "Studio", "status": "completed"},
    }

    assert journal.parse_class(entry) == gym_class(journal, "BJJ (Gi) - All Levels")


def should_list_gi_and_no_gi_classes_in_separate_groups(journal, capsys):
    classes = [
        gym_class(journal, "BJJ (Gi) - All Levels"),
        gym_class(journal, "BJJ (No-Gi) - Basics"),
        gym_class(journal, "BJJ (Gi) - Basics", day=date(2026, 10, 1)),
    ]

    journal.print_report(classes, date(2026, 10, 1), date(2026, 10, 14), "bjj")

    output = ANSI.sub("", capsys.readouterr().out)
    assert "● BJJ Gi 2\n" in output
    assert "● BJJ No-Gi 1\n" in output
    assert "● 3 classes in 2 weeks, 1.5 a week" in output


def should_flag_a_class_that_was_not_checked_in(journal, capsys):
    classes = [gym_class(journal, "BJJ (Gi) - All Levels", status="booked")]

    journal.print_report(classes, date(2026, 10, 7), date(2026, 10, 7), "")

    output = ANSI.sub("", capsys.readouterr().out)
    assert output.rstrip().endswith("● 1 class")
    assert "Coach · Studio  booked" in output


def should_print_help_without_loading_credentials(run_cli, tmp_path):
    result = run_cli("impact-journal", ["--help"], mock_bins=marker_mocks(tmp_path, "envify"))

    assert result.returncode == 0
    assert "--only TEXT" in result.stdout
    assert not (tmp_path / "calls").exists()


def should_reject_a_range_that_ends_before_it_starts(run_cli, tmp_path):
    result = run_cli("impact-journal", ["--from", "1.5.2026", "--to", "2026-04-01"],
                     mock_bins=marker_mocks(tmp_path, "envify"))

    assert result.returncode == 2
    assert "--to is before --from" in result.stderr
    assert not (tmp_path / "calls").exists()


def should_stop_before_any_request_when_envify_fails(run_cli):
    result = run_cli("impact-journal", mock_bins={"envify": 'echo "no keyguard" >&2; return 1'})

    assert result.returncode == 1
    assert "no keyguard" in result.stderr
