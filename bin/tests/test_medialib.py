import pytest


@pytest.fixture
def mod(load_script):
    return load_script("medialib.py")


@pytest.fixture
def answer(mod):
    def _answer(response):
        prompts = []
        mod.input = lambda prompt: prompts.append(prompt) or response
        return prompts
    return _answer


class TestFormatTime:
    @pytest.mark.parametrize("seconds,expected", [
        (0.0, "0.0s"),
        (30.5, "30.5s"),
        (59.9, "59.9s"),
        (60.0, "1m 0s"),
        (90.0, "1m 30s"),
        (3661.0, "61m 1s"),
    ])
    def test_should_format_a_duration(self, mod, seconds, expected):
        assert mod.format_time(seconds) == expected


class TestListInputs:
    def test_should_return_the_file_itself_when_given_a_file(self, mod, tmp_path):
        track = tmp_path / "song.mp3"
        track.touch()

        assert mod.list_inputs(track, mod.AUDIO_EXTS) == [track]

    def test_should_return_a_file_whose_extension_is_not_listed(self, mod, tmp_path):
        document = tmp_path / "notes.txt"
        document.touch()

        assert mod.list_inputs(document, mod.AUDIO_EXTS) == [document]

    def test_should_find_only_the_listed_extensions_in_a_directory(self, mod, tmp_path):
        for name in ("a.mp3", "b.flac", "c.wav", "d.txt", "e.mp4"):
            (tmp_path / name).touch()

        names = {path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)}

        assert names == {"a.mp3", "b.flac", "c.wav"}

    def test_should_match_uppercase_extensions(self, mod, tmp_path):
        (tmp_path / "loud.WAV").touch()

        assert [path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)] == ["loud.WAV"]

    def test_should_search_recursively(self, mod, tmp_path):
        nested = tmp_path / "sub" / "deeper"
        nested.mkdir(parents=True)
        (nested / "buried.mp3").touch()

        assert [path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)] == ["buried.mp3"]

    def test_should_return_results_sorted(self, mod, tmp_path):
        for name in ("c.mp3", "a.mp3", "b.mp3"):
            (tmp_path / name).touch()

        assert [path.name for path in mod.list_inputs(tmp_path, mod.AUDIO_EXTS)] == ["a.mp3", "b.mp3", "c.mp3"]

    def test_should_return_nothing_for_an_empty_directory(self, mod, tmp_path):
        assert mod.list_inputs(tmp_path, mod.AUDIO_EXTS) == []

    def test_should_exit_when_the_path_does_not_exist(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.list_inputs(tmp_path / "nonexistent", mod.AUDIO_EXTS)


class TestCollectInputs:
    def test_should_gather_every_path_when_many_inputs_are_given(self, mod, tmp_path):
        first = tmp_path / "a.wav"
        second = tmp_path / "b.flac"
        first.touch()
        second.touch()

        assert mod.collect_inputs([first, second], mod.AUDIO_EXTS) == [first, second]

    def test_should_keep_each_file_once_when_inputs_overlap(self, mod, tmp_path):
        track = tmp_path / "track.wav"
        track.touch()

        assert mod.collect_inputs([tmp_path, track], mod.AUDIO_EXTS) == [track]

    def test_should_return_nothing_for_no_inputs(self, mod):
        assert mod.collect_inputs([], mod.AUDIO_EXTS) == []

    def test_should_exit_when_an_input_is_missing(self, mod, tmp_path):
        with pytest.raises(SystemExit):
            mod.collect_inputs([tmp_path / "nonexistent.wav"], mod.AUDIO_EXTS)


class TestResolveOutputPath:
    def test_should_place_output_next_to_the_input_by_default(self, mod, tmp_path):
        source = tmp_path / "song.wav"
        source.touch()

        result = mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

        assert result == tmp_path / "song.mp3"

    def test_should_place_output_in_the_given_directory(self, mod, tmp_path):
        source = tmp_path / "song.wav"
        source.touch()
        out_dir = tmp_path / "out"
        out_dir.mkdir()

        result = mod.resolve_output_path(source, out_dir, mod.OutputNaming(extension=".flac"))

        assert result == out_dir / "song.flac"

    def test_should_apply_the_name_suffix_and_keep_the_extension(self, mod, tmp_path):
        source = tmp_path / "song.wav"
        source.touch()

        result = mod.resolve_output_path(
            source, None, mod.OutputNaming(extension=".wav", name_suffix="_boosted",
                                           conflict_suffix="_boosted"))

        assert result == tmp_path / "song_boosted.wav"

    def test_should_overwrite_when_the_answer_is_yes(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        (tmp_path / "song.mp3").touch()
        answer("y")

        result = mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

        assert result == tmp_path / "song.mp3"

    def test_should_abort_when_the_answer_is_abort(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        (tmp_path / "song.mp3").touch()
        answer("a")

        with pytest.raises(SystemExit):
            mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

    def test_should_add_the_conflict_suffix_when_the_answer_is_no(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        (tmp_path / "song.mp3").touch()
        answer("n")

        result = mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

        assert result == tmp_path / "song_converted.mp3"

    def test_should_escalate_the_counter_while_names_are_taken(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        for name in ("song.mp3", "song_converted.mp3", "song_converted_2.mp3"):
            (tmp_path / name).touch()
        answer("n")

        result = mod.resolve_output_path(source, None, mod.OutputNaming(extension=".mp3"))

        assert result == tmp_path / "song_converted_3.mp3"

    def test_should_name_the_actual_conflict_suffix_in_the_prompt(self, mod, tmp_path, answer):
        source = tmp_path / "song.wav"
        source.touch()
        (tmp_path / "song_loud.wav").touch()
        prompts = answer("y")

        mod.resolve_output_path(source, None,
                                mod.OutputNaming(extension=".wav", name_suffix="_loud",
                                                 conflict_suffix="_loud"))

        assert "N=add _loud" in prompts[0]
