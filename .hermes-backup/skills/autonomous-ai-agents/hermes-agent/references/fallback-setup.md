# Fallback / SmartKeyRouter Setup

## Overview

This reference covers how to configure automatic fallback between models when rate limits (429) are hit, using Hermes' built-in credential pool system.

## Commands

```bash
hermes auth add              # Add new API key interactively
hermes auth list             # Show all keys and exhaustion status  
hermes auth remove <PROVIDER> <INDEX>  # Remove key by provider + index
hermes auth reset <PROVIDER>          # Reset exhaustion status after refill
```

## How It Works

```
Provider → Model → 429 Error → Auto-fallback to next available key/provider
```

The system tries next key in the pool, then falls back to alternate providers.

## Common Issues

### After 3 retries still getting 429

1. Check pools exist: `hermes auth list`
2. Verify model isn't pinned in config
3. Add fallback model in config.yaml

### Context lost after fallback

Ensure `agent.max_turns` is set high enough (>40) to preserve conversation across provider switches.

## Configuration

```yaml
# config.yaml - Example structure
credential_pool_strategies:
  openrouter: fill_first  # or round_robin
  
fallback_providers: []
# Add fallback providers here if needed
```

## Key Signals

| Situation | Action |
|-----------|--------|
| Single key 429s | Add more keys to pool via `hermes auth add` |
| All keys exhausted | Use `hermes auth reset` after refill, or switch provider |
| Context lost | Increase `agent.max_turns` in config |
| Fallback not triggering | Check `fallback_providers` list is populated |