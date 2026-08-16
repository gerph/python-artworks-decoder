"""Binary decoder for Computer Concepts ArtWorks files."""

from __future__ import annotations

from dataclasses import dataclass, field
from io import SEEK_END, SEEK_SET
import struct
from .exceptions import (
    ArtWorksDecodeError,
    InvalidHeaderError,
    InvalidPointerError,
    TruncatedDataError,
    UnsupportedValueError,
)
from . import model as m


HEADER_SIZE = 0x80
MAX_STRING_SIZE = 2048
MAX_COLLECTION_SIZE = 0xFFFFFF


class _Reader:
    def __init__(self, data: bytes, position: int = 0, limit: int | None = None) -> None:
        self.data = data
        self.position = position
        self.limit = len(data) if limit is None else limit

    def check(self, size: int, *, aligned: bool = False) -> None:
        if aligned and self.position & 3:
            raise ArtWorksDecodeError("misaligned value", self.position)
        if size < 0 or self.position < 0 or self.position + size > self.limit:
            raise TruncatedDataError("reading outside the available data", self.position)

    def bytes(self, size: int, *, aligned: bool = False) -> bytes:
        self.check(size, aligned=aligned)
        start = self.position
        self.position += size
        return self.data[start:self.position]

    def u32(self) -> int:
        self.check(4, aligned=True)
        value = struct.unpack_from("<I", self.data, self.position)[0]
        self.position += 4
        return value

    def i32(self) -> int:
        self.check(4, aligned=True)
        value = struct.unpack_from("<i", self.data, self.position)[0]
        self.position += 4
        return value

    def fixed_string(self, size: int) -> m.DecodedString:
        raw = self.bytes(size, aligned=True)
        nul = raw.find(b"\0")
        content = raw if nul < 0 else raw[:nul]
        padding = b"" if nul < 0 else raw[nul + 1:]
        return m.DecodedString(content.decode("latin-1"), raw, padding)

    def terminated_string(self) -> m.DecodedString:
        self.check(0, aligned=True)
        start = self.position
        maximum = min(self.limit, start + MAX_STRING_SIZE)
        nul = self.data.find(b"\0", start, maximum)
        if nul < 0:
            if maximum < self.limit:
                raise UnsupportedValueError("unterminated string exceeds safety limit", start)
            raise TruncatedDataError("unterminated string", start)
        self.position = nul + 1
        raw = self.data[start:self.position]
        return m.DecodedString(raw[:-1].decode("latin-1"), raw, b"")


@dataclass(slots=True)
class _ListDraft:
    pointer: m.RelativePointer
    records: list[_RecordDraft]
    span: m.SourceSpan


@dataclass(slots=True)
class _RecordDraft:
    record_class: type[m.Record]
    common: dict[str, object]
    body: dict[str, object]
    child_lists: list[_ListDraft] = field(default_factory=list)


def _point(reader: _Reader) -> m.Point:
    return m.Point(reader.i32(), reader.i32())


def _bounding_box(reader: _Reader) -> m.BoundingBox:
    return m.BoundingBox(reader.i32(), reader.i32(), reader.i32(), reader.i32())


def _polyline(reader: _Reader, count: int) -> tuple[m.Point, ...]:
    return tuple(_point(reader) for _ in range(count))


def _path(reader: _Reader) -> m.Path:
    result: list[m.PathElement] = []
    while True:
        tag = reader.u32()
        masked = tag & 0xFF
        if masked == 0:
            result.append(m.EndElement(tag))
            return tuple(result)
        if masked == 2:
            result.append(m.MoveElement(tag, _point(reader)))
        elif masked == 4:
            result.append(m.UnknownPathElement(tag))
        elif masked == 5:
            result.append(m.CloseElement(tag))
        elif masked == 6:
            result.append(m.BezierElement(tag, _point(reader), _point(reader),
                                          _point(reader)))
        elif masked == 8:
            result.append(m.LineElement(tag, _point(reader)))
        else:
            raise UnsupportedValueError(f"unsupported path tag 0x{tag:08x}",
                                        reader.position - 4)


def _palette(data: bytes, offset: int) -> m.Palette:
    reader = _Reader(data, offset)
    count_word = reader.u32()
    control_word = reader.u32()
    count = count_word & 0xFFFFFF
    if count > MAX_COLLECTION_SIZE or count > (len(data) - reader.position) // 48:
        raise TruncatedDataError("palette entry count exceeds available data", offset)
    entries = []
    for _ in range(count):
        entries.append(m.PaletteEntry(
            reader.fixed_string(24), reader.u32(), reader.u32(), reader.u32(),
            reader.u32(), reader.u32(), reader.u32()))
    return m.Palette(count_word, control_word, tuple(entries),
                     m.SourceSpan(offset, reader.position - offset))


def _header(data: bytes) -> m.ArtWorksHeader:
    if len(data) < HEADER_SIZE:
        raise TruncatedDataError("ArtWorks header is incomplete", 0)
    reader = _Reader(data, limit=HEADER_SIZE)
    identifier = reader.fixed_string(4)
    version = reader.u32()
    program = reader.fixed_string(8)
    values = [reader.u32() for _ in range(6)]
    undo = reader.i32()
    sprite = reader.i32()
    unknown_48 = reader.u32()
    american_width = reader.u32()
    american_height = reader.u32()
    palette = reader.i32()
    unknowns = [reader.u32() for _ in range(7)]
    reserved = reader.bytes(HEADER_SIZE - reader.position)
    if identifier.text != "Top!":
        raise InvalidHeaderError("expected the 'Top!' identifier", 0)
    if program.text != "TopDraw":
        raise InvalidHeaderError("expected the 'TopDraw' program signature", 8)
    body = values[1]
    if body < HEADER_SIZE or body >= len(data) or body & 3:
        raise InvalidHeaderError("invalid body offset", 20)
    for name, offset in (("undo buffer", undo), ("sprite area", sprite),
                         ("palette", palette)):
        if offset != -1 and (offset < HEADER_SIZE or offset >= len(data) or offset & 3):
            raise InvalidHeaderError(f"invalid {name} offset")
    return m.ArtWorksHeader(
        identifier, version, program, values[0], body, values[2], values[3],
        values[4], values[5], undo, sprite, unknown_48, american_width,
        american_height, palette, *unknowns, reserved)


class _Decoder:
    def __init__(self, data: bytes, header: m.ArtWorksHeader,
                 palette: m.Palette | None) -> None:
        self.data = data
        self.header = header
        self.palette = palette
        self.list_offsets: set[int] = set()
        self.record_offsets: set[int] = set()
        self.sublist_offsets: set[int] = set()

    def pointer(self, offset: int, *, record: bool = False) -> m.RelativePointer:
        reader = _Reader(self.data, offset)
        if record:
            next_value, previous = reader.i32(), reader.i32()
        else:
            previous, next_value = reader.i32(), reader.i32()
        pointer = m.RelativePointer(offset, previous, next_value)
        if previous > 0:
            raise InvalidPointerError("positive previous pointer", offset)
        if next_value < 0:
            raise InvalidPointerError("negative next pointer", offset)
        for value, label in ((previous, "previous"), (next_value, "next")):
            if value:
                target = offset + value
                if target < 0 or target + 8 > len(self.data):
                    raise InvalidPointerError(f"{label} pointer is out of range", offset)
                if target & 3:
                    raise InvalidPointerError(f"{label} pointer is misaligned", offset)
        return pointer

    def decode(self) -> tuple[m.RecordList, ...]:
        roots: list[_ListDraft] = []
        tasks: list[tuple[int, list[_ListDraft]]] = [(self.header.body_offset, roots)]
        while tasks:
            start, destination = tasks.pop()
            drafts, children = self._scan_lists(start)
            destination.extend(drafts)
            tasks.extend(children)
        return self._freeze(roots)

    def _scan_lists(self, start: int) -> tuple[list[_ListDraft], list[tuple[int, list[_ListDraft]]]]:
        drafts: list[_ListDraft] = []
        child_tasks: list[tuple[int, list[_ListDraft]]] = []
        offset = start
        while True:
            if offset in self.list_offsets:
                raise InvalidPointerError("cycle or reused list pointer", offset)
            self.list_offsets.add(offset)
            pointer = self.pointer(offset)
            records, end, children = self._scan_records(offset + 8)
            drafts.append(_ListDraft(pointer, records, m.SourceSpan(offset, end - offset)))
            child_tasks.extend(children)
            if pointer.next == 0:
                return drafts, child_tasks
            offset += pointer.next

    def _scan_records(self, start: int) -> tuple[list[_RecordDraft], int, list[tuple[int, list[_ListDraft]]]]:
        records: list[_RecordDraft] = []
        child_tasks: list[tuple[int, list[_ListDraft]]] = []
        offset = start
        while True:
            if offset in self.record_offsets:
                raise InvalidPointerError("cycle or reused record pointer", offset)
            self.record_offsets.add(offset)
            pointer = self.pointer(offset, record=True)
            bounded_end = offset + pointer.next - 8 if pointer.next else None
            if bounded_end is not None and bounded_end < offset + 32:
                raise InvalidPointerError("record is too short for its header", offset)
            reader = _Reader(self.data, offset + 8, bounded_end)
            type_word = reader.u32()
            control_word = reader.u32()
            box = _bounding_box(reader)
            body_start = reader.position
            record_class, body = self._body(reader, type_word & 0xFF,
                                            pointer.next == 0)
            body_end = reader.position
            if bounded_end is None:
                extra = None
                span_length = body_end - offset
            else:
                if body_end > bounded_end:
                    raise TruncatedDataError("record body overruns its boundary", body_end)
                extra = self.data[body_end:bounded_end]
                span_length = pointer.next
            raw = (self.data[body_start:bounded_end]
                   if record_class is m.UnknownRecord and bounded_end is not None else None)
            common: dict[str, object] = {
                "type_word": type_word,
                "type_code": type_word & 0xFF,
                "control_word": control_word,
                "bounding_box": box,
                "pointer": pointer,
                "span": m.SourceSpan(offset, span_length),
                "body_span": m.SourceSpan(body_start,
                                          None if bounded_end is None else bounded_end - body_start),
                "extra_bytes": extra,
                "raw_body": raw,
            }
            draft = _RecordDraft(record_class, common, body)
            records.append(draft)
            if pointer.next == 0:
                return records, body_end, child_tasks
            sub_offset = offset + pointer.next - 8
            if sub_offset in self.sublist_offsets:
                raise InvalidPointerError("cycle or reused sub-list pointer", sub_offset)
            self.sublist_offsets.add(sub_offset)
            sub_pointer = self.pointer(sub_offset)
            if sub_pointer.next:
                child_tasks.append((sub_offset + sub_pointer.next, draft.child_lists))
            offset += pointer.next

    def _require_last(self, last: bool, name: str, offset: int) -> None:
        if not last:
            raise InvalidPointerError(f"records follow {name} record", offset)

    def _body(self, r: _Reader, code: int, last: bool) -> tuple[type[m.Record], dict[str, object]]:
        if code == 0x00:
            return m.Record00Record, {}
        if code == 0x22:
            self._require_last(last, "record 22", r.position)
            return m.Record22Record, {}
        if code == 0x42:
            return m.DistortionSubgroupRecord, {}
        if code == 0x01:
            return m.TextRecord, {"unknown_values": tuple(r.u32() for _ in range(6)),
                                  "rectangle": _polyline(r, 4)}
        if code == 0x02:
            return m.PathRecord, {"path": _path(r)}
        if code == 0x05:
            self._require_last(last, "sprite", r.position)
            unknown_24 = r.u32()
            name = r.fixed_string(12)
            values = tuple([r.u32(), r.u32()] + [r.i32() for _ in range(6)] +
                           [r.u32() for _ in range(8)])
            count = r.u32()
            if count > MAX_COLLECTION_SIZE or count > (r.limit - r.position) // 4:
                raise TruncatedDataError("sprite palette count exceeds record", r.position - 4)
            return m.SpriteRecord, {"unknown_24": unknown_24, "name": name,
                                    "unknown_values": values,
                                    "palette": tuple(r.u32() for _ in range(count))}
        if code == 0x06:
            return m.GroupRecord, {"unknown_values": (r.u32(), r.u32(), r.u32())}
        if code == 0x0A:
            return m.LayerRecord, {"unknown_24": r.u32(), "name": r.fixed_string(32)}
        if code == 0x21:
            self._require_last(last, "work area", r.position)
            return m.WorkAreaRecord, {"palette": self.palette}
        if code == 0x23:
            self._require_last(last, "save location", r.position)
            return m.SaveLocationRecord, {"file_type": r.u32(),
                                          "file_path": r.terminated_string()}
        if code == 0x24:
            self._require_last(last, "stroke colour", r.position)
            return m.StrokeColourRecord, {"colour": m.ColourIndex(r.u32())}
        if code == 0x25:
            self._require_last(last, "stroke width", r.position)
            return m.StrokeWidthRecord, {"width": r.u32()}
        if code == 0x26:
            self._require_last(last, "fill colour", r.position)
            fill_type, unknown = r.u32(), r.u32()
            body: dict[str, object] = {"fill_type": fill_type, "unknown_28": unknown,
                                      "colour": None, "gradient_line": None,
                                      "start_colour": None, "end_colour": None}
            if fill_type == 0:
                body["colour"] = m.ColourIndex(r.u32())
            elif fill_type in (1, 2):
                body["gradient_line"] = _polyline(r, 2)
                body["start_colour"] = m.ColourIndex(r.u32())
                body["end_colour"] = m.ColourIndex(r.u32())
            return m.FillColourRecord, body
        if code == 0x27:
            self._require_last(last, "join style", r.position)
            return m.JoinStyleRecord, {"join_style": r.u32()}
        if code in (0x28, 0x29):
            self._require_last(last, "line cap", r.position)
            cls = m.EndCapRecord if code == 0x28 else m.StartCapRecord
            return cls, {"cap_style": r.u32(), "cap_triangle": r.u32()}
        if code == 0x2A:
            self._require_last(last, "winding rule", r.position)
            return m.WindingRuleRecord, {"winding_rule": r.u32()}
        if code == 0x2B:
            self._require_last(last, "dash pattern", r.position)
            pattern = r.i32()
            if pattern == 0:
                return m.DashPatternRecord, {"pattern": pattern, "offset": None,
                                             "elements": ()}
            dash_offset, count = r.u32(), r.u32()
            if count > MAX_COLLECTION_SIZE or count > (r.limit - r.position) // 4:
                raise TruncatedDataError("dash count exceeds record", r.position - 4)
            return m.DashPatternRecord, {"pattern": pattern, "offset": dash_offset,
                                         "elements": tuple(r.u32() for _ in range(count))}
        if code == 0x2C:
            return m.RectangleRecord, {"unknown_24": r.u32(), "path": _path(r)}
        if code == 0x2D:
            return m.CharacterRecord, {"character_code": r.u32(),
                                       "unknown_values": tuple(r.u32() for _ in range(4))}
        if code == 0x2E:
            self._require_last(last, "record 2e", r.position)
            return m.Unknown2ERecord, {"unknown_24": r.u32(),
                                      "unknown_28": r.fixed_string(8),
                                      "unknown_36": r.fixed_string(24),
                                      "unknown_60": r.i32(), "unknown_64": r.i32()}
        if code == 0x2F:
            self._require_last(last, "font name", r.position)
            return m.FontNameRecord, {"font_name": r.terminated_string()}
        if code == 0x30:
            self._require_last(last, "font size", r.position)
            return m.FontSizeRecord, {"x_size": r.u32(), "y_size": r.u32()}
        if code == 0x31:
            return m.Record31Record, {"values": tuple(r.u32() for _ in range(4))}
        if code == 0x32:
            self._require_last(last, "record 32", r.position)
            return m.Record32Record, {"values": (r.u32(),)}
        if code == 0x33:
            return m.Record33Record, {"values": tuple(r.i32() for _ in range(6))}
        if code == 0x34:
            return m.EllipseRecord, {"triangle": _polyline(r, 3), "path": _path(r)}
        if code == 0x35:
            return m.RoundedRectangleRecord, {"corner_radius": r.u32(),
                                              "triangle": _polyline(r, 3),
                                              "path": _path(r)}
        if code in (0x37, 0x38):
            cls = m.DistortionGroupRecord if code == 0x37 else m.PerspectiveGroupRecord
            if last:
                return cls, {"envelope": None, "unknown_values": (),
                             "original_objects_bounding_box": None}
            envelope = _path(r)
            count = 9 if code == 0x37 else 13
            return cls, {"envelope": envelope,
                         "unknown_values": tuple(r.u32() for _ in range(count)),
                         "original_objects_bounding_box": _bounding_box(r)}
        if code == 0x39:
            self._require_last(last, "file info", r.position)
            return m.FileInfoRecord, {"file_info": r.terminated_string()}
        if code == 0x3A:
            return m.BlendGroupRecord, {"values": tuple(r.i32() for _ in range(11))}
        if code == 0x3B:
            self._require_last(last, "blend options", r.position)
            first, steps = r.i32(), r.i32()
            return m.BlendOptionsRecord, {"unknown_24": first, "blend_steps": steps,
                                          "values": tuple(r.i32() for _ in range(8))}
        if code == 0x3D:
            self._require_last(last, "blend path", r.position)
            return m.BlendPathRecord, {"path": _path(r)}
        if code in (0x3E, 0x3F):
            self._require_last(last, "marker", r.position)
            cls = m.StartMarkerRecord if code == 0x3E else m.EndMarkerRecord
            return cls, {"marker_style": r.i32(), "marker_width": r.u32(),
                         "marker_height": r.u32()}
        # Unknown final records have no safe end and therefore no raw body.
        return m.UnknownRecord, {}

    def _freeze(self, roots: list[_ListDraft]) -> tuple[m.RecordList, ...]:
        completed_lists: dict[int, m.RecordList] = {}
        completed_records: dict[int, m.Record] = {}
        stack: list[tuple[object, bool]] = [(item, False) for item in reversed(roots)]
        while stack:
            node, expanded = stack.pop()
            if isinstance(node, _ListDraft):
                if expanded:
                    records = tuple(completed_records[id(record)] for record in node.records)
                    completed_lists[id(node)] = m.RecordList(node.pointer, records, node.span)
                else:
                    stack.append((node, True))
                    stack.extend((record, False) for record in reversed(node.records))
            else:
                record = node
                assert isinstance(record, _RecordDraft)
                if expanded:
                    common = dict(record.common)
                    common["child_lists"] = tuple(completed_lists[id(item)]
                                                  for item in record.child_lists)
                    completed_records[id(record)] = record.record_class(**common, **record.body)
                else:
                    stack.append((record, True))
                    stack.extend((item, False) for item in reversed(record.child_lists))
        return tuple(completed_lists[id(item)] for item in roots)


def _work_areas(data: bytes, header: m.ArtWorksHeader) -> tuple[m.WorkAreaSection, ...]:
    positions = [("undo_buffer", header.undo_buffer_offset),
                 ("sprite_area", header.sprite_area_offset)]
    boundaries = sorted({len(data), header.body_offset,
                         *(value for value in (header.undo_buffer_offset,
                                               header.sprite_area_offset,
                                               header.palette_offset) if value >= 0)})
    sections = []
    for name, start in positions:
        if start < 0:
            continue
        end = next((value for value in boundaries if value > start), len(data))
        sections.append(m.WorkAreaSection(name, m.SourceSpan(start, end - start),
                                          data[start:end]))
    return tuple(sections)


def decode_buffer(source: object) -> m.ArtWorks:
    """Decode an ArtWorks file from a contiguous buffer-compatible object."""
    try:
        view = memoryview(source)
    except TypeError as error:
        raise TypeError("data must support the buffer protocol") from error
    if not view.c_contiguous:
        raise TypeError("data must be a contiguous buffer")
    try:
        data = bytes(view.cast("B"))
    except TypeError as error:
        raise TypeError("data must be a byte-addressable contiguous buffer") from error
    header = _header(data)
    palette = None if header.palette_offset < 0 else _palette(data, header.palette_offset)
    record_lists = _Decoder(data, header, palette).decode()
    return m.ArtWorks(header, record_lists, palette, _work_areas(data, header), len(data))


def decode_file(handle: object) -> m.ArtWorks:
    """Decode from a seekable binary handle and restore its original position."""
    for method in ("tell", "seek", "read"):
        if not callable(getattr(handle, method, None)):
            raise TypeError("handle must be a seekable binary file")
    seekable = getattr(handle, "seekable", None)
    if callable(seekable) and not seekable():
        raise TypeError("handle must be a seekable binary file")
    original = handle.tell()  # type: ignore[attr-defined]
    try:
        handle.seek(0, SEEK_END)  # type: ignore[attr-defined]
        end = handle.tell()  # type: ignore[attr-defined]
        handle.seek(original, SEEK_SET)  # type: ignore[attr-defined]
        data = handle.read(end - original)  # type: ignore[attr-defined]
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise TypeError("handle must return binary data")
        return decode_buffer(data)
    finally:
        handle.seek(original, SEEK_SET)  # type: ignore[attr-defined]
