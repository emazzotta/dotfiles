import pytest


@pytest.fixture
def mod(load_script):
    return load_script("imgtox")


class TestFindImageFiles:
    def test_finds_common_formats(self, mod, tmp_path):
        for name in ("a.jpg", "b.png", "c.gif", "d.webp", "e.txt"):
            (tmp_path / name).touch()
        results = mod.find_image_files(tmp_path)
        names = {r.name for r in results}
        assert "a.jpg" in names
        assert "b.png" in names
        assert "c.gif" in names
        assert "d.webp" in names
        assert "e.txt" not in names

    def test_finds_uppercase_extensions(self, mod, tmp_path):
        (tmp_path / "photo.JPG").touch()
        results = mod.find_image_files(tmp_path)
        assert any(r.name == "photo.JPG" for r in results)

    def test_recursive_search(self, mod, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.png").touch()
        results = mod.find_image_files(tmp_path)
        assert any(r.name == "nested.png" for r in results)

    def test_empty_directory(self, mod, tmp_path):
        assert mod.find_image_files(tmp_path) == []


MAGICK_OK = 'touch "$2"'
MAGICK_FAILS_ON_BAD = 'case "$1" in *bad*) exit 1 ;; esac\ntouch "$2"'


@pytest.fixture
def work_dir(tmp_path):
    directory = tmp_path / "work"
    directory.mkdir()
    return directory


def make_images(directory, *names):
    for name in names:
        (directory / name).touch()
    return [str(directory / name) for name in names]


class TestCli:
    def test_should_convert_every_file_when_a_glob_expands_to_many_inputs(self, run_cli, work_dir):
        inputs = make_images(work_dir, "IMG_0512.HEIC", "IMG_0513.HEIC", "IMG_0514.HEIC")

        result = run_cli("imgtox", ["-f", "jpg", "-i"] + inputs,
                         mock_bins={"magick": MAGICK_OK}, cwd=work_dir)

        assert result.returncode == 0, result.stderr
        assert {p.name for p in work_dir.glob("*.jpg")} == {"IMG_0512.jpg", "IMG_0513.jpg", "IMG_0514.jpg"}

    def test_should_convert_single_file_when_one_input_is_given(self, run_cli, work_dir):
        inputs = make_images(work_dir, "solo.heic")

        result = run_cli("imgtox", ["-f", "jpg", "-i"] + inputs,
                         mock_bins={"magick": MAGICK_OK}, cwd=work_dir)

        assert result.returncode == 0, result.stderr
        assert (work_dir / "solo.jpg").exists()

    def test_should_convert_directory_contents_when_input_is_a_directory(self, run_cli, work_dir):
        source = work_dir / "photos"
        source.mkdir()
        make_images(source, "one.heic", "two.png")

        result = run_cli("imgtox", ["-f", "jpg", "-i", str(source)],
                         mock_bins={"magick": MAGICK_OK}, cwd=work_dir)

        assert result.returncode == 0, result.stderr
        assert {p.name for p in work_dir.glob("*.jpg")} == {"one.jpg", "two.jpg"}

    def test_should_convert_each_file_once_when_inputs_overlap(self, run_cli, work_dir):
        source = work_dir / "photos"
        source.mkdir()
        inputs = make_images(source, "dup.heic")

        result = run_cli("imgtox", ["-f", "jpg", "-i", str(source)] + inputs,
                         mock_bins={"magick": MAGICK_OK}, cwd=work_dir)

        assert result.returncode == 0, result.stderr
        assert "already exists" not in result.stdout

    def test_should_convert_remaining_files_when_one_conversion_fails(self, run_cli, work_dir):
        inputs = make_images(work_dir, "good.heic", "bad.heic", "later.heic")

        result = run_cli("imgtox", ["-f", "jpg", "-i"] + inputs,
                         mock_bins={"magick": MAGICK_FAILS_ON_BAD}, cwd=work_dir)

        assert result.returncode == 1
        assert {p.name for p in work_dir.glob("*.jpg")} == {"good.jpg", "later.jpg"}
        assert "Conversion failed" in result.stderr

    def test_should_exit_with_error_when_an_input_is_missing(self, run_cli, work_dir):
        inputs = make_images(work_dir, "present.heic")

        result = run_cli("imgtox", ["-f", "jpg", "-i"] + inputs + [str(work_dir / "absent.heic")],
                         mock_bins={"magick": MAGICK_OK}, cwd=work_dir)

        assert result.returncode == 1
        assert "not found" in result.stderr
        assert not list(work_dir.glob("*.jpg"))
