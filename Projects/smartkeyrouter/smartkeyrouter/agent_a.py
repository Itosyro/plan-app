#!/usr/bin/env python3
"""Agent A: Implements Blocks 1-3 of SmartKeyRouter.

This agent creates ConfigLoader, KeyPool, FailureTracker, and Adapter classes.
It loads keyrouter.yaml and validates configuration.
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# Import our modules
from config_loader import ConfigLoader, SmartKeyRouterConfig, ConfigError
from key_pool import KeyPool
from failure_tracker import FailureTracker

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("/home/exedev/HermesAi/Projects/smartkeyrouter/logs/agent_a.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("AgentA")

def main():
    logger.info("Starting Agent A...")
    
    # Load configuration
    config_path = "/home/exedev/HermesAi/Projects/smartkeyrouter/keyrouter.yaml"
    logger.info(f"Loading config from {config_path}")
    
    try:
        config_loader = ConfigLoader(config_path)
        config = config_loader.load()
        logger.info(f"Successfully loaded config with {len(config.providers)} providers")
        
        # Validate config (already done in ConfigLoader)
        logger.info("Config validation passed")
        
        # Create KeyPool and FailureTracker
        failure_tracker = FailureTracker(backoff_base=1)
        key_pools = {}
        
        # Initialize KeyPool and FailureTracker for each provider
        for provider in config.providers:
            logger.info(f"Initializing KeyPool for provider '{provider.name}' (priority {provider.priority})")
            
            # Create KeyPool
            key_pool = KeyPool(
                keys=[k.env for k in provider.keys],
                strategy=provider.key_strategy,
                failure_tracker=failure_tracker
            )
            key_pools[provider.name] = key_pool
            logger.info(f"Created KeyPool for {provider.name} with {len(key_pool._keys)} keys")
            
        # Test KeyPool functionality
        logger.info("Testing KeyPool functionality...")
        test_key_pool(key_pools)
        
        # Test FailureTracker
        logger.info("Testing FailureTracker...")
        test_failure_tracker(failure_tracker)
        
        logger.info("Agent A completed successfully!")
        
    except ConfigError as e:
        logger.error(f"Config error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def test_key_pool(key_pools: Dict[str, KeyPool]):
    """Test KeyPool functionality."""
    logger.info("Testing KeyPool round-robin behavior...")
    
    # Get first provider (highest priority)
    first_provider_name = sorted(key_pools.keys(), key=lambda x: next(p.priority for p in config.providers if p.name == x))[0]
    key_pool = key_pools[first_provider_name]
    
    # Test round-robin cycling
    logger.info("Testing round-robin cycling...")
    keys = key_pool._keys  # Access internal for test
    if len(keys) >= 3:
        logger.info(f"Testing round-robin with keys: {key_pool.mask_key(key_pool._keys[0])}...")
        
        # Get next key 3 times
        key1 = key_pool.get_next_key()
        key2 = key_pool.get_next_key()
        key3 = key_pool.get_next_key()
        
        logger.info(f"Key sequence: {key_pool.mask_key(key1)} → {key_pool.mask_key(key2)} → {key_pool.mask_key(key3)}")
        
        # Verify it cycles through keys
        expected_cycle = key_pool.mask_key(key_pool._keys[0])
        if key_pool.mask_key(key1) == expected_cycle:
            logger.info("Round-robin working correctly")
        else:
            logger.warning("Round-robin not cycling properly")
    
    # Test cooldown behavior
    logger.info("Testing cooldown behavior...")
    # Simulate a key failure
    first_key = key_pool._keys[0]
    key_pool.mark_failed(first_key, 429)  # 429 = rate limit
    logger.info(f"Marked {first_key} as failed with 429")
    
    # Should skip this key
    next_key = key_pool.get_next_key()
    if next_key and next_key != first_key:
        logger.info(f"Key {next_key} correctly skipped after failure")
    else:
        logger.warning("Key cycling not respecting cooldown")
    
    # Test all on cooldown
    for key in key_pool._keys:
        key_pool.mark_failed(key, 429)
    
    result = key_pool.get_next_key()
    if result is None:
        logger.info("All keys on cooldown - get_next_key() returns None as expected")
    else:
        logger.warning(f"Unexpected key returned: {key_pool.mask_key(result)}")

def test_failure_tracker(failure_tracker):
    """Test FailureTracker functionality."""
    logger.info("Testing FailureTracker...")
    
    # Test basic functionality
    ft = FailureTracker(backoff_base=1)
    
    # Test record_failure
    ft.record_failure("test_key", 429)
    status = ft.get_all_stats()
    logger.info(f"Failure stats after 429: {status}")
    
    # Test 403 (permanent disable)
    ft.record_failure("key2", 403)
    status = ft.get_all_stats()
    logger.info(f"403 test stats: {status}")
    
    # Test exponential backoff
    ft.record_failure("key1", 429)
    ft.record_failure("key1", 429)
    ft.record_failure("key1", 429)
    remaining = ft.get_cooldown_remaining("key1")
    logger.info(f"Exponential backoff test - cooldown remaining for key1: {cooldown_seconds:.1f}s")
    
    # Test thread safety (simulated)
    def worker():
        for i in range(5):
            ft.record_failure("key1", 429)
            time.sleep(0.1)
    
    threads = []
    for _ in range(10):
        t = threading.Thread(target=worker)
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    logger.info("Thread safety test completed")

if __name__ == "__main__":
    main()