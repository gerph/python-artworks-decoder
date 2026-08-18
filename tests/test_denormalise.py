"""Tests for denormalise.py -- built directly against the model
dataclasses (see test_records.py's own style) rather than raw bytes,
since this transform is pure tree surgery with no byte-level decoding
involved."""

from riscos_artworks import (
    BoundingBox,
    FillColourRecord,
    GroupRecord,
    PathRecord,
    RecordList,
    RelativePointer,
    SourceSpan,
    StrokeColourRecord,
    StrokeWidthRecord,
    denormalise,
)
from riscos_artworks.model import ArtWorks, ArtWorksHeader, ColourIndex, DecodedString


def _pointer(offset=0):
    return RelativePointer(offset=offset, previous=0, next=0)


def _span(offset=0):
    return SourceSpan(offset=offset, length=0)


def _bbox():
    return BoundingBox(0, 0, 0, 0)


def _record(cls, *, offset=0, child_lists=(), **fields):
    return cls(
        type_word=0, type_code=0, control_word=2, bounding_box=_bbox(),
        pointer=_pointer(offset), span=_span(offset), body_span=_span(offset),
        child_lists=child_lists, extra_bytes=None, raw_body=None, **fields,
    )


def _list(*records, offset=0):
    return RecordList(pointer=_pointer(offset), records=records, span=_span(offset))


def _header():
    return ArtWorksHeader(
        DecodedString("Top!", b"Top!", b""), 9, DecodedString("TopDraw", b"TopDraw", b""),
        0, 0x80, 0, 0, 0, 0, -1, -1, 0, 0, 0, -1, 0, 0, 0, 0, 0, 0, 0, b"",
    )


def _artwork(record_lists):
    return ArtWorks(_header(), record_lists, None, (), 0)


def test_empty_record_lists_are_left_alone():
    result = denormalise(_artwork(()))
    assert result.record_lists == ()


def test_a_solitary_record_is_not_wrapped_in_a_synthetic_child():
    solo = _record(PathRecord, offset=8, path=())
    result = denormalise(_artwork((_list(solo, offset=0),)))
    (record_list,) = result.record_lists
    (record,) = record_list.records
    assert record.child_lists == ()


def test_a_flat_sibling_run_nests_each_one_under_the_previous():
    shape = _record(PathRecord, offset=8, path=())
    fill = _record(FillColourRecord, offset=16, fill_type=0,
                   unknown_28=0, colour=ColourIndex(0x01000000), gradient_line=None,
                   start_colour=None, end_colour=None)
    result = denormalise(_artwork((_list(shape, fill, offset=0),)))
    (record_list,) = result.record_lists
    (nested_shape,) = record_list.records
    assert isinstance(nested_shape, PathRecord)
    (synthetic_list,) = nested_shape.child_lists
    (nested_fill,) = synthetic_list.records
    assert nested_fill.pointer.offset == fill.pointer.offset
    assert isinstance(nested_fill, FillColourRecord)
    assert nested_fill.colour == fill.colour


def test_a_three_way_sibling_chain_nests_all_the_way_down():
    a = _record(GroupRecord, offset=8, unknown_values=())
    b = _record(StrokeColourRecord, offset=16, colour=ColourIndex(0x01000000))
    c = _record(StrokeWidthRecord, offset=24, width=10)
    result = denormalise(_artwork((_list(a, b, c, offset=0),)))
    (record_list,) = result.record_lists
    (nested_a,) = record_list.records
    (a_children,) = nested_a.child_lists
    (nested_b,) = a_children.records
    (b_children,) = nested_b.child_lists
    (nested_c,) = b_children.records
    assert nested_c.pointer.offset == c.pointer.offset
    assert isinstance(nested_c, StrokeWidthRecord)
    assert nested_c.width == c.width
    assert nested_c.child_lists == ()


def test_the_records_own_existing_children_follow_the_synthetic_one():
    grandchild = _record(StrokeWidthRecord, offset=40, width=5)
    own_children = _list(grandchild, offset=32)
    parent = _record(GroupRecord, offset=8, unknown_values=(), child_lists=(own_children,))
    sibling = _record(StrokeColourRecord, offset=16, colour=ColourIndex(0x01000000))
    result = denormalise(_artwork((_list(parent, sibling, offset=0),)))
    (record_list,) = result.record_lists
    (nested_parent,) = record_list.records
    synthetic_list, real_own_list = nested_parent.child_lists
    (nested_sibling,) = synthetic_list.records
    assert nested_sibling.pointer.offset == sibling.pointer.offset
    assert isinstance(nested_sibling, StrokeColourRecord)
    (nested_grandchild,) = real_own_list.records
    assert nested_grandchild.pointer.offset == grandchild.pointer.offset


def test_recurses_into_a_records_own_pre_existing_child_lists_too():
    inner_shape = _record(PathRecord, offset=40, path=())
    inner_fill = _record(FillColourRecord, offset=48, fill_type=0,
                         unknown_28=0, colour=ColourIndex(0x01000000), gradient_line=None,
                         start_colour=None, end_colour=None)
    own_children = _list(inner_shape, inner_fill, offset=32)
    parent = _record(GroupRecord, offset=8, unknown_values=(), child_lists=(own_children,))
    result = denormalise(_artwork((_list(parent, offset=0),)))
    (record_list,) = result.record_lists
    (nested_parent,) = record_list.records
    (real_own_list,) = nested_parent.child_lists
    (nested_inner_shape,) = real_own_list.records
    (synthetic,) = nested_inner_shape.child_lists
    (nested_inner_fill,) = synthetic.records
    assert nested_inner_fill.pointer.offset == inner_fill.pointer.offset
    assert isinstance(nested_inner_fill, FillColourRecord)


def test_denormalise_does_not_mutate_the_original_artwork():
    shape = _record(PathRecord, offset=8, path=())
    fill = _record(FillColourRecord, offset=16, fill_type=0,
                   unknown_28=0, colour=ColourIndex(0x01000000), gradient_line=None,
                   start_colour=None, end_colour=None)
    original = _artwork((_list(shape, fill, offset=0),))
    denormalise(original)
    (record_list,) = original.record_lists
    assert record_list.records == (shape, fill)
    assert shape.child_lists == ()
