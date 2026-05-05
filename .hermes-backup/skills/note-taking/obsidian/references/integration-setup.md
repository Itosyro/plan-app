# Obsidian Integration Setup

## Quick Setup (Local Vault)

```bash
# Add to ~/.hermes/.env
OBSIDIAN_VAULT_PATH="/path/to/your/vault"
```

## Testing Access

```bash
# Should show your vault contents
ls "${OBSIDIAN_VAULT_PATH:-$HOME/Documents/Obsidian Vault}"
```

## Common Vault Locations

| OS | Default Path |
|----|--------------|
| macOS | `~/Library/Application Support/obsidian/` |
| Windows | `%APPDATA%\obsidian\` |
| Linux | `~/.config/obsidian/` |
| Custom | Check user's specific setup |

## API Key Scenarios

| Key Format | Likely Source |
|------------|---------------|
| 64-char hex | Plugin (Local REST API) or custom |
| obsidian.md token | Official cloud services |
| Empty | Local vault only — no cloud |

**Always ask user**: "Where did you get this key?" before assuming it works.