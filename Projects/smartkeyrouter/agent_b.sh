#!/bin/bash
# Agent B: Blocks 4 + 5
# ContextAdapter, RouterCore, ProviderRegistry

cd /home/exedev/HermesAi/Projects/smartkeyrouter
export PYTHONPATH="/home/exedev/HermesAi/Projects/smartkeyrouter:$PYTHONPATH"

PROMPT='You are implementing SmartKeyRouter blocks 4-5.
Project dir: /home/exedev/HermesAi/Projects/smartkeyrouter/

Wait for file smartkeyrouter/config_loader.py to exist before starting.
If it does not exist yet, wait 10 seconds then check again. Keep waiting until it exists.

BLOCK 4: context_adapter.py

**smartkeyrouter/context_adapter.py**:

```python
"""Context adapter — prepares conversation context for target model limits."""

class ContextAdapter:
    def __init__(self, global_settings):
        self._settings = global_settings
    
    def prepare_context(
        self,
        messages: list[dict],
        target_context_limit: int,
        strategy: str = "truncate_middle",
        reserve_for_response: int = 2048
    ) -> list[dict]:
        """Main method. Returns messages ready for target model.
        
        strategy: truncate_middle / truncate_oldest / error
        """
        raise NotImplementedError
    
    def count_tokens_approximate(self, messages: list[dict]) -> int:
        """Approximate token count. Formula: len(text) / 3.5 * 1.1 (10% buffer)"""
        raise NotImplementedError
    
    def _truncate_middle(self, messages: list[dict], target_limit: int) -> list[dict]:
        """Remove messages from middle. Keep: system prompt + last 4 messages."""
        raise NotImplementedError
    
    def _truncate_oldest(self, messages: list[dict], target_limit: int) -> list[dict]:
        """Remove oldest messages. Keep: system prompt."""
        raise NotImplementedError
    
    def convert_tool_calls(
        self,
        messages: list[dict],
        target_provider: str
    ) -> list[dict]:
        """Convert tool_calls format for target provider.
        If provider does not support tool_calls in history,
        convert to text: "[tool: name, result: ...]"
        """
        raise NotImplementedError
```

Implementation rules:
- find the system prompt: first message with role="system"
- _truncate_middle: always keep system prompt + last 4 messages; remove from middle
- _truncate_oldest: always keep system prompt; remove oldest user/assistant pairs
- count_tokens_approximate: total_chars / 3.5 * 1.1
- If strategy="error" and context > limit, raise ValueError

**tests/test_context_adapter.py**:
- context < limit → unchanged
- truncate_middle keeps system + last 4
- truncate_oldest keeps system prompt
- token count: 350 chars ≈ 100 tokens

BLOCK 5: RouterCore + ProviderRegistry

**smartkeyrouter/provider_registry.py**:
```python
from config_loader import SmartKeyRouterConfig, ProviderConfig
from key_pool import KeyPool
from failure_tracker import FailureTracker
from adapters import get_adapter

class ProviderRegistry:
    """Registry that maps provider names to KeyPool + Adapter instances."""
    
    def __init__(self, config: SmartKeyRouterConfig, failure_tracker: FailureTracker):
        raise NotImplementedError
    
    def get_providers_sorted_by_priority(self) -> list:
        """Return enabled providers sorted by priority (lowest first)."""
        raise NotImplementedError
    
    def get_key_pool(self, provider_name: str) -> KeyPool | None:
        raise NotImplementedError
    
    def get_adapter(self, provider_name: str):
        raise NotImplementedError
```

**smartkeyrouter/router_core.py**:
```python
from dataclasses import dataclass
from config_loader import ConfigLoader
from provider_registry import ProviderRegistry
from failure_tracker import FailureTracker
from context_adapter import ContextAdapter

@dataclass
class RouterResponse:
    success: bool
    content: str | None = None
    provider_used: str | None = None
    model_used: str | None = None
    key_masked: str | None = None
    switches_made: int = 0
    total_latency_ms: int = 0
    error_message: str | None = None

class RouterCore:
    def __init__(self, config_path: str = "keyrouter.yaml"):
        raise NotImplementedError
    
    def chat(self, messages: list[dict], **kwargs) -> RouterResponse:
        """Main method. Try providers in priority order.
        
        Algorithm:
        1. Get providers sorted by priority
        2. For each provider:
           a. get_next_key() → None? log WARN, next provider
           b. For each model by priority:
              - ContextAdapter.prepare_context()
              - ProviderAdapter.send_request()
              - Success → record_success, return RouterResponse
              - 429/503 → record_failure, next key/model
              - 401/403 → record_failure, disable key forever
        3. All exhausted → RouterResponse(success=False, error_message)
        """
        raise NotImplementedError
    
    def get_status(self) -> dict:
        raise NotImplementedError
    
    def reset_cooldowns(self, provider_name: str | None = None) -> None:
        raise NotImplementedError
```

Implementation:
- Import and use: ConfigLoader, ProviderRegistry, FailureTracker, ContextAdapter
- For get_adapter, create on-demand based on provider_type
- Track switches_made and total_latency_ms in RouterResponse
- Key masking: first 8 chars + "..." (use ConfigLoader.mask_key)
- Always log every switch with reason

**tests/test_router_core.py**: Use unittest.mock for adapters.
- Provider 1 returns 429 → auto-switch to provider 2
- Provider 2 returns success → RouterResponse has content
- All providers exhausted → success=False, error_message set
- Context is adapted for target model
- switches_made is counted correctly

After all files created and tests pass:
1. Run: cd /home/exedev/HermesAi/Projects/smartkeyrouter && python -m pytest tests/ -v --ignore=tests/test_integration.py
2. Update progress: python3 /home/exedev/HermesAi/Projects/smartkeyrouter/progress_tracker.py set block4 "✅" "ContextAdapter done" && python3 /home/exedev/HermesAi/Projects/smartkeyrouter/progress_tracker.py set block5 "✅" "RouterCore done"
3. Report completion.
'

echo "Starting Agent B (blocks 4-5)..."
hermes chat -q "$PROMPT" 2>&1 | tee /home/exedev/HermesAi/Projects/smartkeyrouter/logs/agent_b.log
echo "AGENT_B_DONE" >> /home/exedev/HermesAi/Projects/smartkeyrouter/logs/agent_done.txt
