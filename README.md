# 🍡 mochi-mochi

<img src="logo.png" alt="mochi-mochi logo" width="200">

**Unofficial CLI tool for local-first [Mochi Cards](https://mochi.cards/) sync**

Edit flashcards in markdown, track with git, sync to Mochi. Your local files are the source of truth.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

---

## 🚀 Quick Start

```bash
# 1. Install (takes 5 seconds)
uv tool install git+https://github.com/tsilva/mochi-mochi.git

# 2. First run will ask for your API key
mochi-mochi decks

# 3. Pull a deck to work with
mochi-mochi pull abc123xyz
# Creates: your-deck-name-abc123xyz.md

# 4. Edit the file however you want
vim your-deck-name-abc123xyz.md

# 5. Push changes back to Mochi
mochi-mochi push your-deck-name-abc123xyz.md
```

That's it! 🎉

---

## 📦 Installation

```bash
# Install
uv tool install git+https://github.com/tsilva/mochi-mochi.git

# Update
uv tool upgrade mochi-mochi

# Uninstall
uv tool uninstall mochi-mochi
```

**Requirements:** Python 3.8+ • `requests>=2.25.0`

---

## 🔑 Configuration

On first run, you'll be prompted for your Mochi API key (get it from [settings](https://app.mochi.cards/settings)). It's saved to `~/.mochi-mochi/config` automatically.

Or create the config manually:
```bash
mkdir -p ~/.mochi-mochi
echo "MOCHI_API_KEY=your_api_key_here" > ~/.mochi-mochi/config
```

---

## 💻 Usage

**Workflow:** List decks → Pull → Edit → Commit → Push

```bash
mochi-mochi decks                        # List all decks
mochi-mochi pull <deck_id>               # Download deck to <name>-<id>.md
mochi-mochi push <deck-file>.md          # Sync changes to Mochi
mochi-mochi push <deck-file>.md --force  # Push without duplicate detection
```

**Managing multiple decks:**
```bash
mkdir ~/my-flashcards && cd ~/my-flashcards && git init
mochi-mochi pull abc123 && mochi-mochi pull def456
git add . && git commit -m "Initial decks"
# Edit files, commit, then push individual decks as needed
```

---

## 📝 Card Format

Cards are markdown with frontmatter, separated by `---`:

```markdown
---
card_id: abc123
tags: ["python", "basics"]
---
What is a list comprehension?
---
A concise way to create lists in Python using [x for x in iterable]
---
card_id: null
---
What is a dictionary?
---
A key-value data structure
```

**Frontmatter fields:**
- `card_id`: Mochi ID (`null` for new cards)
- `tags`: JSON array (optional)
- `archived`: Set to `true` to archive (optional)

**Sync behavior:**
- Existing cards (with IDs) are updated
- New cards (`card_id: null`) are created
- Duplicate detection prevents copies (use `--force` to bypass)

## 📄 License

MIT - see [LICENSE](LICENSE) file

---

## 👤 Author

Prompted by **tsilva** ⚡ Assembled by LLM agents 😮‍💨

---

**Star this repo if it helps your learning! ⭐**

**[Report Bug](https://github.com/tsilva/mochi-mochi/issues)** • **[Request Feature](https://github.com/tsilva/mochi-mochi/issues)**
