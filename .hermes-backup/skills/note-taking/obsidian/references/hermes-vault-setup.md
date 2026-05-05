# Hermes Agent Obsidian Vault Setup

## Current Configuration

**Vault Path:** `/home/exedev/HermesAi/Vault`

**Set in:** `~/.hermes/.env`

```
OBSIDIAN_VAULT_PATH=/home/exedev/HermesAi/Vault
```

## Files Created

| File | Purpose |
|------|---------|
| `Welcome.md` | Entry point with vault overview |
| `Inbox.md` | Incoming/temporary notes |
| `Projects.md` | Active projects |

## Commands

```bash
# List vault contents
ls ~/HermesAi/Vault/

# Read a note
cat ~/HermesAi/Vault/Welcome.md

# Search notes
grep -ri "keyword" ~/HermesAi/Vault/

# Create new note
cat > ~/HermesAi/Vault/NewNote.md << 'EOF'
---
title: New Note
date: 2026-05-05
tags: []
---

# New Note

Content here.
EOF
```

## Workflow for User Requests

When user asks to "remember" something or save to "brain":
1. Ask which file/folder, or create new note
2. Use frontmatter (title, date, tags)
3. Use wikilinks `[[Note Name]]` for internal references
4. Confirm save location