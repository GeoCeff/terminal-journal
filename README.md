# Terminal Journal

A minimal terminal-based journal for writing, organizing, and reviewing notes from the command line.

Terminal Journal is intended to be a small productivity tool for fast daily logging without opening a full notes app. It keeps the workflow lightweight and beginner-friendly while leaving room for search, tags, exports, themes, and richer review tools.

## Features

- Create timestamped Markdown journal entries.
- Store entries locally in a simple `journal/` folder.
- Add titles, moods, tags, and favorites to entries.
- Start entries from built-in templates.
- List, show, search, edit, and delete entries from the terminal.
- Filter entries by tag, mood, date range, or favorites.
- View tag counts, mood counts, stats, and a monthly calendar.
- Review a random entry, today's historical entries, and writing streaks.
- Import existing text or Markdown files as entries.
- Export all entries into one Markdown file for backup or review.
- Export Markdown, JSON, or HTML.
- Back up, restore, archive, validate, and Git-sync the raw journal folder.
- Extract Markdown todos from entries.
- Open a simple HTML journal view in a browser.
- Encrypt and decrypt single files with a passphrase.
- Switch output themes with `plain`, `cutesy`, or `techy`.

## Quick Start

```powershell
python -m pip install -e .
journal --theme cutesy new --title "Tiny win" --mood focused --text "Shipped the first version." --tag work --tag wins --favorite
journal --theme techy list --favorites
journal search shipped
journal stats
journal streak
journal random --favorites
journal calendar
journal export --output journal-export.md
```

By default, entries are stored in `./journal`. You can choose a different folder with `--dir`:

```powershell
journal --dir C:\Users\You\Documents\MyJournal new --text "Private entry"
```

## Commands

```text
journal init
journal config [KEY VALUE]
journal new [--text TEXT] [--title TITLE] [--mood MOOD] [--tag TAG] [--favorite] [--template NAME]
journal list [--tag TAG] [--mood MOOD] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--favorites] [--limit N] [--json]
journal today
journal show ENTRY_ID
journal search QUERY [--tag TAG] [--mood MOOD] [--highlight]
journal random [--favorites]
journal on-this-day
journal edit ENTRY_ID [--text TEXT] [--title TITLE] [--mood MOOD] [--tag TAG] [--favorite | --unfavorite] [--editor [EDITOR]]
journal tag add|remove ENTRY_ID TAG...
journal delete ENTRY_ID --yes
journal tags
journal moods
journal mood-trend [--by day|month]
journal stats [--year YYYY] [--month M]
journal streak
journal calendar [--year YYYY] [--month M] [--heatmap]
journal prompt
journal templates [list|add|delete] [NAME] [TEXT]
journal export [--format markdown|json|html] [--output FILE]
journal import FILE_OR_FOLDER [--folder] [--title TITLE] [--mood MOOD] [--tag TAG]
journal backup [--output DIR]
journal restore DIR [--yes]
journal archive [--before YYYY-MM-DD] [--output DIR]
journal doctor
journal todo [--all]
journal sync [--message MESSAGE]
journal web [--output FILE]
journal remind [--time HH:MM]
journal encrypt INPUT OUTPUT
journal decrypt INPUT OUTPUT
```

If `journal new` is run without `--text`, it reads the entry body from standard input.

Entry IDs can be shortened when they match only one entry:

```powershell
journal show 2026-06-18
```

## Themes

Use `--theme` before the command:

```powershell
journal --theme cutesy list
journal --theme techy stats
```

The themes are dependency-free ANSI terminal styles:

- `plain`: clean and script-friendly.
- `cutesy`: softer colors and playful symbols.
- `techy`: sharper colors and command-line flavored symbols.

## Templates

```powershell
journal templates
journal templates add standup "Yesterday:\nToday:\nBlocked:"
journal new --template daily
journal new --template debug --tag engineering
```

Built-in templates: `daily`, `gratitude`, `retro`, and `debug`.

## Storage Format

Each entry is a Markdown file with lightweight metadata:

```markdown
---
id: 2026-06-18-213000
created: 2026-06-18T21:30:00+08:00
title: Tiny win
mood: focused
tags: work, wins
favorite: true
---

Shipped the first version.
```

## Development

```powershell
python -m pip install -e .
python -m unittest discover -s tests
```

## Roadmap

- Add fuzzy search and highlighted search terms.
- Publish packaging instructions once the CLI is stable.

## License

Add a license before sharing or publishing reusable code from this repository.
