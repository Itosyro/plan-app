"""Shared fake Groq chat.completions payload builder for tests.

The AI modules call instructor in ``Mode.TOOLS``, so instructor parses
``choices[0].message.tool_calls[0].function.arguments`` and asserts the
function name equals the response model's class name. Every test that
mocks Groq via respx must therefore stage a tool-call-shaped response
with the right ``tool_name`` — this helper is the single place that
knows the shape.
"""

from __future__ import annotations

import json


def groq_tool_response(tool_name: str, payload: dict[str, object]) -> dict[str, object]:
    """Build a fake Groq chat completion carrying *payload* as a tool call.

    ``tool_name`` must be the Pydantic response model's class name (e.g.
    ``"SplitterResult"``) — instructor rejects a mismatching name before
    parsing the arguments.
    """
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": "openai/gpt-oss-20b",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(payload, ensure_ascii=False),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130},
    }
