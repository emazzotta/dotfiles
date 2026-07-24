FFPROBE_MOCK = """for a in "$@"; do
  case "$a" in
    stream=pix_fmt) echo "${MOCK_PIX_FMT:-yuv420p}";;
    stream=color_transfer) echo "${MOCK_TRANSFER:-bt709}";;
    stream=color_primaries) echo "${MOCK_PRIMARIES:-bt709}";;
    stream=color_space) echo "${MOCK_SPACE:-bt709}";;
    stream=r_frame_rate) echo "${MOCK_RFR:-60/1}";;
  esac
done"""


def _ffmpeg_mock(encoders="libsvtav1", filters="zscale"):
    return f"""case "$*" in
  *-encoders*) echo " V..... {encoders}  AV1";;
  *-filters*) echo " ..C.. {filters}  V->V";;
esac"""


def _mocks(encoders="libsvtav1", filters="zscale"):
    return {"ffmpeg": _ffmpeg_mock(encoders, filters), "ffprobe": FFPROBE_MOCK}


def _dry_run(run_bash, tmp_path, args, env_extra=None, mocks=None):
    inp = tmp_path / "in.mp4"
    if not inp.exists():
        inp.write_bytes(b"data")
    return run_bash(
        "compressvideo",
        list(args) + ["--dry-run", str(inp)],
        mock_bins=mocks or _mocks(),
        isolate_path=True,
        env_extra=env_extra,
    )


class TestHelp:
    def test_help_flag_prints_usage_and_exits_zero(self, run_bash):
        result = run_bash("compressvideo", ["-h"], isolate_path=True)
        assert result.returncode == 0
        assert "usage:" in result.stdout


class TestDefaults:
    def test_default_uses_libx265_medium_crf28(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, [])
        assert result.returncode == 0
        assert "-c:v libx265 -preset medium -crf 28 -tag:v hvc1" in result.stdout

    def test_default_adds_faststart_and_aac_audio(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, [])
        assert "-movflags +faststart" in result.stdout
        assert "-c:a aac -b:a 128k" in result.stdout

    def test_output_name_gets_compressed_suffix(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, [])
        assert str(tmp_path / "in_compressed.mp4") in result.stdout


class TestScale:
    def test_scale_1080p_builds_downscale_filter(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-s", "1080p"])
        assert r"-vf scale=-2:min(ih\,1080)" in result.stdout

    def test_scale_accepts_bare_pixel_height(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-s", "720"])
        assert r"scale=-2:min(ih\,720)" in result.stdout

    def test_scale_2160p_alias(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-s", "4k"])
        assert r"scale=-2:min(ih\,2160)" in result.stdout

    def test_invalid_scale_exits_two(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-s", "huge"])
        assert result.returncode == 2
        assert "invalid --scale" in result.stderr


class TestFps:
    def test_fps_half_halves_integer_source(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--fps-half"])
        assert "-vf fps=60/2" in result.stdout

    def test_fps_half_stays_exact_on_fractional_source(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--fps-half"], env_extra={"MOCK_RFR": "60000/1001"})
        assert "fps=60000/2002" in result.stdout

    def test_fps_explicit_target(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--fps", "24"])
        assert "-vf fps=24" in result.stdout

    def test_fps_decimates_before_scaling(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--fps-half", "-s", "1080p"])
        assert r"-vf fps=60/2,scale=-2:min(ih\,1080)" in result.stdout

    def test_fps_and_fps_half_are_mutually_exclusive(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--fps-half", "--fps", "24"])
        assert result.returncode == 2
        assert "mutually exclusive" in result.stderr

    def test_invalid_fps_exits_two(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--fps", "fast"])
        assert result.returncode == 2
        assert "invalid --fps" in result.stderr

    def test_fps_half_fails_without_detectable_source_rate(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--fps-half"], env_extra={"MOCK_RFR": "0/0"})
        assert result.returncode == 2
        assert "detectable source frame rate" in result.stderr


class TestCodecs:
    def test_h264_default_crf_and_8bit(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-c", "h264"])
        assert "-c:v libx264 -preset medium -crf 23" in result.stdout
        assert "-pix_fmt yuv420p" in result.stdout

    def test_av1_default_crf_and_svt(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-c", "av1"])
        assert "-c:v libsvtav1 -crf 32 -preset 6" in result.stdout

    def test_av1_falls_back_to_libaom_when_svt_missing(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-c", "av1"], mocks=_mocks(encoders="none"))
        assert "-c:v libaom-av1 -crf 32" in result.stdout
        assert "libsvtav1 not found" in result.stdout

    def test_invalid_codec_exits_two(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-c", "vp9"])
        assert result.returncode == 2
        assert "invalid codec" in result.stderr


class TestPreset:
    def test_quality_override(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-q", "20"])
        assert "-crf 20" in result.stdout

    def test_invalid_preset_exits_two(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["-p", "turbo"])
        assert result.returncode == 2
        assert "invalid --preset" in result.stderr


class TestHardware:
    def test_hw_h265_uses_videotoolbox(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--hw", "-c", "h265"])
        assert "-c:v hevc_videotoolbox -q:v 55 -tag:v hvc1" in result.stdout

    def test_hw_av1_is_rejected(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--hw", "-c", "av1"])
        assert result.returncode == 2
        assert "hardware av1" in result.stderr


class TestArgOrder:
    def test_file_before_flags_parses_correctly(self, run_bash, tmp_path):
        inp = tmp_path / "in.mp4"
        inp.write_bytes(b"data")
        result = run_bash(
            "compressvideo",
            [str(inp), "-q", "20", "--dry-run"],
            mock_bins=_mocks(),
            isolate_path=True,
        )
        assert result.returncode == 0
        assert "-crf 20" in result.stdout
        assert str(inp) in result.stdout


class TestAudio:
    def test_copy_audio(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--copy-audio"])
        assert "-c:a copy" in result.stdout


class TestHdr:
    def test_hdr_10bit_h265_preserves_bitdepth_and_metadata(self, run_bash, tmp_path):
        env = {
            "MOCK_PIX_FMT": "yuv420p10le",
            "MOCK_TRANSFER": "smpte2084",
            "MOCK_PRIMARIES": "bt2020",
            "MOCK_SPACE": "bt2020nc",
        }
        result = _dry_run(run_bash, tmp_path, [], env_extra=env)
        assert "-pix_fmt yuv420p10le" in result.stdout
        assert "-color_primaries bt2020" in result.stdout
        assert "-color_trc smpte2084" in result.stdout
        assert "-colorspace bt2020nc" in result.stdout

    def test_hdr_h264_warns_and_forces_8bit(self, run_bash, tmp_path):
        env = {"MOCK_PIX_FMT": "yuv420p10le", "MOCK_TRANSFER": "smpte2084"}
        result = _dry_run(run_bash, tmp_path, ["-c", "h264"], env_extra=env)
        assert "HDR" in result.stdout
        assert "-pix_fmt yuv420p" in result.stdout

    def test_tonemap_builds_sdr_chain(self, run_bash, tmp_path):
        env = {"MOCK_PIX_FMT": "yuv420p10le", "MOCK_TRANSFER": "smpte2084"}
        result = _dry_run(run_bash, tmp_path, ["--tonemap"], env_extra=env)
        assert "tonemap=tonemap=hable" in result.stdout
        assert "-color_primaries bt709 -color_trc bt709 -colorspace bt709" in result.stdout

    def test_tonemap_requires_zscale(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--tonemap"], mocks=_mocks(filters="scale"))
        assert result.returncode == 2
        assert "zscale" in result.stderr


class TestPreviewCompatible:
    def test_forces_h264(self, run_bash, tmp_path):
        result = _dry_run(run_bash, tmp_path, ["--just-preview-compatible", "-c", "h265"])
        assert "-c:v libx264" in result.stdout


class TestValidation:
    def test_missing_input_file_exits_two(self, run_bash, tmp_path):
        result = run_bash(
            "compressvideo",
            ["--dry-run", str(tmp_path / "nope.mp4")],
            mock_bins=_mocks(),
            isolate_path=True,
        )
        assert result.returncode == 2
        assert "input file not found" in result.stderr
