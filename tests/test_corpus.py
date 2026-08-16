from __future__ import annotations

import os
from pathlib import Path
import unittest

from riscos_artworks import ArtWorks


class CorpusTests(unittest.TestCase):
    def test_optional_examples_decode_from_both_inputs(self) -> None:
        location = os.environ.get("ARTWORKS_EXAMPLES")
        if not location:
            self.skipTest("ARTWORKS_EXAMPLES is not set")
        paths = sorted(path for path in Path(location).iterdir() if path.is_file())
        self.assertTrue(paths)
        record_count = 0
        for path in paths:
            data = path.read_bytes()
            from_buffer = ArtWorks.from_buffer(memoryview(data))
            with path.open("rb") as handle:
                from_file = ArtWorks.from_file(handle)
            self.assertEqual(from_buffer, from_file, path.name)
            record_count += sum(1 for _ in from_buffer.walk())
        expected_files = os.environ.get("ARTWORKS_EXPECTED_FILES")
        expected_records = os.environ.get("ARTWORKS_EXPECTED_RECORDS")
        if expected_files:
            self.assertEqual(len(paths), int(expected_files))
        if expected_records:
            self.assertEqual(record_count, int(expected_records))


if __name__ == "__main__":
    unittest.main()

