---
name: socraticode-principles
description: Use when navigating an unfamiliar codebase or planning a refactor. Distils the SocratiCode approach to codebase intelligence — hybrid search, dependency graphs, blast-radius analysis — into principles you can apply with grep + rg + LSP without installing the actual tool.
---

# SocratiCode principles (lite)

[SocratiCode](https://github.com/giancarloerra/SocratiCode) is a codebase context engine: it indexes the whole repo into a hybrid semantic + BM25 search store, builds a polyglot dependency graph, and exposes the result over MCP. Their published benchmark vs grep-based exploration on a 2.45M-line codebase: **61 % fewer tokens, 84 % fewer calls, 37× faster.**

We **don't bundle SocratiCode itself** in plan-app (it's a separate VS Code extension / MCP server, AGPL-3.0). We bundle the *thinking patterns* — they apply to any agent with `rg`, `glob`, and an LSP.

---

## The three pillars

### 1. Hybrid search (semantic + keyword)

Searching only by keyword (`rg "auth"`) misses semantically related code that uses different words. Searching only by embeddings misses exact identifiers. **Always run both** and merge results in your head.

**In plan-app:**

- **Keyword first** — `rg "ENV_VAR_NAME"`, `rg "TaskHorizon"`, `rg "session_scope"`. Catches exact identifiers, decorators, error strings, constants.
- **Concept second** — describe what you're looking for in plain words, then expand: looking for "rate limiting"? Search for `rate_limit`, `throttle`, `429`, `RetryAfter`, `RateLimitError`.
- **AST-aware second** — when you find one symbol, jump with `lsp_tool goto_definition` / `goto_references` rather than greping its name. The LSP knows shadowed names, the regex doesn't.

### 2. Dependency / call graph awareness

Before changing a function, **always know who calls it.** SocratiCode answers this in milliseconds; we do it manually:

```bash
# Fan-in: who uses X?
rg -n 'split_message\(' app/ tests/

# Fan-out: what does X depend on?
rg -n '^from |^import ' app/ai/splitter.py
```

For symbol-level precision use the LSP:

```text
lsp_tool goto_references symbol="split_message" path="app/ai/splitter.py"
```

**Heuristic:** if a function has > 5 callers across > 3 files, treat any signature change as a Phase-scoped breaking change — open a separate PR, not a drive-by.

### 3. Blast-radius before edit

Before touching a model, prompt, or schema:

1. List every importer (`rg -l "from app.db.models import"` or `lsp_tool goto_references`).
2. Note which tests cover the call sites (`rg -l "split_message" tests/`).
3. Check `docs/ROADMAP.md` to see if this code is owned by another in-flight phase.
4. **Then** decide: extend in-place (small fan-in), or add v2 alongside v1 with a deprecation path (large fan-in).

---

## Plan-app cheat sheet

| Question | Recipe |
|---|---|
| "Where is X handled?" | `rg -n "X" app/` then `lsp_tool goto_definition` on best hit. |
| "What breaks if I rename foo?" | `lsp_tool goto_references` + `rg -n "foo" tests/` + `rg "foo" docs/`. |
| "How does a Telegram update flow through the system?" | Trace: `app/main.py` `telegram_webhook` → `dispatcher.feed_update` → router (start / commands / callbacks / settings / voice / text). Each router is a `create_router()` factory. |
| "Where do I add a new LLM call?" | New module under `app/ai/`, prompt in `app/ai/prompts/<name>.md`, schema in `app/ai/schemas.py`, route via `GroqKeyRouter`. Wire from `app/bot/routers/text.py:_run_pipeline`. |
| "Where does a model change need a migration?" | Always. `app/db/models.py` edits ⇒ `alembic revision --autogenerate -m "..."`. |

---

## Anti-patterns (don't do)

- **Single-shot grep then dive in.** Always do at least one keyword + one concept search before declaring you understand a feature.
- **Skipping the call graph.** "I'll just change the signature, it's only used in one place" — verify with `goto_references`, don't guess.
- **Reading 50 files before forming a hypothesis.** Build a 1-paragraph hypothesis from 3-5 files, then verify by reading the sceptical paths.

---

## When to actually install SocratiCode

If plan-app grows past ~10k LOC across multiple repos, evaluate the real thing — it's free, local, AGPL-licensed, and integrates over MCP. For now (≈3k LOC) the manual recipe above is enough.

## Source

Distilled from the SocratiCode README + benchmark blog post:

- <https://github.com/giancarloerra/SocratiCode>
- <https://themenonlab.blog/blog/socraticode-mcp-codebase-intelligence-ai-agents>

No code copied — this is a methodology summary.
