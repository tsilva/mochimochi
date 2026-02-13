<div align="center">

<img src="logo.png" alt="mochi-mochi" width="512"/>

# mochi-mochi

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/tsilva/mochi-mochi)](https://github.com/tsilva/mochi-mochi/issues)

**🍡 Local-first CLI for curating [Mochi](https://mochi.cards/) flashcard decks with AI-powered deduplication and quality grading ✨**

[Installation](#installation) · [Quick Start](#quick-start) · [Commands](#commands) · [Report Bug](https://github.com/tsilva/mochi-mochi/issues)

</div>

---

## Features

- **Local-first workflow** — Your markdown files are the source of truth, track changes with git
- **AI deduplication** — Find semantically similar cards using embeddings, interactively choose which to keep
- **Quality grading** — LLM-powered card quality scoring with automatic improvement suggestions
- **Bidirectional sync** — Push local changes or sync deletions from Mochi
- **Multi-deck support** — Manage all your decks in one git repository
- **Batch operations** — Push, sync, dedupe, or curate all decks at once

---

## Installation

```bash
# Install with uv (recommended)
uv tool install git+https://github.com/tsilva/mochi-mochi.git

# Update
uv tool upgrade mochi-mochi

# Uninstall
uv tool uninstall mochi-mochi
```

**Requirements:** Python 3.10+

---

## Quick Start

```bash
# First run prompts for your Mochi API key
mochi-mochi decks

# Pull a deck to edit locally
mochi-mochi pull abc123xyz
# Creates: deck-your-deck-name-abc123xyz.md

# Find and remove duplicates with AI
mochi-mochi dedupe deck-your-deck-name-abc123xyz.md

# Grade and improve card quality
mochi-mochi curate deck-your-deck-name-abc123xyz.md

# Push changes back to Mochi
mochi-mochi push deck-your-deck-name-abc123xyz.md
```

---

## Commands

| Command | Description |
|---------|-------------|
| `decks` | List all available decks |
| `pull <deck_id>` | Download deck from Mochi |
| `push [file]` | One-way sync: local → remote |
| `sync [file]` | Bidirectional sync (handles remote deletions) |
| `dedupe [file]` | Find semantic duplicates with AI |
| `curate [file]` | Grade and improve card quality |

Omit `[file]` to operate on all `deck-*.md` files in the current directory.

### Options

```bash
# Dedupe with stricter matching
mochi-mochi dedupe deck.md --threshold 0.9

# Curate with higher quality bar
mochi-mochi curate deck.md --threshold 9

# Push without duplicate detection
mochi-mochi push deck.md --force
```

---

## Card Format

Cards are markdown with YAML frontmatter:

```markdown
---
card_id: abc123
tags: ["python", "basics"]
---
What is a list comprehension?
---
A concise way to create lists: [x for x in iterable]
---
card_id: null
---
New card question
---
New card answer
```

**Fields:**
- `card_id` — Mochi ID (`null` for new cards)
- `tags` — JSON array (optional)
- `archived` — Set to `true` to archive (optional)

---

## Configuration

API keys are stored in `~/.mochi-mochi/config` and prompted on first use:

| Key | Required For | Get From |
|-----|--------------|----------|
| `MOCHI_API_KEY` | All commands | [mochi.cards/settings](https://app.mochi.cards/settings) |
| `OPENAI_API_KEY` | `dedupe` | [platform.openai.com](https://platform.openai.com/api-keys) |
| `OPENROUTER_API_KEY` | `dedupe`, `curate` | [openrouter.ai/keys](https://openrouter.ai/keys) |

---

## Recommended Workflow

```bash
# Create a dedicated repository for your decks
mkdir ~/mochi-decks && cd ~/mochi-decks && git init

# Pull your decks
mochi-mochi pull abc123
mochi-mochi pull def456

# Commit initial state
git add . && git commit -m "Initial decks"

# Daily workflow
vim deck-python-abc123.md          # Edit cards
mochi-mochi dedupe deck-python-abc123.md  # Remove duplicates
mochi-mochi curate deck-python-abc123.md  # Improve quality
git diff                           # Review changes
git commit -am "Curate python deck"
mochi-mochi push deck-python-abc123.md    # Sync to Mochi
```

---

## License

MIT — see [LICENSE](LICENSE)

---

**Prompted by tsilva** · **Assembled by LLM agents**

If this helps you build better flashcard decks, please star the repo!
