import array
import fcntl
import hashlib
import importlib.util
import io
import json
import os
import re
import resource
import shutil
import subprocess
import sys
import time
import types
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from bin.tests.conftest import BIN_DIR, requires_tool

GIB = 1024 ** 3
SCRIPT = BIN_DIR / "wt-transcribe"
SPEECH_FIXTURE = Path(__file__).parent / "data" / "jfk-ask-not.ogg"
REAL_STORE = Path(os.environ.get("WT_TRANSCRIBE_MODELS") or Path.home() / ".local/share/wt-transcribe/models")
PLUCKED_TONES = ("aevalsrc=0.5*exp(-6*mod(t\\,0.5))*(sin(2*PI*262*t)+0.5*sin(2*PI*392*t)+0.3*sin(2*PI*523*t))"
                 ":d=15:s=16000")
requires_ffmpeg = requires_tool("ffmpeg")


@pytest.fixture
def mod(load_script):
    return load_script("wt-transcribe")


@pytest.fixture(autouse=True)
def sandbox(monkeypatch, tmp_path):
    monkeypatch.setenv("WT_TRANSCRIBE_LOCK", str(tmp_path / "run.lock"))
    monkeypatch.setenv("WT_TRANSCRIBE_MODELS", str(tmp_path / "models"))
    monkeypatch.setattr(os, "nice", lambda increment: 0)


class FakeEngine:
    def __init__(self, mod, filtered=(), unfiltered=(), level=-20.0, probabilities=None):
        self.filtered = [mod.Segment(start, text) for start, text in filtered]
        self.unfiltered = [mod.Segment(start, text) for start, text in unfiltered]
        self.level = level
        self.probabilities = probabilities or {}
        self.passes = []
        self.received = []
        self.detections = 0
        self.levels = 0
        self.consumed = 0

    def detect_language(self, samples):
        self.detections += 1
        self.received.append(samples)
        return self.probabilities

    def segments(self, samples, language, vad_filter):
        self.passes.append((language, vad_filter))
        self.received.append(samples)
        for segment in self.filtered if vad_filter else self.unfiltered:
            self.consumed += 1
            yield segment

    def level_db(self, samples):
        self.levels += 1
        return self.level


def silence(mod, seconds):
    return mod.Samples(bytes(int(seconds * 16000) * 4))


def said(*texts):
    return [(float(index), text) for index, text in enumerate(texts)]


def tone_file(tmp_path, name, *codec):
    path = tmp_path / name
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1:sample_rate=44100",
                    *codec, str(path)], check=True)
    return path


def floats(samples):
    values = array.array("f")
    values.frombytes(samples.raw)
    return values


class Untouchable:
    @property
    def buffer(self):
        raise AssertionError("stdin was read")


@contextmanager
def held_lock(path):
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        yield
    finally:
        os.close(descriptor)


def memory_files(tmp_path, monkeypatch, mod, limit, current=0, inactive=0, available=None):
    cgroup = tmp_path / "cgroup"
    cgroup.mkdir(exist_ok=True)
    (cgroup / "memory.max").write_text(f"{limit}\n")
    (cgroup / "memory.current").write_text(f"{current}\n")
    (cgroup / "memory.stat").write_text(f"anon 1\ninactive_file {inactive}\nactive_file 7\n")
    meminfo = tmp_path / "meminfo"
    meminfo.write_text("MemTotal: 16000000 kB\n" + (f"MemAvailable: {available // 1024} kB\n" if available else ""))
    monkeypatch.setattr(mod, "CGROUP_DIR", cgroup)
    monkeypatch.setattr(mod, "MEMINFO", meminfo)


def with_plenty_of_memory(monkeypatch, mod):
    monkeypatch.setattr(mod, "free_bytes", lambda cgroup, meminfo: 64 * GIB)


def store_model(tmp_path, name="small"):
    (tmp_path / "models" / name).mkdir(parents=True)


def run_main(mod, monkeypatch, capfd, args, audio=b""):
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(audio)))
    code = mod.main(args)
    captured = capfd.readouterr()
    return code, captured.out, captured.err


def ready_run(mod, monkeypatch, tmp_path, engine, samples=None, model="small"):
    with_plenty_of_memory(monkeypatch, mod)
    store_model(tmp_path, model)
    monkeypatch.setattr(mod, "WhisperEngine", lambda model_dir: engine)
    monkeypatch.setattr(mod, "decode", lambda audio: samples or silence(mod, 2))


def stub_faster_whisper(monkeypatch, mod, detected=("de", 0.9, [("de", 0.9), ("en", 0.1)])):
    class RecordingModel:
        instances = []

        def __init__(self, path, **options):
            self.path, self.options, self.calls = path, options, []
            RecordingModel.instances.append(self)

        def transcribe(self, audio, **options):
            self.calls.append((audio, options))
            return iter([types.SimpleNamespace(start=0.5, text=" Hallo Welt")]), None

        def detect_language(self, audio, **options):
            self.calls.append((audio, options))
            if isinstance(detected, Exception):
                raise detected
            return detected

    library = types.ModuleType("faster_whisper")
    library.WhisperModel = RecordingModel
    monkeypatch.setitem(sys.modules, "faster_whisper", library)
    return RecordingModel


def stub_numpy(monkeypatch):
    class Array:
        def __init__(self, raw):
            self.raw = raw

    library = types.ModuleType("numpy")
    library.frombuffer = lambda raw, dtype: Array(raw)
    monkeypatch.setitem(sys.modules, "numpy", library)
    return Array


class TestAnswer:
    def should_answer_the_filtered_pass_when_it_has_words(self, mod):
        engine = FakeEngine(mod, filtered=said("Hello there.", " how are you "))

        verdict = mod.transcribe_audio(engine, silence(mod, 5), "en")

        assert (verdict, engine.passes, engine.levels) == (mod.Verdict("Hello there. how are you", False),
                                                           [("en", True)], 0)

    @pytest.mark.parametrize("level", [-50.1, -80.0, float("-inf")])
    def should_answer_no_speech_for_quiet_audio_without_a_second_pass(self, mod, level):
        engine = FakeEngine(mod, unfiltered=said("Thank you."), level=level)

        verdict = mod.transcribe_audio(engine, silence(mod, 5), "en")

        assert (verdict, engine.passes) == (mod.Verdict("", False), [("en", True)])

    @pytest.mark.parametrize("seconds,level", [(5, -20.0), (5, -50.0), (60, -20.0)])
    def should_run_the_second_pass_only_for_loud_audio_without_words(self, mod, seconds, level):
        engine = FakeEngine(mod, unfiltered=said("Bye"), level=level)

        mod.transcribe_audio(engine, silence(mod, seconds), "de")

        assert engine.passes == [("de", True), ("de", False)]

    @pytest.mark.parametrize("seconds", [60.1, 61, 300])
    def should_run_no_second_pass_on_audio_over_60_seconds(self, mod, seconds):
        engine = FakeEngine(mod, unfiltered=said("Thank you."), level=-10.0)

        verdict = mod.transcribe_audio(engine, silence(mod, seconds), "en")

        assert (verdict, engine.passes) == (mod.Verdict("", False), [("en", True)])

    def should_flag_the_text_of_the_second_pass_as_low_confidence(self, mod):
        engine = FakeEngine(mod, unfiltered=said("Thanks", "for watching"))

        verdict = mod.transcribe_audio(engine, silence(mod, 5), "en")

        assert verdict == mod.Verdict("Thanks for watching", True)

    def should_answer_no_speech_when_the_second_pass_has_no_text(self, mod):
        engine = FakeEngine(mod, unfiltered=said("", "  "))

        verdict = mod.transcribe_audio(engine, silence(mod, 5), "en")

        assert verdict == mod.Verdict("", False)

    def should_answer_no_speech_and_stop_reading_when_the_second_pass_loops(self, mod):
        engine = FakeEngine(mod, unfiltered=said("Hello", *["Thank you."] * 10))

        verdict = mod.transcribe_audio(engine, silence(mod, 30), "en")

        assert (verdict, engine.consumed) == (mod.Verdict("", False), 4)

    def should_not_call_a_phrase_a_loop_unless_it_repeats_three_times_in_a_row(self, mod):
        engine = FakeEngine(mod, unfiltered=said("Yes.", "No.", "Yes.", "No.", "Yes.", "Yes."))

        verdict = mod.transcribe_audio(engine, silence(mod, 30), "en")

        assert verdict == mod.Verdict("Yes. No. Yes. No. Yes. Yes.", True)

    @pytest.mark.parametrize("text,seconds,flagged", [
        ("ask not now", 10.5, True),
        ("ask", 11, True),
        ("ask not now please", 11, False),
        ("ask not now", 10, False),
        ("ask not now", 5, False),
    ])
    def should_flag_at_most_three_words_only_from_a_recording_over_10_seconds(self, mod, text, seconds, flagged):
        engine = FakeEngine(mod, filtered=said(text))

        verdict = mod.transcribe_audio(engine, silence(mod, seconds), "en")

        assert verdict == mod.Verdict(text, flagged)

    def should_flag_three_words_from_a_long_recording_as_low_confidence(self, mod):
        engine = FakeEngine(mod, filtered=said("one two three"))

        verdict = mod.transcribe_audio(engine, silence(mod, 30), "en")

        assert verdict.low_confidence is True

    def should_not_flag_three_words_from_a_short_recording(self, mod):
        engine = FakeEngine(mod, filtered=said("one two three"))

        verdict = mod.transcribe_audio(engine, silence(mod, 4), "en")

        assert verdict.low_confidence is False

    def should_drop_segments_that_start_after_the_audio_ends(self, mod):
        engine = FakeEngine(mod, filtered=[(1.0, "Hello world"), (5.0, "Thank you"), (7.0, "Thank you")])

        verdict = mod.transcribe_audio(engine, silence(mod, 5), "en")

        assert verdict.text == "Hello world"

    def should_drop_second_pass_segments_that_start_after_the_audio_ends(self, mod):
        engine = FakeEngine(mod, unfiltered=[(1.0, "Hello"), (5.0, "Thank you"), (6.0, "Thank you"), (7.0, "Thank you")])

        verdict = mod.transcribe_audio(engine, silence(mod, 5), "en")

        assert verdict == mod.Verdict("Hello", True)

    def should_hand_the_model_samples_and_never_a_path(self, mod):
        engine = FakeEngine(mod, filtered=said("Hello world"))
        samples = silence(mod, 2)

        mod.transcribe_audio(engine, samples, "en")

        assert [type(received) for received in engine.received] == [mod.Samples]

    def should_hand_faster_whisper_the_array_of_samples_and_never_a_path(self, mod, monkeypatch, tmp_path):
        recording = stub_faster_whisper(monkeypatch, mod)
        array_type = stub_numpy(monkeypatch)
        engine = mod.WhisperEngine(tmp_path)
        samples = silence(mod, 1)

        list(engine.segments(samples, "en", True))
        engine.detect_language(samples)

        audios = [audio for audio, options in recording.instances[0].calls]
        assert [type(audio) for audio in audios] == [array_type, array_type]
        assert all(audio.raw == samples.raw for audio in audios)

    def should_ask_faster_whisper_for_one_filtered_beam_search_pass(self, mod, monkeypatch, tmp_path):
        recording = stub_faster_whisper(monkeypatch, mod)
        stub_numpy(monkeypatch)
        engine = mod.WhisperEngine(tmp_path)

        segments = list(engine.segments(silence(mod, 1), "it", False))

        assert (segments, recording.instances[0].calls[0][1]) == (
            [mod.Segment(0.5, " Hallo Welt")], {"language": "it", "vad_filter": False, "beam_size": 5})

    def should_load_the_model_from_local_files_only(self, mod, monkeypatch, tmp_path):
        recording = stub_faster_whisper(monkeypatch, mod)
        stub_numpy(monkeypatch)

        mod.WhisperEngine(tmp_path / "small")

        assert (recording.instances[0].path, recording.instances[0].options) == (
            str(tmp_path / "small"),
            {"device": "cpu", "compute_type": "int8", "cpu_threads": 4, "local_files_only": True})

    def should_refuse_as_not_installed_when_faster_whisper_cannot_be_imported(self, mod, monkeypatch, tmp_path):
        stub_numpy(monkeypatch)
        monkeypatch.setitem(sys.modules, "faster_whisper", None)

        with pytest.raises(mod.Refusal) as refusal:
            mod.WhisperEngine(tmp_path)

        assert refusal.value.code.value == "not_installed"

    def should_measure_the_level_of_all_samples_in_decibels_below_full_scale(self, mod, monkeypatch, tmp_path):
        pytest.importorskip("numpy", reason="numpy is not in the dotfiles test environment")
        stub_faster_whisper(monkeypatch, mod)
        engine = mod.WhisperEngine(tmp_path)
        constant = mod.Samples(array.array("f", [0.1] * 16000).tobytes())

        levels = (engine.level_db(constant), engine.level_db(silence(mod, 1)))

        assert (round(levels[0], 3), levels[1]) == (-20.0, float("-inf"))


class TestLanguage:
    def should_force_the_language_when_one_code_is_given(self, mod):
        engine = FakeEngine(mod, probabilities={"en": 0.9})

        language = mod.choose_language(engine, silence(mod, 1), ("de",))

        assert (language, engine.detections) == (mod.Language("de", 1.0), 0)

    def should_pick_the_listed_language_with_the_highest_probability(self, mod):
        engine = FakeEngine(mod, probabilities={"fr": 0.6, "de": 0.2, "it": 0.15, "en": 0.05})

        language = mod.choose_language(engine, silence(mod, 1), ("en", "de", "it"))

        assert (language, engine.detections) == (mod.Language("de", 0.2), 1)

    @pytest.mark.parametrize("probabilities,expected", [
        ({}, ("en", 0.0)),
        ({"fr": 0.9}, ("en", 0.0)),
        ({"de": 0.4, "en": 0.4, "it": 0.2}, ("en", 0.4)),
    ])
    def should_take_the_first_listed_language_when_detection_gives_nothing(self, mod, probabilities, expected):
        engine = FakeEngine(mod, probabilities=probabilities)

        language = mod.choose_language(engine, silence(mod, 1), ("en", "de", "it"))

        assert (language.code, language.probability) == expected

    def should_take_the_first_listed_language_when_the_detection_has_no_speech_to_hear(self, mod, monkeypatch, tmp_path):
        stub_faster_whisper(monkeypatch, mod, detected=ValueError("need at least one array to concatenate"))
        stub_numpy(monkeypatch)
        engine = mod.WhisperEngine(tmp_path)

        language = mod.choose_language(engine, silence(mod, 1), ("it", "de"))

        assert language == mod.Language("it", 0.0)

    def should_answer_in_the_language_it_chose(self, mod):
        engine = FakeEngine(mod, filtered=said("Guten Tag"), probabilities={"de": 0.8, "en": 0.1})
        samples = silence(mod, 3)

        language = mod.choose_language(engine, samples, ("en", "de"))
        mod.transcribe_audio(engine, samples, language.code)

        assert engine.passes == [("de", True)]

    @pytest.mark.parametrize("arguments", [
        ["--model", "huge"],
        ["--language", "xx"],
        ["--language", "en,xx"],
        ["--language", "en,de,it,fr,es,pt"],
        ["--language", ""],
        ["--time-limit", "0"],
        ["--time-limit", "soon"],
        ["--fetch", "huge"],
    ])
    def should_refuse_a_model_or_a_language_it_does_not_know(self, run_cli, tmp_path, arguments):
        result = run_cli("wt-transcribe", arguments, isolate_path=True, stdin="")

        assert (result.returncode, result.stdout, result.stderr.splitlines()[-1].startswith("wt-transcribe: error:")) == (
            2, "", True)

    def should_accept_one_to_five_known_language_codes(self, mod):
        assert [mod.language_list(codes) for codes in ("de", "en,de,it,fr,es")] == [
            ("de",), ("en", "de", "it", "fr", "es")]


class TestGuards:
    def should_refuse_as_busy_while_another_run_holds_the_lock(self, run_cli, tmp_path):
        with held_lock(tmp_path / "run.lock"):
            result = run_cli("wt-transcribe", ["--model", "tiny"], isolate_path=True, stdin="audio")

        assert (result.returncode, json.loads(result.stdout)["refused"], result.stdout.count("\n")) == (3, "busy", 1)

    def should_release_the_lock_when_the_run_ends(self, mod, tmp_path):
        with mod.exclusive_run():
            pass

        with mod.exclusive_run():
            with pytest.raises(mod.Refusal):
                with mod.exclusive_run():
                    pass

    @pytest.mark.parametrize("temp_folder", ["/var/tmp", "/dev/shm", "/home/somebody/tmp"])
    def should_use_one_lock_path_whatever_the_temp_folder_is(self, mod, monkeypatch, temp_folder):
        monkeypatch.delenv("WT_TRANSCRIBE_LOCK")
        monkeypatch.setenv("TMPDIR", temp_folder)

        assert mod.lock_path() == Path(f"/tmp/wt-transcribe-{os.getuid()}.lock")

    @pytest.mark.parametrize("model,needed_gib", [("tiny", 2.5), ("base", 2.75), ("small", 3.0)])
    def should_refuse_when_less_than_two_gib_plus_the_model_budget_is_free(
            self, mod, monkeypatch, tmp_path, model, needed_gib):
        needed = int(needed_gib * GIB)
        memory_files(tmp_path, monkeypatch, mod, limit=needed - GIB // 4)

        with pytest.raises(mod.Refusal) as refusal:
            mod.require_free_memory(model)

        assert (refusal.value.code.value, refusal.value.detail) == (
            "low_memory", f"{needed_gib - 0.25:.2f} GiB free, {needed_gib:.2f} GiB needed for {model}")

    @pytest.mark.parametrize("model,needed_gib", [("tiny", 2.5), ("base", 2.75), ("small", 3.0)])
    def should_accept_exactly_the_free_memory_it_needs(self, mod, monkeypatch, tmp_path, model, needed_gib):
        memory_files(tmp_path, monkeypatch, mod, limit=int(needed_gib * GIB))

        mod.require_free_memory(model)

    def should_count_the_inactive_file_cache_as_free(self, mod, monkeypatch, tmp_path):
        memory_files(tmp_path, monkeypatch, mod, limit=6 * GIB, current=5 * GIB, inactive=3 * GIB)

        mod.require_free_memory("small")

    def should_count_the_used_memory_that_is_not_inactive_file_cache(self, mod, monkeypatch, tmp_path):
        memory_files(tmp_path, monkeypatch, mod, limit=6 * GIB, current=5 * GIB, inactive=1 * GIB)

        with pytest.raises(mod.Refusal, match="2.00 GiB free"):
            mod.require_free_memory("tiny")

    def should_use_memavailable_when_the_limit_reads_max(self, mod, monkeypatch, tmp_path):
        memory_files(tmp_path, monkeypatch, mod, limit="max", current=15 * GIB, available=4 * GIB)

        mod.require_free_memory("small")

    def should_refuse_on_memavailable_when_the_limit_reads_max(self, mod, monkeypatch, tmp_path):
        memory_files(tmp_path, monkeypatch, mod, limit="max", available=2 * GIB)

        with pytest.raises(mod.Refusal, match="2.00 GiB free, 3.00 GiB needed"):
            mod.require_free_memory("small")

    def should_refuse_when_free_memory_cannot_be_read(self, mod, monkeypatch, tmp_path):
        monkeypatch.setattr(mod, "CGROUP_DIR", tmp_path / "no-cgroup")
        monkeypatch.setattr(mod, "MEMINFO", tmp_path / "no-meminfo")

        with pytest.raises(mod.Refusal) as refusal:
            mod.require_free_memory("tiny")

        assert (refusal.value.code.value, "cannot be read" in refusal.value.detail) == ("low_memory", True)

    def should_refuse_when_the_limit_is_a_number_and_the_use_cannot_be_read(self, mod, monkeypatch, tmp_path):
        memory_files(tmp_path, monkeypatch, mod, limit=64 * GIB, available=64 * GIB)
        (tmp_path / "cgroup" / "memory.current").unlink()

        with pytest.raises(mod.Refusal, match="cannot be read"):
            mod.require_free_memory("tiny")

    def should_refuse_a_model_that_is_not_in_the_store_and_name_the_fetch_command(
            self, mod, monkeypatch, tmp_path, capfd):
        with_plenty_of_memory(monkeypatch, mod)

        code, out, err = run_main(mod, monkeypatch, capfd, ["--model", "base"])

        refusal = json.loads(out)
        assert (code, refusal["refused"], "wt-transcribe --fetch base" in refusal["detail"]) == (3, "model_missing", True)

    @pytest.mark.parametrize("guard", ["busy", "low_memory", "model_missing"])
    def should_check_lock_memory_and_model_before_it_reads_the_audio(self, mod, monkeypatch, tmp_path, capfd, guard):
        store_model(tmp_path, "tiny")
        with_plenty_of_memory(monkeypatch, mod)
        if guard == "low_memory":
            monkeypatch.setattr(mod, "free_bytes", lambda cgroup, meminfo: 1)
        if guard == "model_missing":
            shutil.rmtree(tmp_path / "models" / "tiny")
        monkeypatch.setattr(sys, "stdin", Untouchable())

        with held_lock(tmp_path / "run.lock") if guard == "busy" else nullcontext():
            code = mod.main(["--model", "tiny"])

        assert (code, json.loads(capfd.readouterr().out)["refused"]) == (3, guard)

    def should_lower_its_own_priority_before_the_work(self, mod, monkeypatch, tmp_path, capfd):
        nices = []
        monkeypatch.setattr(os, "nice", nices.append)
        ready_run(mod, monkeypatch, tmp_path, FakeEngine(mod, filtered=said("Hi there")))

        run_main(mod, monkeypatch, capfd, ["--model", "small"])

        assert nices == [10]

    def should_refuse_input_over_20_mb(self, mod, monkeypatch, tmp_path, capfd):
        decoded = []
        ready_run(mod, monkeypatch, tmp_path, FakeEngine(mod))
        monkeypatch.setattr(mod, "decode", decoded.append)

        code, out, err = run_main(mod, monkeypatch, capfd, [], audio=bytes(20 * 1024 * 1024 + 1))

        assert (code, json.loads(out)["refused"], decoded) == (3, "too_large", [])

    def should_read_input_of_exactly_20_mb(self, mod):
        stream = io.BytesIO(bytes(20 * 1024 * 1024))

        assert len(mod.read_audio(stream)) == 20 * 1024 * 1024

    def should_refuse_audio_over_the_length_cap(self, mod):
        at_the_cap = mod.Samples(bytes(600 * 16000 * 4))
        over_the_cap = mod.Samples(bytes((600 * 16000 + 1) * 4))

        mod.require_length(at_the_cap)
        with pytest.raises(mod.Refusal) as refusal:
            mod.require_length(over_the_cap)

        assert refusal.value.code.value == "too_long"

    def should_refuse_audio_over_the_length_cap_before_the_model_loads(self, mod, monkeypatch, tmp_path, capfd):
        built = []
        ready_run(mod, monkeypatch, tmp_path, FakeEngine(mod), samples=mod.Samples(bytes((600 * 16000 + 1) * 4)))
        monkeypatch.setattr(mod, "WhisperEngine", built.append)

        code, out, err = run_main(mod, monkeypatch, capfd, [], audio=b"audio")

        assert (code, json.loads(out)["refused"], built) == (3, "too_long", [])

    @requires_ffmpeg
    def should_refuse_bytes_that_are_no_audio(self, mod, monkeypatch, tmp_path, capfd):
        built = []
        with_plenty_of_memory(monkeypatch, mod)
        store_model(tmp_path)
        monkeypatch.setattr(mod, "WhisperEngine", built.append)

        code, out, err = run_main(mod, monkeypatch, capfd, [], audio=b"this is not audio at all")

        assert (code, json.loads(out)["refused"], built) == (3, "no_audio", [])

    def should_report_a_missing_ffmpeg_as_a_failure_with_nothing_on_stdout(self, mod, monkeypatch, tmp_path, capfd):
        with_plenty_of_memory(monkeypatch, mod)
        store_model(tmp_path)
        monkeypatch.setenv("PATH", str(tmp_path / "empty"))

        code, out, err = run_main(mod, monkeypatch, capfd, [], audio=b"audio")

        assert (code, out, err) == (127, "", "wt-transcribe: ffmpeg is not installed\n")

    def should_end_itself_and_ffmpeg_at_the_time_limit(self, mod, monkeypatch, tmp_path, capfd):
        bin_dir = tmp_path / "fake-bin"
        bin_dir.mkdir()
        (bin_dir / "ffmpeg").write_text(f'#!/bin/bash\necho $$ > "{tmp_path}/ffmpeg.pid"\nexec sleep 30\n')
        (bin_dir / "ffmpeg").chmod(0o755)
        monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
        with_plenty_of_memory(monkeypatch, mod)
        store_model(tmp_path)
        started = time.monotonic()

        code, out, err = run_main(mod, monkeypatch, capfd, ["--time-limit", "1"], audio=b"audio")

        pid = int((tmp_path / "ffmpeg.pid").read_text())
        assert (code, json.loads(out)["refused"], time.monotonic() - started < 10) == (3, "timeout", True)
        with pytest.raises(ProcessLookupError):
            os.kill(pid, 0)

    def should_disarm_the_time_limit_when_the_run_ends(self, mod):
        import signal

        with mod.time_limit(5):
            pass

        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)


class TestOutput:
    def should_print_one_json_line_and_nothing_else(self, mod, monkeypatch, tmp_path, capfd):
        class Noisy(FakeEngine):
            def segments(self, samples, language, vad_filter):
                os.write(1, b"native noise on stdout\n")
                return super().segments(samples, language, vad_filter)

        ready_run(mod, monkeypatch, tmp_path, Noisy(mod, filtered=said("Ask not what", "your country")), model="base")

        code, out, err = run_main(mod, monkeypatch, capfd, ["--model", "base", "--language", "en"])

        line = json.loads(out)
        assert (code, out.count("\n"), list(line), line["text"], line["model"], line["seconds"]) == (
            0, 1, ["text", "language", "language_probability", "low_confidence", "seconds", "model", "elapsed", "peak_mb"],
            "Ask not what your country", "base", 2.0)
        assert "noise on stdout" in err

    def should_report_the_language_the_model_and_the_peak_memory(self, mod, monkeypatch, tmp_path, capfd):
        engine = FakeEngine(mod, filtered=said("Guten Tag"), probabilities={"de": 0.876, "en": 0.1})
        ready_run(mod, monkeypatch, tmp_path, engine)

        code, out, err = run_main(mod, monkeypatch, capfd, [])

        line = json.loads(out)
        assert (line["language"], line["language_probability"], line["model"], line["low_confidence"],
                isinstance(line["peak_mb"], int) and line["peak_mb"] > 0, line["elapsed"] >= 0) == (
            "de", 0.88, "small", False, True, True)

    def should_keep_a_transcript_with_umlauts_on_one_ascii_line(self, mod, monkeypatch, tmp_path, capfd):
        ready_run(mod, monkeypatch, tmp_path, FakeEngine(mod, filtered=said("Grüezi mitenand")))

        code, out, err = run_main(mod, monkeypatch, capfd, ["--language", "de"])

        assert (out.isascii(), json.loads(out)["text"]) == (True, "Grüezi mitenand")

    def should_never_print_the_transcript_to_stderr(self, mod, monkeypatch, tmp_path, capfd):
        ready_run(mod, monkeypatch, tmp_path, FakeEngine(mod, filtered=said("a secret sentence")))

        code, out, err = run_main(mod, monkeypatch, capfd, [])

        assert "secret" not in err

    @pytest.mark.parametrize("platform,reported,megabytes", [("linux", 780_000, 762), ("darwin", 799_000_000, 762)])
    def should_read_the_peak_in_kilobytes_on_linux_and_bytes_on_macos(
            self, mod, monkeypatch, platform, reported, megabytes):
        monkeypatch.setattr(sys, "platform", platform)
        monkeypatch.setattr(resource, "getrusage", lambda who: types.SimpleNamespace(ru_maxrss=reported))

        assert mod.peak_mb() == megabytes

    def should_exit_3_with_one_json_line_for_a_refusal(self, run_cli, tmp_path):
        with held_lock(tmp_path / "run.lock"):
            result = run_cli("wt-transcribe", [], isolate_path=True, stdin="")

        assert (result.returncode, result.stdout, result.stderr) == (
            3, '{"refused": "busy", "detail": "another transcription is running"}\n', "")

    def should_show_help_without_touching_lock_memory_or_model(self, mod, monkeypatch, tmp_path, capsys):
        def touched(*arguments):
            raise AssertionError("a guard ran")

        for name in ("exclusive_run", "require_free_memory", "require_model", "WhisperEngine", "free_bytes"):
            monkeypatch.setattr(mod, name, touched)

        with pytest.raises(SystemExit) as stop:
            mod.main(["--help"])

        assert (stop.value.code, capsys.readouterr().out.startswith("usage: wt-transcribe"),
                (tmp_path / "run.lock").exists()) == (0, True, False)

    def should_print_its_usage_on_help_under_the_system_python(self, run_cli):
        result = run_cli("wt-transcribe", ["--help"], isolate_path=True)

        assert (result.returncode, result.stdout.startswith("usage: wt-transcribe"), "--fetch" in result.stdout) == (
            0, True, True)


class TestFetch:
    @pytest.fixture
    def downloads(self, mod, monkeypatch):
        calls = []

        def download(name, folder):
            calls.append((name, folder))
            (folder / "model.bin").write_bytes(b"model weights")

        monkeypatch.setattr(mod, "download_files", download)
        monkeypatch.setitem(mod.MODEL_SHA256, "tiny", hashlib.sha256(b"model weights").hexdigest())
        return calls

    def should_download_only_in_fetch_mode_and_into_the_store(self, mod, monkeypatch, tmp_path, capfd, downloads):
        with_plenty_of_memory(monkeypatch, mod)

        code, out, err = run_main(mod, monkeypatch, capfd, ["--model", "tiny"])
        refused = (list(downloads), json.loads(out)["refused"])
        fetched = run_main(mod, monkeypatch, capfd, ["--fetch", "tiny"])

        assert (refused, fetched[0], len(downloads), (tmp_path / "models" / "tiny" / "model.bin").read_bytes()) == (
            ([], "model_missing"), 0, 1, b"model weights")
        assert downloads[0][1].parent == tmp_path

    def should_leave_nothing_but_the_models_in_the_store_and_beside_it(self, mod, tmp_path, capfd, downloads, monkeypatch):
        run_main(mod, monkeypatch, capfd, ["--fetch", "tiny"])

        assert (sorted(path.name for path in tmp_path.iterdir() if path.name != "run.lock"),
                [path.name for path in (tmp_path / "models").iterdir()]) == (["models"], ["tiny"])

    def should_read_no_stdin_in_fetch_mode(self, mod, monkeypatch, tmp_path, capfd, downloads):
        monkeypatch.setattr(sys, "stdin", Untouchable())

        code = mod.main(["--fetch", "tiny"])

        assert code == 0

    def should_remove_a_download_whose_checksum_differs_and_show_both_values(
            self, mod, monkeypatch, tmp_path, capfd, downloads):
        wanted = hashlib.sha256(b"another file").hexdigest()
        monkeypatch.setitem(mod.MODEL_SHA256, "tiny", wanted)

        code, out, err = run_main(mod, monkeypatch, capfd, ["--fetch", "tiny"])

        assert code == 1
        assert wanted in err and hashlib.sha256(b"model weights").hexdigest() in err
        assert sorted(path.name for path in tmp_path.iterdir() if path.name != "run.lock") == ["models"]
        assert list((tmp_path / "models").iterdir()) == []

    def should_check_a_model_again_that_is_already_in_the_store(self, mod, monkeypatch, tmp_path, capfd, downloads):
        store_model(tmp_path, "tiny")
        (tmp_path / "models" / "tiny" / "model.bin").write_bytes(b"model weights")

        code, out, err = run_main(mod, monkeypatch, capfd, ["--fetch", "tiny"])

        assert (code, downloads, "tiny: checksum matches" in out) == (0, [], True)

    def should_report_a_stored_model_with_a_wrong_checksum_and_keep_it(self, mod, monkeypatch, tmp_path, capfd, downloads):
        store_model(tmp_path, "tiny")
        (tmp_path / "models" / "tiny" / "model.bin").write_bytes(b"damaged")

        code, out, err = run_main(mod, monkeypatch, capfd, ["--fetch", "tiny"])

        assert code == 1
        assert hashlib.sha256(b"damaged").hexdigest() in err and mod.MODEL_SHA256["tiny"] in err
        assert (downloads, (tmp_path / "models" / "tiny" / "model.bin").read_bytes()) == ([], b"damaged")

    def should_report_a_stored_model_without_a_model_file_as_bad(self, mod, monkeypatch, tmp_path, capfd, downloads):
        store_model(tmp_path, "tiny")

        code, out, err = run_main(mod, monkeypatch, capfd, ["--fetch", "tiny"])

        assert (code, "unreadable" in err, downloads) == (1, True, [])

    def should_fetch_each_model_it_is_given_and_fail_when_one_is_bad(self, mod, monkeypatch, tmp_path, capfd, downloads):
        monkeypatch.setitem(mod.MODEL_SHA256, "base", "0" * 64)

        code, out, err = run_main(mod, monkeypatch, capfd, ["--fetch", "tiny", "base"])

        assert (code, sorted(path.name for path in (tmp_path / "models").iterdir())) == (1, ["tiny"])

    def should_pin_the_checksum_of_each_model_in_the_script(self, mod):
        assert mod.MODEL_SHA256 == {
            "tiny": "dcb76c6586fc06cbdac6dd21f14cfd129cc4cdd9dce19bf4ffa62e59cbe6e6d1",
            "base": "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9",
            "small": "3e305921506d8872816023e4c273e75d2419fb89b24da97b4fe7bce14170d671",
        }

    def should_fail_with_text_on_stderr_when_the_download_raises(self, mod, monkeypatch, tmp_path, capfd):
        def broken(name, folder):
            raise OSError("network is down")

        monkeypatch.setattr(mod, "download_files", broken)

        code, out, err = run_main(mod, monkeypatch, capfd, ["--fetch", "tiny"])

        assert (code, "network is down" in err, list((tmp_path / "models").iterdir())) == (1, True, [])


@requires_ffmpeg
class TestDecode:
    def should_decode_an_m4a_and_an_ogg_to_16_khz_mono_float_samples(self, mod, tmp_path):
        files = [tone_file(tmp_path, "tone.m4a", "-ac", "2", "-c:a", "aac"),
                 tone_file(tmp_path, "tone.ogg", "-c:a", "libvorbis")]

        decoded = [mod.decode(path.read_bytes()) for path in files]

        for samples in decoded:
            values = floats(samples)
            assert 15000 <= len(values) <= 17500
            assert 0.1 < max(values) <= 1.0 and min(values) >= -1.0

    def should_decode_through_a_pipe_where_no_memory_file_exists(self, mod, monkeypatch, tmp_path):
        monkeypatch.delattr(os, "memfd_create", raising=False)
        audio = tone_file(tmp_path, "tone.ogg", "-c:a", "libvorbis").read_bytes()

        samples = mod.decode(audio)

        assert 15000 <= samples.count <= 17500

    def should_decode_through_a_memory_file_where_one_exists(self, mod, monkeypatch, tmp_path):
        if not hasattr(os, "memfd_create"):
            pytest.skip("os.memfd_create does not exist on this system")
        opened = []
        original = os.memfd_create
        monkeypatch.setattr(os, "memfd_create", lambda name: opened.append(name) or original(name))
        audio = tone_file(tmp_path, "tone.m4a", "-c:a", "aac").read_bytes()

        samples = mod.decode(audio)

        assert (opened, 15000 <= samples.count <= 17500) == (["wt-transcribe"], True)

    def should_stop_decoding_a_long_file_at_the_length_cap_plus_one_second(self, mod, monkeypatch):
        monkeypatch.setattr(mod, "MAX_AUDIO_SECONDS", 1)
        longer = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=5", "-f", "ogg", "pipe:1"],
                                capture_output=True, check=True).stdout

        samples = mod.decode(longer)

        assert 1.9 < samples.seconds < 2.1

    def should_leave_no_file_behind_but_the_lock(self, mod, monkeypatch, tmp_path, capfd):
        temp, work = tmp_path / "tmp", tmp_path / "work"
        temp.mkdir()
        work.mkdir()
        monkeypatch.setenv("TMPDIR", str(temp))
        monkeypatch.setattr(mod.tempfile, "tempdir", None)
        monkeypatch.chdir(work)
        with_plenty_of_memory(monkeypatch, mod)
        store_model(tmp_path)
        monkeypatch.setattr(mod, "WhisperEngine", lambda model_dir: FakeEngine(mod, filtered=said("Hello world")))
        audio = tone_file(tmp_path, "tone.ogg", "-c:a", "libvorbis").read_bytes()
        before = sorted(path.name for path in tmp_path.iterdir())

        code, out, err = run_main(mod, monkeypatch, capfd, [], audio=audio)

        assert (code, list(temp.iterdir()), list(work.iterdir())) == (0, [], [])
        assert sorted(path.name for path in tmp_path.iterdir()) == sorted([*before, "run.lock"])


def real_model_for(mod):
    missing = [name for name in ("faster_whisper", "numpy") if importlib.util.find_spec(name) is None]
    if missing:
        pytest.skip(f"{', '.join(missing)} is not installed for {sys.executable}")
    if shutil.which("ffmpeg") is None:
        pytest.skip("ffmpeg is not installed")
    free = mod.free_bytes(mod.CGROUP_DIR, mod.MEMINFO)
    for name in reversed(mod.MODELS):
        if (REAL_STORE / name).is_dir() and free is not None and free >= mod.needed_bytes(name):
            return name
    pytest.skip(f"no model of {', '.join(mod.MODELS)} in {REAL_STORE} fits the free memory ({free})")


def transcribe_for_real(audio, model):
    environment = {**os.environ, "WT_TRANSCRIBE_MODELS": str(REAL_STORE)}
    done = subprocess.run([sys.executable, str(SCRIPT), "--model", model], input=audio, capture_output=True,
                          env=environment, timeout=600)
    assert done.returncode == 0, done.stderr.decode()
    return json.loads(done.stdout)


@pytest.mark.slow
class TestWithARealModel:
    def should_hear_the_expected_words_in_the_speech_fixture(self, mod):
        model = real_model_for(mod)

        heard = transcribe_for_real(SPEECH_FIXTURE.read_bytes(), model)

        words = re.sub(r"[^a-z ]", "", heard["text"].lower())
        assert "ask not what your country can do for you" in words
        assert (heard["language"], heard["low_confidence"], heard["model"]) == ("en", False, model)

    def should_never_answer_the_music_fixture_with_confidence(self, mod):
        model = real_model_for(mod)
        music = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", PLUCKED_TONES, "-c:a", "libopus",
                                "-f", "ogg", "pipe:1"], capture_output=True, check=True).stdout

        heard = transcribe_for_real(music, model)

        assert heard["text"] == "" or heard["low_confidence"] is True
