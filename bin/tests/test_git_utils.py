from collections import Counter
from types import SimpleNamespace

import pytest


class TestGac:
    def test_no_args_runs_amend(self, run_bash, tmp_path):
        result = run_bash("gac", mock_bins={
            "git": 'echo "git $@"',
            "first_capitalize": 'echo "$1"',
        })
        combined = result.stdout + result.stderr
        assert "git" in combined.lower() or result.returncode == 0

    def test_with_message(self, run_bash):
        result = run_bash("gac", ["test message"], mock_bins={
            "git": 'echo "git $@"',
            "first_capitalize": 'echo "$@"',
        })
        assert result.returncode == 0


class TestNocontrib:
    def test_runs_without_error(self, run_bash, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        import subprocess
        subprocess.run(["git", "init", str(repo)], capture_output=True)
        subprocess.run(["git", "-C", str(repo), "commit", "--allow-empty", "-m", "init"], capture_output=True)
        result = run_bash("nocontrib", env_extra={"HOME": str(tmp_path)})
        assert result.returncode == 0


class TestCodecost:
    def test_runs_in_empty_dir(self, run_bash, tmp_path):
        result = run_bash("codecost", env_extra={"HOME": str(tmp_path)}, mock_bins={
            "sloccount": 'echo "Total: 0"',
        })
        assert result.returncode == 0 or "sloccount" in (result.stdout + result.stderr).lower()


class TestGitio:
    def test_no_args_shows_usage(self, run_bash):
        result = run_bash("gitio")
        assert "usage" in result.stdout.lower()


@pytest.fixture
def gallcontrib(load_script):
    return load_script("git_gallcontrib")


def tally(mod, *rows):
    return Counter({mod.Identity(name, email): count for name, email, count in rows})


def summarise(mod, *rows):
    return {author.name: author.commits for author in mod.build_authors(tally(mod, *rows))}


class TestGitGallcontrib:
    def should_merge_a_dotted_handle_with_the_spaced_name(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("josef.blatman", "josef.blatman@svn-uuid", 16372),
                           ("Josef Blatman", "josef.blatman@example.ag", 30))

        assert result == {"Josef Blatman": 16402}

    def should_merge_a_reordered_email_local_part(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("Emanuele Mazzotta", "mazzotta.emanuele@gmail.com", 3087),
                           ("emanuele.mazzotta", "emanuele.mazzotta@svn-uuid", 66))

        assert result == {"Emanuele Mazzotta": 3153}

    def should_merge_a_spelling_that_has_no_separator(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("Andreas Ochsner", "andreas.ochsner@example.ag", 232),
                           ("andreasochsner", "andreas.ochsner@example.ag", 342))

        assert result == {"Andreas Ochsner": 574}

    def should_merge_across_a_generic_email_that_carries_no_name(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("Emanuele Mazzotta", "mazzotta.emanuele@gmail.com", 3087),
                           ("Emanuele Mazzotta", "info@example.ag", 7))

        assert result == {"Emanuele Mazzotta": 3094}

    def should_ignore_a_middle_initial(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("Thomas K. Friedli", "thomas.k.friedli@bluewin.ch", 37),
                           ("thomas.friedli", "thomas.friedli@example.ag", 4),
                           ("Thomas Friedli", "thomas.friedli@example.local", 1))

        assert result == {"Thomas K. Friedli": 42}

    def should_fold_a_first_name_into_the_one_full_name_that_claims_it(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("Andreas Ochsner", "andreas.ochsner@example.ag", 232),
                           ("andreas", "andreas@svn-uuid", 47))

        assert result == {"Andreas Ochsner": 279}

    def should_leave_a_first_name_alone_when_several_full_names_claim_it(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("Andreas Ochsner", "andreas.ochsner@example.ag", 232),
                           ("Andreas Meier", "andreas.meier@example.ag", 100),
                           ("andreas", "andreas@svn-uuid", 47))

        assert result == {"Andreas Ochsner": 232, "Andreas Meier": 100, "andreas": 47}

    def should_leave_a_first_name_alone_when_no_full_name_claims_it(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("Andreas Ochsner", "andreas.ochsner@example.ag", 232),
                           ("Damian", "Damian@svn-uuid", 9))

        assert result == {"Andreas Ochsner": 232, "Damian": 9}

    def should_not_fold_a_person_into_a_bot(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("GitLab CI", "ci@gitlab.example", 472),
                           ("gitlab", "gitlab@svn-uuid", 3))

        assert result == {"GitLab CI": 472, "gitlab": 3}

    def should_reconstruct_a_display_name_from_a_dotted_handle(self, gallcontrib):
        result = summarise(gallcontrib,
                           ("caroline.fuchsbausch", "caroline.fuchsbausch@svn-uuid", 194))

        assert result == {"Caroline Fuchsbausch": 194}

    def should_keep_a_single_word_handle_verbatim(self, gallcontrib):
        result = summarise(gallcontrib, ("testaccount", "testaccount@svn-uuid", 2))

        assert result == {"testaccount": 2}

    def should_prefer_the_human_written_spelling_over_the_most_frequent_one(self, gallcontrib):
        authors = gallcontrib.build_authors(tally(
            gallcontrib,
            ("josef.blatman", "josef.blatman@svn-uuid", 16372),
            ("Josef Blatman", "josef.blatman@example.ag", 30)))

        assert authors[0].name == "Josef Blatman"

    @pytest.mark.parametrize("name,email", [
        pytest.param("GitLab CI", "ci@gitlab.example", id="ci_name"),
        pytest.param("VisualSVN Server", "VisualSVN Server@svn-uuid", id="server_name"),
        pytest.param("Access Token", "group_3_bot_abc@noreply.gitlab.example", id="bot_email"),
        pytest.param("dependabot[bot]", "support@github.com", id="bot_suffix"),
    ])
    def should_classify_machine_identities_as_bots(self, gallcontrib, name, email):
        assert gallcontrib.is_bot(gallcontrib.Identity(name, email)) is True

    @pytest.mark.parametrize("name,email", [
        pytest.param("Josef Blatman", "josef.blatman@example.ag", id="full_name"),
        pytest.param("aaron.stampa", "aaron.stampa@uzh.ch", id="dotted_handle"),
    ])
    def should_classify_people_as_people(self, gallcontrib, name, email):
        assert gallcontrib.is_bot(gallcontrib.Identity(name, email)) is False

    def should_preserve_the_total_commit_count(self, gallcontrib):
        rows = (("josef.blatman", "josef.blatman@svn-uuid", 16372),
                ("Josef", "Josef@svn-uuid", 25),
                ("GitLab CI", "ci@gitlab.example", 472),
                ("Damian", "Damian@svn-uuid", 9))

        authors = gallcontrib.build_authors(tally(gallcontrib, *rows))

        assert sum(author.commits for author in authors) == sum(row[2] for row in rows)

    def should_rank_bots_below_people(self, gallcontrib, capsys):
        authors = gallcontrib.build_authors(tally(
            gallcontrib,
            ("GitLab CI", "ci@gitlab.example", 472),
            ("Josef Blatman", "josef.blatman@example.ag", 30)))

        gallcontrib.render(authors, False, gallcontrib.Palette())

        lines = [line for line in capsys.readouterr().out.splitlines() if line]
        assert lines == ["People (1)", " 30 Josef Blatman",
                         "Bots & services (1)", "472 GitLab CI"]

    def should_list_the_raw_spellings_when_verbose(self, gallcontrib, capsys):
        authors = gallcontrib.build_authors(tally(
            gallcontrib,
            ("josef.blatman", "josef.blatman@svn-uuid", 16372),
            ("Josef Blatman", "josef.blatman@example.ag", 30)))

        gallcontrib.render(authors, True, gallcontrib.Palette())

        output = capsys.readouterr().out
        assert "josef.blatman <josef.blatman@svn-uuid>" in output
        assert "Josef Blatman <josef.blatman@example.ag>" in output

    def should_exit_with_an_error_when_the_directory_is_missing(self, run_cli, tmp_path):
        result = run_cli("git_gallcontrib", [str(tmp_path / "absent")])

        assert result.returncode == 1
        assert "does not exist" in result.stderr

    def should_report_when_no_repository_is_found(self, run_cli, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()

        result = run_cli("git_gallcontrib", [str(empty)])

        assert result.returncode == 0
        assert "No Git repositories found." in result.stdout

    def should_aggregate_the_spellings_of_a_real_repository(self, run_cli, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git(repo, "init")
        _commit(repo, "josef.blatman", "josef.blatman@svn-uuid")
        _commit(repo, "Josef Blatman", "josef.blatman@example.ag")
        _commit(repo, "Josef", "Josef@svn-uuid")


        result = run_cli("git_gallcontrib", [str(repo)])

        assert result.returncode == 0
        assert result.stdout.splitlines() == [
            "People (1)", "3 Josef Blatman", "", "Repositories (1)", "3 repo"]


def _git(repo, *args):
    import subprocess
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)


def _commit(repo, name, email):
    """A pathspec-limited log skips commits that touch nothing, so write a file."""
    (repo / f"{len(list(repo.glob('*.txt')))}.txt").write_text(name)
    _git(repo, "add", ".")
    _git(repo, "-c", f"user.name={name}", "-c", f"user.email={email}",
         "commit", "--no-gpg-sign", "-m", f"commit by {name}")


class TestGitGallcontribPresentation:
    def should_not_colour_a_stream_that_is_not_a_terminal(self, gallcontrib):
        palette = gallcontrib.Palette.detect(SimpleNamespace(isatty=lambda: False))

        assert palette == gallcontrib.Palette()

    def should_colour_a_terminal(self, gallcontrib, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)

        palette = gallcontrib.Palette.detect(SimpleNamespace(isatty=lambda: True))

        assert palette.heading and palette.count and palette.muted

    def should_obey_no_color(self, gallcontrib, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")

        palette = gallcontrib.Palette.detect(SimpleNamespace(isatty=lambda: True))

        assert palette == gallcontrib.Palette()

    def should_wrap_coloured_text_in_a_reset(self, gallcontrib):
        assert gallcontrib.paint("x", "<style>") == "<style>x" + gallcontrib.RESET

    def should_leave_text_untouched_when_the_style_is_empty(self, gallcontrib):
        assert gallcontrib.paint("x", "") == "x"

    def should_list_every_scanned_repository(self, gallcontrib, capsys):
        repositories = [_repository(gallcontrib, "alpha", 7), _repository(gallcontrib, "beta", 12)]

        gallcontrib.render_repositories(repositories, gallcontrib.Palette())

        lines = capsys.readouterr().out.splitlines()
        assert lines == ["Repositories (2)", "12 beta", " 7 alpha"]

    def should_mark_a_repository_that_contributed_nothing(self, gallcontrib, capsys):
        repositories = [_repository(gallcontrib, "alpha", 7), _repository(gallcontrib, "empty", 0)]

        gallcontrib.render_repositories(repositories, gallcontrib.Palette())

        assert "0 empty  (nothing counted)" in capsys.readouterr().out

    def should_still_list_repositories_when_nothing_was_counted(self, run_cli, tmp_path):
        repo = tmp_path / "bare"
        repo.mkdir()
        _git(repo, "init")

        result = run_cli("git_gallcontrib", [str(repo)])

        assert result.returncode == 0
        assert "0 bare  (nothing counted)" in result.stdout


def _repository(mod, name, commits):
    tallies = Counter({mod.Identity(name, f"{name}@example.ag"): commits}) if commits else Counter()
    return mod.Repository(name, tallies)
