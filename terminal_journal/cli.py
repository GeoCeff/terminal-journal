from __future__ import annotations

import argparse
import calendar
import getpass
import hashlib
import hmac
import html
import json
import os
import random
import re
import shutil
import subprocess
import sys
import webbrowser
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path


DEFAULT_JOURNAL_DIR = "journal"
CONFIG_FILE = ".terminal-journal.json"
CUSTOM_TEMPLATES_FILE = ".terminal-journal-templates.json"
ID_FORMAT = "%Y-%m-%d-%H%M%S"
DATE_FORMAT = "%Y-%m-%d"

THEMES = {
    "plain": {
        "accent": "",
        "muted": "",
        "good": "",
        "warn": "",
        "reset": "",
        "entry": "*",
        "star": "[*]",
        "empty": "-",
        "prompt": ">",
    },
    "cutesy": {
        "accent": "\033[95m",
        "muted": "\033[90m",
        "good": "\033[92m",
        "warn": "\033[93m",
        "reset": "\033[0m",
        "entry": "o",
        "star": "<3",
        "empty": ".",
        "prompt": "~",
    },
    "techy": {
        "accent": "\033[96m",
        "muted": "\033[90m",
        "good": "\033[92m",
        "warn": "\033[91m",
        "reset": "\033[0m",
        "entry": ">",
        "star": "[!]",
        "empty": "-",
        "prompt": "$",
    },
}

TEMPLATES = {
    "daily": "Today I noticed:\n\nWins:\n\nChallenges:\n\nTomorrow I want to:",
    "gratitude": "I am grateful for:\n\nA small good thing:\n\nSomeone I appreciate:",
    "retro": "What worked:\n\nWhat felt stuck:\n\nWhat I learned:\n\nNext experiment:",
    "debug": "Symptom:\n\nHypothesis:\n\nWhat I tried:\n\nResult:\n\nNext step:",
}

PROMPTS = [
    "What is one thing worth remembering from today?",
    "What felt lighter than expected?",
    "What did you learn, fix, ship, or survive?",
    "What would future-you want a note about?",
    "Where did your attention go today?",
]


@dataclass(frozen=True)
class Entry:
    id: str
    created: str
    tags: tuple[str, ...]
    body: str
    path: Path
    title: str = ""
    mood: str = ""
    favorite: bool = False


def supports_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def config_path() -> Path:
    return Path(CONFIG_FILE)


def custom_templates_path() -> Path:
    return Path(CUSTOM_TEMPLATES_FILE)


def all_templates() -> dict[str, str]:
    return TEMPLATES | read_json(custom_templates_path(), {})


def style(args: argparse.Namespace, key: str, text: str) -> str:
    theme = THEMES.get(getattr(args, "theme", "plain"), THEMES["plain"])
    color = theme.get(key, "")
    reset = theme.get("reset", "")
    if not color or not supports_color():
        return text
    return f"{color}{text}{reset}"


def symbol(args: argparse.Namespace, key: str) -> str:
    theme = THEMES.get(getattr(args, "theme", "plain"), THEMES["plain"])
    return theme.get(key, THEMES["plain"][key])


def normalize_tags(tags: list[str] | None) -> tuple[str, ...]:
    if not tags:
        return ()

    normalized: list[str] = []
    for tag in tags:
        clean = tag.strip().lower().lstrip("#")
        if not clean:
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", clean):
            raise ValueError(f"Invalid tag: {tag!r}")
        if clean not in normalized:
            normalized.append(clean)
    return tuple(normalized)


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid date: {value!r}. Use YYYY-MM-DD.") from exc


def entry_path(journal_dir: Path, entry_id: str) -> Path:
    return journal_dir / f"{entry_id}.md"


def create_entry(
    journal_dir: Path,
    body: str,
    tags: tuple[str, ...],
    now: datetime | None = None,
    title: str = "",
    mood: str = "",
    favorite: bool = False,
) -> Entry:
    body = body.strip()
    if not body:
        raise ValueError("Entry text cannot be empty.")

    timestamp = now or datetime.now().astimezone()
    entry_id = timestamp.strftime(ID_FORMAT)
    path = entry_path(journal_dir, entry_id)
    suffix = 1
    while path.exists():
        entry_id = f"{timestamp.strftime(ID_FORMAT)}-{suffix}"
        path = entry_path(journal_dir, entry_id)
        suffix += 1

    created = timestamp.isoformat(timespec="seconds")
    entry = Entry(entry_id, created, tags, body, path, title.strip(), mood.strip(), favorite)
    journal_dir.mkdir(parents=True, exist_ok=True)
    write_entry(path, format_entry(entry))
    return entry


def format_entry(entry: Entry) -> str:
    metadata = {
        "id": entry.id,
        "created": entry.created,
        "title": entry.title,
        "mood": entry.mood,
        "tags": ", ".join(entry.tags),
        "favorite": "true" if entry.favorite else "false",
    }
    lines = ["---"]
    for key, value in metadata.items():
        lines.append(f"{key}: {value}")
    lines.extend(["---", "", entry.body.strip(), ""])
    return "\n".join(lines)


def parse_entry(path: Path) -> Entry:
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"Entry cannot be read: {path}") from exc
    if not raw.startswith("---\n"):
        raise ValueError(f"Entry is missing metadata: {path}")

    try:
        _, metadata, body = raw.split("---\n", 2)
    except ValueError as exc:
        raise ValueError(f"Entry metadata is incomplete: {path}") from exc

    values: dict[str, str] = {}
    for line in metadata.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        values[key.strip()] = value.strip()

    entry_id = values.get("id") or path.stem
    created = values.get("created") or ""
    try:
        date.fromisoformat(created[:10])
    except ValueError as exc:
        raise ValueError(f"Entry has invalid created date: {path}") from exc
    tags = tuple(tag.strip() for tag in values.get("tags", "").split(",") if tag.strip())
    favorite = values.get("favorite", "false").lower() in {"1", "true", "yes", "y"}
    return Entry(
        entry_id,
        created,
        tags,
        body.strip(),
        path,
        title=values.get("title", ""),
        mood=values.get("mood", ""),
        favorite=favorite,
    )


def save_entry(entry: Entry) -> None:
    write_entry(entry.path, format_entry(entry))


def write_entry(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def load_entries(journal_dir: Path, strict: bool = True) -> list[Entry]:
    if not journal_dir.exists():
        return []

    entries = []
    for path in journal_dir.glob("*.md"):
        try:
            entries.append(parse_entry(path))
        except ValueError:
            if strict:
                raise
    return sorted(entries, key=lambda entry: entry.created, reverse=True)


def find_entry(journal_dir: Path, entry_id: str) -> Entry | None:
    direct = entry_path(journal_dir, entry_id)
    if direct.exists():
        return parse_entry(direct)

    matches = [entry for entry in load_entries(journal_dir, strict=False) if entry.id.startswith(entry_id)]
    if len(matches) == 1:
        return matches[0]
    return None


def filter_entries(
    entries: list[Entry],
    tag: str | None = None,
    mood: str | None = None,
    since: str | None = None,
    until: str | None = None,
    favorites_only: bool = False,
) -> list[Entry]:
    if tag:
        wanted = normalize_tags([tag])[0]
        entries = [entry for entry in entries if wanted in entry.tags]
    if mood:
        entries = [entry for entry in entries if entry.mood.lower() == mood.lower()]
    if since:
        entries = [entry for entry in entries if entry.created[:10] >= since]
    if until:
        entries = [entry for entry in entries if entry.created[:10] <= until]
    if favorites_only:
        entries = [entry for entry in entries if entry.favorite]
    return entries


def entry_summary(entry: Entry, args: argparse.Namespace) -> str:
    marker = symbol(args, "star") if entry.favorite else symbol(args, "entry")
    tags = f" #{' #'.join(entry.tags)}" if entry.tags else ""
    mood = f" mood:{entry.mood}" if entry.mood else ""
    title = f" {entry.title} -" if entry.title else ""
    first_line = entry.body.splitlines()[0] if entry.body else ""
    return f"{marker} {entry.id} {entry.created}{tags}{mood}{title} {first_line}".strip()


def read_text_from_args(args: argparse.Namespace) -> str:
    if args.template:
        base = all_templates()[args.template]
        if args.text:
            return f"{base}\n\n{args.text}"
        return base
    if args.text is not None:
        return args.text
    if not sys.stdin.isatty():
        return sys.stdin.read()
    prompt = prompt_for_today()
    print(f"{symbol(args, 'prompt')} {prompt}")
    print("Write your entry. Finish with Ctrl+Z then Enter on Windows, or Ctrl+D on macOS/Linux.")
    return sys.stdin.read()


def prompt_for_today() -> str:
    day_index = date.today().toordinal() % len(PROMPTS)
    return PROMPTS[day_index]


def command_new(args: argparse.Namespace) -> int:
    try:
        tags = normalize_tags(args.tag)
        body = read_text_from_args(args)
        entry = create_entry(args.dir, body, tags, title=args.title, mood=args.mood, favorite=args.favorite)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(style(args, "good", f"Created {entry.id} at {entry.path}"))
    return 0


def command_list(args: argparse.Namespace) -> int:
    try:
        entries = filter_entries(
            load_entries(args.dir, strict=False),
            tag=args.tag,
            mood=args.mood,
            since=normalize_date(args.since),
            until=normalize_date(args.until),
            favorites_only=args.favorites,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.limit:
        entries = entries[: args.limit]

    if not entries:
        print(f"{symbol(args, 'empty')} No entries found.")
        return 0

    if args.json:
        print(json.dumps([entry_to_dict(entry) for entry in entries], indent=2))
        return 0

    for entry in entries:
        print(entry_summary(entry, args))
    return 0


def entry_to_dict(entry: Entry) -> dict[str, object]:
    return {
        "id": entry.id,
        "created": entry.created,
        "title": entry.title,
        "mood": entry.mood,
        "tags": list(entry.tags),
        "favorite": entry.favorite,
        "body": entry.body,
        "path": str(entry.path),
    }


def command_today(args: argparse.Namespace) -> int:
    today = date.today().isoformat()
    args.since = today
    args.until = today
    return command_list(args)


def command_show(args: argparse.Namespace) -> int:
    entry = find_entry(args.dir, args.entry_id)
    if not entry:
        print(f"error: entry not found: {args.entry_id}", file=sys.stderr)
        return 1

    tags = f"Tags: {', '.join(entry.tags)}" if entry.tags else "Tags: none"
    mood = f"Mood: {entry.mood}" if entry.mood else "Mood: none"
    favorite = f"Favorite: {'yes' if entry.favorite else 'no'}"
    title = f"{entry.title}\n" if entry.title else ""
    print(
        style(args, "accent", f"{title}{entry.id}")
        + f"\nCreated: {entry.created}\n{tags}\n{mood}\n{favorite}\n\n{entry.body}"
    )
    return 0


def command_search(args: argparse.Namespace) -> int:
    try:
        entries = filter_entries(load_entries(args.dir, strict=False), tag=args.tag, mood=args.mood)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    query = args.query.lower()
    matches = [
        entry
        for entry in entries
        if query in entry.body.lower()
        or query in entry.created.lower()
        or query in entry.title.lower()
        or query in entry.mood.lower()
        or query in " ".join(entry.tags)
    ]

    if not matches:
        print(f"{symbol(args, 'empty')} No matches found.")
        return 0

    for entry in matches:
        line = entry_summary(entry, args)
        if args.highlight:
            line = re.sub(re.escape(args.query), lambda match: f"[{match.group(0)}]", line, flags=re.IGNORECASE)
        print(line)
    return 0


def command_random(args: argparse.Namespace) -> int:
    entries = filter_entries(load_entries(args.dir, strict=False), favorites_only=args.favorites)
    if not entries:
        print(f"{symbol(args, 'empty')} No entries found.")
        return 0

    print(entry_summary(random.choice(entries), args))
    return 0


def command_on_this_day(args: argparse.Namespace) -> int:
    today_key = date.today().strftime("%m-%d")
    matches = [entry for entry in load_entries(args.dir, strict=False) if entry.created[5:10] == today_key]
    if not matches:
        print(f"{symbol(args, 'empty')} No entries found for this day.")
        return 0

    for entry in matches:
        print(entry_summary(entry, args))
    return 0


def command_edit(args: argparse.Namespace) -> int:
    entry = find_entry(args.dir, args.entry_id)
    if not entry:
        print(f"error: entry not found: {args.entry_id}", file=sys.stderr)
        return 1

    if args.editor:
        editor = args.editor if isinstance(args.editor, str) else os.environ.get("EDITOR") or "notepad"
        try:
            return subprocess.call([editor, str(entry.path)])
        except OSError as exc:
            print(f"error: could not launch editor: {exc}", file=sys.stderr)
            return 1

    updates = {}
    if args.title is not None:
        updates["title"] = args.title.strip()
    if args.mood is not None:
        updates["mood"] = args.mood.strip()
    if args.text is not None:
        updates["body"] = args.text.strip()
    if args.tag is not None:
        updates["tags"] = normalize_tags(args.tag)
    if args.favorite:
        updates["favorite"] = True
    if args.unfavorite:
        updates["favorite"] = False

    if not updates:
        print("No changes requested.")
        return 0

    edited = replace(entry, **updates)
    save_entry(edited)
    print(style(args, "good", f"Updated {edited.id}"))
    return 0


def command_delete(args: argparse.Namespace) -> int:
    entry = find_entry(args.dir, args.entry_id)
    if not entry:
        print(f"error: entry not found: {args.entry_id}", file=sys.stderr)
        return 1

    if not args.yes:
        print(f"Refusing to delete {entry.id} without --yes.")
        return 2

    entry.path.unlink()
    print(style(args, "warn", f"Deleted {entry.id}"))
    return 0


def command_tag(args: argparse.Namespace) -> int:
    entry = find_entry(args.dir, args.entry_id)
    if not entry:
        print(f"error: entry not found: {args.entry_id}", file=sys.stderr)
        return 1

    tags = set(entry.tags)
    changed = normalize_tags(args.tag)
    if args.action == "add":
        tags.update(changed)
    else:
        tags.difference_update(changed)
    save_entry(replace(entry, tags=tuple(sorted(tags))))
    print(f"Tags: {', '.join(sorted(tags)) if tags else 'none'}")
    return 0


def command_tags(args: argparse.Namespace) -> int:
    counts: dict[str, int] = {}
    for entry in load_entries(args.dir, strict=False):
        for tag in entry.tags:
            counts[tag] = counts.get(tag, 0) + 1

    if not counts:
        print(f"{symbol(args, 'empty')} No tags found.")
        return 0

    for tag, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"#{tag} {count}")
    return 0


def command_moods(args: argparse.Namespace) -> int:
    counts: dict[str, int] = {}
    for entry in load_entries(args.dir, strict=False):
        if entry.mood:
            counts[entry.mood] = counts.get(entry.mood, 0) + 1

    if not counts:
        print(f"{symbol(args, 'empty')} No moods found.")
        return 0

    for mood, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"{mood} {count}")
    return 0


def command_stats(args: argparse.Namespace) -> int:
    since = f"{args.year:04d}-01-01" if args.year else None
    until = f"{args.year:04d}-12-31" if args.year else None
    if args.month:
        year = args.year or date.today().year
        since = f"{year:04d}-{args.month:02d}-01"
        until = f"{year:04d}-{args.month:02d}-{calendar.monthrange(year, args.month)[1]:02d}"
    entries = filter_entries(load_entries(args.dir, strict=False), since=since, until=until)
    words = sum(len(entry.body.split()) for entry in entries)
    favorites = sum(1 for entry in entries if entry.favorite)
    tag_count = len({tag for entry in entries for tag in entry.tags})
    mood_count = len({entry.mood for entry in entries if entry.mood})

    print(style(args, "accent", "Journal Stats"))
    print(f"Entries: {len(entries)}")
    print(f"Words: {words}")
    print(f"Favorites: {favorites}")
    print(f"Unique tags: {tag_count}")
    print(f"Unique moods: {mood_count}")
    if entries:
        print(f"Newest: {entries[0].created}")
        print(f"Oldest: {entries[-1].created}")
    return 0


def command_mood_trend(args: argparse.Namespace) -> int:
    buckets: dict[str, dict[str, int]] = {}
    for entry in load_entries(args.dir, strict=False):
        if not entry.mood:
            continue
        key = entry.created[:7] if args.by == "month" else entry.created[:10]
        buckets.setdefault(key, {})[entry.mood] = buckets.setdefault(key, {}).get(entry.mood, 0) + 1
    for key in sorted(buckets):
        moods = ", ".join(f"{mood}:{count}" for mood, count in sorted(buckets[key].items()))
        print(f"{key} {moods}")
    return 0


def entry_dates(entries: list[Entry]) -> set[date]:
    days = set()
    for entry in entries:
        try:
            days.add(date.fromisoformat(entry.created[:10]))
        except ValueError:
            pass
    return days


def command_streak(args: argparse.Namespace) -> int:
    days = entry_dates(load_entries(args.dir, strict=False))
    today = date.today()
    current = 0
    cursor = today
    while cursor in days:
        current += 1
        cursor -= timedelta(days=1)

    longest = 0
    run = 0
    previous = None
    for day in sorted(days):
        run = run + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day

    print(f"Current streak: {current} day{'s' if current != 1 else ''}")
    print(f"Longest streak: {longest} day{'s' if longest != 1 else ''}")
    return 0


def command_calendar(args: argparse.Namespace) -> int:
    try:
        year = args.year or date.today().year
        month = args.month or date.today().month
        counts: dict[int, int] = {}
        for entry in load_entries(args.dir, strict=False):
            created = date.fromisoformat(entry.created[:10])
            if created.year == year and created.month == month:
                counts[created.day] = counts.get(created.day, 0) + 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(style(args, "accent", calendar.month_name[month] + f" {year}"))
    print("Mo Tu We Th Fr Sa Su")
    for week in calendar.monthcalendar(year, month):
        cells = []
        for day in week:
            if day == 0:
                cells.append("  ")
            elif day in counts:
                cell = f"{day:02d}" if not args.heatmap else f"{day:02d}{min(counts[day], 9)}"
                cells.append(style(args, "good", cell))
            else:
                cells.append(f"{day:02d}")
        print(" ".join(cells))
    return 0


def command_prompt(args: argparse.Namespace) -> int:
    print(prompt_for_today())
    return 0


def command_templates(args: argparse.Namespace) -> int:
    templates = all_templates()
    if args.action == "add":
        if not args.name or args.text is None:
            print("error: templates add needs NAME and TEXT", file=sys.stderr)
            return 2
        templates[args.name] = args.text
        custom = read_json(custom_templates_path(), {})
        custom[args.name] = args.text
        write_json(custom_templates_path(), custom)
    elif args.action == "delete":
        if not args.name:
            print("error: templates delete needs NAME", file=sys.stderr)
            return 2
        custom = read_json(custom_templates_path(), {})
        custom.pop(args.name, None)
        write_json(custom_templates_path(), custom)

    for name, template in templates.items():
        preview = template.splitlines()[0]
        print(f"{name}: {preview}")
    return 0


def command_export(args: argparse.Namespace) -> int:
    entries = list(reversed(load_entries(args.dir, strict=False)))
    output = args.output
    if args.format == "json":
        content = json.dumps([entry_to_dict(entry) for entry in entries], indent=2) + "\n"
    elif args.format == "html":
        content = "<!doctype html><meta charset='utf-8'><title>Journal Export</title><h1>Journal Export</h1>"
        for entry in entries:
            content += f"<article><h2>{html.escape(entry.created)} {html.escape(entry.title)}</h2><pre>{html.escape(entry.body)}</pre></article>"
    else:
        content = export_markdown(entries)

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"Exported {len(entries)} entries to {output}")
    else:
        print(content, end="")
    return 0


def export_markdown(entries: list[Entry]) -> str:
    lines = ["# Journal Export", ""]

    for entry in entries:
        pieces = [entry.created]
        if entry.title:
            pieces.append(entry.title)
        if entry.mood:
            pieces.append(f"Mood: {entry.mood}")
        if entry.tags:
            pieces.append(f"Tags: {', '.join(entry.tags)}")
        if entry.favorite:
            pieces.append("Favorite")
        lines.extend([f"## {' | '.join(pieces)}", "", entry.body, ""])

    return "\n".join(lines).strip() + "\n"


def command_import(args: argparse.Namespace) -> int:
    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1
    if args.folder and not args.input.is_dir():
        print(f"error: --folder needs a directory: {args.input}", file=sys.stderr)
        return 2

    try:
        tags = normalize_tags(args.tag)
        files = sorted(path for path in args.input.rglob("*") if path.is_file()) if args.folder else [args.input]
        for path in files:
            body = path.read_text(encoding="utf-8")
            create_entry(args.dir, body, tags, title=args.title or path.stem, mood=args.mood)
    except (UnicodeDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(style(args, "good", f"Imported {len(files)} file(s)"))
    return 0


def command_backup(args: argparse.Namespace) -> int:
    if not args.dir.exists():
        print("error: journal directory does not exist", file=sys.stderr)
        return 1
    if not args.dir.is_dir():
        print("error: journal path is not a directory", file=sys.stderr)
        return 2

    destination = args.output or Path(f"{args.dir.name}-backup-{datetime.now().strftime(ID_FORMAT)}")
    if destination.exists():
        print(f"error: backup destination already exists: {destination}", file=sys.stderr)
        return 2

    shutil.copytree(args.dir, destination)
    print(style(args, "good", f"Backed up {args.dir} to {destination}"))
    return 0


def command_restore(args: argparse.Namespace) -> int:
    if not args.input.exists():
        print(f"error: backup not found: {args.input}", file=sys.stderr)
        return 1
    if not args.input.is_dir():
        print(f"error: backup is not a directory: {args.input}", file=sys.stderr)
        return 2
    if args.dir.exists() and any(args.dir.iterdir()) and not args.yes:
        print("Refusing to restore over a non-empty journal without --yes.")
        return 2
    if args.dir.exists():
        shutil.rmtree(args.dir)
    shutil.copytree(args.input, args.dir)
    print(f"Restored {args.input} to {args.dir}")
    return 0


def command_archive(args: argparse.Namespace) -> int:
    if not args.before:
        print("Refusing to archive without --before YYYY-MM-DD.")
        return 2
    try:
        before = normalize_date(args.before)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    archive_dir = args.output or args.dir / "archive"
    moved = 0
    for entry in load_entries(args.dir, strict=False):
        if entry.created[:10] >= before:
            continue
        target = archive_dir / entry.created[:4] / entry.path.name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(entry.path), target)
        moved += 1
    print(f"Archived {moved} entries to {archive_dir}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    broken = 0
    for path in args.dir.glob("*.md"):
        try:
            parse_entry(path)
        except ValueError as exc:
            broken += 1
            print(f"{path}: {exc}")
    print(f"Checked {len(list(args.dir.glob('*.md')))} entries, {broken} problem(s).")
    return 1 if broken else 0


def command_init(args: argparse.Namespace) -> int:
    args.dir.mkdir(parents=True, exist_ok=True)
    cfg = read_json(config_path(), {})
    cfg.setdefault("journal_dir", str(args.dir))
    cfg.setdefault("theme", args.theme)
    write_json(config_path(), cfg)
    print(f"Initialized {args.dir}")
    return 0


def command_config(args: argparse.Namespace) -> int:
    cfg = read_json(config_path(), {})
    if args.key:
        if args.value is None:
            print("error: config set needs KEY and VALUE", file=sys.stderr)
            return 2
        cfg[args.key] = args.value
        write_json(config_path(), cfg)
    print(json.dumps(cfg, indent=2))
    return 0


def command_todo(args: argparse.Namespace) -> int:
    pattern = re.compile(r"^\s*[-*]\s+\[( |x)\]\s+(.*)", re.IGNORECASE)
    for entry in load_entries(args.dir, strict=False):
        for line in entry.body.splitlines():
            match = pattern.match(line)
            if match and (args.all or match.group(1) == " "):
                print(f"{entry.id} {'done' if match.group(1).lower() == 'x' else 'todo'} - {match.group(2)}")
    return 0


def command_sync(args: argparse.Namespace) -> int:
    try:
        subprocess.check_call(["git", "add", str(args.dir)])
        if not subprocess.check_output(["git", "status", "--porcelain", "--", str(args.dir)]).strip():
            print("No journal changes to sync.")
            return 0
        subprocess.check_call(["git", "commit", "-m", args.message])
        subprocess.check_call(["git", "push"])
        return 0
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"error: git sync failed: {exc}", file=sys.stderr)
        return 1


def command_web(args: argparse.Namespace) -> int:
    output = args.output or Path("journal.html")
    args.output = output
    args.format = "html"
    command_export(args)
    webbrowser.open(output.resolve().as_uri())
    return 0


def command_remind(args: argparse.Namespace) -> int:
    print(f"Reminder: run `journal new` at {args.time}. Use your OS scheduler for recurring reminders.")
    return 0


def kdf(passphrase: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode(), salt, 200_000, dklen=32)


def xor_crypt(data: bytes, key: bytes) -> bytes:
    out = bytearray()
    for block, offset in enumerate(range(0, len(data), 32)):
        # ponytail: HMAC stream is fine for local file privacy; use a vetted crypto lib if this becomes a real secret store.
        stream = hmac.new(key, block.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(byte ^ stream[i] for i, byte in enumerate(data[offset : offset + 32]))
    return bytes(out)


def command_encrypt(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1
    passphrase = getpass.getpass("Passphrase: ")
    salt = os.urandom(16)
    data = args.input.read_bytes()
    key = kdf(passphrase, salt)
    cipher = xor_crypt(data, key)
    tag = hmac.new(key, cipher, hashlib.sha256).digest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(b"TJ1" + salt + tag + cipher)
    print(f"Encrypted {args.input} to {args.output}")
    return 0


def command_decrypt(args: argparse.Namespace) -> int:
    if not args.input.is_file():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1
    passphrase = getpass.getpass("Passphrase: ")
    blob = args.input.read_bytes()
    if not blob.startswith(b"TJ1") or len(blob) < 51:
        print("error: not a terminal-journal encrypted file", file=sys.stderr)
        return 2
    salt, tag, cipher = blob[3:19], blob[19:51], blob[51:]
    key = kdf(passphrase, salt)
    if not hmac.compare_digest(tag, hmac.new(key, cipher, hashlib.sha256).digest()):
        print("error: wrong passphrase or corrupt file", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(xor_crypt(cipher, key))
    print(f"Decrypted {args.input} to {args.output}")
    return 0


def add_filter_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--tag", help="Only include entries with this tag.")
    parser.add_argument("--mood", help="Only include entries with this mood.")
    parser.add_argument("--since", help="Only include entries on or after YYYY-MM-DD.")
    parser.add_argument("--until", help="Only include entries on or before YYYY-MM-DD.")
    parser.add_argument("--favorites", action="store_true", help="Only include starred entries.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write and review local Markdown journal entries.")
    parser.add_argument("--dir", type=Path, default=Path(DEFAULT_JOURNAL_DIR), help="Journal directory.")
    parser.add_argument("--theme", choices=sorted(THEMES), default="plain", help="Output theme.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    new_parser = subparsers.add_parser("new", help="Create a new journal entry.")
    new_parser.add_argument("--text", help="Entry text. Reads stdin when omitted.")
    new_parser.add_argument("--title", default="", help="Short title for the entry.")
    new_parser.add_argument("--mood", default="", help="Mood label, such as calm, tired, or focused.")
    new_parser.add_argument("--tag", action="append", help="Tag to add. Can be used more than once.")
    new_parser.add_argument("--favorite", action="store_true", help="Star this entry.")
    new_parser.add_argument("--template", choices=sorted(all_templates()), help="Start from a built-in template.")
    new_parser.set_defaults(func=command_new)

    list_parser = subparsers.add_parser("list", help="List recent entries.")
    add_filter_arguments(list_parser)
    list_parser.add_argument("--limit", type=int, help="Maximum number of entries to show.")
    list_parser.add_argument("--json", action="store_true", help="Print entries as JSON.")
    list_parser.set_defaults(func=command_list)

    today_parser = subparsers.add_parser("today", help="List entries from today.")
    add_filter_arguments(today_parser)
    today_parser.add_argument("--limit", type=int, help="Maximum number of entries to show.")
    today_parser.set_defaults(func=command_today)

    show_parser = subparsers.add_parser("show", help="Show one entry. Prefix IDs are accepted.")
    show_parser.add_argument("entry_id")
    show_parser.set_defaults(func=command_show)

    search_parser = subparsers.add_parser("search", help="Search entry text, dates, tags, titles, and moods.")
    search_parser.add_argument("query")
    search_parser.add_argument("--tag", help="Only search entries with this tag.")
    search_parser.add_argument("--mood", help="Only search entries with this mood.")
    search_parser.add_argument("--highlight", action="store_true", help="Bracket matching search terms.")
    search_parser.set_defaults(func=command_search)

    random_parser = subparsers.add_parser("random", help="Show a random entry.")
    random_parser.add_argument("--favorites", action="store_true", help="Only pick from starred entries.")
    random_parser.set_defaults(func=command_random)

    on_this_day_parser = subparsers.add_parser("on-this-day", help="Show entries written on today's month/day.")
    on_this_day_parser.set_defaults(func=command_on_this_day)

    edit_parser = subparsers.add_parser("edit", help="Update entry metadata or replace body text.")
    edit_parser.add_argument("entry_id")
    edit_parser.add_argument("--text", help="Replacement entry text.")
    edit_parser.add_argument("--title", help="Replacement title.")
    edit_parser.add_argument("--mood", help="Replacement mood.")
    edit_parser.add_argument("--tag", action="append", help="Replacement tag. Can be used more than once.")
    edit_parser.add_argument("--editor", nargs="?", const=True, help="Open the raw entry file in an editor.")
    favorite_group = edit_parser.add_mutually_exclusive_group()
    favorite_group.add_argument("--favorite", action="store_true", help="Star this entry.")
    favorite_group.add_argument("--unfavorite", action="store_true", help="Remove this entry's star.")
    edit_parser.set_defaults(func=command_edit)

    delete_parser = subparsers.add_parser("delete", help="Delete one entry.")
    delete_parser.add_argument("entry_id")
    delete_parser.add_argument("--yes", action="store_true", help="Confirm deletion.")
    delete_parser.set_defaults(func=command_delete)

    tag_parser = subparsers.add_parser("tag", help="Add or remove tags on one entry.")
    tag_parser.add_argument("action", choices=["add", "remove"])
    tag_parser.add_argument("entry_id")
    tag_parser.add_argument("tag", nargs="+")
    tag_parser.set_defaults(func=command_tag)

    export_parser = subparsers.add_parser("export", help="Export entries to Markdown.")
    export_parser.add_argument("--output", type=Path, help="Output Markdown file. Prints to stdout when omitted.")
    export_parser.add_argument("--format", choices=["markdown", "json", "html"], default="markdown")
    export_parser.set_defaults(func=command_export)

    import_parser = subparsers.add_parser("import", help="Import a text or Markdown file as a new entry.")
    import_parser.add_argument("input", type=Path)
    import_parser.add_argument("--title", help="Entry title. Defaults to the input file name.")
    import_parser.add_argument("--mood", default="", help="Mood label.")
    import_parser.add_argument("--tag", action="append", help="Tag to add. Can be used more than once.")
    import_parser.add_argument("--folder", action="store_true", help="Import every file under the input folder.")
    import_parser.set_defaults(func=command_import)

    backup_parser = subparsers.add_parser("backup", help="Copy the journal folder to a backup folder.")
    backup_parser.add_argument("--output", type=Path, help="Backup directory.")
    backup_parser.set_defaults(func=command_backup)

    restore_parser = subparsers.add_parser("restore", help="Restore a backup folder into the journal folder.")
    restore_parser.add_argument("input", type=Path)
    restore_parser.add_argument("--yes", action="store_true", help="Allow replacing a non-empty journal.")
    restore_parser.set_defaults(func=command_restore)

    archive_parser = subparsers.add_parser("archive", help="Move old entries into an archive folder.")
    archive_parser.add_argument("--before", help="Archive entries before YYYY-MM-DD.")
    archive_parser.add_argument("--output", type=Path, help="Archive directory.")
    archive_parser.set_defaults(func=command_archive)

    tags_parser = subparsers.add_parser("tags", help="Show tag counts.")
    tags_parser.set_defaults(func=command_tags)

    moods_parser = subparsers.add_parser("moods", help="Show mood counts.")
    moods_parser.set_defaults(func=command_moods)

    stats_parser = subparsers.add_parser("stats", help="Show journal stats.")
    stats_parser.add_argument("--year", type=int)
    stats_parser.add_argument("--month", type=int, choices=range(1, 13))
    stats_parser.set_defaults(func=command_stats)

    mood_trend_parser = subparsers.add_parser("mood-trend", help="Show mood counts by day or month.")
    mood_trend_parser.add_argument("--by", choices=["day", "month"], default="month")
    mood_trend_parser.set_defaults(func=command_mood_trend)

    streak_parser = subparsers.add_parser("streak", help="Show current and longest daily writing streaks.")
    streak_parser.set_defaults(func=command_streak)

    calendar_parser = subparsers.add_parser("calendar", help="Show a month view with entry days highlighted.")
    calendar_parser.add_argument("--year", type=int, help="Calendar year.")
    calendar_parser.add_argument("--month", type=int, choices=range(1, 13), help="Calendar month.")
    calendar_parser.add_argument("--heatmap", action="store_true", help="Append entry count intensity to days.")
    calendar_parser.set_defaults(func=command_calendar)

    prompt_parser = subparsers.add_parser("prompt", help="Show today's journaling prompt.")
    prompt_parser.set_defaults(func=command_prompt)

    templates_parser = subparsers.add_parser("templates", help="List, add, or delete templates.")
    templates_parser.add_argument("action", nargs="?", choices=["list", "add", "delete"], default="list")
    templates_parser.add_argument("name", nargs="?")
    templates_parser.add_argument("text", nargs="?")
    templates_parser.set_defaults(func=command_templates)

    doctor_parser = subparsers.add_parser("doctor", help="Validate journal entry files.")
    doctor_parser.set_defaults(func=command_doctor)

    init_parser = subparsers.add_parser("init", help="Create the journal folder and local config.")
    init_parser.set_defaults(func=command_init)

    config_parser = subparsers.add_parser("config", help="Show or set local defaults.")
    config_parser.add_argument("key", nargs="?")
    config_parser.add_argument("value", nargs="?")
    config_parser.set_defaults(func=command_config)

    todo_parser = subparsers.add_parser("todo", help="Extract Markdown task items from entries.")
    todo_parser.add_argument("--all", action="store_true", help="Include completed tasks.")
    todo_parser.set_defaults(func=command_todo)

    sync_parser = subparsers.add_parser("sync", help="Git add, commit, and push the journal folder.")
    sync_parser.add_argument("--message", default="Update journal")
    sync_parser.set_defaults(func=command_sync)

    web_parser = subparsers.add_parser("web", help="Export HTML and open it in a browser.")
    web_parser.add_argument("--output", type=Path)
    web_parser.set_defaults(func=command_web)

    remind_parser = subparsers.add_parser("remind", help="Print a reminder command for OS schedulers.")
    remind_parser.add_argument("--time", default="20:00")
    remind_parser.set_defaults(func=command_remind)

    encrypt_parser = subparsers.add_parser("encrypt", help="Encrypt one file with a passphrase.")
    encrypt_parser.add_argument("input", type=Path)
    encrypt_parser.add_argument("output", type=Path)
    encrypt_parser.set_defaults(func=command_encrypt)

    decrypt_parser = subparsers.add_parser("decrypt", help="Decrypt one encrypted file with a passphrase.")
    decrypt_parser.add_argument("input", type=Path)
    decrypt_parser.add_argument("output", type=Path)
    decrypt_parser.set_defaults(func=command_decrypt)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    cfg = read_json(config_path(), {})
    if args.dir == Path(DEFAULT_JOURNAL_DIR) and cfg.get("journal_dir"):
        args.dir = Path(cfg["journal_dir"])
    if args.theme == "plain" and cfg.get("theme"):
        args.theme = cfg["theme"]
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
