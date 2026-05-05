# Hermes Agent Backup

This repository contains the backup of my (Hermes AI) configuration, skills, and working files.

## Structure

```
HermesAi/
├── AGENTS.md           # Personal instructions (style, preferences)
├── PROJECTS.md         # Project organization rules
├── Vault/               # Obsidian-like notes vault
├── Projects/            # Active project directories
│   └── smartkey-router/ # SmartKeyRouter implementation plan
└── .hermes-backup/
    └── skills/          # All installed Hermes skills (106 total)
```

## Restoration

To restore on a fresh Hermes installation:

```bash
# 1. Clone this repo
git clone https://github.com/Itosyro/my-agent ~/HermesAi

# 2. Reinstall skills (they're already in .hermes-backup/skills/)
cp -r ~/HermesAi/.hermes-backup/skills/* ~/.hermes/skills/

# 3. Restore Hermes config (manual - contains API keys)
# Copy back your .env and credentials.json manually

# 4. Set terminal working directory
hermes config set terminal.cwd ~/HermesAi
```

## Notes

- `.env`, `credentials.json`, `sessions/` are excluded (sensitive)
- Skills can be reinstalled via: `npx skills add <repo> --skill <name>`
- Full skill list: see `.hermes-backup/skills/`

---
Created: 2026-05-05
Backup location: `/home/exedev/HermesAi`