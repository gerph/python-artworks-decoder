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
    SpriteRecord,
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
        # A direct colour's bytes (LSB to MSB) are K, C, M, Y, decoded
        # via a standard CMYK->RGB conversion -- see ColourIndex's own
        # docstring for how this was confirmed against two real files.
        # For 0x01332211: K=0x11, C=0x22, M=0x33, Y=0x01.
        self.assertEqual(ColourIndex(0x01332211).bgr, (206, 190, 237))
        # "Registration Black" (Colour_RegBlack = -2, i.e. 0xFFFFFFFE)
        # is a print-production sentinel, not a literal direct colour,
        # even though it satisfies the same >= 0x01000000 test a real
        # direct colour does -- resolves to solid black, not the
        # near-white a naive BGR-bit extraction would give (confirmed
        # against !TopCode/Binds/TopBinds.bas's own Colour_RegBlack
        # constant and a real file, TestDocs/RegistrationBlackRect,d94).
        self.assertFalse(ColourIndex(0xFFFFFFFE).is_direct)
        self.assertTrue(ColourIndex(0xFFFFFFFE).is_registration_black)
        self.assertEqual(ColourIndex(0xFFFFFFFE).bgr, (0, 0, 0))
        self.assertEqual(artwork.resolve_colour(0xFFFFFFFE), 0x00000000)
        self.assertEqual(artwork.palette.resolve(0xFFFFFFFE), 0x00000000)  # type: ignore[union-attr]
        self.assertEqual(artwork.palette.entries[0].colour_model_value, 1)  # type: ignore[union-attr]
        self.assertEqual(artwork.palette_entry(0).name.text, "Red")  # type: ignore[union-attr]
        self.assertIsNone(artwork.palette_entry(-1))

    def test_direct_colour_decodes_kcmy_bytes_as_cmyk(self) -> None:
        # Two independent real examples, both checked against the real
        # document's own colour-picker dialog: a document's "SVG logo"
        # shape (0xFFFF9C00, target 59.8/99.6/99.2/0% CMYK) and, later,
        # a background rectangle in the same document
        # (0xFFFF9900, target RGB 40.2/0.4/0.8%, i.e. (102, 1, 2)).
        # Both are reproduced (within rounding of the dialog's own
        # 1-decimal-place percentages) by reading the value's four
        # bytes, LSB to MSB, as K, C, M, Y (0-255 each) through a
        # standard CMYK->RGB conversion.
        self.assertEqual(ColourIndex(0xFFFF9C00).bgr, (99, 0, 0))
        self.assertEqual(ColourIndex(0xFFFF9900).bgr, (102, 0, 0))

    def test_sprite_record_with_a_palette_reads_its_own_entries(self) -> None:
        # The word immediately after "values" is the palette's own
        # entry count directly, with no separate flag word before it --
        # confirmed against two real, deliberately contrasting files
        # (AWDocs/TestDocs/Sprite16ColourPalettedMasked,d94 and
        # Sprite256ColoursPaletedNoMask,d94): the word there reads
        # exactly 16 and 256 respectively, each followed immediately by
        # that many real, sensible-looking palette words (a 16-entry
        # file starting with a clean 8-step greyscale ramp, for
        # instance) -- see the decoder's own comment for the fuller
        # story, including an earlier, wrong version of this fix.
        body = (struct.pack("<I", 1) + b"HasPal\0" + b"x" * 5 +
                struct.pack("<16I", *range(16)) + struct.pack("<I", 2) +
                struct.pack("<2I", 0x11223344, 0x55667788))
        artwork = ArtWorks.from_buffer(record(0x05, body))
        sprite = next(artwork.walk(SpriteRecord))
        self.assertEqual(sprite.name.text, "HasPal")
        self.assertEqual(sprite.palette, (0x11223344, 0x55667788))
        self.assertEqual(sprite.data, b"")

    def test_sprite_record_data_is_resolved_from_its_own_shared_native_area(self) -> None:
        # ArtWorks stores the actual pixel data for one or more sibling
        # SpriteRecords together, once, in a single shared RISC
        # OS-format sprite area placed after all of their own metadata
        # blocks -- confirmed empirically against 5 real files
        # (AWDocs/TestDocs/Sprite1BPP-lefthandwastae,d94,
        # Sprite2BPP-lefthandwastage,d94,
        # Sprite4BPP-lethandwastage,d94, SpriteManyFlame,d94 -- 8
        # sprites sharing one area, and SpritesLots,d94 -- 23 sprites
        # sharing one). Rather than assume any fixed gap, the decoder
        # scans forward for the area's own [size, count, 16, size]
        # header and walks its native sprite chain matching by name.
        one_length = 4 + 12 + 28  # next_offset + name + 7 fixed words
        sprite_one = (struct.pack("<I", one_length) + b"One\0\0\0\0\0\0\0\0\0" +
                     struct.pack("<7i", 0, 0, 0, 0, 0, 0, 0))
        sprite_two = (struct.pack("<I", 0) + b"Two\0\0\0\0\0\0\0\0\0" +
                     struct.pack("<7i", 0, 0, 0, 0, 0, 0, 0))
        area_size = 16 + len(sprite_one) + len(sprite_two)
        area = struct.pack("<4I", area_size, 2, 16, area_size) + sprite_one + sprite_two
        body = (struct.pack("<I", 1) + b"Two\0" + b"x" * 8 +
                struct.pack("<16I", *range(16)) + struct.pack("<I", 0) + area)
        artwork = ArtWorks.from_buffer(record(0x05, body))
        sprite = next(artwork.walk(SpriteRecord))
        self.assertEqual(sprite.name.text, "Two")
        self.assertEqual(sprite.data, sprite_two)

    def test_sprite_record_with_an_implausible_count_degrades_to_no_palette(self) -> None:
        # Regression test: a real ArtWorks picture (an "SVG" logo,
        # confirmed independently via riscos_sprites/riscos-dumpsprites
        # against the same sprite extracted separately: 32bpp, no
        # palette at all) raised "sprite palette count exceeds record"
        # here -- that sprite's own record appears to carry additional
        # fields (at least one further embedded string resembling a
        # mask colour name) this decoder doesn't yet model, throwing
        # off this word's own true position for that case specifically.
        # Rather than raise (crashing every caller) or guess at that
        # structure without a confirmed example to check against, an
        # implausible count here degrades to an empty palette instead --
        # consistent with the one real case seen so far.
        body = (struct.pack("<I", 1) + b"NoPal\0" + b"x" * 6 +
                struct.pack("<16I", *range(16)) + struct.pack("<I", 0xFFFFFFFF))
        artwork = ArtWorks.from_buffer(record(0x05, body))
        sprite = next(artwork.walk(SpriteRecord))
        self.assertEqual(sprite.name.text, "NoPal")
        self.assertEqual(sprite.palette, ())
        self.assertEqual(sprite.data, b"")

    def test_every_reference_record_body_has_a_typed_decoder(self) -> None:
        end_path = struct.pack("<I", 0)
        fixed8 = b"short\0xx"
        fixed24 = b"long\0" + b"x" * 19
        fixed32 = b"Layer\0" + b"x" * 26
        # Trailing word is the palette's own entry count (0 = none) --
        # see test_sprite_record_with_a_palette_reads_its_own_entries
        # and test_sprite_record_with_an_implausible_count_degrades_to_no_palette
        # above for the two more interesting cases spelled out explicitly.
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

    def test_palette_count_word_is_ignored_in_favour_of_control_word(self) -> None:
        # count_word (the first word) is not the palette's own real
        # entry count -- confirmed against two real files created by
        # dragging a DrawFile into ArtWorks (AWDocs/TestDocs/
        # FromDrawfileRGBCircles,d94: count_word=49, control_word=18,
        # only 18 entries genuinely populated; RO4Bugs,d94: count_word
        # =81, control_word=72, 72 populated). Trusting count_word here
        # reads straight past the real palette into unrelated later
        # file content -- RGBCircles's own entry 18 decodes to
        # ArtWorks' own undo-stack labels ("<Nothing>", "Redo"), and
        # entries further in decode as readable Print_* preferences
        # text. control_word (the second word) is the real, live count
        # in every file checked, including ones where the two happen
        # to agree.
        data = header(palette=0x80)
        entry_a = (b"A\0" + b"\0" * 22)[:24]
        entry_b = (b"B\0" + b"\0" * 22)[:24]
        garbage = (b"<Nothing>\0" + b"\0" * 14)[:24]
        data.extend(struct.pack("<II", 3, 2))  # count_word=3, control_word=2
        for entry in (entry_a, entry_b, garbage):
            data.extend(entry)
            data.extend(struct.pack("<6I", 0, 0, 0, 0, 0, 0))
        body_offset = (len(data) + 3) & ~3
        data.extend(b"\0" * (body_offset - len(data)))
        struct.pack_into("<I", data, 20, body_offset)
        data.extend(struct.pack("<iiiiII4i", 0, 0, 0, 0, 0x21, 0, 0, 0, 0, 0))
        artwork = ArtWorks.from_buffer(data)
        self.assertEqual(artwork.palette.count, 2)  # type: ignore[union-attr]
        self.assertEqual([e.name.text for e in artwork.palette.entries], ["A", "B"])  # type: ignore[union-attr]

    def test_malformed_palette_count_is_rejected(self) -> None:
        # control_word (not count_word) is the real entry count -- see
        # _palette()'s own comment -- so the malformed value belongs
        # there.
        data = header(palette=0x80)
        data.extend(struct.pack("<II", 0, 0xFFFFFF))
        struct.pack_into("<I", data, 20, 0x88)
        data.extend(struct.pack("<iiiiII4i", 0, 0, 0, 0, 0x22, 0, 0, 0, 0, 0))
        with self.assertRaises(Exception):
            ArtWorks.from_buffer(data)


if __name__ == "__main__":
    unittest.main()
