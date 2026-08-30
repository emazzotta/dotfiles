"""Replays the pre-refactor audiotox/videotox/audioboost contract against medialib.

The golden file was captured from the three scripts before medialib existed, so
it is the oracle: a diff means medialib drifted from what those scripts did.
Run it through ./check, which knows the one accepted divergence.
"""
import sys
from pathlib import Path
from types import ModuleType

BIN_DIR = Path(__file__).resolve().parent.parent.parent
SCRIPTS = ("audiotox", "videotox", "audioboost")


def load_medialib():
    sys.path.insert(0, str(BIN_DIR))
    medialib = ModuleType("medialib")
    medialib.__file__ = str(BIN_DIR / "medialib.py")
    sys.modules["medialib"] = medialib
    exec((BIN_DIR / "medialib.py").read_text(), medialib.__dict__)
    return medialib


class Shim:
    """The pre-refactor per-script API, re-expressed on top of medialib."""

    def __init__(self, name, medialib, extensions, naming):
        object.__setattr__(self, "__name__", name)
        object.__setattr__(self, "_medialib", medialib)
        object.__setattr__(self, "_extensions", extensions)
        object.__setattr__(self, "_naming", naming)

    def __setattr__(self, key, value):
        if key == "input":
            self._medialib.input = value
        else:
            object.__setattr__(self, key, value)

    def format_time(self, seconds):
        return self._medialib.format_time(seconds)

    def list_inputs(self, path):
        return self._medialib.list_inputs(path, self._extensions)

    def collect_inputs(self, paths):
        return self._medialib.collect_inputs(paths, self._extensions)

    def get_output_path(self, input_file, second, output_dir):
        return self._medialib.resolve_output_path(
            input_file, output_dir, self._naming(self._medialib, input_file, second))


def build_shim(name, medialib):
    if name == "audioboost":
        def naming(lib, input_file, suffix):
            return lib.OutputNaming(extension=input_file.suffix,
                                    name_suffix=suffix, conflict_suffix=suffix)

        return Shim(name, medialib, medialib.AUDIO_EXTS, naming)

    def naming(lib, _input_file, fmt):
        return lib.OutputNaming(extension=f".{fmt}")

    extensions = medialib.VIDEO_EXTS if name == "videotox" else medialib.AUDIO_EXTS
    return Shim(name, medialib, extensions, naming)


def call(fn, *args):
    try:
        return repr(fn(*args))
    except SystemExit as exit_error:
        return f"EX:SystemExit({exit_error.code})"
    except BaseException as error:
        return f"EX:{type(error).__name__}"


FORMAT_TIME_INPUTS = [0.0, 0.04, 0.05, 1.0, 59.0, 59.94, 59.95, 60.0, 60.5, 119.9,
                      3599.0, 3600.0, 3661.0, 86399.0, -1.0, -60.0, 1e9]

MEDIA_NAMES = ["a.mp3", "B.MP3", "c.wav", "d.WAV", "e.flac", "f.mp4", "g.MOV",
               "h.mkv", "i.txt", "j", "k.mp3.bak"]


def build_tree(root, tag):
    tree = root / f"tree_{tag}"
    (tree / "nested" / "deep").mkdir(parents=True)
    for name in MEDIA_NAMES:
        (tree / name).touch()
        (tree / "nested" / name).touch()
    (tree / "nested" / "deep" / "z.mp3").touch()
    empty = root / f"empty_{tag}"
    empty.mkdir()
    return tree, empty


def relative(root, value):
    return repr(value).replace(str(root), "<ROOT>")


def emit(rows, module_name, function_name, slot, value):
    rows.append(f"{module_name}\t{function_name}\t{slot}\t{value}")


def conflict_chain(module_name, second):
    """Names get_output_path walks, in order, when each preceding one exists."""
    if module_name == "audioboost":
        return [f"song{second}.wav", f"song{second}_2.wav",
                f"song{second}_3.wav", f"song{second}_4.wav"]
    return [f"song.{second}", f"song_converted.{second}",
            f"song_converted_2.{second}", f"song_converted_3.{second}"]


def probe_get_output_path(module, root, rows, second_arg_values, responses):
    work = root / f"gop_{module.__name__}"
    work.mkdir()
    out_dir = root / f"gop_out_{module.__name__}"
    out_dir.mkdir()
    source = work / "song.wav"
    source.touch()

    for second in second_arg_values:
        chain = conflict_chain(module.__name__, second)
        for response in responses:
            for use_out_dir in (False, True):
                for preexisting in range(len(chain) + 1):
                    target_dir = out_dir if use_out_dir else work
                    for existing in list(target_dir.glob("song*")):
                        if existing != source:
                            existing.unlink()
                    prompts = []

                    def record(prompt, _r=response, _sink=prompts):
                        _sink.append(prompt)
                        return _r

                    module.input = record
                    for name in chain[:preexisting]:
                        (target_dir / name).touch()
                    slot = f"arg={second}|resp={response}|outdir={use_out_dir}|pre={preexisting}"
                    value = call(module.get_output_path, source,
                                 second, out_dir if use_out_dir else None)
                    emit(rows, module.__name__, "get_output_path", slot,
                         value.replace(str(root), "<ROOT>"))
                    emit(rows, module.__name__, "get_output_path_prompt", slot,
                         repr(prompts).replace(str(root), "<ROOT>"))


def main():
    root = Path(sys.argv[1])
    medialib = load_medialib()
    rows = []

    for name in SCRIPTS:
        module = build_shim(name, medialib)

        for seconds in FORMAT_TIME_INPUTS:
            emit(rows, name, "format_time", repr(seconds), call(module.format_time, seconds))

        tree, empty = build_tree(root, name)
        cases = {
            "file": tree / "a.mp3",
            "file_uppercase": tree / "B.MP3",
            "file_unmatched_ext": tree / "i.txt",
            "dir": tree,
            "dir_nested": tree / "nested",
            "dir_empty": empty,
            "missing": root / "nope",
        }
        for slot, path in cases.items():
            emit(rows, name, "list_inputs", slot,
                 relative(root, call(module.list_inputs, path)).replace("'", ""))

        collect_cases = {
            "single_file": [tree / "a.mp3"],
            "two_files": [tree / "a.mp3", tree / "c.wav"],
            "duplicate_file": [tree / "a.mp3", tree / "a.mp3"],
            "dir_and_member": [tree, tree / "a.mp3"],
            "two_dirs": [tree / "nested", empty],
            "empty_list": [],
            "with_missing": [tree / "a.mp3", root / "nope"],
        }
        for slot, paths in collect_cases.items():
            emit(rows, name, "collect_inputs", slot,
                 relative(root, call(module.collect_inputs, paths)).replace("'", ""))

        second_args = ["_boosted", "_x"] if name == "audioboost" else ["mp3", "mp4"]
        probe_get_output_path(module, root, rows, second_args, ["y", "n", "", "a", "Y"])

    header = (f"# fixtures: {len(MEDIA_NAMES)} media names, "
              f"{len(FORMAT_TIME_INPUTS)} durations\n# rows: {len(rows)}\n")
    Path(sys.argv[2]).write_text(header + "\n".join(rows) + "\n")


main()
