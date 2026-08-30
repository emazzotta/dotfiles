import pytest

EXTENSIONS = ["jpg", "png", "heic"]


@pytest.fixture
def mod(load_script):
    return load_script("imagelib.py")


class TestFindImages:
    def test_should_find_the_listed_extensions(self, mod, tmp_path):
        for name in ("a.jpg", "b.png", "c.heic", "d.txt", "e.gif"):
            (tmp_path / name).touch()

        names = {path.name for path in mod.find_images(tmp_path, EXTENSIONS)}

        assert names == {"a.jpg", "b.png", "c.heic"}

    def test_should_match_uppercase_extensions(self, mod, tmp_path):
        (tmp_path / "photo.JPG").touch()

        assert [path.name for path in mod.find_images(tmp_path, EXTENSIONS)] == ["photo.JPG"]

    def test_should_search_recursively(self, mod, tmp_path):
        nested = tmp_path / "sub" / "deeper"
        nested.mkdir(parents=True)
        (nested / "buried.png").touch()

        assert [path.name for path in mod.find_images(tmp_path, EXTENSIONS)] == ["buried.png"]

    def test_should_include_dotted_files_and_directories(self, mod, tmp_path):
        hidden_dir = tmp_path / ".cache"
        hidden_dir.mkdir()
        (hidden_dir / "inside.jpg").touch()
        (tmp_path / ".hidden.jpg").touch()

        names = {path.name for path in mod.find_images(tmp_path, EXTENSIONS)}

        assert names == {"inside.jpg", ".hidden.jpg"}

    def test_should_return_every_lowercase_match_before_uppercase_ones(self, mod, tmp_path):
        for name in ("z.jpg", "A.JPG", "y.png"):
            (tmp_path / name).touch()

        assert [path.name for path in mod.find_images(tmp_path, EXTENSIONS)] == ["z.jpg", "y.png", "A.JPG"]

    def test_should_return_nothing_for_an_empty_directory(self, mod, tmp_path):
        assert mod.find_images(tmp_path, EXTENSIONS) == []


class TestCollectImages:
    def test_should_take_a_file_whatever_its_extension(self, mod, tmp_path):
        document = tmp_path / "notes.txt"
        document.touch()

        assert mod.collect_images([document], EXTENSIONS) == [document]

    def test_should_expand_a_directory(self, mod, tmp_path):
        first = tmp_path / "a.jpg"
        first.touch()

        assert mod.collect_images([tmp_path], EXTENSIONS) == [first]

    def test_should_keep_each_file_once_when_inputs_overlap(self, mod, tmp_path):
        image = tmp_path / "photo.jpg"
        image.touch()

        assert mod.collect_images([tmp_path, image], EXTENSIONS) == [image]

    def test_should_preserve_the_order_the_inputs_were_given_in(self, mod, tmp_path):
        second = tmp_path / "b.jpg"
        first = tmp_path / "a.jpg"
        second.touch()
        first.touch()

        assert mod.collect_images([second, first], EXTENSIONS) == [second, first]

    def test_should_return_nothing_for_no_inputs(self, mod):
        assert mod.collect_images([], EXTENSIONS) == []

    def test_should_exit_when_an_input_is_missing(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.collect_images([tmp_path / "nonexistent.jpg"], EXTENSIONS)
