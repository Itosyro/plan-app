#!/bin/bash
# Agent C: Blocks 6 + 7
# CLI, Logging, Hermes Integration

cd /home/exedev/HermesAi/Projects/smartkeyrouter
export PYTHONPATH="/home/exedev/HermesAi/Projects/smartkeyrouter:$PYTHONPATH"

PROMPT='You are implementing SmartKeyRouter blocks 6-7.
Project dir: /home/exedev/HermesAi/Projects/smartkeyrouter/

Wait for smartkeyrouter/router_core.py to exist. Poll every 10 seconds until it exists.

BLOCK 6: Logging + CLI

**smartkeyrouter/router_logger.py**:

```python
import logging
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
import threading

class RouterLogger:
    """Central logger for SmartKeyRouter.
    
    Writes to both file (with rotation) and stdout.
    Log format: "2025-01-15 14:23:01 [LEVEL]  [TAG]   key=value key=value"
    
    Tags: REQUEST, SUCCESS, SWITCH, DISABLED, EXHAUSTED, ERROR
    """
    def __init__(self, log_file: str = "keyrouter.log", level: str = "INFO"):
        raise NotImplementedError
    
    def log_request(self, provider: str, model: str, key_masked: str) -> None:
        raise NotImplementedError
    
    def log_success(self, provider: str, model: str, tokens: int, latency_ms: int) -> None:
        raise NotImplementedError
    
    def log_switch(self, reason: str, from_provider: str, to_provider: str, 
                   from_model: str = "", to_model: str = "", cooldown_seconds: int = 0) -> None:
        raise NotImplementedError
    
    def log_disabled(self, key_masked: str, reason: str) -> None:
        raise NotImplementedError
    
    def log_exhausted(self, switches_made: int) -> None:
        raise NotImplementedError
    
    def log_error(self, message: str) -> None:
        raise NotImplementedError
    
    def log_warning(self, message: str) -> None:
        raise NotImplementedError
    
    def log_info(self, message: str) -> None:
        raise NotImplementedError
```

Implementation:
- Use logging module with TimedRotatingFileHandler (when="midnight", backupCount=7)
- File + stdout handler
- Key always masked: first 8 + "..."
- Thread-safe (use logger's internal locking)

**smartkeyrouter/cli.py** — click-based CLI:

```python
import click
from config_loader import ConfigLoader
from router_core import RouterCore
# etc

@click.group()
def cli():
    """SmartKeyRouter CLI."""
    pass

@cli.command()
def status():
    """Show status of all providers and keys."""
    # Load config, show table with emoji status:
    # 🟢 active, 🔴 cooldown, ⚫ disabled
    # Columns: Provider | Key | Status | Cooldown | Requests
    pass

@cli.command()
@click.argument("provider_name", required=False)
def reset(provider_name):
    """Reset cooldowns for all or a specific provider."""
    pass

@cli.command()
def test():
    """Send test request through each active key."""
    # For each active key: send "Say: OK" and show result
    pass
```

Install click if needed: pip install click
Run with: python smartkeyrouter/cli.py <command>

**tests/test_logger.py**:
- Log file is created
- Keys are masked correctly
- Rotation schedule is set

BLOCK 7: Hermes Integration

**smartkeyrouter/hermes_integration.py**:

```python
"""Hermes Agent integration for SmartKeyRouter.

This module provides a drop-in replacement for direct LLM API calls,
automatically handling rate limits and key rotation.

Usage:
    from hermes_integration import get_router
    
    router = get_router()
    response = router.chat(messages=[{"role": "user", "content": "Hello"}])
    
    if response.success:
        print(response.content)
    else:
        print(f"Error: {response.error_message}")
```

Implement as singleton pattern (use threading.Lock for thread safety).
RouterCore instance created once, reused for all calls.

**smartkeyrouter/README.md**:
1. Requirements: Python 3.10+, PyYAML, requests, click
2. Installation
3. Configuration: keyrouter.yaml + .env setup
4. Quick start: how to use RouterCore
5. CLI commands reference
6. How to connect to Hermes Agent (with hermes_integration.py)
7. Troubleshooting

After all files created:
1. Test CLI: cd /home/exedev/HermesAi/Projects/smartkeyrouter && python smartkeyrouter/cli.py status
2. Run: cd /home/exedev/HermesAi/Projects/smartkeyrouter && python -m pytest tests/ -v --ignore=tests/test_integration.py
3. Update progress: python3 /home/exedev/HermesAi/Projects/smartkeyrouter/progress_tracker.py set block6 "✅" "CLI + Logging done" && python3 /home/exedev/HermesAi/Projects/smartkeyrouter/progress_tracker.py set block7 "✅" "Hermes Integration done"
4. Report completion.
'

echo "Starting Agent C (blocks 6-7)..."
hermes chat -q "$PROMPT" 2>&1 | tee /home/exedev/HermesAi/Projects/smartkeyrouter/logs/agent_c.log
echo "AGENT_C_DONE" >> /home/exedev/HermesAi/Projects/smartkeyrouter/logs/agent_done.txt
