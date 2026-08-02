from datetime import datetime, timedelta
from pathlib import Path

import pytest

DESTINATION_INFO = """====================================================
Name          : Crucial_4TB_TimeMachine
Kind          : Local
Mount Point   : /Volumes/Crucial_4TB_TimeMachine
ID            : 02CF3786-477C-424D-AD76-5944FB153106
"""

TWO_DESTINATIONS = DESTINATION_INFO + """====================================================
Name          : Attic NAS
Kind          : Network
URL           : smb://nas.local/backups
ID            : 9E1B0C42-1111-2222-3333-444455556666
"""

LIST_BACKUPS = (
    "/Volumes/.timemachine/43210DFB-AEEE-4BB1-856B-4FCFC4475480/"
    "2026-06-22-071617.backup/2026-06-22-071617.backup\n"
)


@pytest.fixture
def mod(load_script):
    return load_script("timemachine")


@pytest.fixture
def make_report(mod):
    def _make(trees=(), restorable=(), used=1_000, total=4_000,
              volume_name="Crucial_4TB_TimeMachine", device="disk5s3",
              is_whole_disk=False):
        destination = mod.Destination(
            name="Crucial_4TB_TimeMachine",
            kind="Local",
            identifier="02CF3786-477C-424D-AD76-5944FB153106",
            mount_point=Path("/Volumes/Crucial_4TB_TimeMachine"),
        )
        return mod.Report(
            destination=destination,
            volume=mod.Volume(device=device, name=volume_name,
                              is_whole_disk=is_whole_disk),
            usage=mod.Usage(total=total, used=used, free=total - used),
            trees=tuple(trees),
            restorable=tuple(restorable),
        )
    return _make


@pytest.fixture
def make_tree(mod):
    def _make(state, days_ago=0):
        stamp = datetime.now() - timedelta(days=days_ago)
        return mod.BackupTree(stamp=stamp, state=state)
    return _make


class TestParseTree:
    @pytest.mark.parametrize("name,expected_state", [
        ("2026-06-22-071617.backup", "BACKUP"),
        ("2023-08-02-110040.previous", "PREVIOUS"),
        ("2026-07-29-204338.interrupted", "INTERRUPTED"),
        ("2026-08-02-211915.inprogress", "IN_PROGRESS"),
    ])
    def should_recognise_every_backup_tree_suffix(self, mod, name, expected_state):
        tree = mod.parse_tree(name)

        assert tree is not None
        assert tree.state is getattr(mod.TreeState, expected_state)

    def should_extract_the_timestamp(self, mod):
        tree = mod.parse_tree("2026-06-22-071617.backup")

        assert tree.stamp == datetime(2026, 6, 22, 7, 16, 17)

    @pytest.mark.parametrize("name", [
        "backup_manifest.plist",
        ".Spotlight-V100",
        "com.apple.TimeMachine.inheritance.plist",
        "2026-06-22-071617.unknownsuffix",
        "2026-13-45-999999.backup",
        "notatimestamp.backup",
    ])
    def should_ignore_entries_that_are_not_backup_trees(self, mod, name):
        assert mod.parse_tree(name) is None


class TestTreeState:
    @pytest.mark.parametrize("state,expected", [
        ("INTERRUPTED", True),
        ("IN_PROGRESS", True),
        ("BACKUP", False),
        ("PREVIOUS", False),
    ])
    def should_flag_only_unreclaimable_trees_as_orphans(self, mod, state, expected):
        assert getattr(mod.TreeState, state).is_orphan is expected


class TestParseDestinations:
    def should_read_a_local_destination(self, mod):
        destinations = mod.parse_destinations(DESTINATION_INFO)

        assert len(destinations) == 1
        assert destinations[0].name == "Crucial_4TB_TimeMachine"
        assert destinations[0].kind == "Local"
        assert destinations[0].identifier == "02CF3786-477C-424D-AD76-5944FB153106"
        assert destinations[0].mount_point == Path("/Volumes/Crucial_4TB_TimeMachine")

    def should_read_every_configured_destination(self, mod):
        destinations = mod.parse_destinations(TWO_DESTINATIONS)

        assert [d.name for d in destinations] == ["Crucial_4TB_TimeMachine", "Attic NAS"]

    def should_leave_mount_point_unset_for_an_unmounted_destination(self, mod):
        destinations = mod.parse_destinations(TWO_DESTINATIONS)

        assert destinations[1].mount_point is None

    def should_keep_a_url_value_containing_a_colon_intact(self, mod):
        fields = mod.parse_fields("URL           : smb://nas.local/backups")

        assert fields["URL"] == "smb://nas.local/backups"

    def should_return_nothing_when_no_destination_is_configured(self, mod):
        assert mod.parse_destinations("") == ()


class TestParseStamps:
    def should_deduplicate_a_stamp_repeated_within_one_path(self, mod):
        assert mod.parse_stamps(LIST_BACKUPS) == (datetime(2026, 6, 22, 7, 16, 17),)

    def should_return_stamps_in_chronological_order(self, mod):
        text = "2026-06-22-071617\n2024-01-09-222924\n2026-01-22-133058\n"

        stamps = mod.parse_stamps(text)

        assert stamps == tuple(sorted(stamps))

    def should_return_nothing_when_there_are_no_backups(self, mod):
        assert mod.parse_stamps("") == ()


class TestFormatBytes:
    @pytest.mark.parametrize("count,expected", [
        (0, "0 B"),
        (512, "512 B"),
        (95_000_000_000, "95.0 GB"),
        (3_628_185_276_416, "3.6 TB"),
        (4_000_575_389_696, "4.0 TB"),
    ])
    def should_render_a_human_readable_size(self, mod, count, expected):
        assert mod.format_bytes(count) == expected


class TestDescribeTrees:
    def should_break_the_count_down_by_state(self, mod, make_tree):
        trees = [
            make_tree(mod.TreeState.BACKUP),
            make_tree(mod.TreeState.PREVIOUS),
            make_tree(mod.TreeState.PREVIOUS),
            make_tree(mod.TreeState.INTERRUPTED),
        ]

        assert mod.describe_trees(tuple(trees)) == (
            "4 on disk: 1 backup, 2 previous, 1 interrupted")

    def should_say_none_when_the_destination_is_empty(self, mod):
        assert mod.describe_trees(()) == "none"


class TestDiagnose:
    def should_report_a_stale_newest_backup(self, mod, make_report):
        report = make_report(restorable=[datetime.now() - timedelta(days=41)])

        findings = mod.diagnose(report)

        assert any("41 days old" in finding for finding in findings)

    def should_stay_quiet_about_a_fresh_backup(self, mod, make_report):
        report = make_report(restorable=[datetime.now() - timedelta(days=1)])

        assert not any("days old" in finding for finding in mod.diagnose(report))

    def should_report_when_no_backup_is_restorable(self, mod, make_report):
        findings = mod.diagnose(make_report(restorable=[]))

        assert any("No restorable backup" in finding for finding in findings)

    def should_report_orphaned_trees(self, mod, make_report, make_tree):
        trees = [make_tree(mod.TreeState.INTERRUPTED)] * 6
        trees.append(make_tree(mod.TreeState.IN_PROGRESS))

        findings = mod.diagnose(make_report(trees=trees))

        assert any("7 interrupted or in-progress" in finding for finding in findings)

    def should_stay_quiet_when_no_tree_is_orphaned(self, mod, make_report, make_tree):
        report = make_report(trees=[make_tree(mod.TreeState.BACKUP)])

        assert not any("interrupted" in f for f in mod.diagnose(report))

    def should_report_a_nearly_full_volume(self, mod, make_report):
        report = make_report(used=3_900, total=4_000)

        assert any("98% full" in finding for finding in mod.diagnose(report))

    def should_stay_quiet_about_a_volume_with_room(self, mod, make_report):
        report = make_report(used=2_000, total=4_000)

        assert not any("full" in finding for finding in mod.diagnose(report))

    def should_report_history_shrinking_to_a_single_backup(self, mod, make_report,
                                                           make_tree):
        report = make_report(
            restorable=[datetime.now()],
            trees=[make_tree(mod.TreeState.PREVIOUS)] * 100,
        )

        findings = mod.diagnose(report)

        assert any("pruning history aggressively" in finding for finding in findings)

    def should_stay_quiet_when_several_backups_are_restorable(self, mod, make_report,
                                                              make_tree):
        report = make_report(
            restorable=[datetime.now(), datetime.now() - timedelta(days=1)],
            trees=[make_tree(mod.TreeState.PREVIOUS)] * 100,
        )

        assert not any("pruning history" in f for f in mod.diagnose(report))


class TestVerifyErasable:
    def should_accept_a_volume_matching_its_destination(self, mod, make_report):
        mod.verify_erasable(make_report())

    def should_refuse_when_diskutil_reports_a_different_volume_name(self, mod,
                                                                    make_report):
        report = make_report(volume_name="Crucial_4TB_Manual")

        with pytest.raises(mod.CommandError, match="expected"):
            mod.verify_erasable(report)

    def should_refuse_a_whole_disk(self, mod, make_report):
        report = make_report(device="disk5", is_whole_disk=True)

        with pytest.raises(mod.CommandError, match="not a single volume"):
            mod.verify_erasable(report)

    @pytest.mark.parametrize("device", ["disk5", "disk0", "", "rdisk5s3", "disk5s3x"])
    def should_refuse_any_device_that_is_not_a_volume_slice(self, mod, make_report,
                                                            device):
        report = make_report(device=device)

        with pytest.raises(mod.CommandError, match="not a single volume"):
            mod.verify_erasable(report)


class TestSelectDestination:
    def should_return_the_only_destination_when_none_is_named(self, mod, monkeypatch):
        monkeypatch.setattr(mod, "read_destinations",
                            lambda: mod.parse_destinations(DESTINATION_INFO))

        assert mod.select_destination(None).name == "Crucial_4TB_TimeMachine"

    def should_require_a_name_when_several_are_configured(self, mod, monkeypatch):
        monkeypatch.setattr(mod, "read_destinations",
                            lambda: mod.parse_destinations(TWO_DESTINATIONS))

        with pytest.raises(mod.CommandError, match="several destinations"):
            mod.select_destination(None)

    def should_select_by_name(self, mod, monkeypatch):
        monkeypatch.setattr(mod, "read_destinations",
                            lambda: mod.parse_destinations(TWO_DESTINATIONS))

        assert mod.select_destination("Attic NAS").kind == "Network"

    def should_reject_an_unknown_destination_name(self, mod, monkeypatch):
        monkeypatch.setattr(mod, "read_destinations",
                            lambda: mod.parse_destinations(DESTINATION_INFO))

        with pytest.raises(mod.CommandError, match="not a registered"):
            mod.select_destination("Nope")

    def should_report_when_nothing_is_configured(self, mod, monkeypatch):
        monkeypatch.setattr(mod, "read_destinations", tuple)

        with pytest.raises(mod.CommandError, match="no Time Machine destination"):
            mod.select_destination(None)


class TestConfirmErase:
    def should_refuse_without_an_interactive_terminal(self, mod, monkeypatch):
        monkeypatch.setattr(mod.sys.stdin, "isatty", lambda: False)

        assert mod.confirm_erase("Crucial_4TB_TimeMachine") is False


class TestDirectoryName:
    @pytest.mark.parametrize("name", [
        "2026-06-22-071617.backup",
        "2023-08-02-110040.previous",
        "2026-07-29-204338.interrupted",
        "2026-08-02-211915.inprogress",
    ])
    def should_round_trip_with_parse_tree(self, mod, name):
        assert mod.parse_tree(name).directory_name == name


class TestSelectPrunable:
    @pytest.fixture
    def stamps(self):
        return tuple(datetime(2026, 6, day, 7, 0, 0) for day in range(1, 6))

    def should_return_nothing_when_fewer_backups_than_kept(self, mod, stamps):
        assert mod.select_prunable(stamps[:3], keep=5) == ()

    def should_return_nothing_when_exactly_the_kept_count(self, mod, stamps):
        assert mod.select_prunable(stamps, keep=5) == ()

    def should_return_the_oldest_surplus_backups(self, mod, stamps):
        assert mod.select_prunable(stamps, keep=2) == stamps[:3]

    def should_order_the_doomed_backups_oldest_first(self, mod, stamps):
        doomed = mod.select_prunable(tuple(reversed(stamps)), keep=1)

        assert doomed == tuple(sorted(doomed))

    def should_keep_only_the_newest_when_keeping_one(self, mod, stamps):
        assert mod.select_prunable(stamps, keep=1) == stamps[:4]

    def should_handle_an_empty_destination(self, mod):
        assert mod.select_prunable((), keep=3) == ()

    @pytest.mark.parametrize("keep", [0, -1])
    def should_reject_a_keep_count_below_one(self, mod, stamps, keep):
        with pytest.raises(mod.CommandError, match="at least 1"):
            mod.select_prunable(stamps, keep=keep)


class TestIsBackupRunning:
    @pytest.mark.parametrize("phase,expected", [
        ("BackupNotRunning\n", False),
        ("  BackupNotRunning  ", False),
        ("Copying\n", True),
        ("ThinningPostBackup\n", True),
        ("", True),
    ])
    def should_treat_any_phase_but_idle_as_running(self, mod, phase, expected):
        assert mod.is_backup_running(phase) is expected


class TestResolveOrphan:
    def should_return_the_path_of_an_interrupted_tree(self, mod, tmp_path, make_tree):
        tree = make_tree(mod.TreeState.INTERRUPTED)
        (tmp_path / tree.directory_name).mkdir()

        assert mod.resolve_orphan(tmp_path, tree) == tmp_path / tree.directory_name

    @pytest.mark.parametrize("state", ["BACKUP", "PREVIOUS"])
    def should_refuse_a_tree_that_is_not_orphaned(self, mod, tmp_path, make_tree, state):
        tree = make_tree(getattr(mod.TreeState, state))
        (tmp_path / tree.directory_name).mkdir()

        with pytest.raises(mod.CommandError, match="not an interrupted tree"):
            mod.resolve_orphan(tmp_path, tree)

    def should_refuse_a_symlink(self, mod, tmp_path, make_tree):
        tree = make_tree(mod.TreeState.INTERRUPTED)
        target = tmp_path / "elsewhere"
        target.mkdir()
        (tmp_path / tree.directory_name).symlink_to(target)

        with pytest.raises(mod.CommandError, match="refusing to remove"):
            mod.resolve_orphan(tmp_path, tree)

    def should_refuse_a_path_that_does_not_exist(self, mod, tmp_path, make_tree):
        with pytest.raises(mod.CommandError, match="refusing to remove"):
            mod.resolve_orphan(tmp_path, make_tree(mod.TreeState.IN_PROGRESS))

    def should_refuse_a_regular_file(self, mod, tmp_path, make_tree):
        tree = make_tree(mod.TreeState.INTERRUPTED)
        (tmp_path / tree.directory_name).write_text("not a backup")

        with pytest.raises(mod.CommandError, match="refusing to remove"):
            mod.resolve_orphan(tmp_path, tree)


class TestRemoveOrphan:
    @pytest.fixture
    def recorded_run(self, mod, monkeypatch):
        calls = []

        def _install(tmutil_fails):
            def fake_run(*args):
                calls.append(args)
                if tmutil_fails and 'tmutil' in args:
                    raise mod.CommandError("tmutil refused")
                return ""
            monkeypatch.setattr(mod, "run", fake_run)
            return calls
        return _install

    def should_ask_tmutil_first(self, mod, tmp_path, make_tree, recorded_run):
        calls = recorded_run(tmutil_fails=False)
        tree = make_tree(mod.TreeState.INTERRUPTED)
        (tmp_path / tree.directory_name).mkdir()

        mod.remove_orphan(tmp_path, tree)

        assert len(calls) == 1
        assert calls[0][:4] == ('sudo', 'tmutil', 'delete', '-p')

    def should_fall_back_to_removing_the_tree_when_tmutil_refuses(
            self, mod, tmp_path, make_tree, recorded_run):
        calls = recorded_run(tmutil_fails=True)
        tree = make_tree(mod.TreeState.INTERRUPTED)
        directory = tmp_path / tree.directory_name
        directory.mkdir()

        mod.remove_orphan(tmp_path, tree)

        assert calls[1] == ('sudo', '/bin/rm', '-rf', str(directory))

    def should_keep_deleting_after_one_tree_fails(self, mod, tmp_path, make_tree,
                                                  monkeypatch, capsys):
        good = make_tree(mod.TreeState.INTERRUPTED, days_ago=1)
        missing = make_tree(mod.TreeState.INTERRUPTED, days_ago=2)
        (tmp_path / good.directory_name).mkdir()
        monkeypatch.setattr(mod, "run", lambda *args: "")

        mod.delete_orphans(tmp_path, (missing, good))

        assert good.directory_name in capsys.readouterr().out


class TestLocalSnapshots:
    LISTING = ("Snapshots for volume group containing disk /:\n"
               "com.apple.TimeMachine.2026-08-02-211912.local\n"
               "com.apple.TimeMachine.2026-08-01-104500.local\n")

    @pytest.fixture
    def deletions(self, mod, monkeypatch):
        recorded = []
        monkeypatch.setattr(mod, "delete_local_snapshots",
                            lambda: recorded.append("deleted"))
        return recorded

    def should_delete_every_snapshot_in_a_single_call(self, mod, monkeypatch):
        calls = []
        monkeypatch.setattr(mod, "run", lambda *args: calls.append(args) or "")

        mod.delete_local_snapshots()

        assert calls == [('sudo', 'tmutil', 'deletelocalsnapshots', '/')]

    def should_skip_deletion_when_nothing_is_listed(self, mod, monkeypatch, deletions,
                                                    capsys):
        monkeypatch.setattr(mod, "run", lambda *args: "")

        mod.purge_local_snapshots(skip_confirmation=True)

        assert not deletions
        assert "No local snapshots" in capsys.readouterr().out

    def should_delete_without_asking_when_confirmation_is_skipped(self, mod, monkeypatch,
                                                                  deletions):
        monkeypatch.setattr(mod, "run", lambda *args: self.LISTING)

        mod.purge_local_snapshots(skip_confirmation=True)

        assert deletions == ["deleted"]

    def should_not_delete_when_the_user_declines(self, mod, monkeypatch, deletions):
        monkeypatch.setattr(mod, "run", lambda *args: self.LISTING)
        monkeypatch.setattr(mod, "confirm", lambda question: False)

        mod.purge_local_snapshots(skip_confirmation=False)

        assert not deletions

    def should_list_both_snapshots_from_the_tmutil_output(self, mod):
        assert len(mod.parse_stamps(self.LISTING)) == 2


class TestComplete:
    def should_print_every_destination_name(self, mod, monkeypatch, capsys):
        monkeypatch.setattr(mod, "read_destinations",
                            lambda: mod.parse_destinations(TWO_DESTINATIONS))

        mod.complete("destinations")

        assert capsys.readouterr().out.splitlines() == [
            "Crucial_4TB_TimeMachine", "Attic NAS"]

    def should_print_nothing_for_an_unknown_field(self, mod, capsys):
        mod.complete("nonsense")

        assert capsys.readouterr().out == ""

    def should_stay_silent_when_the_destination_lookup_fails(self, mod, monkeypatch,
                                                             capsys):
        def explode():
            raise mod.CommandError("tmutil is not available")

        monkeypatch.setattr(mod, "read_destinations", explode)

        assert mod.complete("destinations") == 0
        assert capsys.readouterr().out == ""


class TestExecute:
    def should_raise_a_readable_error_when_the_binary_is_missing(self, mod):
        with pytest.raises(mod.CommandError, match="needs macOS"):
            mod.run("definitely-not-a-real-binary")

    def should_raise_a_readable_error_when_a_command_fails(self, mod):
        with pytest.raises(mod.CommandError, match="failed"):
            mod.run("false")
