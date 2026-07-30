import math
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
def make_box(mod):
    def _make(**overrides):
        base = dict(pad_x=15, rounding=20, scale_y=100, margin_v=500, alignment=8)
        return mod.Box(**{**base, **overrides})

    return _make


@pytest.fixture
def make_style(mod, make_box):
    def _make(**overrides):
        base = dict(
            font_size=60,
            outline=4,
            glow_outline=6,
            glow_blur=3,
            spacing=0,
            highlights=mod.DEFAULT_PALETTE,
            max_words=5,
            max_gap=0.6,
            play_w=1080,
            play_h=1920,
            margin_v=500,
            alignment=2,
            mode=mod.Highlight.FILL,
            pop=mod.NO_POP,
            font=mod.FONTS["anton"],
            box=make_box(),
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


class TestPopTags:
    def should_animate_towards_the_requested_scale(self, mod):
        assert mod._pop_tags(106) == "\\fscx100\\fscy100\\t(0,140,\\fscx106\\fscy106)"

    def should_emit_nothing_when_pop_is_disabled(self, mod):
        assert mod._pop_tags(mod.NO_POP) == ""

    def should_pop_from_the_squashed_height_rather_than_full_size(self, mod):
        assert mod._pop_tags(110, scale_y=80) == (
            "\\fscx100\\fscy80\\t(0,140,\\fscx110\\fscy88)"
        )


def _font(mod, **overrides):
    base = dict(family="F", path="ofl/f/F.ttf", scale=0.05)
    return mod.Font(**{**base, **overrides})


class TestInkTop:
    def should_measure_a_top_anchored_line_down_from_the_margin(self, mod):
        font = _font(mod, ink_top=0.20, ink_bottom=0.10)

        assert mod._ink_top(100, font, 8, margin_v=200, play_h=1920) == 220

    def should_measure_a_bottom_anchored_line_up_from_the_frame_edge(self, mod):
        font = _font(mod, ink_top=0.20, ink_bottom=0.10)

        assert mod._ink_top(100, font, 2, margin_v=200, play_h=1920) == 1640

    def should_centre_a_middle_anchored_line_and_ignore_the_margin(self, mod):
        font = _font(mod, ink_top=0.20, ink_bottom=0.10)

        assert mod._ink_top(100, font, 5, margin_v=200, play_h=1920) == 930


class TestBuildBox:
    def should_wrap_the_ink_band_in_padding_on_every_side(self, mod):
        box = mod._build_box(200, ink_top=1000.0, ink_height=100.0, alignment=2)

        pad = 100 * mod.BOX_PAD_Y_RATIO - box.rounding * mod.BOX_BLEED_RATIO
        assert box.margin_v == round(1000 - pad)
        assert box.scale_y == round(100 * math.sqrt((100 + 2 * pad) / 200))

    def should_discount_the_padding_by_the_softening_it_bleeds(self, mod):
        box = mod._build_box(200, ink_top=1000.0, ink_height=100.0, alignment=2)

        bleed = box.rounding * mod.BOX_BLEED_RATIO
        assert box.pad_x == round(100 * mod.BOX_PAD_X_RATIO - bleed)

    @pytest.mark.parametrize(
        "alignment,expected", [(1, 7), (2, 8), (3, 9), (4, 7), (5, 8), (6, 9), (9, 9)]
    )
    def should_anchor_the_box_to_the_top_of_its_own_column(
        self, mod, alignment, expected
    ):
        box = mod._build_box(200, ink_top=500.0, ink_height=100.0, alignment=alignment)

        assert box.alignment == expected

    def should_never_squash_past_the_floor(self, mod):
        box = mod._build_box(4000, ink_top=100.0, ink_height=10.0, alignment=2)

        assert box.scale_y == mod.MIN_BOX_SCALE

    def should_keep_the_box_on_screen_for_a_line_near_the_top_edge(self, mod):
        box = mod._build_box(200, ink_top=2.0, ink_height=100.0, alignment=8)

        assert box.margin_v == 0


class TestFillLine:
    def should_wrap_only_the_active_word_in_the_highlight_colour(
        self, mod, make_words, make_style
    ):
        words = make_words([("one", 0, 1), ("two", 1, 2), ("three", 2, 3)])
        line = mod._fill_line(words, 1, "&H00FF00&", make_style())
        assert line.count("&H00FF00&") == 1
        assert "{\\c&H00FF00&" in line
        assert line.startswith("{\\r}ONE ")
        assert line.endswith(" {\\r}THREE")

    def should_apply_pop_scale_animation_to_active_word(
        self, mod, make_words, make_style
    ):
        words = make_words([("one", 0, 1)])
        line = mod._fill_line(words, 0, "&H00FF00&", make_style(pop=106))
        assert "\\fscx106\\fscy106" in line


class TestPlainLine:
    def should_scale_only_the_active_word(self, mod, make_words, make_style):
        words = make_words([("one", 0, 1), ("two", 1, 2)])
        line = mod._plain_line(words, 1, make_style(pop=106))
        assert line.count("\\fscx106\\fscy106") == 1
        assert line.startswith("{\\r}ONE ")

    def should_leave_every_word_plain_when_pop_is_disabled(
        self, mod, make_words, make_style
    ):
        words = make_words([("one", 0, 1), ("two", 1, 2)])
        line = mod._plain_line(words, 0, make_style(pop=mod.NO_POP))
        assert line == "{\\r}ONE {\\r}TWO"


class TestCasing:
    def should_shout_in_capitals_for_an_uppercase_font(
        self, mod, make_words, make_style
    ):
        words = make_words([("loud", 0, 1)])
        style = make_style(font=mod.FONTS["anton"])

        assert "}LOUD" in mod._plain_line(words, 0, style)

    def should_keep_the_spoken_casing_for_a_script_font(
        self, mod, make_words, make_style
    ):
        words = make_words([("Soft", 0, 1)])
        style = make_style(font=mod.FONTS["lobster-two-italic"])

        assert "}Soft" in mod._plain_line(words, 0, style)

    def should_keep_the_punctuation_the_speaker_used(
        self, mod, make_words, make_style
    ):
        words = make_words([("so,", 0, 1), ("thema.", 1, 2), ("what?", 2, 3)])

        line = mod._plain_line(words, 0, make_style())

        assert "SO," in line
        assert "THEMA." in line
        assert "WHAT?" in line


class TestTracking:
    def should_tighten_every_token_when_the_face_asks_for_it(
        self, mod, make_words, make_style
    ):
        words = make_words([("one", 0, 1), ("two", 1, 2)])

        line = mod._plain_line(words, 1, make_style(spacing=-0.99))

        assert all("\\fsp-0.99" in token for token in line.split(" "))

    def should_leave_the_spacing_alone_for_a_face_drawn_as_set(
        self, mod, make_words, make_style
    ):
        words = make_words([("one", 0, 1)])

        assert "\\fsp" not in mod._plain_line(words, 0, make_style(spacing=0))


class TestGlowLine:
    def should_blur_every_token_of_the_line(self, mod, make_words, make_style):
        words = make_words([("one", 0, 1), ("two", 1, 2)])

        line = mod._glow_line(words, 0, make_style(glow_blur=3))

        assert all("\\blur3" in token for token in line.split(" "))
        assert f"\\r{mod.GLOW_STYLE}" in line

    def should_never_recolour_a_word(self, mod, make_words, make_style):
        words = make_words([("one", 0, 1), ("two", 1, 2)])

        assert "\\c&" not in mod._glow_line(words, 1, make_style())

    def should_pop_with_the_word_it_backs(self, mod, make_words, make_style):
        words = make_words([("one", 0, 1), ("two", 1, 2)])

        line = mod._glow_line(words, 1, make_style(pop=106))

        assert line.count("\\fscx106\\fscy106") == 1


class TestBoxLine:
    def should_colour_only_the_active_word_outline_and_reset_to_the_box_style(
        self, mod, make_words, make_style
    ):
        words = make_words([("one", 0, 1), ("two", 1, 2), ("three", 2, 3)])
        line = mod._box_line(words, 1, "&H00FF00&", make_style())
        assert line.count("\\3c&H00FF00&\\3a&H00&") == 1
        assert line.startswith("{\\rBox}ONE ")
        assert line.endswith(" {\\rBox}THREE")

    def should_never_recolour_the_glyph_fill(self, mod, make_words, make_style):
        words = make_words([("one", 0, 1)])
        assert "\\c&" not in mod._box_line(words, 0, "&H00FF00&", make_style())

    def should_pad_the_box_sideways_only_and_round_its_corners(
        self, mod, make_words, make_style, make_box
    ):
        words = make_words([("one", 0, 1)])
        style = make_style(box=make_box(pad_x=15, rounding=20))

        line = mod._box_line(words, 0, "&H00FF00&", style)

        assert "\\xbord15\\ybord0\\be20" in line


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

    def should_scale_the_outline_and_its_glow_with_the_ink_band(self, mod):
        args = mod.parse_args(["clip.mp4"])
        style = mod.build_style(1080, 1920, args)
        font = mod.FONTS[mod.DEFAULT_FONT]
        ink = style.font_size * (1 - font.ink_top - font.ink_bottom)
        assert style.outline == round(ink * mod.OUTLINE_RATIO)
        assert style.glow_outline == round(style.outline * mod.GLOW_OUTLINE_RATIO)
        assert style.glow_blur == round(style.outline * mod.GLOW_BLUR_RATIO)

    def should_derive_letter_spacing_from_the_face_tracking(self, mod):
        style = mod.build_style(1080, 1920, mod.parse_args(["clip.mp4"]))
        font = mod.FONTS[mod.DEFAULT_FONT]
        assert style.spacing == round(style.font_size * font.tracking, 2)
        assert style.spacing < 0

    def should_reproduce_the_reference_geometry_for_a_portrait_reel(self, mod):
        args = mod.parse_args(["clip.mp4", "--mode", "background"])

        style = mod.build_style(1080, 1920, args)

        assert style.font_size == 142
        assert (style.outline, style.glow_outline, style.glow_blur) == (6, 9, 5)
        assert (style.box.pad_x, style.box.rounding) == (9, 40)
        assert (style.box.scale_y, style.box.margin_v) == (91, 1411)

    def should_derive_margin_from_height_and_position(self, mod):
        args = mod.parse_args(["clip.mp4", "--position", "0.25"])
        style = mod.build_style(1080, 1920, args)
        assert style.margin_v == int(1920 * 0.25)

    def should_pass_highlight_palette_through(self, mod):
        args = mod.parse_args(["clip.mp4", "--highlight", "#ff0000,#00ff00"])
        style = mod.build_style(1080, 1920, args)
        assert style.highlights == ("#ff0000", "#00ff00")

    def should_paint_one_red_box_when_no_palette_is_given(self, mod):
        args = mod.parse_args(["clip.mp4", "--mode", "background"])
        style = mod.build_style(1080, 1920, args)
        assert style.highlights == mod.BOX_PALETTE

    def should_cycle_the_rainbow_when_filling_without_a_palette(self, mod):
        args = mod.parse_args(["clip.mp4", "--mode", "fill"])
        style = mod.build_style(1080, 1920, args)
        assert style.highlights == mod.DEFAULT_PALETTE

    def should_pass_mode_and_pop_through(self, mod):
        args = mod.parse_args(["clip.mp4", "--mode", "background", "--pop", "112"])
        style = mod.build_style(1080, 1920, args)
        assert style.mode is mod.Highlight.BACKGROUND
        assert style.pop == 112

    def should_size_from_the_font_when_no_scale_is_given(self, mod):
        args = mod.parse_args(["clip.mp4", "--font", "lobster-two-italic"])
        style = mod.build_style(1080, 1920, args)
        assert style.font_size == int(1920 * mod.FONTS["lobster-two-italic"].scale)

    def should_let_an_explicit_scale_override_the_font_default(self, mod):
        args = mod.parse_args(
            ["clip.mp4", "--font", "lobster-two-italic", "--scale", "0.07"]
        )
        style = mod.build_style(1080, 1920, args)
        assert style.font_size == int(1920 * 0.07)

    @pytest.mark.parametrize("face", ["anton", "barlow-condensed", "caveat"])
    def should_wrap_the_box_around_the_ink_of_a_bottom_anchored_line(self, mod, face):
        args = mod.parse_args(["clip.mp4", "--font", face])
        style = mod.build_style(1080, 1920, args)
        font = style.font
        ink_top = mod._ink_top(style.font_size, font, 2, style.margin_v, 1920)
        ink_height = style.font_size * (1 - font.ink_top - font.ink_bottom)
        box_height = style.font_size * (style.box.scale_y / 100) ** 2

        assert style.box.margin_v < ink_top
        assert style.box.margin_v + box_height > ink_top + ink_height
        assert style.box.alignment == 8

    def should_keep_rounding_visible_on_tiny_videos(self, mod):
        args = mod.parse_args(["clip.mp4", "--scale", "0.01"])
        style = mod.build_style(100, 100, args)
        assert style.box.rounding == 1
        assert style.box.pad_x == 0


class TestFonts:
    def should_shout_in_capitals_only_for_the_grotesques(self, mod):
        shouting = {name for name, font in mod.FONTS.items() if font.uppercase}
        assert shouting == {"anton", "barlow-condensed"}
        assert mod.FONTS[mod.DEFAULT_FONT].uppercase

    def should_measure_an_ink_band_for_every_face(self, mod):
        assert all(
            0 < font.ink_top + font.ink_bottom < 1 for font in mod.FONTS.values()
        )

    def should_percent_encode_bracketed_variable_font_paths(self, mod):
        assert "%5Bwght%5D" in mod.FONTS["caveat"].url

    def should_cache_under_the_file_name_from_the_path(self, mod):
        assert mod.FONTS["lobster-two-italic"].file_name == "LobsterTwo-Italic.ttf"

    def should_serve_every_face_from_google_fonts(self, mod):
        assert all(f.url.startswith(mod.GOOGLE_FONTS) for f in mod.FONTS.values())


class TestBuildAss:
    def should_emit_header_with_play_resolution(self, mod, make_style, make_words):
        groups = mod.group_words(make_words([("a", 0, 1)]), 5, 0.6)
        ass = mod.build_ass(groups, make_style(play_w=1080, play_h=1920))
        assert "[Script Info]" in ass
        assert "PlayResX: 1080" in ass
        assert "PlayResY: 1920" in ass
        assert "[Events]" in ass

    def should_emit_a_glow_and_a_text_event_per_word_when_filling(
        self, mod, make_style, make_words
    ):
        words = make_words([(f"w{i}", i, i + 0.5) for i in range(4)])
        groups = mod.group_words(words, 2, 10.0)

        ass = mod.build_ass(groups, make_style())

        events = [l for l in ass.splitlines() if l.startswith("Dialogue")]
        assert len(events) == 8
        assert [e.split(",")[3] for e in events[:2]] == ["Glow", "Default"]

    def should_hold_one_colour_per_line_and_advance_between_lines(
        self, mod, make_style, make_words
    ):
        words = make_words([(f"w{i}", i, i + 0.5) for i in range(8)])
        groups = mod.group_words(words, 3, 10.0)
        ass = mod.build_ass(groups, make_style(highlights=mod.DEFAULT_PALETTE))
        lines = [
            l for l in ass.splitlines()
            if l.startswith("Dialogue") and l.split(",")[3] == "Default"
        ]
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

    def should_name_the_chosen_family_and_slant_in_every_style(
        self, mod, make_style, make_words
    ):
        groups = mod.group_words(make_words([("a", 0, 1)]), 5, 0.6)
        style = make_style(
            mode=mod.Highlight.BACKGROUND, font=mod.FONTS["lobster-two-italic"]
        )

        ass = mod.build_ass(groups, style)

        fields = [s.split(",") for s in ass.splitlines() if s.startswith("Style: ")]
        assert {f[1] for f in fields} == {"Lobster Two"}
        assert {(f[7], f[8]) for f in fields} == {("0", "1")}

    def should_omit_the_box_style_in_fill_mode(self, mod, make_style, make_words):
        groups = mod.group_words(make_words([("a", 0, 1)]), 5, 0.6)
        ass = mod.build_ass(groups, make_style(mode=mod.Highlight.FILL))
        assert "Style: Box," not in ass
        assert "Style: Glow," in ass

    def should_bed_the_text_in_a_thicker_bordered_glow_style(
        self, mod, make_style, make_words
    ):
        groups = mod.group_words(make_words([("a", 0, 1)]), 5, 0.6)

        ass = mod.build_ass(groups, make_style(outline=4, glow_outline=6))

        text, glow = [
            s.split(",") for s in ass.splitlines() if s.startswith("Style: ")
        ]
        assert (text[16], glow[16]) == ("4", "6")
        assert glow[3] == mod.TRANSPARENT
        assert text[6] == glow[6]

    def should_define_a_transparent_opaque_box_style_in_background_mode(
        self, mod, make_style, make_words
    ):
        groups = mod.group_words(make_words([("a", 0, 1)]), 5, 0.6)
        ass = mod.build_ass(groups, make_style(mode=mod.Highlight.BACKGROUND))
        box = next(s for s in ass.splitlines() if s.startswith("Style: Box,"))
        fields = box.split(",")
        assert fields[3:7] == [mod.TRANSPARENT] * 4
        assert fields[15] == "3"
        assert fields[16] == "15"

    def should_anchor_the_box_style_on_its_own_edge_in_background_mode(
        self, mod, make_style, make_words, make_box
    ):
        groups = mod.group_words(make_words([("a", 0, 1)]), 5, 0.6)
        style = make_style(
            mode=mod.Highlight.BACKGROUND,
            alignment=2,
            margin_v=190,
            box=make_box(scale_y=78, margin_v=1210, alignment=8),
        )

        ass = mod.build_ass(groups, style)

        text, glow, box = [
            s.split(",") for s in ass.splitlines() if s.startswith("Style: ")
        ]
        assert text[2] == box[2]
        assert (text[12], text[18], text[21]) == ("100", "2", "190")
        assert (box[12], box[18], box[21]) == ("78", "8", "1210")
        assert glow[18:22] == text[18:22]

    def should_stack_the_box_copies_on_their_own_layers_under_the_text(
        self, mod, make_style, make_words
    ):
        words = make_words([(f"w{i}", i, i + 0.5) for i in range(3)])
        groups = mod.group_words(words, 3, 10.0)
        per_word = mod.BOX_ROUND_LAYERS + 2

        ass = mod.build_ass(groups, make_style(mode=mod.Highlight.BACKGROUND))

        events = [e for e in ass.splitlines() if e.startswith("Dialogue")]
        assert len(events) == 3 * per_word
        word = events[:per_word]
        assert [e.split(",")[0] for e in word] == [
            f"Dialogue: {layer}" for layer in range(per_word)
        ]
        assert [e.split(",")[3] for e in word] == ["Box"] * mod.BOX_ROUND_LAYERS + [
            "Glow", "Default"
        ]

    def should_pair_each_box_copy_with_the_text_event_it_backs(
        self, mod, make_style, make_words
    ):
        words = make_words([(f"w{i}", i, i + 0.5) for i in range(2)])
        groups = mod.group_words(words, 2, 10.0)
        per_word = mod.BOX_ROUND_LAYERS + 2
        ass = mod.build_ass(groups, make_style(mode=mod.Highlight.BACKGROUND))
        spans = [e.split(",")[1:3] for e in ass.splitlines() if e.startswith("Dialogue")]
        assert len(set(map(tuple, spans[:per_word]))) == 1
        assert len(set(map(tuple, spans[per_word:]))) == 1
        assert spans[0] != spans[per_word]

    def should_keep_the_text_layer_white_in_background_mode(
        self, mod, make_style, make_words
    ):
        groups = mod.group_words(make_words([("a", 0, 1), ("b", 1, 2)]), 5, 10.0)
        ass = mod.build_ass(groups, make_style(mode=mod.Highlight.BACKGROUND))
        prefix = f"Dialogue: {mod.BOX_ROUND_LAYERS + 1},"
        text_events = [e for e in ass.splitlines() if e.startswith(prefix)]
        assert text_events
        assert not any(mod.re.search(r"\\c&H", e) for e in text_events)


class TestVideoEncoderArgs:
    def should_use_videotoolbox_when_available(self, mod, monkeypatch):
        monkeypatch.setattr(
            mod, "_has_encoder", lambda name: name == "h264_videotoolbox"
        )
        assert mod.video_encoder_args() == [
            "-c:v", "h264_videotoolbox", "-b:v", mod.VIDEOTOOLBOX_BITRATE,
        ]

    def should_fall_back_to_libx264_when_videotoolbox_absent(self, mod, monkeypatch):
        monkeypatch.setattr(mod, "_has_encoder", lambda name: False)
        args = mod.video_encoder_args()
        assert args[:2] == ["-c:v", "libx264"]
        assert "-crf" in args


class TestDefaultOutput:
    def should_append_captioned_suffix_next_to_input(self, mod):
        out = mod.default_output(mod.Path("/videos/clip.mov"))
        assert out == mod.Path("/videos/clip_captioned.mp4")


class TestParseArgs:
    def should_default_max_words_to_three(self, mod):
        assert mod.parse_args(["clip.mp4"]).words == 3

    def should_leave_the_highlight_palette_to_the_mode(self, mod):
        assert mod.parse_args(["clip.mp4"]).highlight is None

    def should_default_cache_enabled(self, mod):
        assert mod.parse_args(["clip.mp4"]).no_cache is False

    def should_enable_no_cache_flag(self, mod):
        assert mod.parse_args(["clip.mp4", "--no-cache"]).no_cache is True

    def should_parse_highlight_into_palette_tuple(self, mod):
        assert mod.parse_args(["clip.mp4", "--highlight", "#ff0000"]).highlight == (
            "#ff0000",
        )

    def should_default_alignment_to_bottom_centre(self, mod):
        assert mod.parse_args(["clip.mp4"]).alignment == 2

    def should_default_position_clear_of_the_bottom_edge(self, mod):
        assert mod.parse_args(["clip.mp4"]).position == 0.20

    def should_accept_top_centre_alignment_override(self, mod):
        assert mod.parse_args(["clip.mp4", "--alignment", "8"]).alignment == 8

    def should_default_mode_to_fill(self, mod):
        assert mod.parse_args(["clip.mp4"]).mode is mod.Highlight.FILL

    def should_accept_background_mode(self, mod):
        assert (
            mod.parse_args(["clip.mp4", "--mode", "background"]).mode
            is mod.Highlight.BACKGROUND
        )

    def should_reject_an_unknown_mode(self, mod):
        with pytest.raises(SystemExit):
            mod.parse_args(["clip.mp4", "--mode", "glow"])

    def should_default_pop_to_holding_every_word_at_its_own_size(self, mod):
        assert mod.parse_args(["clip.mp4"]).pop == mod.NO_POP

    def should_default_font_to_the_reference_face(self, mod):
        assert mod.parse_args(["clip.mp4"]).font == "barlow-condensed"


class TestParsePop:
    def should_accept_a_value_inside_the_allowed_range(self, mod):
        assert mod._parse_pop("120") == 120

    def should_accept_the_disabling_value(self, mod):
        assert mod._parse_pop("100") == mod.NO_POP

    @pytest.mark.parametrize("value", ["99", "151"])
    def should_reject_out_of_range_values(self, mod, value):
        with pytest.raises(mod.argparse.ArgumentTypeError):
            mod._parse_pop(value)

    def should_reject_a_non_numeric_value(self, mod):
        with pytest.raises(mod.argparse.ArgumentTypeError):
            mod._parse_pop("big")


class TestEmitCompletions:
    def should_print_whisper_models_one_per_line(self, mod, capsys):
        mod.emit_completions("models")
        printed = capsys.readouterr().out.split()
        assert list(mod.WHISPER_MODELS) == printed

    def should_print_alignment_values_one_to_nine(self, mod, capsys):
        mod.emit_completions("alignment")
        assert capsys.readouterr().out.split() == [str(n) for n in range(1, 10)]

    def should_print_highlight_modes(self, mod, capsys):
        mod.emit_completions("modes")
        assert capsys.readouterr().out.split() == ["fill", "background"]

    def should_print_font_names(self, mod, capsys):
        mod.emit_completions("fonts")
        assert capsys.readouterr().out.split() == sorted(mod.FONTS)

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

    @pytest.mark.parametrize("mode", ["fill", "background"])
    def should_burn_captions_into_a_playable_output(
        self, mod, tmp_path, make_words, mode
    ):
        video = tmp_path / "in.mp4"
        self._make_video(video)
        args = mod.parse_args([str(video), "--mode", mode])
        style = mod.build_style(320, 240, args)
        words = make_words([("Hello", 0.0, 0.4), ("world", 0.4, 0.9)])
        groups = mod.group_words(words, style.max_words, style.max_gap)
        ass_path = tmp_path / "captions.ass"
        ass_path.write_text(mod.build_ass(groups, style), encoding="utf-8")
        out = tmp_path / "out.mp4"

        mod.burn(video, ass_path, tmp_path, out)

        assert out.exists() and out.stat().st_size > 0
        assert self._stream_count(out) == "video"
