import pytest


@pytest.fixture
def slugify(run_cli, tmp_path):
    work = tmp_path / "work"
    (work / "dir").mkdir(parents=True)

    def _run(name):
        (work / name).write_text("content")
        result = run_cli("rename_file_to_slugified", [name], cwd=work)
        assert result.returncode == 0, result.stderr
        return sorted(str(path.relative_to(work)) for path in work.rglob("*") if path.is_file())
    return _run


class TestRenameFileToSlugified:
    @pytest.mark.parametrize("name,renamed", [
        ("My Photo (1).JPG", "My_Photo_1_.JPG"),
        ("photo name.jpg", "photo_name.jpg"),
        ("dir/my file.txt", "dir/my_file.txt"),
        ("notes & todos", "notes_todos"),
        ("archive.tar.gz", "archive_tar.gz"),
    ])
    def test_should_slugify_the_stem_and_keep_the_extension_and_directory(self, slugify, name, renamed):
        assert slugify(name) == [renamed]

    @pytest.mark.parametrize("name", ["photo.jpg", "dir/clean_name.txt", ".bashrc"])
    def test_should_leave_an_already_clean_name_alone(self, slugify, name):
        assert slugify(name) == [name]

    def test_should_print_usage_without_arguments(self, run_cli):
        result = run_cli("rename_file_to_slugified")

        assert result.returncode == 0
        assert "usage:" in result.stdout
