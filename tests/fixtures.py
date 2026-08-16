"""Small binary ArtWorks fixture builders."""

from __future__ import annotations

import struct


def header(*, body: int = 0x80, version: int = 9, palette: int = -1,
           undo: int = -1, sprite: int = -1) -> bytearray:
    data = bytearray(0x80)
    struct.pack_into("<4sI8sII", data, 0, b"Top!", version,
                     b"TopDraw\0", 0, body)
    struct.pack_into("<ii", data, 0x28, undo, sprite)
    struct.pack_into("<i", data, 0x3C, palette)
    return data


def record(record_type: int, body: bytes = b"", *, type_flags: int = 0,
           control: int = 0, box: tuple[int, int, int, int] = (0, 0, 0, 0),
           version: int = 9) -> bytes:
    data = header(version=version)
    data.extend(struct.pack("<ii", 0, 0))
    data.extend(struct.pack("<ii", 0, 0))
    data.extend(struct.pack("<II4i", type_flags | record_type, control, *box))
    data.extend(body)
    return bytes(data)


def path(*elements: tuple[int, tuple[int, ...]]) -> bytes:
    data = bytearray()
    for tag, coordinates in elements:
        data.extend(struct.pack("<I", tag))
        if coordinates:
            data.extend(struct.pack("<" + "i" * len(coordinates), *coordinates))
    return bytes(data)


def nested_with_unknown() -> bytes:
    """Return two root records, with a child list beneath the first."""
    data = header()
    data.extend(struct.pack("<ii", 0, 0))             # root list at 128
    data.extend(struct.pack("<ii", 52, 0))            # group record at 136
    data.extend(struct.pack("<II4i", 0x106, 3, 1, 2, 3, 4))
    data.extend(struct.pack("<III", 10, 20, 30))      # body ends at 180
    data.extend(struct.pack("<ii", -44, 40))          # child lists pointer
    data.extend(struct.pack("<ii", 0, -52))           # second root record
    data.extend(struct.pack("<II4i", 0x22, 0, 0, 0, 0, 0))
    data.extend(struct.pack("<ii", -40, 0))           # child list at 220
    data.extend(struct.pack("<ii", 0, -92))           # unknown child record
    data.extend(struct.pack("<II4i", 0x99, 0, 0, 0, 0, 0))
    return bytes(data)


def bounded_unknown(raw_body: bytes) -> bytes:
    padding = (-len(raw_body)) & 3
    raw_body += b"\x00" * padding
    next_value = 32 + len(raw_body) + 8
    data = header()
    data.extend(struct.pack("<ii", 0, 0))
    data.extend(struct.pack("<ii", next_value, 0))
    data.extend(struct.pack("<II4i", 0xABCD0199, 7, -1, -2, 3, 4))
    data.extend(raw_body)
    data.extend(struct.pack("<ii", 0, 0))
    data.extend(struct.pack("<ii", 0, -next_value))
    data.extend(struct.pack("<II4i", 0x22, 0, 0, 0, 0, 0))
    return bytes(data)


def bounded_record(record_type: int, body: bytes) -> bytes:
    padding = (-len(body)) & 3
    body += b"\x00" * padding
    next_value = 32 + len(body) + 8
    data = header()
    data.extend(struct.pack("<ii", 0, 0))
    data.extend(struct.pack("<ii", next_value, 0))
    data.extend(struct.pack("<II4i", record_type, 0, 0, 0, 0, 0))
    data.extend(body)
    data.extend(struct.pack("<ii", 0, 0))
    data.extend(struct.pack("<ii", 0, -next_value))
    data.extend(struct.pack("<II4i", 0x22, 0, 0, 0, 0, 0))
    return bytes(data)


def deeply_nested(depth: int) -> bytes:
    """Create an iterative-decoder stress fixture with ``depth`` groups."""
    data = header()
    for _ in range(depth):
        data.extend(struct.pack("<ii", 0, 0))
        data.extend(struct.pack("<ii", 52, 0))
        data.extend(struct.pack("<II4i", 0x06, 0, 0, 0, 0, 0))
        data.extend(struct.pack("<III", 0, 0, 0))
        data.extend(struct.pack("<ii", 0, 40))
        data.extend(struct.pack("<ii", 0, -52))
        data.extend(struct.pack("<II4i", 0x22, 0, 0, 0, 0, 0))
    data.extend(struct.pack("<iiiiII4i", 0, 0, 0, 0, 0x22, 0,
                            0, 0, 0, 0))
    return bytes(data)
