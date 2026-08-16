"""Resumable feature audit for large collections of ArtWorks files."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
from time import monotonic
from typing import Sequence

from . import __version__
from .exceptions import ArtWorksDecodeError
from .model import ArtWorks, RecordType, UnknownRecord


SCHEMA_VERSION = "1"
DEFAULT_SOURCE = Path("/cd/ARTWORKS")
DEFAULT_OUTPUT = Path("reports/artworks-audit")

CSV_FIELDS = (
    "path", "size", "mtime_ns", "sha256", "status", "candidate",
    "version", "record_count", "top_level_lists", "max_depth",
    "palette_entries", "unsupported_records", "type_counts",
    "unknown_types", "features", "work_areas", "error_type",
    "error_offset", "error_message",
)

STYLE_TYPES = frozenset(range(0x24, 0x2C)) | {0x3E, 0x3F}
TEXT_TYPES = frozenset({0x01, 0x2D})
ADVANCED_TYPES = frozenset({0x37, 0x38, 0x3A, 0x3B, 0x3D, 0x42})
GEOMETRY_TYPES = frozenset({0x02, 0x2C, 0x34, 0x35})
FONT_TYPES = frozenset(range(0x2E, 0x34))
SPRITE_TYPES = frozenset({0x05})
GROUP_TYPES = frozenset({0x06, 0x0A})
METADATA_TYPES = frozenset({0x23, 0x39})
KNOWN_TYPES = frozenset(record_type.value for record_type in RecordType)


@dataclass(frozen=True, slots=True)
class AuditRow:
    """One stable report row, suitable for SQLite and CSV output."""

    path: str
    size: int
    mtime_ns: int
    sha256: str
    status: str
    candidate: int
    version: int | None
    record_count: int | None
    top_level_lists: int | None
    max_depth: int | None
    palette_entries: int | None
    unsupported_records: int | None
    type_counts: str
    unknown_types: str
    features: str
    work_areas: str
    decode_ms: float
    error_type: str
    error_offset: int | None
    error_message: str
    scanned_at: str


def _safe_text(value: object) -> str:
    """Return single-line text which can always be encoded as UTF-8."""
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def _relative_name(path: Path, source: Path) -> str:
    return _safe_text(path.relative_to(source).as_posix())


def _features(type_counts: Counter[int], unsupported: int) -> tuple[str, ...]:
    present = set(type_counts)
    features = []
    for name, codes in (
        ("geometry", GEOMETRY_TYPES),
        ("styling", STYLE_TYPES),
        ("text", TEXT_TYPES),
        ("fonts", FONT_TYPES),
        ("sprites", SPRITE_TYPES),
        ("groups", GROUP_TYPES),
        ("advanced", ADVANCED_TYPES),
        ("metadata", METADATA_TYPES),
    ):
        if present & codes:
            features.append(name)
    if unsupported:
        features.append("unknown_records")
    return tuple(features)


def _describe_artwork(artwork: ArtWorks) -> tuple[
        Counter[int], int, int, tuple[str, ...]]:
    counts: Counter[int] = Counter()
    unsupported = 0
    maximum_depth = 0
    stack = [(record, 1) for record_list in reversed(artwork.record_lists)
             for record in reversed(record_list.records)]
    while stack:
        record, depth = stack.pop()
        counts[record.type_code] += 1
        unsupported += isinstance(record, UnknownRecord)
        maximum_depth = max(maximum_depth, depth)
        for child_list in reversed(record.child_lists):
            stack.extend((child, depth + 1)
                         for child in reversed(child_list.records))
    return counts, unsupported, maximum_depth, _features(counts, unsupported)


def audit_file(path: Path, source: Path) -> AuditRow:
    """Inspect and, when applicable, decode one filesystem object."""
    started = monotonic()
    scanned_at = datetime.now(timezone.utc).isoformat()
    relative = _relative_name(path, source)
    size = -1
    mtime_ns = -1
    candidate = 0
    digest = ""
    try:
        stat = path.stat()
        size, mtime_ns = stat.st_size, stat.st_mtime_ns
        with path.open("rb") as handle:
            signature = handle.read(16)
        candidate = int(signature[:4] == b"Top!")
        if not candidate:
            return AuditRow(
                relative, size, mtime_ns, "", "not_artworks", 0, None,
                None, None, None, None, None, "{}", "[]", "[]", "[]",
                (monotonic() - started) * 1000, "", None, "", scanned_at)

        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        artwork = ArtWorks.from_buffer(data)
        counts, unsupported, depth, features = _describe_artwork(artwork)
        unknown = sorted(code for code in counts if code not in KNOWN_TYPES)
        type_counts = {f"{code:02X}": count
                       for code, count in sorted(counts.items())}
        return AuditRow(
            relative, size, mtime_ns, digest, "decoded", 1,
            artwork.header.version, sum(counts.values()),
            len(artwork.record_lists), depth,
            0 if artwork.palette is None else len(artwork.palette.entries),
            unsupported, json.dumps(type_counts, separators=(",", ":")),
            json.dumps([f"{code:02X}" for code in unknown]),
            json.dumps(features),
            json.dumps([section.name for section in artwork.work_areas]),
            (monotonic() - started) * 1000, "", None, "", scanned_at)
    except Exception as error:
        # A report must retain unexpected I/O failures too.
        offset = error.offset if isinstance(error, ArtWorksDecodeError) else None
        return AuditRow(
            relative, size, mtime_ns, digest,
            "decode_error" if candidate else "io_error", candidate, None,
            None, None, None, None, None, "{}", "[]", "[]", "[]",
            (monotonic() - started) * 1000, type(error).__name__,
            offset, _safe_text(error), scanned_at)


def _connect(database: Path, restart: bool, source: Path) -> sqlite3.Connection:
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    if restart:
        connection.executescript(
            "DROP TABLE IF EXISTS files; DROP TABLE IF EXISTS metadata;")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            size INTEGER NOT NULL,
            mtime_ns INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            status TEXT NOT NULL,
            candidate INTEGER NOT NULL,
            version INTEGER,
            record_count INTEGER,
            top_level_lists INTEGER,
            max_depth INTEGER,
            palette_entries INTEGER,
            unsupported_records INTEGER,
            type_counts TEXT NOT NULL,
            unknown_types TEXT NOT NULL,
            features TEXT NOT NULL,
            work_areas TEXT NOT NULL,
            decode_ms REAL NOT NULL,
            error_type TEXT NOT NULL,
            error_offset INTEGER,
            error_message TEXT NOT NULL,
            scanned_at TEXT NOT NULL
        );
    """)
    metadata = dict(connection.execute("SELECT key, value FROM metadata"))
    old_schema = metadata.get("schema_version")
    if old_schema is not None and old_schema != SCHEMA_VERSION:
        connection.close()
        raise RuntimeError(
            f"audit database schema {old_schema} is not supported; use --restart")
    old_source = metadata.get("source")
    if old_source is not None and old_source != str(source):
        connection.close()
        raise RuntimeError(
            f"audit database belongs to {old_source}; use --restart for {source}")
    connection.executemany(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES (?, ?)",
        (("schema_version", SCHEMA_VERSION), ("decoder_version", __version__),
         ("source", str(source))),
    )
    connection.commit()
    return connection


def _store(connection: sqlite3.Connection, row: AuditRow) -> None:
    values = asdict(row)
    columns = tuple(values)
    assignments = ", ".join(f"{column}=excluded.{column}" for column in columns[1:])
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"INSERT INTO files ({', '.join(columns)}) VALUES ({placeholders}) "
        f"ON CONFLICT(path) DO UPDATE SET {assignments}",
        tuple(values[column] for column in columns),
    )


def _unchanged(connection: sqlite3.Connection, relative: str,
               stat: os.stat_result) -> bool:
    row = connection.execute(
        "SELECT size, mtime_ns FROM files WHERE path = ?", (relative,)).fetchone()
    return row == (stat.st_size, stat.st_mtime_ns)


def _files(source: Path, excluded: frozenset[Path]) -> list[Path]:
    return sorted((path for path in source.rglob("*")
                   if path.is_file() and path not in excluded),
                  key=lambda path: _relative_name(path, source))


def export_csv(connection: sqlite3.Connection, destination: Path) -> None:
    """Atomically export database rows as a spreadsheet-friendly CSV."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_FIELDS)
        for row in connection.execute(
                f"SELECT {', '.join(CSV_FIELDS)} FROM files ORDER BY path"):
            values = list(row)
            counts = json.loads(values[CSV_FIELDS.index("type_counts")])
            values[CSV_FIELDS.index("type_counts")] = " ".join(
                f"{code}:{count}" for code, count in counts.items())
            for field in ("unknown_types", "features", "work_areas"):
                index = CSV_FIELDS.index(field)
                values[index] = ";".join(json.loads(values[index]))
            writer.writerow(values)
    os.replace(temporary, destination)


def _counter_dict(counter: Counter[object]) -> dict[str, int]:
    return {str(key): counter[key] for key in sorted(counter, key=str)}


def export_summary(connection: sqlite3.Connection, destination: Path,
                   source: Path) -> dict[str, object]:
    """Atomically export aggregate coverage and failure information as JSON."""
    statuses: Counter[str] = Counter()
    versions: Counter[int] = Counter()
    types: Counter[str] = Counter()
    unknown_types: Counter[str] = Counter()
    feature_files: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    top_levels: Counter[str] = Counter()
    top_level_statuses: dict[str, Counter[str]] = {}
    total_bytes = 0
    total_records = 0
    for row in connection.execute(
            "SELECT path, size, status, version, record_count, type_counts, "
            "unknown_types, features, error_type FROM files"):
        (path, size, status, version, records, encoded_types,
         encoded_unknown, encoded_features, error) = row
        top_level = path.split("/", 1)[0]
        total_bytes += max(size, 0)
        statuses[status] += 1
        top_levels[top_level] += 1
        top_level_statuses.setdefault(top_level, Counter())[status] += 1
        if version is not None:
            versions[version] += 1
        total_records += records or 0
        types.update(json.loads(encoded_types))
        unknown_types.update(json.loads(encoded_unknown))
        feature_files.update(json.loads(encoded_features))
        if error:
            errors[error] += 1
    duplicates = connection.execute(
        "SELECT COUNT(*) FROM (SELECT sha256 FROM files WHERE sha256 != '' "
        "GROUP BY sha256 HAVING COUNT(*) > 1)").fetchone()[0]
    summary: dict[str, object] = {
        "source": str(source),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decoder_version": __version__,
        "files": sum(statuses.values()),
        "bytes": total_bytes,
        "statuses": _counter_dict(statuses),
        "files_by_top_level": _counter_dict(top_levels),
        "statuses_by_top_level": {
            name: _counter_dict(top_level_statuses[name])
            for name in sorted(top_level_statuses)
        },
        "versions": _counter_dict(versions),
        "records": total_records,
        "record_types": _counter_dict(types),
        "unknown_record_types": _counter_dict(unknown_types),
        "files_by_feature": _counter_dict(feature_files),
        "errors": _counter_dict(errors),
        "duplicate_content_groups": duplicates,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    os.replace(temporary, destination)
    return summary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Audit a tree of possible ArtWorks files into SQLite, CSV, and JSON."))
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE,
                        help="tree to scan (default: /cd/ARTWORKS)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="output filename prefix (default: reports/artworks-audit)")
    parser.add_argument("--refresh", action="store_true",
                        help="decode files again even when size and timestamp match")
    parser.add_argument("--restart", action="store_true",
                        help=(
                            "discard rows in the existing audit database before scanning"))
    parser.add_argument("--export-only", action="store_true",
                        help="regenerate CSV and summary from the existing database")
    parser.add_argument("--limit", type=int,
                        help="process at most this many discovered files")
    parser.add_argument("--checkpoint", type=int, default=50,
                        help="commit and export after this many new rows (default: 50)")
    parser.add_argument("--quiet", action="store_true",
                        help="suppress progress messages")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    source = args.source.resolve()
    prefix = args.output.resolve()
    database = prefix.with_suffix(".sqlite3")
    csv_path = prefix.with_suffix(".csv")
    summary_path = prefix.with_suffix(".summary.json")
    if not source.is_dir() and not args.export_only:
        raise FileNotFoundError(f"source directory does not exist: {source}")
    if args.checkpoint < 1:
        raise ValueError("--checkpoint must be at least 1")
    connection = _connect(database, args.restart, source)
    try:
        if not args.export_only:
            excluded = frozenset({database, csv_path, summary_path})
            paths = _files(source, excluded)
            if args.limit is not None:
                paths = paths[:max(args.limit, 0)]
            changed = 0
            skipped = 0
            started = monotonic()
            for index, path in enumerate(paths, 1):
                relative = _relative_name(path, source)
                try:
                    unchanged = _unchanged(connection, relative, path.stat())
                except OSError:
                    unchanged = False
                if unchanged and not args.refresh:
                    skipped += 1
                    continue
                row = audit_file(path, source)
                _store(connection, row)
                changed += 1
                if changed % args.checkpoint == 0:
                    connection.commit()
                    export_csv(connection, csv_path)
                    export_summary(connection, summary_path, source)
                    if not args.quiet:
                        elapsed = monotonic() - started
                        print(f"[{index}/{len(paths)}] audited {changed}, skipped {skipped} "
                              f"({elapsed:.1f}s)", file=sys.stderr, flush=True)
            if args.limit is None:
                present = {_relative_name(path, source) for path in paths}
                recorded = {
                    row[0] for row in connection.execute("SELECT path FROM files")
                }
                connection.executemany("DELETE FROM files WHERE path = ?",
                                       ((path,) for path in recorded - present))
            connection.commit()
        export_csv(connection, csv_path)
        summary = export_summary(connection, summary_path, source)
    finally:
        connection.close()
    if not args.quiet:
        print(f"Database: {database}", file=sys.stderr)
        print(f"CSV:      {csv_path}", file=sys.stderr)
        print(f"Summary:  {summary_path}", file=sys.stderr)
        print(f"Statuses: {summary['statuses']}", file=sys.stderr)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        run(args)
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
