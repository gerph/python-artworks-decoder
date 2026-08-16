from __future__ import annotations

from dataclasses import FrozenInstanceError
import io
import struct
import unittest

from riscos_artworks import (
    ArtWorks,
    EmptyRecord,
    InvalidHeaderError,
    InvalidPointerError,
    TruncatedDataError,
    UnknownRecord,
)

from fixtures import bounded_unknown, deeply_nested, header, nested_with_unknown, record


class InputTests(unittest.TestCase):
    def test_buffer_and_memoryview_are_equivalent(self) -> None:
        source = record(0x22, version=12)
        from_bytes = ArtWorks.from_buffer(source)
        from_view = ArtWorks.from_buffer(memoryview(source))
        self.assertEqual(from_bytes, from_view)
        self.assertEqual(from_bytes.header.version, 12)

    def test_mutable_input_is_copied(self) -> None:
        source = bytearray(record(0x22))
        artwork = ArtWorks.from_buffer(source)
        source[:] = b"\0" * len(source)
        self.assertEqual(artwork.header.identifier.text, "Top!")

    def test_file_origin_is_relative_and_position_is_restored(self) -> None:
        stream = io.BytesIO(b"prefix" + record(0x22) + b"suffix")
        stream.seek(6)
        artwork = ArtWorks.from_file(stream)
        self.assertEqual(stream.tell(), 6)
        self.assertFalse(stream.closed)
        self.assertEqual(artwork.source_length, len(record(0x22)) + 6)

    def test_file_position_is_restored_after_failure(self) -> None:
        stream = io.BytesIO(b"prefixbad data")
        stream.seek(6)
        with self.assertRaises(TruncatedDataError):
            ArtWorks.from_file(stream)
        self.assertEqual(stream.tell(), 6)
        self.assertFalse(stream.closed)

    def test_non_seekable_and_text_handles_are_rejected(self) -> None:
        class NonSeekable:
            def read(self, _size: int = -1) -> bytes:
                return b""
        with self.assertRaises(TypeError):
            ArtWorks.from_file(NonSeekable())
        with self.assertRaises(TypeError):
            ArtWorks.from_file(io.StringIO("x" * 200))

    def test_non_contiguous_buffer_is_rejected(self) -> None:
        with self.assertRaises(TypeError):
            ArtWorks.from_buffer(memoryview(bytearray(300))[::2])

    def test_multidimensional_contiguous_buffer_is_accepted(self) -> None:
        source = record(0x22)
        view = memoryview(source).cast("B", shape=(len(source) // 4, 4))
        self.assertEqual(ArtWorks.from_buffer(view).header.version, 9)


class HeaderAndStructureTests(unittest.TestCase):
    def test_invalid_signatures_and_truncated_header(self) -> None:
        with self.assertRaises(TruncatedDataError):
            ArtWorks.from_buffer(b"Top!")
        bad = bytearray(record(0x22))
        bad[:4] = b"Draw"
        with self.assertRaises(InvalidHeaderError):
            ArtWorks.from_buffer(bad)
        bad = bytearray(record(0x22))
        bad[8:15] = b"NotDraw"
        with self.assertRaises(InvalidHeaderError):
            ArtWorks.from_buffer(bad)

    def test_objects_are_immutable_and_slotted(self) -> None:
        artwork = ArtWorks.from_buffer(record(0x22))
        with self.assertRaises(FrozenInstanceError):
            artwork.header.version = 10  # type: ignore[misc]
        # CPython's frozen/slotted dataclass setter reports either of these,
        # depending on whether the attempted name is a field.
        with self.assertRaises((AttributeError, TypeError)):
            artwork.header.new_field = 1  # type: ignore[attr-defined]

    def test_nested_lists_walk_depth_first(self) -> None:
        artwork = ArtWorks.from_buffer(nested_with_unknown())
        records = list(artwork.walk())
        self.assertEqual([item.type_code for item in records], [0x06, 0x99, 0x22])
        self.assertEqual(len(artwork.record_lists), 1)
        self.assertEqual(len(records[0].child_lists), 1)
        self.assertEqual(list(artwork.walk(UnknownRecord)), [records[1]])

    def test_deep_nesting_does_not_use_python_recursion(self) -> None:
        artwork = ArtWorks.from_buffer(deeply_nested(1500))
        self.assertEqual(artwork.structural_summary().records, 3001)

    def test_bounded_unknown_preserves_full_words_and_body(self) -> None:
        artwork = ArtWorks.from_buffer(bounded_unknown(b"opaque"))
        unknown = artwork.unsupported_records[0]
        self.assertEqual(unknown.type_word, 0xABCD0199)
        self.assertEqual(unknown.type_code, 0x99)
        self.assertEqual(unknown.raw_body, b"opaque\0\0")
        self.assertEqual(unknown.extra_bytes, unknown.raw_body)
        self.assertEqual(unknown.bounding_box.min_x, -1)

    def test_final_unknown_has_explicitly_unavailable_boundary(self) -> None:
        artwork = ArtWorks.from_buffer(record(0x99, b"not safely bounded"))
        unknown = artwork.unsupported_records[0]
        self.assertIsNone(unknown.raw_body)
        self.assertIsNone(unknown.extra_bytes)
        self.assertIsNone(unknown.body_span.length)

    def test_bad_pointer_sign_alignment_range_and_cycle(self) -> None:
        for next_pointer in (-4, 3, 0x1000):
            data = bytearray(record(0x22))
            struct.pack_into("<i", data, 132, next_pointer)
            with self.subTest(next_pointer=next_pointer):
                with self.assertRaises(InvalidPointerError):
                    ArtWorks.from_buffer(data)
        data = bytearray(record(0x22))
        struct.pack_into("<i", data, 132, 0)
        struct.pack_into("<i", data, 128, 4)
        with self.assertRaises(InvalidPointerError):
            ArtWorks.from_buffer(data)

    def test_truncated_record_header(self) -> None:
        with self.assertRaises(TruncatedDataError):
            ArtWorks.from_buffer(bytes(header()) + b"\0" * 12)

    def test_opaque_work_areas_are_bounded_by_header_offsets(self) -> None:
        data = header(body=0x90, undo=0x80, sprite=0x88)
        data.extend(b"undoDATA")
        data.extend(b"sprite!!")
        data.extend(struct.pack("<iiiiII4i", 0, 0, 0, 0, 0x22, 0,
                                0, 0, 0, 0))
        artwork = ArtWorks.from_buffer(data)
        self.assertEqual([section.name for section in artwork.work_areas],
                         ["undo_buffer", "sprite_area"])
        self.assertEqual(artwork.work_areas[0].data, b"undoDATA")
        self.assertEqual(artwork.work_areas[1].data, b"sprite!!")


if __name__ == "__main__":
    unittest.main()
