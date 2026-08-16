"""Immutable public model for decoded Computer Concepts ArtWorks files."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterator, TypeVar

_RecordT = TypeVar("_RecordT", bound="Record")


__all__ = [
    "ArtWorks", "ArtWorksHeader", "BezierElement", "BlendGroupRecord",
    "BlendOptionsRecord", "BlendPathRecord", "BoundingBox", "CapStyle",
    "CharacterRecord", "CloseElement", "ColourIndex", "ColourModel",
    "DashPatternRecord",
    "DecodedString", "DistortionGroupRecord", "EllipseRecord", "EmptyRecord",
    "EndCapRecord", "EndElement", "EndMarkerRecord", "FileInfoRecord",
    "FillColourRecord", "FillType", "FontNameRecord", "FontSizeRecord",
    "GroupRecord", "JoinStyle", "JoinStyleRecord", "LayerRecord",
    "LineCapRecord", "LineElement", "MarkerRecord", "MarkerStyle",
    "MoveElement", "Palette", "PaletteEntry", "Path", "PathElement",
    "PathRecord", "PerspectiveGroupRecord", "Point", "Record", "RecordList",
    "Record00Record", "Record22Record", "Record31Record", "Record32Record",
    "Record33Record", "RecordType", "RectangleRecord", "RelativePointer",
    "RoundedRectangleRecord", "SaveLocationRecord", "SourceSpan",
    "SpriteRecord", "StartCapRecord", "StartMarkerRecord", "StrokeColourRecord",
    "StrokeWidthRecord", "TextRecord", "Unknown2ERecord", "UnknownPathElement",
    "UnknownRecord", "WindingRule", "WindingRuleRecord", "WorkAreaRecord",
    "WorkAreaSection", "DistortionSubgroupRecord", "ArtWorksSummary",
]


class RecordType(IntEnum):
    UNKNOWN_00 = 0x00
    TEXT = 0x01
    PATH = 0x02
    SPRITE = 0x05
    GROUP = 0x06
    LAYER = 0x0A
    WORK_AREA = 0x21
    UNKNOWN_22 = 0x22
    SAVE_LOCATION = 0x23
    STROKE_COLOUR = 0x24
    STROKE_WIDTH = 0x25
    FILL_COLOUR = 0x26
    JOIN_STYLE = 0x27
    END_CAP = 0x28
    START_CAP = 0x29
    WINDING_RULE = 0x2A
    DASH_PATTERN = 0x2B
    RECTANGLE = 0x2C
    CHARACTER = 0x2D
    UNKNOWN_2E = 0x2E
    FONT_NAME = 0x2F
    FONT_SIZE = 0x30
    UNKNOWN_31 = 0x31
    UNKNOWN_32 = 0x32
    UNKNOWN_33 = 0x33
    ELLIPSE = 0x34
    ROUNDED_RECTANGLE = 0x35
    DISTORTION_GROUP = 0x37
    PERSPECTIVE_GROUP = 0x38
    FILE_INFO = 0x39
    BLEND_GROUP = 0x3A
    BLEND_OPTIONS = 0x3B
    BLEND_PATH = 0x3D
    START_MARKER = 0x3E
    END_MARKER = 0x3F
    DISTORTION_SUBGROUP = 0x42


class FillType(IntEnum):
    FLAT = 0
    LINEAR = 1
    RADIAL = 2


class ColourModel(IntEnum):
    RGB = 0
    CMYK = 1
    HSV = 2
    NON_INTERPOLATING_RGB = 3


class JoinStyle(IntEnum):
    MITRE = 0
    ROUND = 1
    BEVEL = 2


class CapStyle(IntEnum):
    BUTT = 0
    ROUND = 1
    SQUARE = 2
    TRIANGLE = 3


class WindingRule(IntEnum):
    NON_ZERO = 0
    EVEN_ODD = 1


class MarkerStyle(IntEnum):
    NONE = -1
    TRIANGLE = 0
    ARROW_HEAD = 1
    CIRCLE = 2
    ARROW_TAIL = 3


def _as_enum(enum_type: type[IntEnum], value: int) -> IntEnum | None:
    try:
        return enum_type(value)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class SourceSpan:
    offset: int
    length: int | None


@dataclass(frozen=True, slots=True)
class RelativePointer:
    offset: int
    previous: int
    next: int

    @property
    def previous_target(self) -> int | None:
        return None if self.previous == 0 else self.offset + self.previous

    @property
    def next_target(self) -> int | None:
        return None if self.next == 0 else self.offset + self.next


@dataclass(frozen=True, slots=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True, slots=True)
class BoundingBox:
    min_x: int
    min_y: int
    max_x: int
    max_y: int


@dataclass(frozen=True, slots=True)
class DecodedString:
    text: str
    raw: bytes
    padding: bytes


@dataclass(frozen=True, slots=True)
class PathElement:
    tag: int

    @property
    def flags(self) -> int:
        return self.tag & ~0xFF

    @property
    def masked_tag(self) -> int:
        return self.tag & 0xFF


@dataclass(frozen=True, slots=True)
class MoveElement(PathElement):
    point: Point


@dataclass(frozen=True, slots=True)
class LineElement(PathElement):
    point: Point


@dataclass(frozen=True, slots=True)
class BezierElement(PathElement):
    control_1: Point
    control_2: Point
    end: Point


@dataclass(frozen=True, slots=True)
class CloseElement(PathElement):
    pass


@dataclass(frozen=True, slots=True)
class EndElement(PathElement):
    pass


@dataclass(frozen=True, slots=True)
class UnknownPathElement(PathElement):
    pass


Path = tuple[PathElement, ...]


@dataclass(frozen=True, slots=True)
class ColourIndex:
    """A raw indexed, direct-BGR, or transparent colour reference."""

    value: int

    @property
    def is_indexed(self) -> bool:
        return self.value < 0x01000000

    @property
    def is_direct(self) -> bool:
        return 0x01000000 <= self.value < 0xFFFFFFFF

    @property
    def is_transparent(self) -> bool:
        return self.value == 0xFFFFFFFF

    @property
    def palette_index(self) -> int | None:
        return self.value if self.is_indexed else None

    @property
    def bgr(self) -> tuple[int, int, int] | None:
        if not self.is_direct:
            return None
        return ((self.value >> 16) & 0xFF, (self.value >> 8) & 0xFF,
                self.value & 0xFF)


@dataclass(frozen=True, slots=True)
class PaletteEntry:
    """One named ArtWorks palette entry with raw components and flags."""

    name: DecodedString
    colour: int
    component_0: int
    component_1: int
    component_2: int
    component_3: int
    flags: int

    @property
    def bgr(self) -> tuple[int, int, int]:
        return ((self.colour >> 16) & 0xFF, (self.colour >> 8) & 0xFF,
                self.colour & 0xFF)

    @property
    def colour_model_value(self) -> int:
        return self.flags & 0x3

    @property
    def colour_model(self) -> ColourModel:
        return ColourModel(self.colour_model_value)


@dataclass(frozen=True, slots=True)
class Palette:
    """An indexed palette retaining both complete header words."""

    count_word: int
    control_word: int
    entries: tuple[PaletteEntry, ...]
    span: SourceSpan

    @property
    def count(self) -> int:
        return self.count_word & 0xFFFFFF

    @property
    def masked_control(self) -> int:
        return self.control_word & 0xFFFFFF

    def resolve(self, colour: ColourIndex | int) -> int | None:
        value = colour.value if isinstance(colour, ColourIndex) else colour
        if value == 0xFFFFFFFF:
            return None
        if value >= 0x01000000:
            return value
        return self.entries[value].colour if value < len(self.entries) else None


@dataclass(frozen=True, slots=True)
class WorkAreaSection:
    name: str
    span: SourceSpan
    data: bytes


@dataclass(frozen=True, slots=True)
class ArtWorksHeader:
    """The complete interpreted 128-byte ArtWorks file header."""

    identifier: DecodedString
    version: int
    program: DecodedString
    unknown_16: int
    body_offset: int
    european_paper_width: int
    european_paper_height: int
    unknown_32: int
    unknown_36: int
    undo_buffer_offset: int
    sprite_area_offset: int
    unknown_48: int
    american_paper_width: int
    american_paper_height: int
    palette_offset: int
    unknown_64: int
    unknown_68: int
    unknown_72: int
    unknown_76: int
    unknown_80: int
    unknown_84: int
    unknown_88: int
    reserved: bytes


@dataclass(frozen=True, slots=True, kw_only=True)
class Record:
    """Fields shared by every linked ArtWorks record."""

    type_word: int
    type_code: int
    control_word: int
    bounding_box: BoundingBox
    pointer: RelativePointer
    span: SourceSpan
    body_span: SourceSpan
    child_lists: tuple[RecordList, ...]
    extra_bytes: bytes | None
    raw_body: bytes | None

    @property
    def record_type(self) -> RecordType | None:
        return _as_enum(RecordType, self.type_code)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class UnknownRecord(Record):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class EmptyRecord(Record):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class Record00Record(EmptyRecord):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class Record22Record(EmptyRecord):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class DistortionSubgroupRecord(EmptyRecord):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class TextRecord(Record):
    unknown_values: tuple[int, ...]
    rectangle: tuple[Point, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class PathRecord(Record):
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class SpriteRecord(Record):
    unknown_24: int
    name: DecodedString
    unknown_values: tuple[int, ...]
    palette: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class GroupRecord(Record):
    unknown_values: tuple[int, int, int]


@dataclass(frozen=True, slots=True, kw_only=True)
class LayerRecord(Record):
    unknown_24: int
    name: DecodedString


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkAreaRecord(Record):
    palette: Palette | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SaveLocationRecord(Record):
    file_type: int
    file_path: DecodedString


@dataclass(frozen=True, slots=True, kw_only=True)
class StrokeColourRecord(Record):
    colour: ColourIndex


@dataclass(frozen=True, slots=True, kw_only=True)
class StrokeWidthRecord(Record):
    width: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FillColourRecord(Record):
    fill_type: int
    unknown_28: int
    colour: ColourIndex | None
    gradient_line: tuple[Point, Point] | None
    start_colour: ColourIndex | None
    end_colour: ColourIndex | None

    @property
    def fill_type_enum(self) -> FillType | None:
        return _as_enum(FillType, self.fill_type)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class JoinStyleRecord(Record):
    join_style: int

    @property
    def join_style_enum(self) -> JoinStyle | None:
        return _as_enum(JoinStyle, self.join_style)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class LineCapRecord(Record):
    cap_style: int
    cap_triangle: int

    @property
    def cap_style_enum(self) -> CapStyle | None:
        return _as_enum(CapStyle, self.cap_style)  # type: ignore[return-value]

    @property
    def triangle_dimensions(self) -> tuple[int, int] | None:
        if self.cap_style != CapStyle.TRIANGLE:
            return None
        return (self.cap_triangle & 0xFFFF,
                (self.cap_triangle >> 16) & 0xFFFF)


@dataclass(frozen=True, slots=True, kw_only=True)
class StartCapRecord(LineCapRecord):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class EndCapRecord(LineCapRecord):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class WindingRuleRecord(Record):
    winding_rule: int

    @property
    def winding_rule_enum(self) -> WindingRule | None:
        return _as_enum(WindingRule, self.winding_rule)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class DashPatternRecord(Record):
    pattern: int
    offset: int | None
    elements: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class RectangleRecord(Record):
    unknown_24: int
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterRecord(Record):
    character_code: int
    unknown_values: tuple[int, int, int, int]


@dataclass(frozen=True, slots=True, kw_only=True)
class Unknown2ERecord(Record):
    unknown_24: int
    unknown_28: DecodedString
    unknown_36: DecodedString
    unknown_60: int
    unknown_64: int


@dataclass(frozen=True, slots=True, kw_only=True)
class FontNameRecord(Record):
    font_name: DecodedString


@dataclass(frozen=True, slots=True, kw_only=True)
class FontSizeRecord(Record):
    x_size: int
    y_size: int


@dataclass(frozen=True, slots=True, kw_only=True)
class Record31Record(Record):
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Record32Record(Record):
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Record33Record(Record):
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class EllipseRecord(Record):
    triangle: tuple[Point, Point, Point]
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class RoundedRectangleRecord(Record):
    corner_radius: int
    triangle: tuple[Point, Point, Point]
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class DistortionGroupRecord(Record):
    envelope: Path | None
    unknown_values: tuple[int, ...]
    original_objects_bounding_box: BoundingBox | None


@dataclass(frozen=True, slots=True, kw_only=True)
class PerspectiveGroupRecord(DistortionGroupRecord):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class FileInfoRecord(Record):
    file_info: DecodedString


@dataclass(frozen=True, slots=True, kw_only=True)
class BlendGroupRecord(Record):
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class BlendOptionsRecord(Record):
    unknown_24: int
    blend_steps: int
    values: tuple[int, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class BlendPathRecord(Record):
    path: Path


@dataclass(frozen=True, slots=True, kw_only=True)
class MarkerRecord(Record):
    marker_style: int
    marker_width: int
    marker_height: int

    @property
    def marker_style_enum(self) -> MarkerStyle | None:
        return _as_enum(MarkerStyle, self.marker_style)  # type: ignore[return-value]


@dataclass(frozen=True, slots=True, kw_only=True)
class StartMarkerRecord(MarkerRecord):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class EndMarkerRecord(MarkerRecord):
    pass


@dataclass(frozen=True, slots=True)
class RecordList:
    """One node in an ArtWorks list of record lists."""

    pointer: RelativePointer
    records: tuple[Record, ...]
    span: SourceSpan

    def walk(self, record_class: type[_RecordT] | None = None) -> Iterator[Record | _RecordT]:
        stack: list[Iterator[Record]] = [iter(self.records)]
        while stack:
            try:
                record = next(stack[-1])
            except StopIteration:
                stack.pop()
                continue
            if record_class is None or isinstance(record, record_class):
                yield record
            for child_list in reversed(record.child_lists):
                stack.append(iter(child_list.records))


@dataclass(frozen=True, slots=True)
class ArtWorksSummary:
    """A compact deterministic summary suitable for structural comparison."""

    source_length: int
    top_level_lists: int
    records: int
    type_counts: tuple[tuple[int, int], ...]
    unsupported_records: int
    palette_entries: int


@dataclass(frozen=True, slots=True)
class ArtWorks:
    """An eagerly decoded, immutable ArtWorks document."""

    header: ArtWorksHeader
    record_lists: tuple[RecordList, ...]
    palette: Palette | None
    work_areas: tuple[WorkAreaSection, ...]
    source_length: int

    @classmethod
    def from_buffer(cls, data: object) -> ArtWorks:
        """Decode a contiguous buffer-compatible object."""
        from .decoder import decode_buffer
        return decode_buffer(data)

    @classmethod
    def from_file(cls, handle: object) -> ArtWorks:
        """Decode at a binary handle's position, then restore that position."""
        from .decoder import decode_file
        return decode_file(handle)

    def walk(self, record_class: type[_RecordT] | None = None) -> Iterator[Record | _RecordT]:
        """Yield records depth first in file order, optionally by class."""
        for record_list in self.record_lists:
            yield from record_list.walk(record_class)

    @property
    def unsupported_records(self) -> tuple[UnknownRecord, ...]:
        """Return every record whose masked type is not understood."""
        return tuple(record for record in self.walk(UnknownRecord))

    def resolve_colour(self, colour: ColourIndex | int) -> int | None:
        """Resolve a colour reference to a BGR word or transparent ``None``."""
        value = colour.value if isinstance(colour, ColourIndex) else colour
        if value == 0xFFFFFFFF:
            return None
        if value >= 0x01000000:
            return value
        return None if self.palette is None else self.palette.resolve(value)

    def palette_entry(self, index: int) -> PaletteEntry | None:
        """Look up an entry safely, returning ``None`` when it is unavailable."""
        if self.palette is None or index < 0 or index >= len(self.palette.entries):
            return None
        return self.palette.entries[index]

    def structural_summary(self) -> ArtWorksSummary:
        """Summarise record counts without discarding the decoded structure."""
        counts: dict[int, int] = {}
        total = 0
        unsupported = 0
        for record in self.walk():
            total += 1
            counts[record.type_code] = counts.get(record.type_code, 0) + 1
            unsupported += isinstance(record, UnknownRecord)
        return ArtWorksSummary(
            self.source_length,
            len(self.record_lists),
            total,
            tuple(sorted(counts.items())),
            unsupported,
            0 if self.palette is None else len(self.palette.entries),
        )
