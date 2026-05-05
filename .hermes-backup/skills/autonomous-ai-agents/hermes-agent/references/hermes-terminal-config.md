# Hermes Terminal Configuration

Default working directory for terminal commands.

## Setting Default Working Directory

To ensure Hermes always works from a specific folder:

```bash
# Set the default working directory
hermes config set terminal.cwd /home/exedev/HermesAi

# Verify
hermes config show | grep -E "(cwd|workdir|Working)"
```

## Why Set a Default Directory

- Reduces token usage (no need to navigate to project each time)
- Saves time on path resolution
- Establishes a "home base" for the agent

## Environment Variables for Path-Dependent Skills

For skills that need specific paths, set environment variables in `~/.hermes/.env`:

```bash
# Obsidian Vault
echo "OBSIDIAN_VAULT_PATH=/home/exedev/HermesAi/Vault" >> ~/.hermes/.env

# Custom paths
echo "MY_PROJECT_PATH=/home/exedev/HermesAi/project" >> ~/.hermes/.env
```

## Verification

Always verify paths after setting:
```bash
# Check working directory
pwd

# Check vault access
ls "$OBSIDIAN_VAULT_PATH"
```

## Common Pitfalls

1. **Don't set cwd to vault if you need project root**: If working on code, cwd should be project root, not the vault
2. **Relative paths break in different contexts**: Use absolute paths for reliability
3. **Spaces in paths**: Always quote paths containing spaces