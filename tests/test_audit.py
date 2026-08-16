from __future__ import annotations

import csv
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from riscos_artworks.audit import main

from fixtures import record


class AuditTests(unittest.TestCase):
    def test_audit_reports_success_non_artworks_and_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "good").write_bytes(record(0x22, version=12))
            (source / "text").write_text("not an artwork", encoding="ascii")
            (source / "broken").write_bytes(b"Top!" + b"\0" * 140)
            prefix = root / "output" / "audit"

            self.assertEqual(main([str(source), "--output", str(prefix),
                                   "--checkpoint", "1", "--quiet"]), 0)
            with prefix.with_suffix(".csv").open(newline="", encoding="utf-8") as handle:
                rows = {row["path"]: row for row in csv.DictReader(handle)}
            self.assertEqual(rows["good"]["status"], "decoded")
            self.assertEqual(rows["good"]["version"], "12")
            self.assertEqual(rows["good"]["record_count"], "1")
            self.assertEqual(rows["text"]["status"], "not_artworks")
            self.assertEqual(rows["broken"]["status"], "decode_error")
            self.assertEqual(rows["broken"]["error_type"], "InvalidHeaderError")
            self.assertEqual(len(rows["broken"]["sha256"]), 64)
            self.assertNotIn("decode_ms", rows["good"])
            self.assertNotIn("scanned_at", rows["good"])

            summary = json.loads(prefix.with_suffix(".summary.json").read_text())
            self.assertEqual(summary["files"], 3)
            self.assertEqual(summary["statuses"], {
                "decode_error": 1, "decoded": 1, "not_artworks": 1})
            self.assertEqual(summary["record_types"], {"22": 1})
            self.assertEqual(summary["statuses_by_top_level"], {
                "broken": {"decode_error": 1},
                "good": {"decoded": 1},
                "text": {"not_artworks": 1},
            })

            # An ordinary rerun reuses the existing rows without duplicates.
            self.assertEqual(main([str(source), "--output", str(prefix),
                                   "--quiet"]), 0)
            with sqlite3.connect(prefix.with_suffix(".sqlite3")) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM files").fetchone()[0], 3)

            (source / "text").unlink()
            self.assertEqual(main([str(source), "--output", str(prefix),
                                   "--quiet"]), 0)
            with sqlite3.connect(prefix.with_suffix(".sqlite3")) as connection:
                self.assertEqual(connection.execute(
                    "SELECT COUNT(*) FROM files").fetchone()[0], 2)

    def test_export_only_recreates_deleted_exports(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "good").write_bytes(record(0x22))
            prefix = root / "audit"
            main([str(source), "--output", str(prefix), "--quiet"])
            prefix.with_suffix(".csv").unlink()
            prefix.with_suffix(".summary.json").unlink()
            self.assertEqual(main([str(source), "--output", str(prefix),
                                   "--export-only", "--quiet"]), 0)
            self.assertTrue(prefix.with_suffix(".csv").is_file())
            self.assertTrue(prefix.with_suffix(".summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
