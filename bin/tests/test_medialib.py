import os
import re
import signal
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

FFMPEG_OK = 'touch "${@: -1}"'
FFMPEG_FAILS_ON_MARKED = 'case "$*" in *zzfail*) exit 1;; esac\n' + FFMPEG_OK
FFMPEG_LEAVES_PARTIAL_AND_FAILS = 'touch "${@: -1}"\nexit 1'
FFMPEG_WRITES_NEW = 'printf new > "${@: -1}"'
FFMPEG_INTERRUPTED_ON_MARKED = (
    'for last; do :; done\n'
    'case "$last" in *zzstop*) printf partial > "$last"; kill -INT "$PPID"; exec sleep 10;; esac\n'
    'touch "$last"'
)
GUM_MARKER = 'echo called >> "$MARKER"'
SIGINT_IGNORED = signal.getsignal(signal.SIGINT) == signal.SIG_IGN

BULLETS = {
    "\033[1m\033[34m\u25cf\033[0m": "[info]",
    "\033[1m\033[32m\u25cf\033[0m": "[ok]",
    "\033[1m\033[31m\u25cf\033[0m": "[err]",
}
DURATION = re.compile(r"\d+m \d+s|\d+\.\ds")


def _fake_gum(stdout):
    return lambda *args, **kwargs: SimpleNamespace(stdout=stdout, returncode=0)


@pytest.fixture
def mod(load_script):
    return load_script("medialib.py")


@pytest.fixture
def answer(mod):
    def _answer(response):
        prompts = []
        mod.input = lambda prompt: prompts.append(prompt) or response
        return prompts
    return _answer


class TestFormatTime:
    @pytest.mark.parametrize("seconds,expected", [
        (0.0, "0.0s"),
        (30.5, "30.5s"),
        (59.9, "59.9s"),
        (60.0, "1m 0s"),
        (90.0, "1m 30s"),
        (3661.0, "61m 1s"),
    ])
    def test_should_format_a_duration(self, mod, seconds, expected):
        assert mod.format_time(seconds) == expected


class TestListInputs:
    def test_should_return_the_file_itself_when_given_a_file(self, mod, tmp_path):
        track = tmp_path / "song.mp3"
        track.touch()

        assert mod.list_inputs(track, mod.AUDIO_EXTS) == [track]

    def test_should_return_a_file_whose_extension_is_not_listed(self, mod, tmp_path):
        document = tmp_path / "notes.txt"
        document.touch()

        assert mod.list_inputs(document, mod.AUDIO_EXTS) == [document]

    def test_should_find_only_the_listed_extensions_in_a_directory(self, mod, tmp_path):
        for name in ("a.mp3", "b.flac", "c.wav", "d.txt", "e.mp4"):
            (tmp_path / name).touch()

        names = {path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)}

        assert names == {"a.mp3", "b.flac", "c.wav"}

    def test_should_match_uppercase_extensions(self, mod, tmp_path):
        (tmp_path / "loud.WAV").touch()

        assert [path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)] == ["loud.WAV"]

    def test_should_search_recursively(self, mod, tmp_path):
        nested = tmp_path / "sub" / "deeper"
        nested.mkdir(parents=True)
        (nested / "buried.mp3").touch()

        assert [path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)] == ["buried.mp3"]

    def test_should_return_results_sorted(self, mod, tmp_path):
        for name in ("c.mp3", "a.mp3", "b.mp3"):
            (tmp_path / name).touch()

        assert [path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)] == ["a.mp3", "b.mp3", "c.mp3"]

    def test_should_return_nothing_for_an_empty_directory(self, mod, tmp_path):
        assert mod.list_inputs(tmp_path, mod.AUDIO_EXTS) == []

    def test_should_exit_when_the_path_does_not_exist(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.list_inputs(tmp_path / "nonexistent", mod.AUDIO_EXTS)

    @pytest.mark.parametrize("folder", ["[2020] Album", "[abc]", "Best of *"])
    def test_should_search_a_directory_whose_name_has_glob_characters(self, mod, tmp_path, folder):
        album = tmp_path / folder
        (album / "disc 1").mkdir(parents=True)
        (album / "disc 1" / "track.mp3").touch()

        assert [path.name for path in mod.list_inputs(album, mod.AUDIO_EXTS)] == ["track.mp3"]

    def test_should_skip_hidden_files_and_folders(self, mod, tmp_path):
        (tmp_path / ".hidden").mkdir()
        (tmp_path / ".hidden" / "buried.mp3").touch()
        (tmp_path / "._resource-fork.mp3").touch()
        (tmp_path / "song.mp3").touch()

        assert [path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)] == ["song.mp3"]


class TestCollectInputs:
    def test_should_gather_every_path_when_many_inputs_are_given(self, mod, tmp_path):
        first = tmp_path / "a.wav"
        second = tmp_path / "b.flac"
        first.touch()
        second.touch()

        assert mod.collect_inputs([first, second], mod.AUDIO_EXTS) == [first, second]

    def test_should_keep_each_file_once_when_inputs_overlap(self, mod, tmp_path):
        track = tmp_path / "track.wav"
        track.touch()

        assert mod.collect_inputs([tmp_path, track], mod.AUDIO_EXTS) == [track]

    def test_should_return_nothing_for_no_inputs(self, mod):
        assert mod.collect_inputs([], mod.AUDIO_EXTS) == []

    def test_should_exit_when_an_input_is_missing(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.collect_inputs([tmp_path / "nonexistent.wav"], mod.AUDIO_EXTS)


class TestResolveOutputPath:
    def test_should_place_output_next_to_the_input_by_default(self, mod, tmp_path):
        source = tmp_path / "song.wav"
        source.touch()

        result = mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

        assert result == tmp_path / "song.mp3"

    def test_should_place_output_in_the_given_directory(self, mod, tmp_path):
        source = tmp_path / "song.wav"
        source.touch()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = mod.resolve_output_path(source, out_dir, mod.OutputNaming(extension=".flac"))

        assert result == out_dir / "song.flac"

    def test_should_apply_the_name_suffix_and_keep_the_extension(self, mod, tmp_path):
        source = tmp_path / "song.wav"
        source.touch()

        result = mod.resolve_output_path(
            source, None, mod.OutputNaming(extension=".wav", name_suffix="_boosted",
                                           conflict_suffix="_boosted"))

        assert result == tmp_path / "song_boosted.wav"

    def test_should_overwrite_when_the_answer_is_yes(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        (tmp_path / "song.mp3").touch()
        answer("y")

        result = mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

        assert result == tmp_path / "song.mp3"

    def test_should_abort_when_the_answer_is_abort(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        (tmp_path / "song.mp3").touch()
        answer("a")

        with pytest.raises(SystemExit):
            mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

    def test_should_add_the_conflict_suffix_when_the_answer_is_no(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        (tmp_path / "song.mp3").touch()
        answer("n")

        result = mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

        assert result == tmp_path / "song_converted.mp3"

    def test_should_escalate_the_counter_while_names_are_taken(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        for name in ("song.mp3", "song_converted.mp3", "song_converted_2.mp3"):
            (tmp_path / name).touch()
        answer("n")

        result = mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

        assert result == tmp_path / "song_converted_3.mp3"

    def test_should_name_the_actual_conflict_suffix_in_the_prompt(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        (tmp_path / "song_loud.wav").touch()
        prompts = answer("y")

        mod.resolve_output_path(source, None,
                                mod.OutputNaming(extension=".wav", name_suffix="_loud",
                                                 conflict_suffix="_loud"))

        assert "N=add _loud" in prompts[0]


class TestFindInCwd:
    def test_should_find_only_matching_extensions_in_the_current_directory(self, mod, tmp_path, monkeypatch):
        for name in ("a.mp3", "b.flac", "skip.txt"):
            (tmp_path / name).touch()
        monkeypatch.chdir(tmp_path)

        assert [path.name for path in mod.find_in_cwd(mod.AUDIO_EXTS)] == ["a.mp3", "b.flac"]

    def test_should_not_descend_into_subdirectories(self, mod, tmp_path, monkeypatch):
        (tmp_path / "top.mp3").touch()
        nested = tmp_path / "sub"
        nested.mkdir()
        (nested / "buried.mp3").touch()
        monkeypatch.chdir(tmp_path)

        assert [path.name for path in mod.find_in_cwd(mod.AUDIO_EXTS)] == ["top.mp3"]

    def test_should_match_uppercase_extensions(self, mod, tmp_path, monkeypatch):
        (tmp_path / "loud.WAV").touch()
        monkeypatch.chdir(tmp_path)

        assert [path.name for path in mod.find_in_cwd(mod.AUDIO_EXTS)] == ["loud.WAV"]


class TestResolveInputsOrPick:
    def test_should_return_the_sole_candidate_without_prompting(self, mod, tmp_path, monkeypatch):
        (tmp_path / "only.wav").touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(mod, "can_prompt", lambda: pytest.fail("must not prompt for one file"))

        result = mod.resolve_inputs_or_pick(mod.AUDIO_EXTS, "audio")

        assert [path.name for path in result] == ["only.wav"]

    def test_should_exit_when_no_candidate_matches(self, mod, tmp_path, monkeypatch):
        (tmp_path / "notes.txt").touch()
        monkeypatch.chdir(tmp_path)

        with pytest.raises(SystemExit):
            mod.resolve_inputs_or_pick(mod.AUDIO_EXTS, "audio")

    def test_should_exit_when_several_match_but_prompting_is_impossible(self, mod, tmp_path, monkeypatch):
        for name in ("a.wav", "b.wav"):
            (tmp_path / name).touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(mod, "can_prompt", lambda: False)

        with pytest.raises(SystemExit):
            mod.resolve_inputs_or_pick(mod.AUDIO_EXTS, "audio")

    def test_should_return_every_candidate_when_the_user_picks_convert_all(self, mod, tmp_path, monkeypatch):
        for name in ("a.wav", "b.wav"):
            (tmp_path / name).touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(mod, "can_prompt", lambda: True)
        monkeypatch.setattr(mod.subprocess, "run", _fake_gum("Convert all (2)"))

        result = mod.resolve_inputs_or_pick(mod.AUDIO_EXTS, "audio")

        assert [path.name for path in result] == ["a.wav", "b.wav"]

    def test_should_return_only_the_chosen_file_when_the_user_picks_one(self, mod, tmp_path, monkeypatch):
        for name in ("a.wav", "b.wav"):
            (tmp_path / name).touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(mod, "can_prompt", lambda: True)
        monkeypatch.setattr(mod.subprocess, "run", _fake_gum("b.wav"))

        result = mod.resolve_inputs_or_pick(mod.AUDIO_EXTS, "audio")

        assert [path.name for path in result] == ["b.wav"]

    def test_should_exit_when_the_picker_selects_nothing(self, mod, tmp_path, monkeypatch):
        for name in ("a.wav", "b.wav"):
            (tmp_path / name).touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(mod, "can_prompt", lambda: True)
        monkeypatch.setattr(mod.subprocess, "run", _fake_gum(""))

        with pytest.raises(SystemExit):
            mod.resolve_inputs_or_pick(mod.AUDIO_EXTS, "audio")


class TestPickFromWithTheRealPicker:
    def test_should_leave_the_menu_on_the_terminal_and_read_only_the_choice(
        self, mod, tmp_path, monkeypatch, create_mock_bin, capfd
    ):
        for name in ("a.wav", "b.wav"):
            (tmp_path / name).touch()
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(mod, "can_prompt", lambda: True)
        gum = create_mock_bin("gum", 'echo "MENU: $*" >&2\necho b.wav')
        monkeypatch.setenv("PATH", f"{gum.parent}:{os.environ['PATH']}")

        result = mod.pick_from([tmp_path / "a.wav", tmp_path / "b.wav"], "audio")

        assert [path.name for path in result] == ["b.wav"]
        assert "MENU: choose" in capfd.readouterr().err


@dataclass(frozen=True)
class Script:
    name: str
    options: tuple
    kind: str
    input_ext: str
    task: str
    doing: str
    done: str
    output: str
    conflict_output: str
    conflict_hint: str


SCRIPTS = [
    Script("audiotox", ("-f", "mp3"), "audio", "wav", "convert", "Converting", "Converted",
           "{stem}.mp3", "{stem}_converted.mp3", "_converted"),
    Script("videotox", ("-f", "mp4"), "video", "mov", "convert", "Converting", "Converted",
           "{stem}.mp4", "{stem}_converted.mp4", "_converted"),
    Script("audioboost", (), "audio", "wav", "boost at 2.0x volume", "Boosting", "Boosted",
           "{stem}_boosted.wav", "{stem}_boosted_2.wav", "_boosted"),
]


def _readable(text, work):
    for bullet, tag in BULLETS.items():
        text = text.replace(bullet, tag)
    return DURATION.sub("<T>", text.replace(str(work.resolve()), "<work>"))


def _expected_stdout(script, stems, failed=()):
    total = len(stems)
    text = f"[info] Found {total} {script.kind} file(s) to {script.task}\n"
    for number, stem in enumerate(stems, 1):
        source = f"{stem}.{script.input_ext}"
        output = script.output.format(stem=stem)
        text += f"[info] \n[{number}/{total}] {script.doing}: {source} -> {output}\n\n\n"
        if stem not in failed:
            text += f"[ok] {script.done} in <T>: {source} -> {output}\n"
    return text + (f"\n[info] Summary: {total - len(failed)} succeeded, "
                   f"{len(failed)} failed, {total} total in <T>\n")


def _overwrite_prompt(script, output):
    return (f"File exists: <work>/{output}\nOverwrite? [y/N/a] "
            f"(N=add {script.conflict_hint}, a=abort): ")


@pytest.fixture(params=SCRIPTS, ids=lambda script: script.name)
def script(request):
    return request.param


@pytest.fixture
def work(tmp_path):
    folder = tmp_path / "work"
    folder.mkdir()
    return folder


@pytest.fixture
def batch(run_cli, script, work):
    def _run(stems, *options, ffmpeg=FFMPEG_OK, stdin=None):
        inputs = []
        for stem in stems:
            source = work / f"{stem}.{script.input_ext}"
            source.touch()
            inputs.append(str(source))
        return run_cli(script.name, [*script.options, *options, "-i", *inputs],
                       mock_bins={"ffmpeg": ffmpeg}, stdin=stdin, cwd=work)
    return _run


def _listing(folder):
    return sorted(path.name for path in folder.iterdir())


class TestBatchFlowOfTheScripts:
    def test_should_convert_one_file_and_report_it(self, script, work, batch):
        result = batch(["one"])

        assert result.returncode == 0
        assert _readable(result.stdout, work) == _expected_stdout(script, ["one"])
        assert result.stderr == ""
        assert _listing(work) == sorted([f"one.{script.input_ext}", script.output.format(stem="one")])

    def test_should_print_the_exact_report_of_one_file(self, script, work, batch):
        result = batch(["one"])

        output = script.output.format(stem="one")
        assert _readable(result.stdout, work) == (
            f"[info] Found 1 {script.kind} file(s) to {script.task}\n"
            "[info] \n"
            f"[1/1] {script.doing}: one.{script.input_ext} -> {output}\n"
            "\n"
            "\n"
            f"[ok] {script.done} in <T>: one.{script.input_ext} -> {output}\n"
            "\n"
            "[info] Summary: 1 succeeded, 0 failed, 1 total in <T>\n"
        )

    def test_should_convert_several_files_in_the_order_given(self, script, work, batch):
        stems = ["three", "one", "two"]

        result = batch(stems)

        assert result.returncode == 0
        assert _readable(result.stdout, work) == _expected_stdout(script, stems)
        assert result.stderr == ""
        assert _listing(work) == sorted(
            [f"{stem}.{script.input_ext}" for stem in stems]
            + [script.output.format(stem=stem) for stem in stems])

    def test_should_go_on_and_count_the_failure_when_one_file_fails_among_good_ones(self, script, work, batch):
        stems = ["one", "zzfail", "three"]

        result = batch(stems, ffmpeg=FFMPEG_FAILS_ON_MARKED)

        assert result.returncode == 0
        assert _readable(result.stdout, work) == _expected_stdout(script, stems, failed=["zzfail"])
        assert _readable(result.stderr, work) == f"[err] Failed: zzfail.{script.input_ext}\n"
        assert _listing(work) == sorted(
            [f"{stem}.{script.input_ext}" for stem in stems]
            + [script.output.format(stem=stem) for stem in ("one", "three")])

    def test_should_exit_zero_and_report_every_failure_when_all_files_fail(self, script, work, batch):
        stems = ["zzfail1", "zzfail2"]

        result = batch(stems, ffmpeg=FFMPEG_FAILS_ON_MARKED)

        assert result.returncode == 0
        assert _readable(result.stdout, work) == _expected_stdout(script, stems, failed=stems)
        assert result.stderr.count("Failed: ") == 2

    def test_should_leave_the_partial_output_when_ffmpeg_fails_after_writing(self, script, work, batch):
        result = batch(["one"], ffmpeg=FFMPEG_LEAVES_PARTIAL_AND_FAILS)

        assert result.returncode == 0
        assert (work / script.output.format(stem="one")).exists()
        assert f"Failed: one.{script.input_ext}" in result.stderr

    def test_should_delete_the_original_only_when_its_conversion_succeeded(self, script, work, batch):
        stems = ["one", "zzfail"]

        result = batch(stems, "-d", ffmpeg=FFMPEG_FAILS_ON_MARKED)

        assert result.returncode == 0
        assert _listing(work) == sorted(
            [f"zzfail.{script.input_ext}", script.output.format(stem="one")])

    def test_should_keep_every_original_without_the_delete_option(self, script, work, batch):
        result = batch(["one", "two"])

        assert result.returncode == 0
        assert (work / f"one.{script.input_ext}").exists()
        assert (work / f"two.{script.input_ext}").exists()

    def test_should_create_the_output_directory_and_write_into_it(self, script, work, batch):
        out_dir = work / "made" / "deeper"

        result = batch(["one"], "-o", str(out_dir))

        assert result.returncode == 0
        assert _listing(out_dir) == [script.output.format(stem="one")]
        assert _listing(work) == sorted(["made", f"one.{script.input_ext}"])

    def test_should_create_the_output_directory_even_when_no_input_is_found(self, script, work, run_cli):
        empty = work / "empty"
        empty.mkdir()
        out_dir = work / "made"

        result = run_cli(script.name, [*script.options, "-o", str(out_dir), "-i", str(empty)],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 1
        assert out_dir.is_dir()
        assert result.stdout == ""
        assert _readable(result.stderr, work) == f"[err] No {script.kind} files found\n"

    def test_should_report_a_missing_input_and_exit_one(self, script, work, run_cli):
        result = run_cli(script.name, [*script.options, "-i", str(work / "ghost.wav")],
                         mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 1
        assert result.stdout == ""
        assert _readable(result.stderr, work) == "[err] Input not found: <work>/ghost.wav\n"

    def test_should_say_no_files_were_found_when_the_current_directory_has_none(self, script, work, run_cli):
        (work / "notes.txt").touch()

        result = run_cli(script.name, list(script.options), mock_bins={"ffmpeg": FFMPEG_OK}, cwd=work)

        assert result.returncode == 1
        assert result.stdout == ""
        assert _readable(result.stderr, work) == (
            f"[err] No {script.kind} files in <work>\n")

    def test_should_not_start_the_picker_when_several_files_match_and_no_terminal_exists(
        self, script, work, run_cli, tmp_path
    ):
        for stem in ("one", "two"):
            (work / f"{stem}.{script.input_ext}").touch()
        marker = tmp_path / "gum_calls"

        result = run_cli(script.name, list(script.options),
                         mock_bins={"ffmpeg": FFMPEG_OK, "gum": GUM_MARKER},
                         env_extra={"MARKER": str(marker)}, cwd=work)

        assert result.returncode == 1
        assert not marker.exists()
        assert _readable(result.stderr, work) == (
            f"[err] Several {script.kind} files here; pass -i to choose\n")

    @pytest.mark.skipif(SIGINT_IGNORED, reason="SIGINT is ignored here, so no KeyboardInterrupt can be raised")
    def test_should_stop_on_an_interrupt_without_summary_and_leave_the_partial_output(self, script, work, batch):
        stems = ["one", "zzstop", "three"]

        result = batch(stems, ffmpeg=FFMPEG_INTERRUPTED_ON_MARKED)

        assert result.returncode == -signal.SIGINT
        assert "KeyboardInterrupt" in result.stderr
        assert "Summary" not in result.stdout
        assert f"{script.done} in" in result.stdout
        assert (work / script.output.format(stem="one")).exists()
        assert (work / script.output.format(stem="zzstop")).read_text() == "partial"
        assert not (work / script.output.format(stem="three")).exists()
        assert (work / f"zzstop.{script.input_ext}").exists()


class TestOverwriteHandlingOfTheScripts:
    @staticmethod
    def _existing_output(script, work, stem="one"):
        existing = work / script.output.format(stem=stem)
        existing.write_text("old")
        return existing

    def test_should_overwrite_the_existing_output_when_the_answer_is_yes(self, script, work, batch):
        existing = self._existing_output(script, work)

        result = batch(["one"], ffmpeg=FFMPEG_WRITES_NEW, stdin="y\n")

        assert result.returncode == 0
        assert existing.read_text() == "new"
        assert _readable(result.stdout, work) == (
            f"[info] Found 1 {script.kind} file(s) to {script.task}\n"
            + _overwrite_prompt(script, existing.name)
            + _expected_stdout(script, ["one"]).split("\n", 1)[1])

    def test_should_write_beside_the_existing_output_when_the_answer_is_no(self, script, work, batch):
        existing = self._existing_output(script, work)

        result = batch(["one"], ffmpeg=FFMPEG_WRITES_NEW, stdin="n\n")

        assert result.returncode == 0
        assert existing.read_text() == "old"
        assert (work / script.conflict_output.format(stem="one")).read_text() == "new"
        assert f"-> {script.conflict_output.format(stem='one')}\n" in result.stdout

    def test_should_treat_any_other_answer_as_no(self, script, work, batch):
        existing = self._existing_output(script, work)

        result = batch(["one"], ffmpeg=FFMPEG_WRITES_NEW, stdin="maybe\n")

        assert result.returncode == 0
        assert existing.read_text() == "old"
        assert (work / script.conflict_output.format(stem="one")).read_text() == "new"

    def test_should_abort_the_whole_run_when_the_answer_is_abort(self, script, work, batch):
        existing = self._existing_output(script, work, stem="two")

        result = batch(["one", "two", "three"], ffmpeg=FFMPEG_WRITES_NEW, stdin="a\n")

        assert result.returncode == 1
        assert _readable(result.stderr, work) == "[err] Aborted\n"
        assert "Summary" not in result.stdout
        assert existing.read_text() == "old"
        assert (work / script.output.format(stem="one")).read_text() == "new"
        assert not (work / script.output.format(stem="three")).exists()
        assert not (work / script.conflict_output.format(stem="two")).exists()

    def test_should_fail_with_a_traceback_when_the_prompt_gets_no_answer(self, script, work, batch):
        existing = self._existing_output(script, work)

        result = batch(["one"], ffmpeg=FFMPEG_WRITES_NEW, stdin="")

        assert result.returncode == 1
        assert "EOFError" in result.stderr
        assert existing.read_text() == "old"
        assert "Summary" not in result.stdout
