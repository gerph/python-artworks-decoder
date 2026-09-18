from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from riscos_artworks.cli import main

from fixtures import nested_with_unknown, path, record


def _run(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            status = main(argv)
        except SystemExit as exit_:
            status = int(exit_.code or 0)
    return status, stdout.getvalue(), stderr.getvalue()


class DumpTests(unittest.TestCase):
    def _write(self, root: Path, name: str, data: bytes) -> Path:
        target = root / name
        target.write_bytes(data)
        return target

    def test_text_dump_is_default_and_shows_record_tree(self) -> None:
        body = path((0x80000002, (1, 2)), (8, (3, 4)), (5, ()), (0, ()))
        with tempfile.TemporaryDirectory() as temporary:
            target = self._write(Path(temporary), "drawing",
                                 record(0x02, body, control=2, version=12))
            status, output, errors = _run(["dump", str(target)])
        self.assertEqual(status, 0)
        self.assertEqual(errors, "")
        lines = output.splitlines()
        self.assertTrue(lines[0].startswith("ArtWorks version 12, program 'TopDraw'"))
        self.assertIn("  identifier: 'Top!'", lines)
        self.assertIn("Palette: none", lines)
        self.assertIn("List 0: @0x80 prev=+0 next=+0 (1 record)", lines)
        self.assertTrue(any(
            line.startswith("  [0] PathRecord type=0x02 (PATH) @0x88+") and
            "(visible)" in line for line in lines), output)
        self.assertIn("      path: [4 items]", lines)
        self.assertIn("        [0]: MoveElement(tag=2147483650 (0x80000002), point=(1, 2))",
                      lines)
        self.assertIn("        [3]: EndElement(tag=0)", lines)

    def test_text_dump_can_omit_header_and_shows_children(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._write(Path(temporary), "nested", nested_with_unknown())
            status, output, _ = _run(["dump", "--format", "text", "--no-header",
                                      str(target)])
        self.assertEqual(status, 0)
        self.assertNotIn("identifier:", output)
        self.assertIn("  [0] GroupRecord type=0x06 (GROUP)", output)
        self.assertIn("      child_list[0]:", output)
        self.assertIn("        [0] UnknownRecord type=0x99 (unknown)", output)
        self.assertIn("  [1] Record22Record type=0x22 (UNKNOWN_22)", output)

    def test_json_dump_is_structured(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._write(Path(temporary), "nested", nested_with_unknown())
            status, output, _ = _run(["dump", "--format", "json", str(target)])
        self.assertEqual(status, 0)
        document = json.loads(output)
        self.assertEqual(document["version"], 9)
        self.assertEqual(document["program"], "TopDraw")
        self.assertEqual(document["header"]["class"], "ArtWorksHeader")
        self.assertEqual(document["header"]["identifier"]["raw"], "546f7021")
        self.assertIsNone(document["palette"])
        root = document["record_lists"][0]["records"]
        self.assertEqual(root[0]["class"], "GroupRecord")
        self.assertEqual(root[0]["record_type"], "GROUP")
        self.assertEqual(root[0]["type_word"], 0x106)
        self.assertEqual(root[0]["unknown_values"], [10, 20, 30])
        child = root[0]["child_lists"][0]["records"][0]
        self.assertEqual(child["class"], "UnknownRecord")
        self.assertIsNone(child["record_type"])
        self.assertEqual(root[1]["class"], "Record22Record")

    def test_json_dump_can_omit_header(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._write(Path(temporary), "plain", record(0x22))
            status, output, _ = _run(["dump", "--format", "json", "--no-header",
                                      str(target)])
        self.assertEqual(status, 0)
        self.assertIsNone(json.loads(output)["header"])

    def test_dump_reports_decode_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = self._write(Path(temporary), "broken", b"Top!" + b"\0" * 140)
            status, output, errors = _run(["dump", str(target)])
        self.assertEqual(status, 2)
        self.assertEqual(output, "")
        self.assertIn("error:", errors)

    def test_dump_reports_missing_files(self) -> None:
        status, _, errors = _run(["dump", "/nonexistent/artwork"])
        self.assertEqual(status, 2)
        self.assertIn("error:", errors)


class CommandTests(unittest.TestCase):
    def test_version_is_reported(self) -> None:
        from riscos_artworks import __version__
        status, output, _ = _run(["--version"])
        self.assertEqual(status, 0)
        self.assertEqual(output.strip(), f"riscos-artworks {__version__}")

    def test_command_is_required(self) -> None:
        status, _, errors = _run([])
        self.assertEqual(status, 2)
        self.assertIn("COMMAND", errors)

    def test_audit_subcommand_runs_the_auditor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            source.mkdir()
            (source / "good").write_bytes(record(0x22))
            prefix = root / "audit"
            status, _, _ = _run(["audit", str(source), "--output", str(prefix),
                                 "--quiet"])
            self.assertEqual(status, 0)
            self.assertTrue(prefix.with_suffix(".csv").is_file())
            self.assertTrue(prefix.with_suffix(".summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
