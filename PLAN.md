# Python ArtWorks Structural Decoder

Create an MIT-licensed Python 3.11+ distribution named `riscos-artworks`,
imported as `riscos_artworks`. It will structurally decode Computer Concepts
ArtWorks files into immutable, slotted dataclasses without rendering,
normalisation, or writing support.

The uncommitted `examples/` corpus and `riscos-artworks-js/` reference checkout
are compatibility inputs only and must never be committed.

## Implementation checklist

- [x] Inspect repository guidance and confirm the JavaScript reference revision.
- [x] Create the `feature/python-artworks-decoder` branch.
- [x] Add packaging, licence, README, source layout, tests, and targeted ignores.
- [x] Implement buffer/file adapters, primitive reads, source spans, exceptions,
      and header validation.
- [x] Test buffer/file equivalence, non-zero file origins, position restoration,
      headers, and failures; then commit the foundation.
- [x] Decode linked lists, record headers, relative pointers, sublists, cycles,
      bad signs, misalignment, truncation, and out-of-range targets.
- [x] Preserve unknown records and test synthetic nested/corrupt structures;
      then commit the structural graph decoder.
- [x] Decode points, bounding boxes, paths, palette data, colour indices, work
      areas, sprites, groups, layers, rectangles, ellipses, and rounded
      rectangles; then commit core graphical records.
- [x] Decode stroke, fill, joins, caps, winding, dash, and marker records with
      raw enum preservation and convenience properties; then commit styling.
- [x] Decode text and metadata records `0x00`, `0x01`, `0x22`, `0x23`,
      `0x2D`-`0x33`, and `0x39`; then commit text and metadata support.
- [x] Decode distortion, perspective, subgroup, blend group, blend options,
      and blend path records; then commit advanced structures.
- [x] Finalise traversal/filtering, summaries, palette resolution, exports,
      type annotations, docstrings, README examples, and optional corpus tests.
- [x] Decode and compare all 55 corpus files with the JavaScript implementation,
      including record counts/types and selected values.
- [x] Run `python3 -m unittest discover -s tests` and
      `python3 -m compileall -q src tests`.
- [x] Build and inspect wheel/sdist, confirming reference data, examples,
      caches, and generated reports are absent.
- [x] Complete the documented v0.1.0 package and final commit.

## Acceptance constraints

- Input is a contiguous buffer or a seekable binary handle at its current
  position; supplied handles remain open and are restored after success or
  failure.
- File offsets are relative to the start of the supplied ArtWorks stream.
- Decoded objects are immutable, slotted, eager, and remain usable after an
  input handle closes.
- Unexpected record types and enum values remain inspectable whenever their
  size can be derived safely.
- Strings use a one-to-one Latin-1 mapping and retain raw bytes/padding.
- Undo and sprite work areas remain opaque; the palette is interpreted.
- Versions beyond documented 9 and 10 are accepted when signatures and
  structure are valid.

## Collection audit utility

- [x] Add a resumable SQLite auditor for large trees of possible ArtWorks files.
- [x] Export deterministic per-file CSV coverage and an aggregate JSON summary.
- [x] Report versions, record types, nesting, features, work areas, unknown
      records, hashes, and detailed decode failures.
- [x] Test successful, non-ArtWorks, failed, resumed, and export-only scans.
- [x] Audit all 1,414 files under `/cd/ARTWORKS` and verify generated reports.
