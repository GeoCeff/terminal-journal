from __future__ import annotations

import io
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta
from pathlib import Path

from terminal_journal.cli import create_entry, find_entry, load_entries, main, normalize_tags


class CliTests(unittest.TestCase):
    def test_create_entry_writes_markdown_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            now = datetime.fromisoformat("2026-06-18T21:30:00+08:00")

            entry = create_entry(
                journal_dir,
                "A useful note",
                ("work", "wins"),
                now=now,
                title="Useful",
                mood="focused",
                favorite=True,
            )

            self.assertEqual(entry.id, "2026-06-18-213000")
            self.assertTrue(entry.path.exists())
            written = entry.path.read_text(encoding="utf-8")
            self.assertIn("title: Useful", written)
            self.assertIn("mood: focused", written)
            self.assertIn("tags: work, wins", written)
            self.assertIn("favorite: true", written)

    def test_load_entries_sorts_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            create_entry(journal_dir, "Old note", (), now=datetime.fromisoformat("2026-06-17T09:00:00+08:00"))
            create_entry(journal_dir, "New note", (), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))

            entries = load_entries(journal_dir)

            self.assertEqual([entry.body for entry in entries], ["New note", "Old note"])

    def test_normalize_tags_deduplicates_and_strips_hashes(self) -> None:
        self.assertEqual(normalize_tags(["#Work", "work", "wins"]), ("work", "wins"))

    def test_search_finds_entry_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            create_entry(
                journal_dir,
                "Remember the quiet win",
                ("wins",),
                now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"),
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "search", "quiet"])

            self.assertEqual(exit_code, 0)
            self.assertIn("quiet win", stdout.getvalue())

    def test_list_filters_by_favorite_and_mood(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            create_entry(
                journal_dir,
                "Favorite note",
                ("wins",),
                now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"),
                mood="bright",
                favorite=True,
            )
            create_entry(
                journal_dir,
                "Regular note",
                ("wins",),
                now=datetime.fromisoformat("2026-06-18T10:00:00+08:00"),
                mood="tired",
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "list", "--favorites", "--mood", "bright"])

            self.assertEqual(exit_code, 0)
            self.assertIn("Favorite note", stdout.getvalue())
            self.assertNotIn("Regular note", stdout.getvalue())

    def test_edit_updates_title_and_favorite(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            entry = create_entry(journal_dir, "Draft", (), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "edit", entry.id, "--title", "Done", "--favorite"])

            edited = find_entry(journal_dir, entry.id)
            self.assertEqual(exit_code, 0)
            self.assertIsNotNone(edited)
            self.assertEqual(edited.title, "Done")
            self.assertTrue(edited.favorite)

    def test_delete_requires_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            entry = create_entry(journal_dir, "Draft", (), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "delete", entry.id])

            self.assertEqual(exit_code, 2)
            self.assertTrue(entry.path.exists())

    def test_templates_can_create_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", temp_dir, "new", "--template", "debug", "--text", "Fixed it"])

            entries = load_entries(Path(temp_dir))
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(entries), 1)
            self.assertIn("Symptom:", entries[0].body)
            self.assertIn("Fixed it", entries[0].body)

    def test_stats_counts_entries_and_words(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            create_entry(journal_dir, "Two words", ("tag",), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "stats"])

            output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Entries: 1", output)
            self.assertIn("Words: 2", output)

    def test_import_creates_entry_from_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "note.md"
            journal_dir = root / "journal"
            source.write_text("Imported body", encoding="utf-8")
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "import", str(source), "--tag", "old"])

            entries = load_entries(journal_dir)
            self.assertEqual(exit_code, 0)
            self.assertEqual(entries[0].title, "note")
            self.assertEqual(entries[0].tags, ("old",))
            self.assertEqual(entries[0].body, "Imported body")

    def test_streak_counts_consecutive_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            today = date.today()
            create_entry(journal_dir, "Today", (), now=datetime.combine(today, datetime.min.time()).astimezone())
            create_entry(
                journal_dir,
                "Yesterday",
                (),
                now=datetime.combine(today - timedelta(days=1), datetime.min.time()).astimezone(),
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "streak"])

            output = stdout.getvalue()
            self.assertEqual(exit_code, 0)
            self.assertIn("Current streak: 2 days", output)
            self.assertIn("Longest streak: 2 days", output)

    def test_random_can_pick_only_favorites(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            create_entry(journal_dir, "Boring", (), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))
            create_entry(
                journal_dir,
                "Chosen",
                (),
                now=datetime.fromisoformat("2026-06-18T10:00:00+08:00"),
                favorite=True,
            )
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "random", "--favorites"])

            self.assertEqual(exit_code, 0)
            self.assertIn("Chosen", stdout.getvalue())
            self.assertNotIn("Boring", stdout.getvalue())

    def test_list_json_outputs_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            create_entry(journal_dir, "Json note", ("api",), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "list", "--json"])

            self.assertEqual(exit_code, 0)
            self.assertIn('"body": "Json note"', stdout.getvalue())

    def test_tag_add_appends_tag(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            entry = create_entry(journal_dir, "Tagged", ("old",), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "tag", "add", entry.id, "new"])

            edited = find_entry(journal_dir, entry.id)
            self.assertEqual(exit_code, 0)
            self.assertEqual(edited.tags, ("new", "old"))

    def test_doctor_reports_valid_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            create_entry(journal_dir, "Healthy", (), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "doctor"])

            self.assertEqual(exit_code, 0)
            self.assertIn("0 problem", stdout.getvalue())

    def test_export_json_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            journal_dir = Path(temp_dir)
            create_entry(journal_dir, "Json export", (), now=datetime.fromisoformat("2026-06-18T09:00:00+08:00"))
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--dir", str(journal_dir), "export", "--format", "json"])

            self.assertEqual(exit_code, 0)
            self.assertIn('"body": "Json export"', stdout.getvalue())

    def test_show_missing_entry_returns_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            stderr = io.StringIO()

            with redirect_stderr(stderr):
                exit_code = main(["--dir", temp_dir, "show", "missing"])

            self.assertEqual(exit_code, 1)
            self.assertIn("entry not found", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
