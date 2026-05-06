#!/usr/bin/env python3
"""Progress tracker for SmartKeyRouter blocks."""
from datetime import datetime

BLOCKS = {
    "block1": {"name": "ConfigLoader + YAML", "agent": "agent-1", "status": "⏳"},
    "block2": {"name": "KeyPool + FailureTracker", "agent": "agent-2", "status": "⏳"},
    "block3": {"name": "ProviderAdapter", "agent": "agent-3", "status": "⏳"},
    "block4": {"name": "ContextAdapter", "agent": "agent-4", "status": "⏳"},
    "block5": {"name": "RouterCore + ProviderRegistry", "agent": "agent-5", "status": "⏳"},
    "block6": {"name": "CLI + Logging", "agent": "agent-6", "status": "⏳"},
    "block7": {"name": "Hermes Integration", "agent": "agent-7", "status": "⏳"},
}

STATUS_FILE = "/home/exedev/HermesAi/Projects/smartkeyrouter/.progress.json"

def read_status():
    import json
    try:
        with open(STATUS_FILE) as f:
            return json.load(f)
    except:
        return {k: {"status": "⏳", "done": False} for k in BLOCKS}

def write_status(data):
    import json
    with open(STATUS_FILE, "w") as f:
        json.dump(data, f, indent=2)

def render():
    data = read_status()
    print(f"\n{'='*60}")
    print(f"SmartKeyRouter Progress — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*60}")
    done = 0
    for key, info in BLOCKS.items():
        s = data.get(key, {"status": "⏳", "done": False})
        icon = "✅" if s.get("done") else s.get("status", "⏳")
        line = f"  {icon} [{key}] {info['name']} ({info['agent']})"
        if s.get("message"):
            line += f" — {s['message']}"
        print(line)
        if s.get("done"):
            done += 1
    print(f"\n  {done}/{len(BLOCKS)} blocks complete")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if sys.argv[1] == "render":
            render()
        elif sys.argv[1] == "set":
            key, status, msg = sys.argv[2], sys.argv[3], " ".join(sys.argv[4:])
            data = read_status()
            data[key] = {"status": status, "message": msg, "done": status == "✅"}
            write_status(data)
    else:
        render()
