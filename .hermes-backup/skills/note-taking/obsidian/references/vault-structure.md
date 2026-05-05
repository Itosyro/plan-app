# Project Structure Rules for Hermes Vault

## Requirements

User prefers:
1. **English file names only** (no Cyrillic in paths)
2. **Kebab-case** for directory and file names
3. **Structured project folders** with clear separation

## Standard Structure

```
~/HermesAi/
├── AGENTS.md          # Agent personality + fallback instructions
├── PROJECTS.md        # Project creation rules
├── Vault/             # Obsidian vault (notes, knowledge base)
├── Projects/          # Active projects (kebab-case names)
├── Archives/          # Completed projects
└── Logs/              # Session logs
```

## Rules

| Do | Don't |
|----|-------|
| `project-name/` | `Проект Название/` |
| `file-name.md` | `файл название.md` |
| `my-project/README.md` | `мой проект/читай меня.md` |

## Why This Matters

- Cross-platform compatibility (Windows has issues with Cyrillic paths)
- Easier programmatic access (no encoding issues)
- Consistency with standard development practices