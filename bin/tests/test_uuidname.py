import re

UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"


def should_replace_whitespace_and_insert_uuid_before_extension(run_bash, tmp_path):
    (tmp_path / "Vibe Raters - AVA Club Debut.mp3").write_text("x")

    result = run_bash("uuidname", ["Vibe Raters - AVA Club Debut.mp3"], cwd=tmp_path)

    assert result.returncode == 0
    names = [p.name for p in tmp_path.iterdir() if p.is_file()]
    assert len(names) == 1
    assert re.fullmatch(rf"Vibe_Raters-AVA_Club_Debut-{UUID}\.mp3", names[0])


def should_append_uuid_to_names_without_extension(run_bash, tmp_path):
    folder = tmp_path / "in"
    folder.mkdir()
    (folder / "my notes").write_text("x")

    result = run_bash("uuidname", [str(folder / "my notes")])

    assert result.returncode == 0
    [renamed] = list(folder.iterdir())
    assert re.fullmatch(rf"my_notes-{UUID}", renamed.name)
    assert result.stdout.strip() == str(renamed)


def should_fail_for_missing_file_and_still_rename_the_rest(run_bash, tmp_path):
    (tmp_path / "a b.txt").write_text("x")

    result = run_bash("uuidname", ["missing.txt", "a b.txt"], cwd=tmp_path)

    assert result.returncode == 1
    assert "not found: missing.txt" in result.stderr
    assert not (tmp_path / "a b.txt").exists()


def should_print_usage_without_arguments(run_bash):
    result = run_bash("uuidname", [])

    assert result.returncode == 2
    assert "Usage:" in result.stderr
