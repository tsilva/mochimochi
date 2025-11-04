<div align="center">

# 🍡 mochi-mochi

<img src="logo.png" alt="mochi-mochi logo" width="200">

**CLI tool for curating [Mochi](https://mochi.cards/) flashcard decks**

Curate high-quality flashcards with local-first workflow: edit in markdown, find duplicates with AI, track changes with git. Your local files are the source of truth.

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

</div>

---

## 🚀 Quick Start

```bash
# 1. Install (takes 5 seconds)
uv tool install git+https://github.com/tsilva/mochi-mochi.git

# 2. First run will ask for your API key
mochi-mochi decks

# 3. Pull a deck to curate
mochi-mochi pull abc123xyz
# Creates: your-deck-name-abc123xyz.md

# 4. Clean up duplicates with AI
mochi-mochi dedupe your-deck-name-abc123xyz.md

# 5. Edit cards however you want
vim your-deck-name-abc123xyz.md

# 6. Push your curated deck back to Mochi
mochi-mochi push your-deck-name-abc123xyz.md
```

That's it! Your deck is now curated and synced. 🎉

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

**Requirements:** Python 3.8+ • `requests>=2.25.0` • `openai>=1.0.0` (for dedupe)

---

## 🔑 Configuration

On first run, you'll be prompted for your Mochi API key (get it from [settings](https://app.mochi.cards/settings)). It's saved to `~/.mochi-mochi/config` automatically.

**Optional:** For the `dedupe` command, you'll also need an OpenAI API key (get it from [platform.openai.com](https://platform.openai.com/api-keys)). You'll be prompted when first running `dedupe`.

Manual config file format:
```bash
mkdir -p ~/.mochi-mochi
cat > ~/.mochi-mochi/config << EOF
MOCHI_API_KEY=your_mochi_key_here
OPENAI_API_KEY=your_openai_key_here
EOF
```

---

## 💻 Usage

**Curation Workflow:** Pull → Dedupe → Edit → Commit → Push

### 🔍 Find and Remove Duplicates

```bash
mochi-mochi dedupe <deck-file>.md                 # Find semantic duplicates
mochi-mochi dedupe <deck-file>.md --threshold 0.9 # Stricter matching
```

Uses OpenAI embeddings to find semantically similar cards. Interactive prompt lets you choose which to keep. Requires `OPENAI_API_KEY` in config (prompted on first use).

### 🔄 Sync Operations

```bash
mochi-mochi decks                        # List all decks
mochi-mochi pull <deck_id>               # Download deck to <name>-<id>.md
mochi-mochi push <deck-file>.md          # Sync changes to Mochi
mochi-mochi push <deck-file>.md --force  # Push without duplicate detection
```

### 📚 Managing Multiple Decks

```bash
mkdir ~/my-flashcards && cd ~/my-flashcards && git init
mochi-mochi pull abc123 && mochi-mochi pull def456
git add . && git commit -m "Initial decks"
# Dedupe, edit, commit, then push individual decks as needed
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

**Star this repo if it helps you build better flashcard decks! ⭐**

**[Report Bug](https://github.com/tsilva/mochi-mochi/issues)** • **[Request Feature](https://github.com/tsilva/mochi-mochi/issues)**
