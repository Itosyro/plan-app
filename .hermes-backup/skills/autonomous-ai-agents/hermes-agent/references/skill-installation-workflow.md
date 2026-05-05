# Skill Installation Workflow

## How `npx skills add` actually works

**Critical discovery:** When you install a skill via `npx --yes skills add <url> --skill <name> --yes --global`, it installs to:

```
~/.agents/skills/<skill-name>/SKILL.md
```

NOT to `~/.hermes/skills/`. This is a common source of confusion.

## Correct workflow to add a skill

```bash
# Step 1: Install via npx
npx --yes skills add https://github.com/anthropics/skills --skill frontend-design --yes --global

# Step 2: Copy to Hermes skills directory
mkdir -p ~/.hermes/skills/<category>/<skill-name>
cp -r ~/.agents/skills/<skill-name>/* ~/.hermes/skills/<category>/<skill-name>/

# Step 3: Verify it's visible
hermes skills list | grep <skill-name>
```

## Why skills don't appear in `skills_list` tool

The `skills_list` tool only shows skills with explicit `category` in their frontmatter OR in a properly-named subdirectory. However, `hermes skills list` (CLI) shows ALL installed skills.

## Quick verification commands

```bash
ls ~/.agents/skills/           # where skills actually live
hermes skills list | grep X   # check visibility
```

## GitHub repos — actual contents

| Repo | Skills |
|------|--------|
| `anthropics/skills` | frontend-design, skill-creator, pdf, pptx, docx, xlsx (only 6) |
| `obra/superpowers` | brainstorming, writing-plans, systematic-debugging, TDD, code-review, using-superpowers |
| `forrestchang/andrej-karpathy-skills` | karpathy-guidelines |

## Skill frontmatter minimum

```yaml
---
name: skill-name
description: What it does
---
```

Skills without category won't show in `skills_list` filtered by category, but ARE visible in `hermes skills list`.