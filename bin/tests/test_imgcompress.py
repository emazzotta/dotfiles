
import pytest


@pytest.fixture
def mod(load_script):
    return load_script("imgcompress")


class TestFmtSize:
    @pytest.mark.parametrize("size,expected", [
        (0, "0.0 B"),
        (500, "500.0 B"),
        (1024, "1.0 KB"),
        (1536, "1.5 KB"),
        (1048576, "1.0 MB"),
        (1073741824, "1.0 GB"),
        (1099511627776, "1.0 TB"),
    ])
    def test_formats_correctly(self, mod, size, expected):
        assert mod.fmt_size(size) == expected


class TestBuildMagickCommand:
    def test_jpeg_command(self, mod, tmp_path):
        cmd = mod.build_magick_command(tmp_path / "photo.jpg", tmp_path / "out.jpg", quality=80, scale=50)
        assert cmd[0] == "magick"
        assert "-strip" in cmd
        assert "50%" in cmd
        assert "-quality" in cmd
        assert "80" in cmd
        assert "-define" not in cmd

    def test_png_uses_compression_defines(self, mod, tmp_path):
        cmd = mod.build_magick_command(tmp_path / "image.png", tmp_path / "out.png", quality=80, scale=100)
        assert "png:compression-level=9" in cmd
        assert "-quality" not in cmd

    @pytest.mark.parametrize("ext", ["jpg", "jpeg", "webp", "tiff", "bmp", "heic"])
    def test_non_png_uses_quality(self, mod, tmp_path, ext):
        cmd = mod.build_magick_command(tmp_path / f"img.{ext}", tmp_path / f"out.{ext}", quality=75, scale=80)
        assert "-quality" in cmd
        assert "75" in cmd

    def test_output_file_is_last_arg(self, mod, tmp_path):
        out = tmp_path / "out.jpg"
        cmd = mod.build_magick_command(tmp_path / "in.jpg", out, quality=80, scale=50)
        assert cmd[-1] == str(out)


class TestResolveOutputFile:
    def test_with_output_path(self, mod, tmp_path):
        result = mod.resolve_output_file(tmp_path / "photo.jpg", tmp_path / "output", rm_original=False)
        assert result == tmp_path / "output" / "photo.jpg"

    def test_rm_original_returns_same_path(self, mod, tmp_path):
        input_file = tmp_path / "photo.jpg"
        assert mod.resolve_output_file(input_file, None, rm_original=True) == input_file

    def test_default_adds_compressed_suffix(self, mod, tmp_path):
        result = mod.resolve_output_file(tmp_path / "photo.jpg", None, rm_original=False)
        assert result == tmp_path / "photo_compressed.jpg"

    def test_preserves_extension(self, mod, tmp_path):
        result = mod.resolve_output_file(tmp_path / "image.png", None, rm_original=False)
        assert result.suffix == ".png"
        assert "_compressed" in result.stem


MAGICK_OK = 'printf x > "${@: -1}"'


class TestCli:
    def test_should_compress_every_file_when_a_glob_expands_to_many_inputs(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        names = ["one.jpg", "two.jpg", "three.jpg"]
        for name in names:
            (work / name).write_text("original content, larger than the mock output")

        result = run_cli("imgcompress", ["-i"] + [str(work / n) for n in names],
                         mock_bins={"magick": MAGICK_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert {p.name for p in work.glob("*_compressed.jpg")} == {
            "one_compressed.jpg", "two_compressed.jpg", "three_compressed.jpg"}

class TestCwdDefault:
    def test_should_compress_the_sole_image_when_no_input_is_given(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "photo.jpg").write_text("original content, larger than the mock output")
        (work / "notes.txt").write_text("ignore me")

        result = run_cli("imgcompress", [], mock_bins={"magick": MAGICK_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "photo_compressed.jpg").exists()

    def test_should_exit_when_several_images_match_and_no_terminal_can_prompt(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        for name in ("one.jpg", "two.jpg"):
            (work / name).write_text("original content, larger than the mock output")

        result = run_cli("imgcompress", [], mock_bins={"magick": MAGICK_OK}, cwd=work)

        assert result.returncode != 0
        assert not list(work.glob("*_compressed.jpg"))


ORIGINAL = "original content, larger than the mock output"
MAGICK_BY_FOLDER = 'printf "compressed from %s" "$(basename "$(dirname "$1")")" > "${@: -1}"'
MAGICK_FAILS_ON_ONE = (
    'case "${@: -1}" in *one*) echo "magick: corrupt header" >&2; exit 1;; esac\n'
    + MAGICK_OK
)


class TestSafety:
    def test_should_continue_with_the_next_file_and_exit_non_zero_when_one_conversion_fails(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        for name in ("one.jpg", "two.jpg"):
            (work / name).write_text(ORIGINAL)

        result = run_cli("imgcompress", ["-i", str(work / "one.jpg"), str(work / "two.jpg")],
                         mock_bins={"magick": MAGICK_FAILS_ON_ONE}, cwd=work)

        assert result.returncode != 0
        assert (work / "two_compressed.jpg").exists()
        assert (work / "one.jpg").read_text() == ORIGINAL
        assert not list(work.glob("*_tmp_compress*"))

    def test_should_show_what_the_converter_reported_when_it_fails(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "one.jpg").write_text(ORIGINAL)

        result = run_cli("imgcompress", ["-i", str(work / "one.jpg")],
                         mock_bins={"magick": MAGICK_FAILS_ON_ONE}, cwd=work)

        assert "magick: corrupt header" in result.stderr

    def test_should_replace_the_original_in_place_when_rm_original_has_no_output_path(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "photo.jpg").write_text(ORIGINAL)

        result = run_cli("imgcompress", ["-i", str(work / "photo.jpg"), "--rm-original"],
                         mock_bins={"magick": MAGICK_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "photo.jpg").read_text() == "x"
        assert sorted(p.name for p in work.iterdir()) == ["photo.jpg"]

    def test_should_leave_the_file_untouched_when_the_output_path_is_its_own_folder_and_nothing_is_removed(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "photo.jpg").write_text(ORIGINAL)

        result = run_cli("imgcompress", ["-i", str(work / "photo.jpg"), "-o", str(work)],
                         mock_bins={"magick": MAGICK_OK}, cwd=work)

        assert result.returncode == 0, result.stderr
        assert (work / "photo.jpg").read_text() == ORIGINAL

    def test_should_keep_the_second_original_when_two_inputs_share_a_name_and_one_output_path(self, run_cli, tmp_path):
        first = tmp_path / "100APPLE"
        second = tmp_path / "101APPLE"
        out = tmp_path / "out"
        for folder in (first, second):
            folder.mkdir()
            (folder / "IMG_0001.jpg").write_text(ORIGINAL)

        result = run_cli("imgcompress", ["-i", str(first / "IMG_0001.jpg"), str(second / "IMG_0001.jpg"),
                                         "-o", str(out), "--rm-original"],
                         mock_bins={"magick": MAGICK_BY_FOLDER}, cwd=tmp_path)

        assert result.returncode == 0, result.stderr
        assert (out / "IMG_0001.jpg").read_text() == "compressed from 100APPLE"
        assert not (first / "IMG_0001.jpg").exists()
        assert (second / "IMG_0001.jpg").read_text() == ORIGINAL

    def test_should_keep_the_original_when_the_result_cannot_be_moved_to_the_output_path(self, run_cli, tmp_path):
        work = tmp_path / "work"
        work.mkdir()
        (work / "photo.jpg").write_text(ORIGINAL)
        out = tmp_path / "out"
        magick_that_removes_the_output_path = f'{MAGICK_OK}\nrmdir "{out}"'

        result = run_cli("imgcompress", ["-i", str(work / "photo.jpg"), "-o", str(out), "--rm-original"],
                         mock_bins={"magick": magick_that_removes_the_output_path}, cwd=work)

        assert result.returncode != 0
        assert (work / "photo.jpg").read_text() == ORIGINAL
        assert not list(work.glob("*_tmp_compress*"))
