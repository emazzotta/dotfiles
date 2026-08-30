"""Replays the pre-refactor imgtox/imgcompress contract against imagelib.

The golden file was captured from the two scripts before imagelib existed, so it
is the oracle: a diff means imagelib drifted from what those scripts did. Order
matters here and is compared as-is, because conversion order is observable.
"""
import sys
from pathlib import Path
from types import ModuleType

BIN_DIR = Path(__file__).resolve().parent.parent.parent

IMGTOX_EXTS = ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'svg', 'heic']
IMGCOMPRESS_EXTS = ["jpg", "jpeg", "png", "webp", "tiff", "bmp", "heic"]

NAMES = [
    "plain.jpg", "UPPER.JPG", "MiXeD.JpG", ".hidden.jpg", "with space.jpg",
    "uniè.jpg", "two.dots.jpg", "no_ext", "trailing.jpg.", "a.jpeg", "b.png",
    "c.gif", "d.bmp", "e.tiff", "f.webp", "g.svg", "h.heic", "i.HEIC", "j.txt",
    "k.mp3", "sub/nested.jpg", "sub/.hidden_nested.png", "sub/.hid/deep.jpg",
    "sub/deep/deeper/way.heic",
]


def load_imagelib():
    sys.path.insert(0, str(BIN_DIR))
    imagelib = ModuleType("imagelib")
    imagelib.__file__ = str(BIN_DIR / "imagelib.py")
    sys.modules["imagelib"] = imagelib
    exec((BIN_DIR / "imagelib.py").read_text(), imagelib.__dict__)
    return imagelib


class Shim:
    """The pre-refactor per-script API, re-expressed on top of imagelib."""

    def __init__(self, name, lib, extensions):
        self.__name__ = name
        self._lib = lib
        self._extensions = extensions

    def find_image_files(self, directory):
        return self._lib.find_images(directory, self._extensions)

    def collect_input_files(self, inputs):
        return self._lib.collect_images(inputs, self._extensions)


def call(fn, *args):
    try:
        value = fn(*args)
    except SystemExit as exit_error:
        return f"EX:SystemExit({exit_error.code})"
    except BaseException as error:
        return f"EX:{type(error).__name__}"
    if isinstance(value, list):
        return repr([str(v) for v in value])
    return repr(value)


def build(root):
    tree = root / "tree"
    for name in NAMES:
        path = tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    empty = root / "empty"
    empty.mkdir()
    return tree, empty


def main():
    root = Path(sys.argv[1])
    tree, empty = build(root)
    imagelib = load_imagelib()
    rows = []

    for name in ("imgtox", "imgcompress"):
        module = Shim(name, imagelib, IMGTOX_EXTS if name == "imgtox" else IMGCOMPRESS_EXTS)
        cases = {
            "tree": tree,
            "sub": tree / "sub",
            "hidden_dir": tree / "sub" / ".hid",
            "empty": empty,
        }
        for slot, path in cases.items():
            rows.append(f"{name}\tfind_image_files\t{slot}\t"
                        f"{call(module.find_image_files, path).replace(str(root), '<R>')}")

        collect_cases = {
            "single_file": [tree / "plain.jpg"],
            "file_and_dir": [tree / "plain.jpg", tree / "sub"],
            "dir_twice": [tree / "sub", tree / "sub"],
            "dir_and_member": [tree, tree / "plain.jpg"],
            "unlisted_ext_file": [tree / "j.txt"],
            "empty_dir": [empty],
            "no_inputs": [],
            "missing": [root / "nope.jpg"],
            "file_then_missing": [tree / "plain.jpg", root / "nope.jpg"],
        }
        for slot, paths in collect_cases.items():
            rows.append(f"{name}\tcollect_input_files\t{slot}\t"
                        f"{call(module.collect_input_files, paths).replace(str(root), '<R>')}")

    Path(sys.argv[2]).write_text(f"# rows: {len(rows)}\n" + "\n".join(rows) + "\n")


main()
