from pathlib import Path

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


class TestCollectInputFiles:
    def test_should_gather_every_path_when_many_inputs_are_given(self, mod, tmp_path):
        first = tmp_path / "a.jpg"
        second = tmp_path / "b.png"
        first.touch()
        second.touch()

        assert mod.collect_input_files([first, second]) == [first, second]

    def test_should_keep_each_file_once_when_inputs_overlap(self, mod, tmp_path):
        image = tmp_path / "photo.jpg"
        image.touch()

        assert mod.collect_input_files([tmp_path, image]) == [image]

    def test_should_exit_when_an_input_is_missing(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.collect_input_files([tmp_path / "nonexistent.jpg"])


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
