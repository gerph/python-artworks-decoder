# riscos-artworks

`riscos-artworks` is a read-only Python decoder for Computer Concepts ArtWorks
files. It exposes the file's linked structure as immutable, slotted dataclasses
without rendering, rewriting, normalising, or applying inherited styles.

The package requires Python 3.11 or later and has no runtime dependencies.

## Installation

Install the published package with `pip`:

```console
python3 -m pip install riscos-artworks
```

Confirm that it is available:

```console
python3 -c 'import riscos_artworks; print(riscos_artworks.__version__)'
```

## Usage

```python
from riscos_artworks import ArtWorks, PathRecord

artwork = ArtWorks.from_buffer(memoryview(data))

for path_record in artwork.walk(PathRecord):
    print(path_record.bounding_box, path_record.path)

with open("drawing,aff", "rb") as handle:
    artwork = ArtWorks.from_file(handle)
```

`from_file()` treats the handle's current position as offset zero for the
ArtWorks stream. It restores that position after success or failure and never
closes the handle. All source data needed by decoded objects is copied eagerly,
so the objects remain usable after a source handle closes or a mutable source
buffer changes.

## Structural model

`ArtWorks.record_lists` retains the file's list-of-lists structure. Every
record includes its complete type word, masked type code, control word,
bounding box, relative pointer, source spans, child lists, and any safely
bounded trailing bytes. `walk()` traverses records depth first in file order
and optionally filters by record class.

`structural_summary()` provides deterministic totals and a per-type histogram
for indexing or decoder comparisons without flattening the stored graph.

Known record bodies have dedicated classes. Unknown record types become
`UnknownRecord` instances rather than aborting the decode. Their raw body is
available when a following record provides a safe boundary; for a final record
the raw body and body length are `None` because no boundary can be inferred.

Path tags retain their complete words and flags. Move, line, Bezier, close,
end, and ArtWorks' known unknown tag are represented by separate element
classes. Strings use a one-to-one Latin-1 mapping and retain their raw bytes
and fixed-field padding.

The indexed palette is decoded into `PaletteEntry` objects. `ColourIndex`
classifies indexed, direct, and transparent values, while
`ArtWorks.resolve_colour()` resolves palette references without applying any
rendering semantics. Undo-buffer and sprite-area sections are retained as
opaque byte strings.

## Errors and limits

Malformed files raise an `ArtWorksDecodeError` subclass with the failing
stream-relative offset where available. The decoder rejects truncation,
misalignment, invalid pointer signs or targets, repeated/cyclic nodes, unsafe
collection sizes, invalid signatures, non-contiguous buffers, and non-seekable
or text file handles.

Header versions are exposed without restricting them to the historically
documented versions 9 and 10; known files also use versions 11 and 12.

## Development

Run the standard-library test suite with:

```console
python3 -m unittest discover -s tests
python3 -m compileall -q src tests
```

GitHub Actions tests the installed package on Python 3.11 through 3.14. Once
those tests pass, every workflow run builds and uploads a source distribution
and wheel as the `python-distributions` workflow artifact.

Pushing a tag matching `v*` also creates a GitHub release containing those same
tested distributions. The tag must be `v` followed by the exact version in
`pyproject.toml`; for example, package version `0.2.0` must be tagged `v0.2.0`.
Rerunning a tag workflow replaces the release assets without creating a second
release.

An optional private-corpus test is enabled by pointing `ARTWORKS_EXAMPLES` at a
directory of ArtWorks files. No sample documents or JavaScript reference files
are included in the distribution.

## Auditing a collection

The collection auditor recursively scans `/cd/ARTWORKS` by default. It writes a
SQLite database as it runs, checkpointing regularly, and exports deterministic
CSV coverage data plus an aggregate JSON summary:

```console
python3 scripts/audit_artworks.py
```

The default outputs are `reports/artworks-audit.sqlite3`,
`reports/artworks-audit.csv`, and `reports/artworks-audit.summary.json`.
Generated reports are ignored by Git. Each file records whether it is an
ArtWorks candidate, whether it decoded, the candidate's content hash, version,
record and palette totals, nesting depth, complete per-type counts, unsupported
types, feature families, work areas, and any decode error and source offset.

Rerunning the command skips files whose size and modification time have not
changed. Use `--refresh` to decode everything again with the current decoder,
`--restart` to replace existing audit state, or `--export-only` to recreate the
CSV and JSON from a partially or fully completed database. `--output PREFIX`
selects a different destination.

After interruption, simply run the same command again. Up to the current
checkpoint is retained in SQLite and scanning resumes without duplicate rows.

The format coverage follows `riscos-artworks-js` commit
`fb8525eedb663af882fb26f87d199ca4ed60d52b`. ArtWorks is a trademark of its
respective owner. This independent decoder is distributed under the MIT
licence.
