from dataclasses import dataclass
from pathlib import Path

import pytest


@dataclass
class _Completed:
    returncode: int


FFPROBE_MOCK = """cat <<EOF
{"streams":[{"pix_fmt":"${MOCK_PIX_FMT:-yuv420p}","color_transfer":"${MOCK_TRANSFER:-bt709}",
"color_primaries":"${MOCK_PRIMARIES:-bt709}","color_space":"${MOCK_SPACE:-bt709}",
"height":${MOCK_HEIGHT:-1080},"r_frame_rate":"${MOCK_RFR:-60/1}"}]}
EOF"""


def _ffmpeg_mock(encoders="libsvtav1", filters="zscale"):
    return f"""case "$*" in
  *-encoders*) echo " V..... {encoders}  AV1"; exit 0;;
  *-filters*) echo " ..C.. {filters}  V->V"; exit 0;;
esac
for last; do :; done
case "$last" in
  *"${{MOCK_FAIL_ON:-@@nevermatches@@}}"*) exit 1;;
esac
printf 'compressed' > "$last"
"""


INTERRUPTING_FFMPEG_MOCK = """case "$*" in
  *-encoders*) echo " V..... libsvtav1  AV1"; exit 0;;
  *-filters*) echo " ..C.. zscale  V->V"; exit 0;;
esac
for last; do :; done
printf 'partial' > "$last"
kill -INT "$PPID"
sleep 5
"""


def _mocks(encoders="libsvtav1", filters="zscale"):
    return {"ffmpeg": _ffmpeg_mock(encoders, filters), "ffprobe": FFPROBE_MOCK}


def _make_video(path: Path, size: int = 4096) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"v" * size)
    return path


@pytest.fixture
def mod(load_script):
    return load_script("compressvideo")


@pytest.fixture
def settings(mod):
    def _make(**overrides):
        defaults = {
            "codec": "h265", "quality": 28, "preset": "medium", "scale_height": None,
            "fps_target": None, "fps_half": False, "tonemap": False, "copy_audio": False,
            "hardware_encoder": None, "av1_encoder": None,
        }
        return mod.EncodeSettings(**{**defaults, **overrides})
    return _make


@pytest.fixture
def compress(run_cli, tmp_path):
    def _run(args, mocks=None, env_extra=None, cwd=None):
        return run_cli("compressvideo", args, mock_bins=mocks or _mocks(),
                       isolate_path=True, env_extra=env_extra, cwd=cwd)
    return _run


@pytest.fixture
def dry_run(compress, tmp_path):
    def _run(args, **kwargs):
        video = tmp_path / "in.mp4"
        if not video.exists():
            _make_video(video)
        return compress(list(args) + ["--dry-run", str(video)], **kwargs)
    return _run


class TestHelp:
    def should_print_usage_and_exit_zero(self, compress):
        result = compress(["-h"])
        assert result.returncode == 0
        assert "usage:" in result.stdout

    @pytest.mark.parametrize("flag", ["--recursive", "--max-depth", "--rm-original",
                                      "--fps-half", "--tonemap", "--dry-run"])
    def should_list_long_flags_for_autocomplete(self, compress, flag):
        assert flag in compress(["-h"]).stdout


class TestFmtSize:
    @pytest.mark.parametrize("size,expected", [
        (0, "0.0 B"),
        (512, "512.0 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1048576, "1.0 MB"),
        (1073741824, "1.0 GB"),
        (1099511627776, "1.0 TB"),
    ])
    def should_format_binary_units(self, mod, size, expected):
        assert mod.fmt_size(size) == expected


class TestSizeDelta:
    @pytest.mark.parametrize("before,after,expected", [
        (1000, 500, "50.0% smaller"),
        (1000, 1000, "0.0% smaller"),
        (1000, 1500, "50.0% bigger"),
        (0, 500, "0.0% smaller"),
    ])
    def should_describe_change(self, mod, before, after, expected):
        assert mod.size_delta(before, after) == expected


class TestParseScale:
    @pytest.mark.parametrize("value,expected", [
        ("2160p", 2160), ("4k", 2160), ("4K", 2160), ("uhd", 2160),
        ("1440p", 1440), ("1080p", 1080), ("fhd", 1080),
        ("720p", 720), ("hd", 720), ("480p", 480), ("360p", 360),
        ("900", 900),
    ])
    def should_resolve_aliases_and_pixel_heights(self, mod, value, expected):
        assert mod.parse_scale(value) == expected

    @pytest.mark.parametrize("value", ["huge", "", "-720", "1080px"])
    def should_reject_unparseable_heights(self, mod, value):
        with pytest.raises(Exception, match="invalid scale"):
            mod.parse_scale(value)


class TestParseFps:
    @pytest.mark.parametrize("value", ["24", "25", "29.97", "60"])
    def should_keep_valid_rates_verbatim(self, mod, value):
        assert mod.parse_fps(value) == value

    @pytest.mark.parametrize("value", ["fast", "0", "-24", ""])
    def should_reject_non_positive_rates(self, mod, value):
        with pytest.raises(Exception, match="invalid fps"):
            mod.parse_fps(value)


class TestParseMaxDepth:
    def should_accept_positive_integers(self, mod):
        assert mod.parse_max_depth("3") == 3

    @pytest.mark.parametrize("value", ["0", "-1", "deep", "2.5"])
    def should_reject_anything_else(self, mod, value):
        with pytest.raises(Exception, match="invalid max depth"):
            mod.parse_max_depth(value)


class TestIsCompressibleVideo:
    @pytest.mark.parametrize("name", ["clip.mov", "clip.mp4", "clip.mpg", "clip.mpeg",
                                      "clip.avi", "clip.mkv", "clip.webm", "clip.m4v",
                                      "clip.wmv", "clip.flv", "clip.3gp", "clip.mts", "clip.m2ts"])
    def should_accept_common_video_extensions(self, mod, name):
        assert mod.is_compressible_video(Path(name))

    @pytest.mark.parametrize("name", ["CLIP.MOV", "clip.Mp4", "clip.AVI"])
    def should_match_extensions_case_insensitively(self, mod, name):
        assert mod.is_compressible_video(Path(name))

    @pytest.mark.parametrize("name", ["notes.txt", "photo.jpg", "audio.mp3", "clip"])
    def should_reject_non_video_files(self, mod, name):
        assert not mod.is_compressible_video(Path(name))

    @pytest.mark.parametrize("name", ["clip_compressed.mp4", "Clip_Compressed.mov",
                                      "already-COMPRESSED.avi"])
    def should_reject_names_containing_compressed(self, mod, name):
        assert not mod.is_compressible_video(Path(name))


class TestFindVideoFiles:
    def should_find_videos_across_nested_directories(self, mod, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "one" / "b.mp4")
        _make_video(tmp_path / "one" / "two" / "c.avi")

        found = mod.find_video_files(tmp_path)

        assert [path.name for path in found] == ["a.mov", "b.mp4", "c.avi"]

    def should_ignore_non_video_and_compressed_files(self, mod, tmp_path):
        _make_video(tmp_path / "keep.mov")
        _make_video(tmp_path / "skip_compressed.mp4")
        (tmp_path / "notes.txt").write_text("x")

        assert [path.name for path in mod.find_video_files(tmp_path)] == ["keep.mov"]

    def should_return_sorted_paths(self, mod, tmp_path):
        for name in ("c.mov", "a.mov", "b.mov"):
            _make_video(tmp_path / name)

        found = mod.find_video_files(tmp_path)

        assert found == sorted(found)

    @pytest.mark.parametrize("max_depth,expected", [
        (1, ["d1.mov"]),
        (2, ["d1.mov", "d2.mov"]),
        (3, ["d1.mov", "d2.mov", "d3.mov"]),
        (5, ["d1.mov", "d2.mov", "d3.mov", "d4.mov", "d5.mov"]),
    ])
    def should_respect_max_depth(self, mod, tmp_path, max_depth, expected):
        directory = tmp_path
        for level in range(1, 7):
            _make_video(directory / f"d{level}.mov")
            directory = directory / f"level{level}"

        found = {path.name for path in mod.find_video_files(tmp_path, max_depth)}

        assert found == set(expected)

    def should_default_to_depth_five(self, mod, tmp_path):
        assert mod.DEFAULT_MAX_DEPTH == 5
        _make_video(tmp_path / "a" / "b" / "c" / "d" / "deep.mov")
        _make_video(tmp_path / "a" / "b" / "c" / "d" / "e" / "deeper.mov")

        found = {path.name for path in mod.find_video_files(tmp_path)}

        assert found == {"deep.mov"}

    def should_return_empty_list_for_directory_without_videos(self, mod, tmp_path):
        (tmp_path / "notes.txt").write_text("x")

        assert mod.find_video_files(tmp_path) == []


class TestOutputFileFor:
    def should_append_compressed_suffix_and_force_mp4(self, mod, tmp_path):
        assert mod.output_file_for(tmp_path / "clip.mov") == tmp_path / "clip_compressed.mp4"

    def should_keep_dots_inside_the_stem(self, mod, tmp_path):
        assert mod.output_file_for(tmp_path / "a.b.mov") == tmp_path / "a.b_compressed.mp4"


class TestSourceInfo:
    def should_parse_ffprobe_stream(self, mod):
        source = mod.SourceInfo.from_stream({
            "pix_fmt": "yuv420p10le", "color_transfer": "smpte2084",
            "color_primaries": "bt2020", "color_space": "bt2020nc",
            "height": 2160, "r_frame_rate": "60000/1001",
        })

        assert source.height == 2160
        assert source.primaries == "bt2020"
        assert source.frame_rate == "60000/1001"

    def should_tolerate_missing_fields(self, mod):
        source = mod.SourceInfo.from_stream({})

        assert source.height is None
        assert source.pix_fmt == ""

    @pytest.mark.parametrize("transfer,expected", [
        ("smpte2084", True), ("arib-std-b67", True), ("bt709", False), ("", False),
    ])
    def should_detect_hdr_transfer(self, mod, transfer, expected):
        assert mod.SourceInfo(transfer=transfer).is_hdr is expected

    @pytest.mark.parametrize("pix_fmt,expected", [
        ("yuv420p10le", True), ("yuv422p10be", True), ("p010le", True),
        ("yuv420p", False), ("", False),
    ])
    def should_detect_ten_bit_pixel_formats(self, mod, pix_fmt, expected):
        assert mod.SourceInfo(pix_fmt=pix_fmt).is_10bit is expected

    @pytest.mark.parametrize("frame_rate,expected", [
        ("60/1", (60, 1)), ("60000/1001", (60000, 1001)),
        ("0/0", None), ("", None), ("N/A", None), ("30", None),
    ])
    def should_parse_frame_rate_fraction(self, mod, frame_rate, expected):
        assert mod.SourceInfo(frame_rate=frame_rate).frame_rate_fraction == expected


class TestResolveFps:
    def should_pass_through_explicit_target(self, mod, settings):
        assert mod.resolve_fps(settings(fps_target="24"), mod.SourceInfo()) == "24"

    def should_return_none_without_fps_options(self, mod, settings):
        assert mod.resolve_fps(settings(), mod.SourceInfo(frame_rate="60/1")) is None

    def should_halve_integer_source_rate(self, mod, settings):
        source = mod.SourceInfo(frame_rate="60/1")

        assert mod.resolve_fps(settings(fps_half=True), source) == "60/2"

    def should_stay_exact_on_fractional_source_rate(self, mod, settings):
        source = mod.SourceInfo(frame_rate="60000/1001")

        assert mod.resolve_fps(settings(fps_half=True), source) == "60000/2002"

    def should_raise_without_detectable_source_rate(self, mod, settings):
        with pytest.raises(ValueError, match="detectable source frame rate"):
            mod.resolve_fps(settings(fps_half=True), mod.SourceInfo(frame_rate="0/0"))


class TestBuildVideoFilter:
    def should_build_no_filter_by_default(self, mod, settings):
        assert mod.build_video_filter(settings(), mod.SourceInfo()) is None

    def should_escape_the_comma_inside_the_scale_expression(self, mod, settings):
        result = mod.build_video_filter(settings(scale_height=1080), mod.SourceInfo())

        assert result == r"scale=-2:min(ih\,1080)"

    def should_decimate_before_scaling(self, mod, settings):
        result = mod.build_video_filter(settings(fps_half=True, scale_height=1080),
                                        mod.SourceInfo(frame_rate="60/1"))

        assert result == r"fps=60/2,scale=-2:min(ih\,1080)"

    def should_tonemap_before_everything_else(self, mod, settings):
        result = mod.build_video_filter(settings(tonemap=True, scale_height=720),
                                        mod.SourceInfo())

        assert result.startswith("zscale=t=linear")
        assert result.endswith(r"scale=-2:min(ih\,720)")


class TestBuildEncoderArgs:
    def should_use_libx265_with_hvc1_tag(self, mod, settings):
        assert mod.build_encoder_args(settings()) == [
            "-c:v", "libx265", "-preset", "medium", "-crf", "28", "-tag:v", "hvc1"]

    def should_use_libx264_without_tag(self, mod, settings):
        assert mod.build_encoder_args(settings(codec="h264", quality=23)) == [
            "-c:v", "libx264", "-preset", "medium", "-crf", "23"]

    def should_use_svtav1_when_available(self, mod, settings):
        args = mod.build_encoder_args(settings(codec="av1", quality=32, av1_encoder="libsvtav1"))

        assert args == ["-c:v", "libsvtav1", "-crf", "32", "-preset", "6"]

    def should_fall_back_to_libaom(self, mod, settings):
        args = mod.build_encoder_args(settings(codec="av1", quality=32, av1_encoder="libaom-av1"))

        assert args[:4] == ["-c:v", "libaom-av1", "-crf", "32"]

    def should_use_videotoolbox_quality_scale(self, mod, settings):
        args = mod.build_encoder_args(settings(quality=55, hardware_encoder="hevc_videotoolbox"))

        assert args == ["-c:v", "hevc_videotoolbox", "-q:v", "55", "-tag:v", "hvc1"]

    def should_not_tag_hardware_h264(self, mod, settings):
        args = mod.build_encoder_args(
            settings(codec="h264", quality=55, hardware_encoder="h264_videotoolbox"))

        assert args == ["-c:v", "h264_videotoolbox", "-q:v", "55"]


class TestBuildColorArgs:
    def should_force_rec709_when_tonemapping(self, mod, settings):
        args = mod.build_color_args(settings(tonemap=True), mod.SourceInfo(transfer="smpte2084"))

        assert args == ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]

    def should_stay_out_of_the_way_for_hardware_encodes(self, mod, settings):
        args = mod.build_color_args(settings(hardware_encoder="hevc_videotoolbox"),
                                    mod.SourceInfo(pix_fmt="yuv420p10le"))

        assert args == []

    def should_force_eight_bit_for_h264(self, mod, settings):
        args = mod.build_color_args(settings(codec="h264"), mod.SourceInfo(pix_fmt="yuv420p10le"))

        assert args == ["-pix_fmt", "yuv420p"]

    def should_add_nothing_for_sdr_eight_bit_sources(self, mod, settings):
        assert mod.build_color_args(settings(), mod.SourceInfo(pix_fmt="yuv420p")) == []

    def should_preserve_bit_depth_and_metadata_for_hdr(self, mod, settings):
        source = mod.SourceInfo(pix_fmt="yuv420p10le", transfer="smpte2084",
                                primaries="bt2020", space="bt2020nc")

        args = mod.build_color_args(settings(), source)

        assert args == ["-pix_fmt", "yuv420p10le", "-color_primaries", "bt2020",
                        "-color_trc", "smpte2084", "-colorspace", "bt2020nc"]

    def should_drop_unknown_metadata_values(self, mod, settings):
        source = mod.SourceInfo(pix_fmt="yuv420p10le", transfer="unknown",
                                primaries="N/A", space="")

        assert mod.build_color_args(settings(), source) == ["-pix_fmt", "yuv420p10le"]


class TestBuildCommand:
    def should_build_a_full_default_command(self, mod, settings, tmp_path):
        command = mod.build_command(settings(), mod.SourceInfo(),
                                    tmp_path / "in.mov", tmp_path / "out.mp4")

        assert command[:5] == ["ffmpeg", "-hide_banner", "-y", "-i", str(tmp_path / "in.mov")]
        assert command[-3:] == ["-movflags", "+faststart", str(tmp_path / "out.mp4")]
        assert "-c:a" in command and "aac" in command

    def should_copy_audio_when_asked(self, mod, settings, tmp_path):
        command = mod.build_command(settings(copy_audio=True), mod.SourceInfo(),
                                    tmp_path / "in.mov", tmp_path / "out.mp4")

        assert "-c:a" in command and "copy" in command
        assert "aac" not in command

    def should_omit_the_filter_flag_without_filters(self, mod, settings, tmp_path):
        command = mod.build_command(settings(), mod.SourceInfo(),
                                    tmp_path / "in.mov", tmp_path / "out.mp4")

        assert "-vf" not in command


class TestResolveHardwareEncoder:
    def should_pick_videotoolbox_when_available(self, mod):
        assert mod.resolve_hardware_encoder("h265", "auto", {"hevc_videotoolbox"}) \
            == "hevc_videotoolbox"

    def should_stay_software_when_videotoolbox_is_missing(self, mod):
        assert mod.resolve_hardware_encoder("h265", "auto", {"libx265"}) is None

    def should_stay_software_when_forced_off(self, mod):
        assert mod.resolve_hardware_encoder("h265", "off", {"hevc_videotoolbox"}) is None

    def should_exit_when_forced_on_without_support(self, mod):
        with pytest.raises(SystemExit) as excinfo:
            mod.resolve_hardware_encoder("h265", "on", set())

        assert excinfo.value.code == 2

    def should_exit_when_hardware_av1_is_requested(self, mod):
        with pytest.raises(SystemExit) as excinfo:
            mod.resolve_hardware_encoder("av1", "on", {"hevc_videotoolbox"})

        assert excinfo.value.code == 2

    def should_never_pick_hardware_for_av1(self, mod):
        assert mod.resolve_hardware_encoder("av1", "auto", {"hevc_videotoolbox"}) is None


class TestRunFfmpeg:
    def should_report_success_and_keep_both_files(self, mod, monkeypatch, tmp_path):
        source = _make_video(tmp_path / "in.mov")
        output = _make_video(tmp_path / "out.mp4", size=128)
        monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Completed(0))

        outcome = mod.run_ffmpeg(["ffmpeg"], source, output, rm_original=False)

        assert outcome is mod.Outcome.COMPRESSED
        assert source.exists() and output.exists()

    def should_remove_the_original_when_asked(self, mod, monkeypatch, tmp_path):
        source = _make_video(tmp_path / "in.mov")
        output = _make_video(tmp_path / "out.mp4", size=128)
        monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Completed(0))

        mod.run_ffmpeg(["ffmpeg"], source, output, rm_original=True)

        assert not source.exists()

    def should_delete_the_partial_output_on_failure(self, mod, monkeypatch, tmp_path):
        source = _make_video(tmp_path / "in.mov")
        output = _make_video(tmp_path / "out.mp4", size=16)
        monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Completed(1))

        outcome = mod.run_ffmpeg(["ffmpeg"], source, output, rm_original=True)

        assert outcome is mod.Outcome.FAILED
        assert not output.exists()
        assert source.exists()

    def should_delete_the_partial_output_on_interrupt(self, mod, monkeypatch, tmp_path):
        source = _make_video(tmp_path / "in.mov")
        output = _make_video(tmp_path / "out.mp4", size=16)

        def interrupted(*args, **kwargs):
            raise KeyboardInterrupt

        monkeypatch.setattr(mod.subprocess, "run", interrupted)

        with pytest.raises(KeyboardInterrupt):
            mod.run_ffmpeg(["ffmpeg"], source, output, rm_original=False)

        assert not output.exists()
        assert source.exists()


class TestSelectAv1Encoder:
    def should_prefer_svtav1(self, mod):
        assert mod.select_av1_encoder({"libsvtav1", "libaom-av1"}) == "libsvtav1"

    def should_fall_back_to_libaom(self, mod):
        assert mod.select_av1_encoder({"libaom-av1"}) == "libaom-av1"


class TestSingleFileDefaults:
    def should_use_libx265_medium_crf28(self, dry_run):
        result = dry_run([])

        assert result.returncode == 0
        assert "-c:v libx265 -preset medium -crf 28 -tag:v hvc1" in result.stdout

    def should_add_faststart_and_aac_audio(self, dry_run):
        result = dry_run([])

        assert "-movflags +faststart" in result.stdout
        assert "-c:a aac -b:a 128k" in result.stdout

    def should_name_the_output_with_a_compressed_suffix(self, dry_run, tmp_path):
        assert str(tmp_path / "in_compressed.mp4") in dry_run([]).stdout

    def should_apply_scale_flag(self, dry_run):
        assert r"-vf scale=-2:min(ih\,1080)" in dry_run(["-s", "1080p"]).stdout

    def should_apply_quality_override(self, dry_run):
        assert "-crf 20" in dry_run(["-q", "20"]).stdout

    def should_accept_the_file_before_the_flags(self, compress, tmp_path):
        video = _make_video(tmp_path / "in.mp4")

        result = compress([str(video), "-q", "20", "--dry-run"])

        assert result.returncode == 0
        assert "-crf 20" in result.stdout

    def should_force_h264_for_preview_compatibility(self, dry_run):
        assert "-c:v libx264" in dry_run(["--just-preview-compatible", "-c", "h265"]).stdout


class TestSingleFileHardware:
    def should_auto_enable_videotoolbox_when_available(self, dry_run):
        result = dry_run([], mocks=_mocks(encoders="hevc_videotoolbox"))

        assert "-c:v hevc_videotoolbox -q:v 55 -tag:v hvc1" in result.stdout
        assert "hardware encoding via hevc_videotoolbox" in result.stdout

    def should_stay_software_without_videotoolbox(self, dry_run):
        assert "-c:v libx265 -preset medium" in dry_run([]).stdout

    @pytest.mark.parametrize("flag", ["--sw", "--no-hw"])
    def should_force_software_with_sw_flag(self, dry_run, flag):
        result = dry_run([flag], mocks=_mocks(encoders="hevc_videotoolbox"))

        assert "-c:v libx265 -preset medium" in result.stdout

    def should_exit_two_when_hardware_is_unavailable(self, dry_run):
        result = dry_run(["--hw"], mocks=_mocks(encoders="none"))

        assert result.returncode == 2
        assert "unavailable" in result.stderr


class TestSingleFileColour:
    def should_preserve_hdr_bit_depth_and_metadata(self, dry_run):
        env = {"MOCK_PIX_FMT": "yuv420p10le", "MOCK_TRANSFER": "smpte2084",
               "MOCK_PRIMARIES": "bt2020", "MOCK_SPACE": "bt2020nc"}

        result = dry_run([], env_extra=env)

        assert "-pix_fmt yuv420p10le" in result.stdout
        assert "-color_primaries bt2020 -color_trc smpte2084 -colorspace bt2020nc" in result.stdout

    def should_warn_and_force_eight_bit_for_hdr_h264(self, dry_run):
        env = {"MOCK_PIX_FMT": "yuv420p10le", "MOCK_TRANSFER": "smpte2084"}

        result = dry_run(["-c", "h264"], env_extra=env)

        assert "HDR" in result.stdout
        assert "-pix_fmt yuv420p" in result.stdout

    def should_build_the_sdr_tonemap_chain(self, dry_run):
        env = {"MOCK_PIX_FMT": "yuv420p10le", "MOCK_TRANSFER": "smpte2084"}

        result = dry_run(["--tonemap"], env_extra=env)

        assert "tonemap=tonemap=hable" in result.stdout
        assert "-color_primaries bt709 -color_trc bt709 -colorspace bt709" in result.stdout

    def should_exit_two_when_tonemap_lacks_zscale(self, dry_run):
        result = dry_run(["--tonemap"], mocks=_mocks(filters="scale"))

        assert result.returncode == 2
        assert "zscale" in result.stderr

    def should_hint_a_downscale_for_sources_above_1080p(self, dry_run):
        assert "add --scale 1080p" in dry_run([], env_extra={"MOCK_HEIGHT": "2160"}).stdout

    def should_not_hint_when_already_downscaling(self, dry_run):
        result = dry_run(["-s", "1080p"], env_extra={"MOCK_HEIGHT": "2160"})

        assert "add --scale 1080p" not in result.stdout


class TestSingleFileValidation:
    def should_exit_two_for_a_missing_input_file(self, compress, tmp_path):
        result = compress(["--dry-run", str(tmp_path / "nope.mp4")])

        assert result.returncode == 2
        assert "input file not found" in result.stderr

    def should_exit_two_without_any_argument(self, compress):
        assert compress([]).returncode == 2

    def should_exit_two_when_the_output_already_exists(self, compress, tmp_path):
        video = _make_video(tmp_path / "clip.mov")
        _make_video(tmp_path / "clip_compressed.mp4")

        result = compress(["--dry-run", str(video)])

        assert result.returncode == 2
        assert "output already exists" in result.stderr

    def should_point_at_recursive_mode_for_a_directory(self, compress, tmp_path):
        result = compress(["--dry-run", str(tmp_path)])

        assert result.returncode == 2
        assert "pass -r" in result.stderr

    @pytest.mark.parametrize("args,expected", [
        (["-s", "huge"], "invalid scale"),
        (["--fps", "fast"], "invalid fps"),
        (["--max-depth", "0"], "invalid max depth"),
        (["-c", "vp9"], "invalid choice"),
        (["-p", "turbo"], "invalid choice"),
        (["--fps-half", "--fps", "24"], "not allowed with"),
    ])
    def should_exit_two_on_bad_options(self, dry_run, args, expected):
        result = dry_run(args)

        assert result.returncode == 2
        assert expected in result.stderr

    def should_report_an_undetectable_frame_rate(self, dry_run):
        result = dry_run(["--fps-half"], env_extra={"MOCK_RFR": "0/0"})

        assert result.returncode == 1
        assert "detectable source frame rate" in result.stderr


class TestRecursiveDiscovery:
    def should_compress_every_video_it_finds(self, compress, tmp_path):
        for name in ("a.mov", "b.mp4", "c.avi", "d.mpg", "e.mpeg"):
            _make_video(tmp_path / name)

        result = compress(["-r", "--dry-run", str(tmp_path)])

        assert result.returncode == 0
        for name in ("a.mov", "b.mp4", "c.avi", "d.mpg", "e.mpeg"):
            assert str(tmp_path / name) in result.stdout

    def should_descend_into_subdirectories(self, compress, tmp_path):
        _make_video(tmp_path / "one" / "two" / "deep.mov")

        result = compress(["-r", "--dry-run", str(tmp_path)])

        assert str(tmp_path / "one" / "two" / "deep.mov") in result.stdout

    def should_skip_names_containing_compressed(self, compress, tmp_path):
        _make_video(tmp_path / "keep.mov")
        _make_video(tmp_path / "earlier_compressed.mp4")
        _make_video(tmp_path / "Holiday_COMPRESSED.mov")

        result = compress(["-r", "--dry-run", str(tmp_path)])

        assert "found 1 video file(s)" in result.stdout
        assert "earlier_compressed.mp4" not in result.stdout
        assert "Holiday_COMPRESSED.mov" not in result.stdout

    def should_ignore_non_video_files(self, compress, tmp_path):
        _make_video(tmp_path / "clip.mov")
        (tmp_path / "notes.txt").write_text("x")
        (tmp_path / "cover.jpg").write_bytes(b"x")

        assert "found 1 video file(s)" in compress(["-r", "--dry-run", str(tmp_path)]).stdout

    def should_stop_at_depth_five_by_default(self, compress, tmp_path):
        _make_video(tmp_path / "a" / "b" / "c" / "d" / "deep.mov")
        _make_video(tmp_path / "a" / "b" / "c" / "d" / "e" / "deeper.mov")

        result = compress(["-r", "--dry-run", str(tmp_path)])

        assert "deep.mov" in result.stdout
        assert "deeper.mov" not in result.stdout

    def should_honour_an_explicit_max_depth(self, compress, tmp_path):
        _make_video(tmp_path / "top.mov")
        _make_video(tmp_path / "sub" / "nested.mov")

        result = compress(["-r", "--max-depth", "1", "--dry-run", str(tmp_path)])

        assert "top.mov" in result.stdout
        assert "nested.mov" not in result.stdout

    def should_default_to_the_current_directory(self, compress, tmp_path):
        _make_video(tmp_path / "here.mov")

        result = compress(["-r", "--dry-run"], cwd=tmp_path)

        assert result.returncode == 0
        assert "here.mov" in result.stdout

    def should_warn_when_no_videos_are_found(self, compress, tmp_path):
        result = compress(["-r", "--dry-run", str(tmp_path)])

        assert result.returncode == 0
        assert "no videos found" in result.stdout
        assert "compressed 0" not in result.stdout

    def should_exit_two_when_the_path_is_not_a_directory(self, compress, tmp_path):
        video = _make_video(tmp_path / "clip.mov")

        result = compress(["-r", "--dry-run", str(video)])

        assert result.returncode == 2
        assert "not a directory" in result.stderr


class TestRecursiveOptions:
    def should_apply_the_same_options_to_every_file(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "b.mp4")

        result = compress(["-r", "-c", "h264", "-s", "720p", "-q", "21",
                           "--copy-audio", "--dry-run", str(tmp_path)])

        commands = [line for line in result.stdout.splitlines() if line.startswith("ffmpeg")]
        assert len(commands) == 2
        for command in commands:
            assert "-c:v libx264" in command
            assert r"scale=-2:min(ih\,720)" in command
            assert "-crf 21" in command
            assert "-c:a copy" in command

    def should_apply_fps_half_per_file(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "b.mov")

        result = compress(["-r", "--fps-half", "--dry-run", str(tmp_path)],
                          env_extra={"MOCK_RFR": "30/1"})

        assert result.stdout.count("-vf fps=30/2") == 2

    def should_number_the_progress_lines(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "b.mov")

        result = compress(["-r", "--dry-run", str(tmp_path)])

        assert "[1/2]" in result.stdout
        assert "[2/2]" in result.stdout

    def should_not_touch_the_filesystem_on_a_dry_run(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")

        compress(["-r", "--dry-run", str(tmp_path)])

        assert list(tmp_path.glob("*_compressed.mp4")) == []
        assert (tmp_path / "a.mov").exists()


class TestRecursiveExecution:
    def should_write_one_compressed_file_per_source(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "nested" / "b.mp4")

        result = compress(["-r", str(tmp_path)])

        assert result.returncode == 0
        assert (tmp_path / "a_compressed.mp4").exists()
        assert (tmp_path / "nested" / "b_compressed.mp4").exists()

    def should_remove_every_original_with_rm_original(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "b.mp4")

        result = compress(["-r", "--rm-original", str(tmp_path)])

        assert result.returncode == 0
        assert not (tmp_path / "a.mov").exists()
        assert not (tmp_path / "b.mp4").exists()
        assert (tmp_path / "a_compressed.mp4").exists()
        assert (tmp_path / "b_compressed.mp4").exists()

    def should_keep_originals_by_default(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")

        compress(["-r", str(tmp_path)])

        assert (tmp_path / "a.mov").exists()

    def should_report_a_summary(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "b.mov")

        result = compress(["-r", str(tmp_path)])

        assert "compressed 2, skipped 0, failed 0 of 2 file(s)" in result.stdout

    def should_skip_sources_whose_output_already_exists(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "a_compressed.mp4")

        result = compress(["-r", str(tmp_path)])

        assert result.returncode == 0
        assert "already exists" in result.stdout
        assert "compressed 0, skipped 1, failed 0 of 1 file(s)" in result.stdout

    def should_be_idempotent_across_runs(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")

        compress(["-r", str(tmp_path)])
        result = compress(["-r", str(tmp_path)])

        assert "compressed 0, skipped 1, failed 0 of 1 file(s)" in result.stdout

    def should_continue_after_a_failure_and_exit_one(self, compress, tmp_path):
        _make_video(tmp_path / "bad.mov")
        _make_video(tmp_path / "good.mov")

        result = compress(["-r", str(tmp_path)], env_extra={"MOCK_FAIL_ON": "bad"})

        assert result.returncode == 1
        assert "compressed 1, skipped 0, failed 1 of 2 file(s)" in result.stdout
        assert (tmp_path / "good_compressed.mp4").exists()
        assert not (tmp_path / "bad_compressed.mp4").exists()

    def should_clean_up_and_summarise_on_interrupt(self, compress, tmp_path):
        _make_video(tmp_path / "a.mov")
        _make_video(tmp_path / "b.mov")

        result = compress(["-r", str(tmp_path)],
                          mocks={"ffmpeg": INTERRUPTING_FFMPEG_MOCK, "ffprobe": FFPROBE_MOCK})

        assert result.returncode == 130
        assert "interrupted" in result.stdout
        assert "compressed 0, skipped 0, failed 0 of 2 file(s)" in result.stdout
        assert not (tmp_path / "a_compressed.mp4").exists()
        assert (tmp_path / "a.mov").exists()

    def should_keep_the_original_when_its_encode_fails(self, compress, tmp_path):
        _make_video(tmp_path / "bad.mov")

        result = compress(["-r", "--rm-original", str(tmp_path)],
                          env_extra={"MOCK_FAIL_ON": "bad"})

        assert result.returncode == 1
        assert (tmp_path / "bad.mov").exists()
