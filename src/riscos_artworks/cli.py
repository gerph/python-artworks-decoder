"""The ``riscos-artworks`` command line: ``audit`` and ``dump`` subcommands."""

from __future__ import annotations

import argparse
import dataclasses
from enum import IntEnum
import json
from pathlib import Path
import sys
from typing import Any, Sequence

from . import __version__, audit
from . import model as m

# Fields every Record carries; the text dump shows these on the record's
# own heading line rather than repeating them as named fields.
_COMMON_RECORD_FIELDS = frozenset(
    field.name for field in dataclasses.fields(m.Record))

# Above this many entries a tuple is written one item per line in the
# text dump, so that long paths and polylines stay readable. Tuples of
# structured items (path elements, points, palette entries) wrap sooner
# than tuples of plain numbers.
_INLINE_TUPLE_LIMIT = 8
_INLINE_STRUCTURED_LIMIT = 3


# ---------------------------------------------------------------------
# Generic value conversion
# ---------------------------------------------------------------------

def _to_json(value: Any) -> Any:
    """Convert decoded objects to JSON-compatible structures.

    Dataclasses become objects carrying their class name under ``"class"``
    so that record and path-element types survive the round trip; bytes
    become hex strings; enums become their integer values.
    """
    if isinstance(value, IntEnum):
        return int(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value).hex()
    if isinstance(value, m.Record):
        result: dict[str, Any] = {"class": type(value).__name__}
        record_type = value.record_type
        result["record_type"] = record_type.name if record_type else None
        for field in dataclasses.fields(value):
            result[field.name] = _to_json(getattr(value, field.name))
        return result
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        result = {"class": type(value).__name__}
        for field in dataclasses.fields(value):
            result[field.name] = _to_json(getattr(value, field.name))
        return result
    if isinstance(value, (tuple, list)):
        return [_to_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_json(item) for key, item in value.items()}
    return value


def _inline(value: Any) -> str:
    """Render a value on a single line for the text dump."""
    if isinstance(value, IntEnum):
        return f"{value.name} ({int(value)})"
    if isinstance(value, bool) or value is None:
        return str(value)
    if isinstance(value, int):
        return str(value) if -256 < value < 256 else f"{value} (0x{value & 0xFFFFFFFF:X})"
    if isinstance(value, str):
        return repr(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        preview = data[:16].hex(" ")
        suffix = " ..." if len(data) > 16 else ""
        return f"<{len(data)} bytes{': ' + preview if data else ''}{suffix}>"
    if isinstance(value, m.Point):
        return f"({value.x}, {value.y})"
    if isinstance(value, m.BoundingBox):
        return f"({value.min_x}, {value.min_y})-({value.max_x}, {value.max_y})"
    if isinstance(value, m.DecodedString):
        return repr(value.text)
    if isinstance(value, m.SourceSpan):
        length = "?" if value.length is None else str(value.length)
        return f"@0x{value.offset:X}+{length}"
    if isinstance(value, m.RelativePointer):
        return f"@0x{value.offset:X} prev={value.previous:+d} next={value.next:+d}"
    if isinstance(value, m.ColourIndex):
        return f"ColourIndex(0x{value.value:08X})"
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        fields = ", ".join(
            f"{field.name}={_inline(getattr(value, field.name))}"
            for field in dataclasses.fields(value))
        return f"{type(value).__name__}({fields})"
    if isinstance(value, (tuple, list)):
        return "[" + ", ".join(_inline(item) for item in value) + "]"
    return repr(value)


def _multiline(value: Any) -> bool:
    """Decide whether a value deserves one line per item in the text dump."""
    if isinstance(value, (tuple, list)):
        structured = any(dataclasses.is_dataclass(item) for item in value)
        limit = _INLINE_STRUCTURED_LIMIT if structured else _INLINE_TUPLE_LIMIT
        return len(value) > limit or any(_multiline(item) for item in value)
    if isinstance(value, m.RecordList):
        return True
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return any(_multiline(getattr(value, field.name))
                   for field in dataclasses.fields(value))
    return False


# ---------------------------------------------------------------------
# Text dump
# ---------------------------------------------------------------------

def _write_value(out: list[str], indent: str, name: str, value: Any) -> None:
    if not _multiline(value):
        out.append(f"{indent}{name}: {_inline(value)}")
        return
    if isinstance(value, (tuple, list)):
        out.append(f"{indent}{name}: [{len(value)} items]")
        for index, item in enumerate(value):
            _write_value(out, indent + "  ", f"[{index}]", item)
        return
    if isinstance(value, m.RecordList):
        _write_list(out, indent, name, value)
        return
    out.append(f"{indent}{name}: {type(value).__name__}")
    for field in dataclasses.fields(value):
        _write_value(out, indent + "  ", field.name, getattr(value, field.name))


def _write_record(out: list[str], indent: str, index: int, record: m.Record) -> None:
    record_type = record.record_type
    type_name = record_type.name if record_type else "unknown"
    visible = "visible" if record.control_word & 2 else "hidden"
    out.append(f"{indent}[{index}] {type(record).__name__} "
               f"type=0x{record.type_code:02X} ({type_name}) "
               f"{_inline(record.span)} "
               f"control=0x{record.control_word:08X} ({visible}) "
               f"bbox={_inline(record.bounding_box)}")
    inner = indent + "    "
    if record.type_word != record.type_code:
        out.append(f"{inner}type_word: 0x{record.type_word:08X}")
    for field in dataclasses.fields(record):
        if field.name in _COMMON_RECORD_FIELDS:
            continue
        _write_value(out, inner, field.name, getattr(record, field.name))
    if record.extra_bytes:
        _write_value(out, inner, "extra_bytes", record.extra_bytes)
    if record.raw_body is not None and isinstance(record, m.UnknownRecord):
        _write_value(out, inner, "raw_body", record.raw_body)
    for list_index, child in enumerate(record.child_lists):
        _write_list(out, inner, f"child_list[{list_index}]", child)


def _write_list(out: list[str], indent: str, name: str, record_list: m.RecordList) -> None:
    count = len(record_list.records)
    plural = "" if count == 1 else "s"
    out.append(f"{indent}{name}: {_inline(record_list.pointer)} "
               f"({count} record{plural})")
    for index, record in enumerate(record_list.records):
        _write_record(out, indent + "  ", index, record)


def format_text(artwork: m.ArtWorks, *, header: bool = True) -> str:
    """Render a decoded document as an indented text tree."""
    out: list[str] = []
    head = artwork.header
    out.append(f"ArtWorks version {head.version}, program {head.program.text!r}, "
               f"{artwork.source_length} bytes")
    if header:
        for field in dataclasses.fields(head):
            _write_value(out, "  ", field.name, getattr(head, field.name))
    if artwork.palette is None:
        out.append("Palette: none")
    else:
        out.append(f"Palette: {artwork.palette.count} entries "
                   f"{_inline(artwork.palette.span)}")
        for index, entry in enumerate(artwork.palette.entries):
            _write_value(out, "  ", f"[{index}]", entry)
    for area in artwork.work_areas:
        out.append(f"Work area {area.name!r}: {_inline(area.span)} "
                   f"{_inline(area.data)}")
    for index, record_list in enumerate(artwork.record_lists):
        _write_list(out, "", f"List {index}", record_list)
    return "\n".join(out) + "\n"


def format_json(artwork: m.ArtWorks, *, header: bool = True) -> str:
    """Render a decoded document as JSON."""
    document = {
        "version": artwork.header.version,
        "program": artwork.header.program.text,
        "source_length": artwork.source_length,
        "header": _to_json(artwork.header) if header else None,
        "palette": _to_json(artwork.palette),
        "work_areas": _to_json(artwork.work_areas),
        "record_lists": _to_json(artwork.record_lists),
    }
    return json.dumps(document, indent=2) + "\n"


# ---------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riscos-artworks",
        description="Inspect Computer Concepts ArtWorks files.")
    parser.add_argument("--version", action="version",
                        version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True,
                                       metavar="COMMAND")

    audit_parser = subparsers.add_parser(
        "audit", help="audit a tree of ArtWorks files into SQLite, CSV, and JSON",
        description=audit.DESCRIPTION)
    audit.add_arguments(audit_parser)

    dump_parser = subparsers.add_parser(
        "dump", help="display the record tree of an ArtWorks file",
        description="Decode one ArtWorks file and display its record tree.")
    dump_parser.add_argument("file", type=Path, help="ArtWorks file to decode")
    dump_parser.add_argument("--format", choices=("text", "json"), default="text",
                             help="output format (default: text)")
    dump_parser.add_argument("--no-header", dest="header", action="store_false",
                             help="omit the decoded file header fields")
    return parser


def run_dump(args: argparse.Namespace) -> str:
    with args.file.open("rb") as handle:
        artwork = m.ArtWorks.from_file(handle)
    if args.format == "json":
        return format_json(artwork, header=args.header)
    return format_text(artwork, header=args.header)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            audit.run(args)
        else:
            sys.stdout.write(run_dump(args))
    except (OSError, RuntimeError, ValueError) as error:
        parser.exit(2, f"error: {error}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
