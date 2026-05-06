# agent_a.sh
#!/bin/bash
# Agent A: Blocks 1-3 (ConfigLoader, KeyPool, FailureTracker, Adapters)

cd /home/exedev/HermesAi/Projects/smartkeyrouter

# Ensure Python path is set
export PYTHONPATH="/home/exedev/HermesAi/Projects/smartkeyrouter:$PYTHONPATH"

# Wait for config_loader.py to exist (in case it's not ready yet)
while [ ! -f "/home/exedev/HermesAi/Projects/smartkeyrouter/smartkeyrouter/config_loader.py" ]; do
    echo "Waiting for config_loader.py..."
    sleep 5
done

# Run the agent
exec python3 -u smartkeyrouter/agent_a.py