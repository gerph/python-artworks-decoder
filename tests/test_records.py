from __future__ import annotations

import struct
import unittest

from riscos_artworks import (
    ArtWorks,
    BezierElement,
    ColourIndex,
    EndElement,
    FillColourRecord,
    JoinStyleRecord,
    LineElement,
    MoveElement,
    PathRecord,
    StartCapRecord,
    UnknownPathElement,
    Record00Record,
    Record22Record,
)

from fixtures import bounded_record, header, path, record


class PrimitiveAndRecordTests(unittest.TestCase):
    def test_path_elements_retain_tags_and_flags(self) -> None:
        body = path(
            (0x80000002, (1, 2)),
            (8, (3, 4)),
            (6, (5, 6, 7, 8, 9, 10)),
            (4, ()),
            (0, ()),
        )
        artwork = ArtWorks.from_buffer(record(0x02, body, type_flags=0x12340000))
        item = next(artwork.walk(PathRecord))
        self.assertEqual(item.type_word, 0x12340002)
        self.assertIsInstance(item.path[0], MoveElement)
        self.assertEqual(item.path[0].flags, 0x80000000)
        self.assertIsInstance(item.path[1], LineElement)
        self.assertIsInstance(item.path[2], BezierElement)
        self.assertIsInstance(item.path[3], UnknownPathElement)
        self.assertIsInstance(item.path[4], EndElement)

    def test_raw_enum_value_is_preserved(self) -> None:
        artwork = ArtWorks.from_buffer(record(0x27, struct.pack("<I", 99)))
        join = next(artwork.walk(JoinStyleRecord))
        self.assertEqual(join.join_style, 99)
        self.assertIsNone(join.join_style_enum)

    def test_unknown_fill_enum_is_preserved(self) -> None:
        artwork = ArtWorks.from_buffer(record(0x26, struct.pack("<II", 99, 7)))
        fill = next(artwork.walk(FillColourRecord))
        self.assertEqual(fill.fill_type, 99)
        self.assertIsNone(fill.fill_type_enum)

    def test_triangle_cap_dimensions_are_width_then_height(self) -> None:
        cap = next(ArtWorks.from_buffer(record(
            0x29, struct.pack("<II", 3, (4 << 16) | 2))).walk(StartCapRecord))
        self.assertEqual(cap.triangle_dimensions, (2, 4))

    def test_flat_and_gradient_fills(self) -> None:
        flat = ArtWorks.from_buffer(record(0x26, struct.pack("<III", 0, 7, 3)))
        fill = next(flat.walk(FillColourRecord))
        self.assertEqual(fill.colour, ColourIndex(3))
        gradient_body = struct.pack("<II4iII", 1, 9, 1, 2, 3, 4,
                                    0x00112233, 0xFFFFFFFF)
        gradient = next(ArtWorks.from_buffer(record(0x26, gradient_body)).walk(
            FillColourRecord))
        self.assertEqual(gradient.gradient_line[1].y, 4)  # type: ignore[index]
        self.assertTrue(gradient.end_colour.is_transparent)  # type: ignore[union-attr]

    def test_palette_masks_count_and_resolves_colours(self) -> None:
        data = header(palette=0x80)
        entry = (b"Red\0" + b"padding" + b"\0" * 13)[:24]
        data.extend(struct.pack("<II", 0xAA000001, 0xBB000001))
        data.extend(entry)
        data.extend(struct.pack("<7I", 0x00332211, 1, 2, 3, 4, 5, 0))
        body_offset = len(data)
        body_offset = (body_offset + 3) & ~3
        data.extend(b"\0" * (body_offset - len(data)))
        struct.pack_into("<I", data, 20, body_offset)
        data.extend(struct.pack("<iiiiII4i", 0, 0, 0, 0, 0x21, 0, 0, 0, 0, 0))
        artwork = ArtWorks.from_buffer(data)
        self.assertEqual(artwork.palette.count, 1)  # type: ignore[union-attr]
        self.assertEqual(artwork.palette.entries[0].name.text, "Red")  # type: ignore[union-attr]
        self.assertEqual(artwork.resolve_colour(0), 0x00332211)
        self.assertEqual(artwork.resolve_colour(0xFFFFFFFF), None)
        self.assertEqual(ColourIndex(0x00332211).bgr, None)
        self.assertEqual(ColourIndex(0x01332211).bgr, (0x33, 0x22, 0x11))
        self.assertEqual(artwork.palette.entries[0].colour_model_value, 1)  # type: ignore[union-attr]
        self.assertEqual(artwork.palette_entry(0).name.text, "Red")  # type: ignore[union-attr]
        self.assertIsNone(artwork.palette_entry(-1))

    def test_every_reference_record_body_has_a_typed_decoder(self) -> None:
        end_path = struct.pack("<I", 0)
        fixed8 = b"short\0xx"
        fixed24 = b"long\0" + b"x" * 19
        fixed32 = b"Layer\0" + b"x" * 26
        sprite_body = (struct.pack("<I", 1) + b"Sprite\0" + b"x" * 5 +
                       struct.pack("<16I", *range(16)) + struct.pack("<I", 0))
        cases = {
            0x00: b"", 0x01: struct.pack("<6I8i", *range(14)),
            0x02: end_path, 0x05: sprite_body,
            0x06: struct.pack("<3I", 1, 2, 3),
            0x0A: struct.pack("<I", 1) + fixed32,
            0x21: b"", 0x22: b"", 0x23: struct.pack("<I", 0xAFF) + b"file\0",
            0x24: struct.pack("<I", 1), 0x25: struct.pack("<I", 2),
            0x26: struct.pack("<3I", 0, 0, 1),
            0x27: struct.pack("<I", 0), 0x28: struct.pack("<2I", 0, 0),
            0x29: struct.pack("<2I", 0, 0), 0x2A: struct.pack("<I", 0),
            0x2B: struct.pack("<i", 0), 0x2C: struct.pack("<I", 0) + end_path,
            0x2D: struct.pack("<5I", *range(5)),
            0x2E: struct.pack("<I", 0) + fixed8 + fixed24 + struct.pack("<2i", -1, -2),
            0x2F: b"Homerton.Medium\0", 0x30: struct.pack("<2I", 12, 13),
            0x31: struct.pack("<4I", *range(4)), 0x32: struct.pack("<I", 1),
            0x33: struct.pack("<6i", *range(-3, 3)),
            0x34: struct.pack("<6i", *range(6)) + end_path,
            0x35: struct.pack("<I6i", 8, *range(6)) + end_path,
            0x39: b"information\0", 0x3A: struct.pack("<11i", *range(11)),
            0x3B: struct.pack("<10i", *range(10)), 0x3D: end_path,
            0x3E: struct.pack("<iII", -1, 2, 3),
            0x3F: struct.pack("<iII", -1, 2, 3), 0x42: b"",
        }
        for code, body in cases.items():
            with self.subTest(code=hex(code)):
                artwork = ArtWorks.from_buffer(record(code, body))
                decoded = next(artwork.walk())
                self.assertNotEqual(decoded.__class__.__name__, "UnknownRecord")
        self.assertIsInstance(next(ArtWorks.from_buffer(record(0x00)).walk()),
                              Record00Record)
        self.assertIsInstance(next(ArtWorks.from_buffer(record(0x22)).walk()),
                              Record22Record)

    def test_advanced_group_bodies_are_preserved(self) -> None:
        end_path = struct.pack("<I", 0)
        distortion = end_path + struct.pack("<9I4i", *range(13))
        perspective = end_path + struct.pack("<13I4i", *range(17))
        for code, body, count in ((0x37, distortion, 9),
                                  (0x38, perspective, 13)):
            with self.subTest(code=hex(code)):
                decoded = next(ArtWorks.from_buffer(
                    bounded_record(code, body)).walk())
                self.assertEqual(len(decoded.unknown_values), count)
                self.assertIsNotNone(decoded.original_objects_bounding_box)

    def test_malformed_palette_count_is_rejected(self) -> None:
        data = header(palette=0x80)
        data.extend(struct.pack("<II", 0xFFFFFF, 0))
        struct.pack_into("<I", data, 20, 0x88)
        data.extend(struct.pack("<iiiiII4i", 0, 0, 0, 0, 0x22, 0, 0, 0, 0, 0))
        with self.assertRaises(Exception):
            ArtWorks.from_buffer(data)


if __name__ == "__main__":
    unittest.main()
