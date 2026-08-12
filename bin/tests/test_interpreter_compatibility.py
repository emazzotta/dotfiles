"""Guards bin/ against syntax the oldest interpreter it can land on cannot run.

`#!/usr/bin/env python3` resolves to whatever python3 the *caller's* PATH finds,
which is not the interpreter running this suite. macOS ships 3.9 at
/usr/bin/python3, and the crontab PATH has no homebrew entry at all - so a
script that needs 3.10+ works interactively and dies under cron.

PEP 604 (`int | None`) is the trap: valid syntax everywhere, but evaluated at
runtime below 3.10 unless the file postpones annotations.
"""

import ast
from pathlib import Path

BIN_DIR = Path(__file__).parent.parent
OLDEST_SUPPORTED = (3, 9)


def _python_files():
    for path in sorted(BIN_DIR.rglob("*")):
        if not path.is_file() or path.parent.name == "tests":
            continue
        if path.suffix == ".py":
            yield path
            continue
        try:
            shebang = path.open("rb").readline(200)
        except OSError:
            continue
        if shebang.startswith(b"#!") and b"python" in shebang:
            yield path


def _postpones_annotations(tree):
    return any(
        isinstance(node, ast.ImportFrom) and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )


def _annotations_using_pep604(tree):
    found = []

    def scan(annotation):
        if annotation is None:
            return
        for node in ast.walk(annotation):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
                found.append(node.lineno)

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            scan(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                             arguments.vararg, arguments.kwarg]:
                if argument is not None:
                    scan(argument.annotation)
            scan(node.returns)
    return sorted(set(found))


def test_should_postpone_annotations_in_every_file_using_pep604():
    offenders = []
    for path in _python_files():
        tree = ast.parse(path.read_text(errors="replace"))
        lines = _annotations_using_pep604(tree)
        if lines and not _postpones_annotations(tree):
            offenders.append(f"{path.relative_to(BIN_DIR)}: lines {lines}")

    assert offenders == [], (
        "add `from __future__ import annotations` - `X | Y` annotations are "
        f"evaluated at runtime below Python {'.'.join(map(str, OLDEST_SUPPORTED))}:\n"
        + "\n".join(offenders)
    )


def test_should_only_use_syntax_the_oldest_interpreter_can_parse():
    offenders = []
    for path in _python_files():
        try:
            ast.parse(path.read_text(errors="replace"), feature_version=OLDEST_SUPPORTED)
        except SyntaxError as e:
            offenders.append(f"{path.relative_to(BIN_DIR)}:{e.lineno}: {e.msg}")

    assert offenders == [], (
        f"syntax newer than Python {'.'.join(map(str, OLDEST_SUPPORTED))}:\n" + "\n".join(offenders)
    )
