<div align="center">

# 🍡 mochi-mochi

<img src="logo.png" alt="mochi-mochi logo" width="200">

### Your flashcards, your way. Local-first sync for [Mochi Cards](https://mochi.cards/)

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

**Edit in markdown • Sync to Mochi • Review anywhere**

[Quick Start](#-quick-start) • [Features](#-what-makes-it-special) • [Installation](#-installation) • [Documentation](#-usage)

</div>

---

## 🎯 What is this?

An **unofficial** CLI tool that brings your [Mochi Cards](https://mochi.cards/) flashcards to your local machine. Think "git for flashcards" – edit in your favorite text editor, track changes with git, and sync when you're ready.

> **💡 Local = source of truth, Mochi = review platform**

## ✨ What makes it special?

<table>
<tr>
<td width="50%">

### 🧠 For Learners
- ✍️ Edit cards in your favorite editor (VS Code, Vim, whatever!)
- 🔄 Version control with git (see exactly what changed)
- 📁 Organize multiple decks as simple files
- 🔒 Keep private study notes in your repo
- ⚡ Work offline, sync when ready

</td>
<td width="50%">

### 🤖 For Builders
- 🔧 Build automation pipelines
- 🎯 Find inaccurate/redundant cards
- 🤖 Use LLMs and agents for curation
- 📊 Analyze card quality at scale
- 🛠️ Apply custom transformations

</td>
</tr>
</table>

**The secret sauce?** Your cards are just markdown files. That means you can use *any tool* – scripts, AI, bulk editing, you name it – to work with them. Then push to Mochi for spaced repetition.

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

### First-Time Setup (Easy Mode)

Just run any command! The tool will guide you:

```bash
mochi-mochi decks

# 🤔 Mochi API key not found.
# 🔗 Get your API key from: https://app.mochi.cards/settings
#
# 🔑 Enter your Mochi API key: [paste here]
#
# ✅ API key saved to ~/.mochi-mochi/config
```

Your key is saved at `~/.mochi-mochi/config` and used for all future commands.

### Manual Setup (Pro Mode)

Create the config file yourself:

```bash
mkdir -p ~/.mochi-mochi
cat > ~/.mochi-mochi/config << EOF
MOCHI_API_KEY=your_api_key_here
EOF
```

---

## 💻 Usage

### The Workflow

```
📚 List decks → 📥 Pull → ✏️  Edit → 💾 Commit → 📤 Push → 🔄 Repeat
```

### Commands

<table>
<tr>
<td width="40%"><strong>📚 List all your decks</strong></td>
<td width="60%">

```bash
mochi-mochi decks
```

</td>
</tr>
<tr>
<td><strong>📥 Pull a deck locally</strong></td>
<td>

```bash
mochi-mochi pull <deck_id>
```

</td>
</tr>
<tr>
<td><strong>📤 Push changes to Mochi</strong></td>
<td>

```bash
mochi-mochi push <deck-file>.md
```

</td>
</tr>
<tr>
<td><strong>⚡ Push without duplicate check</strong></td>
<td>

```bash
mochi-mochi push <deck-file>.md --force
```

</td>
</tr>
</table>

### Pro Tips

<details>
<summary>🎯 <strong>Managing Multiple Decks</strong></summary>

```bash
# Create a dedicated repo for all your decks
mkdir ~/my-flashcards && cd ~/my-flashcards
git init

# Pull multiple decks
mochi-mochi pull abc123  # Creates: python-basics-abc123.md
mochi-mochi pull def456  # Creates: javascript-def456.md

# Track everything in git
git add .
git commit -m "Initial decks"

# Edit, commit, and push individual decks
vim python-basics-abc123.md
git commit -am "Add list comprehension examples"
mochi-mochi push python-basics-abc123.md
```

</details>

<details>
<summary>🤖 <strong>Using as a Python Library</strong></summary>

```python
from main import get_decks, pull, push, get_cards, create_card

# Fetch all decks
decks = get_decks()

# Pull deck to file
pull("abc123xyz")  # Creates <deck-name>-abc123xyz.md

# Push changes
push("python-basics-abc123.md")

# Direct API operations
cards = get_cards("abc123xyz")
card = create_card("abc123xyz", content="Q: What is Python?\n---\nA: A programming language.")
```

</details>

---

## 📝 Card Format

### How Cards Look Locally

Each deck is a markdown file with frontmatter:

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
tags: ["python"]
---
What is a dictionary?
---
A key-value data structure in Python
```

### What Each Field Means

| Field | Description |
|-------|-------------|
| `card_id` | Mochi's unique ID (or `null` for new cards) |
| `tags` | JSON array of tags (optional) |
| `archived` | Set to `true` to archive (optional, omitted if false) |

### Sync Behavior

- ✅ Cards with IDs → **updated** in Mochi
- ➕ Cards with `card_id: null` → **created** as new
- 🔍 Duplicate detection prevents copies (use `--force` to bypass)

---




## 📄 License

See [LICENSE](LICENSE) file for details.

---

## 👤 Author

Prompted by **tsilva** ⚡ Assembled by LLM agents 😮‍💨

---

<div align="center">

**Star this repo if it helps your learning! ⭐**

[Report Bug](https://github.com/tsilva/mochi-mochi/issues) • [Request Feature](https://github.com/tsilva/mochi-mochi/issues)

</div>
