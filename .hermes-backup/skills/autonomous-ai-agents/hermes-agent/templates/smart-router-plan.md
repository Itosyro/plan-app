# SmartKeyRouter Concept Plan

## Overview

Future enhancement to Hermes' existing credential pool system.

## Current System (Already Works)

`hermes auth add` → adds to pool → auto-fallback on 429

## Proposed Features

| Phase | Feature | Command |
|-------|---------|---------|
| 1 | Multi-key pool per provider | `hermes auth add --provider openrouter --key2` |
| 2 | Dashboard | `hermes router status` |
| 3 | CSV bulk import | `hermes router import keys.csv` |
| 4 | Cross-provider fallback | Config in `fallback_providers` |
| 5 | Cost-aware routing | `hermes router set --cost-priority` |
| 6 | Circuit breaker | Auto-disable failed keys |

## Notes for Future Implementation

- This is a concept document, not yet implemented
- Current workaround: Add keys sequentially via `hermes auth add`