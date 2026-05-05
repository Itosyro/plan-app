---
name: find-skills
description: Helps users discover and install agent skills when they ask questions like "how do I do X", "find a skill for X", "is there a skill that can...", or express interest in extending capabilities. This skill should be used when the user is looking for functionality that might exist as an installable skill.
---

# Find Skills

This skill helps you discover and install skills from the open agent skills ecosystem.

## When to Use This Skill

Use this skill when the user:

- Asks "how do I do X" where X might be a common task with an existing skill
- Says "find a skill for X" or "is there a skill for X"
- Asks "can you do X" where X is a specialized capability
- Expresses interest in extending agent capabilities
- Wants to search for tools, templates, or workflows
- Mentions they wish they had help with a specific domain (design, testing, deployment, etc.)
- Requests "all skills from author X" (e.g., "give me the Anthropic ones" or "install all Vercel skills")

## What is the Skills CLI?

The Skills CLI (`npx skills`) is the package manager for the open agent skills ecosystem. Skills are modular packages that extend agent capabilities with specialized knowledge, workflows, and tools.

**Key commands:**

- `npx skills find [query]` - Search for skills interactively or by keyword
- `npx skills add <package>` - Install a skill from GitHub or other sources
- `npx skills check` - Check for skill updates
- `npx skills update` - Update all installed skills

**Browse skills at:** https://skills.sh/

## Critical Workflow: User Requests "All Skills from Author X"

When the user says things like:
- "Install all skills from obra/superpowers"
- "Give me the Anthropic ones"
- "I want all the Vercel skills"
- "Download everything from anthropics/skills"

**DO NOT auto-install everything blindly.** Follow this sequence:

1. **`find-skills` step** — Run `npx skills search <author>` or browse the leaderboard to get the FULL list
2. **Present options** — Show the user the available skills with descriptions and install counts
3. **Ask for selection** — "Here are the 6 skills from obra/superpowers. Which ones do you want?" (or "All of them?" after showing the list)
4. **Install selected** — Only after user confirmation, proceed with installation

**Why this matters:** Sources like `obra/superpowers` or `anthropics/skills` each contain 10+ skills with unrelated domains. The user may only want `brainstorming` from obra but not `test-driven-development`. Showing the list prevents wasted installs and达不到 expectations.

**Pitfall to avoid:** Auto-installing all skills from a source without asking → wastes time, clutters environment, may install skills the user doesn't want.

### Example user request:

User: "…and also find me all the skills from obra/superpowers"

WRONG (skip listing):
```bash
npx skills add obra/superpowers --all --yes
```

RIGHT (discover → present → confirm):
```bash
npx skills search "obra superpowers"
# → Shows: brainstorming, systematic-debugging, test-driven-development, etc.
```

You: "Here are the 6 skills from obra/superpowers:
- brainstorming — creative exploration before coding
- systematic-debugging — root cause analysis
- test-driven-development — TDD workflow
- writing-plans — implementation planning
- requesting-code-review — pre-commit reviews
- using-superpowers — skill framework guide

Which ones do you want? I can install all or just specific ones."

## How to Help Users Find Skills

### Step 1: Understand What They Need

When a user asks for help with something, identify:

1. The domain (e.g., React, testing, design, deployment)
2. The specific task (e.g., writing tests, creating animations, reviewing PRs)
3. Whether this is a common enough task that a skill likely exists

### Step 2: Check the Leaderboard First

Before running a CLI search, check the [skills.sh leaderboard](https://skills.sh/) to see if a well-known skill already exists for the domain. The leaderboard ranks skills by total installs, surfacing the most popular and battle-tested options.

For example, top skills for web development include:
- `vercel-labs/agent-skills` — React, Next.js, web design (100K+ installs each)
- `anthropics/skills` — Frontend design, document processing (100K+ installs)

### Step 3: Search for Skills

If the leaderboard doesn't cover the user's need, run the find command:

```bash
npx skills find [query]
```

For example:

- User asks "how do I make my React app faster?" → `npx skills find react performance`
- User asks "can you help me with PR reviews?" → `npx skills find pr review`
- User asks "I need to create a changelog" → `npx skills find changelog`

### Step 4: Verify Quality Before Recommending

**Do not recommend a skill based solely on search results.** Always verify:

1. **Install count** — Prefer skills with 1K+ installs. Be cautious with anything under 100.
2. **Source reputation** — Official sources (`vercel-labs`, `anthropics`, `microsoft`) are more trustworthy than unknown authors.
3. **GitHub stars** — Check the source repository. A skill from a repo with <100 stars should be treated with skepticism.
4. **Verify the actual repo** — For skills claiming to be from official sources (e.g., `anthropics/skills`, `obra/superpowers`), manually navigate to the GitHub repo and verify the skill exists in the actual file tree. Malicious actors sometimes create repos with similar names to impersonate trusted sources.

**⚠️ PITFALL: Impersonation Risk**

Skills can be published under any name — a skill claiming to be from `anthropics` or `obra` may not actually be from them. Always verify:

1. Check the actual GitHub URL: navigate to `github.com/<owner>/<repo>/tree/main`
2. Look for the skill folder in the file tree
3. Verify the repo has many stars and recent commits from the official org
4. For anthropics/skills: check `skills/` folder for expected skills like `pdf`, `pptx`, `docx`, `xlsx`, `frontend-design`, `skill-creator`
5. For obra/superpowers: check for `brainstorming`, `writing-plans`, `systematic-debugging`, `test-driven-development`

### Step 5: Present Options to the User

When you find relevant skills, present them to the user with:

1. The skill name and what it does
2. The install count and source
3. The install command they can run
4. A link to learn more at skills.sh

Example response:

```
I found a skill that might help! The "react-best-practices" skill provides
React and Next.js performance optimization guidelines from Vercel Engineering.
(185K installs)

To install it:
npx skills add vercel-labs/agent-skills@react-best-practices

Learn more: https://skills.sh/vercel-labs/agent-skills/react-best-practices
```

### Step 6: Offer to Install

If the user wants to proceed, you can install the skill for them:

```bash
npx skills add <owner/repo@skill> -g -y
```

The `-g` flag installs globally (user-level) and `-y` skips confirmation prompts.

## Common Skill Categories

When searching, consider these common categories:

| Category        | Example Queries                          |
| --------------- | ---------------------------------------- |
| Web Development | react, nextjs, typescript, css, tailwind |
| Testing         | testing, jest, playwright, e2e           |
| DevOps          | deploy, docker, kubernetes, ci-cd        |
| Documentation   | docs, readme, changelog, api-docs        |
| Code Quality    | review, lint, refactor, best-practices     |
| Design          | ui, ux, design-system, accessibility     |
| Productivity    | workflow, automation, git                |

## Tips for Effective Searches

1. **Use specific keywords**: "react testing" is better than just "testing"
2. **Try alternative terms**: If "deploy" doesn't work, try "deployment" or "ci-cd"
3. **Check popular sources**: Many skills come from `vercel-labs/agent-skills` or `ComposioHQ/awesome-claude-skills`

## Reference Files

- `references/verified-official-skills.md` — List of verified skills from trusted sources (Anthropic, Obra, Vercel). Always cross-check when recommending skills claiming to be from these orgs.

## When No Skills Are Found

If no relevant skills exist:

1. Acknowledge that no existing skill was found
2. Offer to help with the task directly using your general capabilities
3. Suggest the user could create their own skill with `npx skills init`

Example:

```
I searched for skills related to "xyz" but didn't find any matches.
I can still help you with this task directly! Would you like me to proceed?

If this is something you do often, you could create your own skill:
npx skills init my-xyz-skill
```
