# Parity harnesses

`./check` replays a frozen pre-refactor contract against the module that replaced
it. Green means the shared module still behaves the way the scripts it was
extracted from used to. Run it after touching `medialib.py` or `imagelib.py`.

Not part of `pytest bin/tests` - these are slower, filesystem-heavy, and answer a
different question than the unit tests do. `test_medialib.py` and
`test_imagelib.py` pin the behaviour going forward; these pin it against history.

| Harness | Oracle | Frozen rows |
|---|---|---|
| `medialib_parity.py` | `audiotox`, `videotox`, `audioboost` before `medialib.py` existed | 693 |
| `imagelib_parity.py` | `imgtox`, `imgcompress` before `imagelib.py` existed | 26 |

Each emits one row per input slot, always - never data-dependent - with
exceptions captured as `EX:<Type>` values so a crash that turns into a wrong
answer shows up as a diff rather than an error.

## Covered

- **medialib**: duration boundaries either side of a minute and negatives; files,
  directories, nested directories, empty directories and missing paths; dedupe
  across overlapping inputs; both output naming schemes; every answer to the
  overwrite prompt, including the abort exit; the full conflict-counter
  escalation; and the prompt text itself.
- **imagelib**: dotted files and dotted directories, uppercase extensions,
  recursion, spaces and non-ASCII in names, files whose extension is not in the
  list, dedupe, input order, and the missing-input exit.

Not reached by either: case-insensitive filesystems, symlink loops,
permission-denied directories, and the ffmpeg/magick calls themselves.

## Accepted divergence

One row family differs on purpose, and `check` filters it: `audioboost`'s
conflict prompt used to hardcode `N=add _boosted` while honouring whatever
`--suffix` asked for, so `-s _x` wrote `song_x.wav` and announced `_boosted`.
The prompt now names the real suffix.

## Regenerating

Don't, unless you mean to move the contract. The golden files are the record of
what the original scripts did; regenerating them from current code makes every
future diff self-approving. If a change is meant to alter behaviour, update the
golden file in the same commit that changes the code, and say why in the message.
