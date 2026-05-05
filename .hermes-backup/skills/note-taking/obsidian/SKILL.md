---
name: obsidian
description: Read, search, and create notes in the Obsidian vault.
---

# Obsidian Vault

**Location:** Set via `OBSIDIAN_VAULT_PATH` environment variable (e.g. in `~/.hermes/.env`).

If unset, defaults to `~/Documents/Obsidian Vault`.

Note: Vault paths may contain spaces - always quote them.

## Read a note

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
cat "$VAULT/Note Name.md"
```

## List notes

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

# All notes
find "$VAULT" -name "*.md" -type f

# In a specific folder
ls "$VAULT/Subfolder/"
```

## Search

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"

# By filename
find "$VAULT" -name "*.md" -iname "*keyword*"

# By content
grep -rli "keyword" "$VAULT" --include="*.md"
```

## Create a note

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
cat > "$VAULT/New Note.md" << 'ENDNOTE'
# Title

Content here.
ENDNOTE
```

## Append to a note

```bash
VAULT="${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
echo "
New content here." >> "$VAULT/Existing Note.md"
```

## Wikilinks

Obsidian links notes with `[[Note Name]]` syntax. When creating notes, use these to link related content.

---

## Integration Options

### Option 1: Local Vault (Default)
Access vault files directly via filesystem. **No API key needed.**
- Set `OBSIDIAN_VAULT_PATH` in `~/.hermes/.env`
- Works with any local folder containing .md files

### Option 2: MCP Server
For cloud-based Obsidian services or remote vaults, use the `native-mcp` skill to configure an MCP server.

### Option 3: Obsidian API (rare)
Some plugins expose REST APIs. If user provides an API key:
1. Ask where they got it (which plugin/service)
2. Check if it's obsidian-sync, obsidian-publish, or a plugin
3. Configure accordingly

⚠️ **Pitfall**: Users often confuse local vault access with cloud API keys. If they provide a 64-char hex key, clarify the source before assuming it works.

---

## Using with Hermes Memory

To use Obsidian as Hermes's "second brain":
1. Set `OBSIDIAN_VAULT_PATH` to your vault location
2. Use the vault for long-term knowledge storage
3. Reference notes via wikilinks in conversations

## Creating a New Vault (No Existing Vault)

If user has no existing Obsidian vault:

1. **Create the vault folder:**
   ```bash
   mkdir -p ~/HermesAi/Vault
   ```

2. **Create starter notes** (use obsidian-markdown skill for syntax):
   - `Welcome.md` — entry point with vault overview
   - `Inbox.md` — for incoming/temporary notes
   - `Projects.md` — for active projects

3. **Configure Hermes:**
   ```bash
   echo "OBSIDIAN_VAULT_PATH=/home/exedev/HermesAi/Vault" >> ~/.hermes/.env
   ```

4. **Test access:**
   ```bash
   ls "$OBSIDIAN_VAULT_PATH"
   ```

⚠️ **Pitfall**: Don't try to download Obsidian app — it's not needed! Obsidian is just a local folder with .md files. The app is only for human editing, not API access.

⚠️ **Pitfall**: Users may provide "API keys" from their Obsidian desktop app settings. These are usually for cloud sync/publish, not needed for local vault access. Always clarify what service the key is for.
