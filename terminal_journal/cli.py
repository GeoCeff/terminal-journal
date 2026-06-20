from __future__ import annotations

import argparse
import calendar
import os
import random
import re
import shutil
import sys
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path


DEFAULT_JOURNAL_DIR = "journal"
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
    path.write_text(format_entry(entry), encoding="utf-8")
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
    raw = path.read_text(encoding="utf-8")
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
    entry.path.write_text(format_entry(entry), encoding="utf-8")


def load_entries(journal_dir: Path) -> list[Entry]:
    if not journal_dir.exists():
        return []

    entries = [parse_entry(path) for path in journal_dir.glob("*.md")]
    return sorted(entries, key=lambda entry: entry.created, reverse=True)


def find_entry(journal_dir: Path, entry_id: str) -> Entry | None:
    direct = entry_path(journal_dir, entry_id)
    if direct.exists():
        return parse_entry(direct)

    matches = [entry for entry in load_entries(journal_dir) if entry.id.startswith(entry_id)]
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
        base = TEMPLATES[args.template]
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
            load_entries(args.dir),
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

    for entry in entries:
        print(entry_summary(entry, args))
    return 0


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
        entries = filter_entries(load_entries(args.dir), tag=args.tag, mood=args.mood)
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
        print(entry_summary(entry, args))
    return 0


def command_random(args: argparse.Namespace) -> int:
    entries = filter_entries(load_entries(args.dir), favorites_only=args.favorites)
    if not entries:
        print(f"{symbol(args, 'empty')} No entries found.")
        return 0

    print(entry_summary(random.choice(entries), args))
    return 0


def command_on_this_day(args: argparse.Namespace) -> int:
    today_key = date.today().strftime("%m-%d")
    matches = [entry for entry in load_entries(args.dir) if entry.created[5:10] == today_key]
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


def command_tags(args: argparse.Namespace) -> int:
    counts: dict[str, int] = {}
    for entry in load_entries(args.dir):
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
    for entry in load_entries(args.dir):
        if entry.mood:
            counts[entry.mood] = counts.get(entry.mood, 0) + 1

    if not counts:
        print(f"{symbol(args, 'empty')} No moods found.")
        return 0

    for mood, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        print(f"{mood} {count}")
    return 0


def command_stats(args: argparse.Namespace) -> int:
    entries = load_entries(args.dir)
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


def entry_dates(entries: list[Entry]) -> set[date]:
    days = set()
    for entry in entries:
        try:
            days.add(date.fromisoformat(entry.created[:10]))
        except ValueError:
            pass
    return days


def command_streak(args: argparse.Namespace) -> int:
    days = entry_dates(load_entries(args.dir))
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
        for entry in load_entries(args.dir):
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
                cells.append(style(args, "good", f"{day:02d}"))
            else:
                cells.append(f"{day:02d}")
        print(" ".join(cells))
    return 0


def command_prompt(args: argparse.Namespace) -> int:
    print(prompt_for_today())
    return 0


def command_templates(args: argparse.Namespace) -> int:
    for name, template in TEMPLATES.items():
        preview = template.splitlines()[0]
        print(f"{name}: {preview}")
    return 0


def command_export(args: argparse.Namespace) -> int:
    entries = list(reversed(load_entries(args.dir)))
    output = args.output
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

    content = "\n".join(lines).strip() + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content, encoding="utf-8")
        print(f"Exported {len(entries)} entries to {output}")
    else:
        print(content, end="")
    return 0


def command_import(args: argparse.Namespace) -> int:
    if not args.input.exists():
        print(f"error: input file not found: {args.input}", file=sys.stderr)
        return 1

    try:
        body = args.input.read_text(encoding="utf-8")
        tags = normalize_tags(args.tag)
        entry = create_entry(args.dir, body, tags, title=args.title or args.input.stem, mood=args.mood)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(style(args, "good", f"Imported {args.input} as {entry.id}"))
    return 0


def command_backup(args: argparse.Namespace) -> int:
    if not args.dir.exists():
        print("error: journal directory does not exist", file=sys.stderr)
        return 1

    destination = args.output or Path(f"{args.dir.name}-backup-{datetime.now().strftime(ID_FORMAT)}")
    if destination.exists():
        print(f"error: backup destination already exists: {destination}", file=sys.stderr)
        return 2

    shutil.copytree(args.dir, destination)
    print(style(args, "good", f"Backed up {args.dir} to {destination}"))
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
    new_parser.add_argument("--template", choices=sorted(TEMPLATES), help="Start from a built-in template.")
    new_parser.set_defaults(func=command_new)

    list_parser = subparsers.add_parser("list", help="List recent entries.")
    add_filter_arguments(list_parser)
    list_parser.add_argument("--limit", type=int, help="Maximum number of entries to show.")
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
    favorite_group = edit_parser.add_mutually_exclusive_group()
    favorite_group.add_argument("--favorite", action="store_true", help="Star this entry.")
    favorite_group.add_argument("--unfavorite", action="store_true", help="Remove this entry's star.")
    edit_parser.set_defaults(func=command_edit)

    delete_parser = subparsers.add_parser("delete", help="Delete one entry.")
    delete_parser.add_argument("entry_id")
    delete_parser.add_argument("--yes", action="store_true", help="Confirm deletion.")
    delete_parser.set_defaults(func=command_delete)

    export_parser = subparsers.add_parser("export", help="Export entries to Markdown.")
    export_parser.add_argument("--output", type=Path, help="Output Markdown file. Prints to stdout when omitted.")
    export_parser.set_defaults(func=command_export)

    import_parser = subparsers.add_parser("import", help="Import a text or Markdown file as a new entry.")
    import_parser.add_argument("input", type=Path)
    import_parser.add_argument("--title", help="Entry title. Defaults to the input file name.")
    import_parser.add_argument("--mood", default="", help="Mood label.")
    import_parser.add_argument("--tag", action="append", help="Tag to add. Can be used more than once.")
    import_parser.set_defaults(func=command_import)

    backup_parser = subparsers.add_parser("backup", help="Copy the journal folder to a backup folder.")
    backup_parser.add_argument("--output", type=Path, help="Backup directory.")
    backup_parser.set_defaults(func=command_backup)

    tags_parser = subparsers.add_parser("tags", help="Show tag counts.")
    tags_parser.set_defaults(func=command_tags)

    moods_parser = subparsers.add_parser("moods", help="Show mood counts.")
    moods_parser.set_defaults(func=command_moods)

    stats_parser = subparsers.add_parser("stats", help="Show journal stats.")
    stats_parser.set_defaults(func=command_stats)

    streak_parser = subparsers.add_parser("streak", help="Show current and longest daily writing streaks.")
    streak_parser.set_defaults(func=command_streak)

    calendar_parser = subparsers.add_parser("calendar", help="Show a month view with entry days highlighted.")
    calendar_parser.add_argument("--year", type=int, help="Calendar year.")
    calendar_parser.add_argument("--month", type=int, choices=range(1, 13), help="Calendar month.")
    calendar_parser.set_defaults(func=command_calendar)

    prompt_parser = subparsers.add_parser("prompt", help="Show today's journaling prompt.")
    prompt_parser.set_defaults(func=command_prompt)

    templates_parser = subparsers.add_parser("templates", help="List built-in templates.")
    templates_parser.set_defaults(func=command_templates)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
