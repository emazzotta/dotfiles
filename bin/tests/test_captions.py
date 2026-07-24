import shutil
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def mod(load_script):
    return load_script("captions")


@pytest.fixture
def make_words(mod):
    def _make(specs):
        return [mod.Word(text=t, start=s, end=e) for t, s, e in specs]

    return _make


@pytest.fixture
def make_style(mod):
    def _make(**overrides):
        base = dict(
            font_size=60,
            outline=4,
            highlights=mod.DEFAULT_PALETTE,
            max_words=5,
            max_gap=0.6,
            play_w=1080,
            play_h=1920,
            margin_v=500,
            alignment=2,
        )
        return mod.Style(**{**base, **overrides})

    return _make


def _render_ready() -> bool:
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        return False
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True
    ).stdout
    return any(
        len(f) >= 2 and f[1] == "subtitles" for f in (l.split() for l in out.splitlines())
    )


render_integration = pytest.mark.skipif(
    not _render_ready(), reason="ffmpeg/ffprobe with libass required"
)


class TestWord:
    def should_uppercase_and_strip_trailing_punctuation_in_display(self, mod):
        assert mod.Word("world.", 0.0, 0.1).display == "WORLD"
        assert mod.Word("mid,", 0.0, 0.1).display == "MID"
        assert mod.Word("list;", 0.0, 0.1).display == "LIST"
        assert mod.Word("colon:", 0.0, 0.1).display == "COLON"

    def should_keep_exclamation_and_question_marks_in_display(self, mod):
        assert mod.Word("yes!!", 0.0, 0.1).display == "YES!!"
        assert mod.Word("what?", 0.0, 0.1).display == "WHAT?"

    def should_keep_internal_punctuation_in_display(self, mod):
        assert mod.Word("don't", 0.0, 0.1).display == "DON'T"

    def should_detect_sentence_end(self, mod):
        assert mod.Word("end.", 0.0, 0.1).ends_sentence
        assert mod.Word("really?", 0.0, 0.1).ends_sentence
        assert not mod.Word("middle", 0.0, 0.1).ends_sentence


class TestParsePalette:
    def should_parse_single_colour_to_one_element_tuple(self, mod):
        assert mod._parse_palette("#ff00aa") == ("#ff00aa",)

    def should_prepend_hash_when_missing(self, mod):
        assert mod._parse_palette("ff00aa,00ffcc") == ("#ff00aa", "#00ffcc")

    def should_trim_whitespace_around_list_items(self, mod):
        assert mod._parse_palette(" #21FF5E , #FF2E9A ") == ("#21FF5E", "#FF2E9A")

    def should_reject_invalid_hex(self, mod):
        with pytest.raises(mod.argparse.ArgumentTypeError):
            mod._parse_palette("nothex")

    def should_reject_empty_value(self, mod):
        with pytest.raises(mod.argparse.ArgumentTypeError):
            mod._parse_palette("  ")

    def should_reject_a_list_with_one_bad_colour(self, mod):
        with pytest.raises(mod.argparse.ArgumentTypeError):
            mod._parse_palette("#ff0000,bad")


class TestTranscriptKey:
    def should_vary_by_model_and_language(self, mod, tmp_path):
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"x" * 100)
        base = mod._transcript_key(video, "small", None)
        assert base != mod._transcript_key(video, "large-v3", None)
        assert base != mod._transcript_key(video, "small", "en")

    def should_be_stable_for_identical_inputs(self, mod, tmp_path):
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"x" * 100)
        assert mod._transcript_key(video, "small", None) == mod._transcript_key(
            video, "small", None
        )

    def should_change_when_file_content_size_changes(self, mod, tmp_path):
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"x" * 100)
        before = mod._transcript_key(video, "small", None)
        video.write_bytes(b"x" * 200)
        assert before != mod._transcript_key(video, "small", None)

    def should_place_key_under_transcripts_dir_as_json(self, mod, tmp_path):
        video = tmp_path / "clip.mp4"
        video.write_bytes(b"x")
        key = mod._transcript_key(video, "small", None)
        assert key.parent == mod.TRANSCRIPTS
        assert key.suffix == ".json"


class TestTranscriptCache:
    def should_round_trip_words(self, mod, tmp_path, make_words):
        words = make_words([("Hello", 0.0, 0.4), ("world.", 0.4, 0.9)])
        path = tmp_path / "t.json"
        mod._save_transcript(path, words)
        assert mod._load_transcript(path) == words

    def should_return_none_for_missing_file(self, mod, tmp_path):
        assert mod._load_transcript(tmp_path / "absent.json") is None

    def should_return_none_for_corrupt_file(self, mod, tmp_path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")
        assert mod._load_transcript(bad) is None

    def should_create_parent_directory_when_saving(self, mod, tmp_path, make_words):
        path = tmp_path / "nested" / "deeper" / "t.json"
        mod._save_transcript(path, make_words([("a", 0.0, 0.1)]))
        assert path.exists()


class TestGrouping:
    def should_split_on_max_words(self, mod, make_words):
        words = make_words([(f"w{i}", i * 0.1, i * 0.1 + 0.05) for i in range(6)])
        groups = mod.group_words(words, max_words=3, max_gap=1.0)
        assert [len(g) for g in groups] == [3, 3]

    def should_split_on_silence_gap(self, mod, make_words):
        words = make_words([("a", 0.0, 0.2), ("b", 0.3, 0.5), ("c", 2.0, 2.2)])
        groups = mod.group_words(words, max_words=10, max_gap=0.6)
        assert [[w.text for w in g] for g in groups] == [["a", "b"], ["c"]]

    def should_split_after_sentence_end(self, mod, make_words):
        words = make_words([("a", 0.0, 0.2), ("end.", 0.2, 0.4), ("b", 0.4, 0.6)])
        groups = mod.group_words(words, max_words=10, max_gap=10.0)
        assert [[w.text for w in g] for g in groups] == [["a", "end."], ["b"]]

    def should_return_single_group_when_nothing_breaks(self, mod, make_words):
        words = make_words([("a", 0.0, 0.2), ("b", 0.2, 0.4)])
        assert len(mod.group_words(words, max_words=10, max_gap=10.0)) == 1


class TestFmtTime:
    def should_format_zero(self, mod):
        assert mod._fmt_time(0.0) == "0:00:00.00"

    def should_format_hours_minutes_seconds(self, mod):
        assert mod._fmt_time(3661.5) == "1:01:01.50"

    def should_clamp_negative_to_zero(self, mod):
        assert mod._fmt_time(-5.0) == "0:00:00.00"


class TestAssColour:
    def should_convert_rgb_to_bgr_for_style_field(self, mod):
        assert mod._ass_colour("#22FF00", style_field=True) == "&H0000FF22"

    def should_convert_rgb_to_bgr_for_inline_override(self, mod):
        assert mod._ass_colour("#22FF00", style_field=False) == "&H00FF22&"

    def should_ignore_leading_hash(self, mod):
        assert mod._ass_colour("22FF00", style_field=False) == mod._ass_colour(
            "#22FF00", style_field=False
        )


class TestDialogueLine:
    def should_wrap_only_the_active_word_in_the_highlight_colour(self, mod, make_words):
        words = make_words([("one", 0, 1), ("two", 1, 2), ("three", 2, 3)])
        line = mod._dialogue_line(words, active=1, highlight="&H00FF00&")
        assert line.count("&H00FF00&") == 1
        assert "{\\c&H00FF00&" in line
        assert line.startswith("{\\r}ONE ")
        assert line.endswith(" {\\r}THREE")

    def should_apply_pop_scale_animation_to_active_word(self, mod, make_words):
        words = make_words([("one", 0, 1)])
        line = mod._dialogue_line(words, active=0, highlight="&H00FF00&")
        assert "\\fscx118\\fscy118" in line


class TestWordEnd:
    def should_end_at_next_word_start_when_not_last(self, mod, make_words):
        group = make_words([("a", 0.0, 0.3), ("b", 0.5, 0.9)])
        assert mod._word_end(group, 0, group[0], next_start=None) == 0.5

    def should_add_tail_for_last_word_without_following_group(self, mod, make_words):
        group = make_words([("a", 0.0, 0.3)])
        assert mod._word_end(group, 0, group[0], next_start=None) == pytest.approx(
            0.3 + mod.LAST_WORD_TAIL
        )

    def should_clamp_last_word_tail_to_next_group_start(self, mod, make_words):
        group = make_words([("a", 0.0, 0.3)])
        assert mod._word_end(group, 0, group[0], next_start=0.35) == 0.35


class TestBuildStyle:
    def should_derive_font_size_from_height_and_scale(self, mod):
        args = mod.parse_args(["clip.mp4", "--scale", "0.05"])
        style = mod.build_style(1080, 1920, args)
        assert style.font_size == int(1920 * 0.05)

    def should_floor_outline_at_three(self, mod):
        args = mod.parse_args(["clip.mp4", "--scale", "0.01"])
        style = mod.build_style(100, 100, args)
        assert style.outline == 3

    def should_derive_margin_from_height_and_position(self, mod):
        args = mod.parse_args(["clip.mp4", "--position", "0.25"])
        style = mod.build_style(1080, 1920, args)
        assert style.margin_v == int(1920 * 0.25)

    def should_pass_highlight_palette_through(self, mod):
        args = mod.parse_args(["clip.mp4", "--highlight", "#ff0000,#00ff00"])
        style = mod.build_style(1080, 1920, args)
        assert style.highlights == ("#ff0000", "#00ff00")


class TestBuildAss:
    def should_emit_header_with_play_resolution(self, mod, make_style, make_words):
        groups = mod.group_words(make_words([("a", 0, 1)]), 5, 0.6)
        ass = mod.build_ass(groups, make_style(play_w=1080, play_h=1920))
        assert "[Script Info]" in ass
        assert "PlayResX: 1080" in ass
        assert "PlayResY: 1920" in ass
        assert "[Events]" in ass

    def should_emit_one_dialogue_event_per_word(self, mod, make_style, make_words):
        words = make_words([(f"w{i}", i, i + 0.5) for i in range(4)])
        groups = mod.group_words(words, 2, 10.0)
        ass = mod.build_ass(groups, make_style())
        assert sum(l.startswith("Dialogue") for l in ass.splitlines()) == 4

    def should_hold_one_colour_per_line_and_advance_between_lines(
        self, mod, make_style, make_words
    ):
        words = make_words([(f"w{i}", i, i + 0.5) for i in range(8)])
        groups = mod.group_words(words, 3, 10.0)
        ass = mod.build_ass(groups, make_style(highlights=mod.DEFAULT_PALETTE))
        lines = [l for l in ass.splitlines() if l.startswith("Dialogue")]
        colour = lambda l: mod.re.search(r"\\c(&H[0-9A-F]+&)", l).group(1)
        per_group, idx = [], 0
        for group in groups:
            colours = {colour(lines[idx + j]) for j in range(len(group))}
            assert len(colours) == 1
            per_group.append(colours.pop())
            idx += len(group)
        assert per_group[0] != per_group[1] != per_group[2]

    def should_reuse_single_highlight_colour_for_every_line(
        self, mod, make_style, make_words
    ):
        words = make_words([(f"w{i}", i, i + 0.5) for i in range(6)])
        groups = mod.group_words(words, 2, 10.0)
        ass = mod.build_ass(groups, make_style(highlights=("#22FF00",)))
        colours = set(mod.re.findall(r"\\c(&H[0-9A-F]+&)", ass))
        assert colours == {"&H00FF22&"}


class TestDefaultOutput:
    def should_append_captioned_suffix_next_to_input(self, mod):
        out = mod.default_output(mod.Path("/videos/clip.mov"))
        assert out == mod.Path("/videos/clip_captioned.mp4")


class TestParseArgs:
    def should_default_max_words_to_five(self, mod):
        assert mod.parse_args(["clip.mp4"]).words == 5

    def should_default_highlight_to_rainbow_palette(self, mod):
        assert mod.parse_args(["clip.mp4"]).highlight == mod.DEFAULT_PALETTE

    def should_default_cache_enabled(self, mod):
        assert mod.parse_args(["clip.mp4"]).no_cache is False

    def should_enable_no_cache_flag(self, mod):
        assert mod.parse_args(["clip.mp4", "--no-cache"]).no_cache is True

    def should_parse_highlight_into_palette_tuple(self, mod):
        assert mod.parse_args(["clip.mp4", "--highlight", "#ff0000"]).highlight == (
            "#ff0000",
        )

    def should_default_alignment_to_top_centre(self, mod):
        assert mod.parse_args(["clip.mp4"]).alignment == 8

    def should_default_position_high_near_the_top(self, mod):
        assert mod.parse_args(["clip.mp4"]).position == 0.10

    def should_accept_bottom_centre_alignment_override(self, mod):
        assert mod.parse_args(["clip.mp4", "--alignment", "2"]).alignment == 2


class TestEmitCompletions:
    def should_print_whisper_models_one_per_line(self, mod, capsys):
        mod.emit_completions("models")
        printed = capsys.readouterr().out.split()
        assert list(mod.WHISPER_MODELS) == printed

    def should_print_alignment_values_one_to_nine(self, mod, capsys):
        mod.emit_completions("alignment")
        assert capsys.readouterr().out.split() == [str(n) for n in range(1, 10)]

    def should_print_common_languages(self, mod, capsys):
        mod.emit_completions("langs")
        assert capsys.readouterr().out.split() == list(mod.COMMON_LANGS)

    def should_print_nothing_for_unknown_field(self, mod, capsys):
        mod.emit_completions("bogus")
        assert capsys.readouterr().out == ""

    def should_route_complete_flag_through_main(self, mod, capsys):
        assert mod.main(["--complete", "models"]) == 0
        assert capsys.readouterr().out.split() == list(mod.WHISPER_MODELS)


class TestQuoteFilterPath:
    def should_single_quote_the_path(self, mod):
        assert mod._quote_filter_path(mod.Path("/a/b.ass")) == "'/a/b.ass'"

    def should_double_backslashes(self, mod):
        assert mod._quote_filter_path(mod.Path("a\\b")) == "'a\\\\b'"


class TestObtainWords:
    @pytest.fixture
    def redirect_cache(self, mod, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "TRANSCRIPTS", tmp_path / "transcripts")
        return tmp_path

    def _args(self, **overrides):
        base = dict(model="small", lang=None, no_cache=False)
        return SimpleNamespace(**{**base, **overrides})

    def should_reuse_cached_transcript_without_transcribing(
        self, mod, redirect_cache, monkeypatch, make_words
    ):
        video = redirect_cache / "clip.mp4"
        video.write_bytes(b"x")
        cached = make_words([("Hi", 0.0, 0.3)])
        mod._save_transcript(mod._transcript_key(video, "small", None), cached)

        def _boom(*_args, **_kwargs):
            raise AssertionError("transcription must not run on a cache hit")

        monkeypatch.setattr(mod, "extract_audio", _boom)
        monkeypatch.setattr(mod, "transcribe_words", _boom)

        assert mod.obtain_words(video, redirect_cache, self._args()) == cached

    def should_transcribe_and_persist_on_cache_miss(
        self, mod, redirect_cache, monkeypatch, make_words
    ):
        video = redirect_cache / "clip.mp4"
        video.write_bytes(b"x")
        produced = make_words([("New", 0.0, 0.4), ("words", 0.4, 0.9)])
        monkeypatch.setattr(mod, "extract_audio", lambda v, w: v)
        monkeypatch.setattr(mod, "transcribe_words", lambda wav, lang, model: produced)

        result = mod.obtain_words(video, redirect_cache, self._args())

        assert result == produced
        key = mod._transcript_key(video, "small", None)
        assert mod._load_transcript(key) == produced

    def should_retranscribe_when_cache_disabled(
        self, mod, redirect_cache, monkeypatch, make_words
    ):
        video = redirect_cache / "clip.mp4"
        video.write_bytes(b"x")
        stale = make_words([("Stale", 0.0, 0.3)])
        mod._save_transcript(mod._transcript_key(video, "small", None), stale)
        fresh = make_words([("Fresh", 0.0, 0.3)])
        monkeypatch.setattr(mod, "extract_audio", lambda v, w: v)
        monkeypatch.setattr(mod, "transcribe_words", lambda wav, lang, model: fresh)

        result = mod.obtain_words(video, redirect_cache, self._args(no_cache=True))

        assert result == fresh


@render_integration
@pytest.mark.slow
class TestRenderIntegration:
    def _make_video(self, path):
        subprocess.run(
            [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc=size=320x240:rate=10:duration=1",
                "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
                "-shortest", str(path),
            ],
            check=True, capture_output=True,
        )

    def _stream_count(self, path):
        out = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path),
            ],
            capture_output=True, text=True,
        ).stdout.strip()
        return out

    def should_probe_generated_video_dimensions(self, mod, tmp_path):
        video = tmp_path / "in.mp4"
        self._make_video(video)
        assert mod.probe_dimensions(video) == (320, 240)

    def should_burn_captions_into_a_playable_output(self, mod, tmp_path, make_words):
        video = tmp_path / "in.mp4"
        self._make_video(video)
        args = mod.parse_args([str(video)])
        style = mod.build_style(320, 240, args)
        words = make_words([("Hello", 0.0, 0.4), ("world", 0.4, 0.9)])
        groups = mod.group_words(words, style.max_words, style.max_gap)
        ass_path = tmp_path / "captions.ass"
        ass_path.write_text(mod.build_ass(groups, style), encoding="utf-8")
        out = tmp_path / "out.mp4"

        mod.burn(video, ass_path, tmp_path, out)

        assert out.exists() and out.stat().st_size > 0
        assert self._stream_count(out) == "video"
