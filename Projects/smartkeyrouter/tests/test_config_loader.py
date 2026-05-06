import os
import tempfile
import yaml
from pathlib import Path

from smartkeyrouter.config_loader import ConfigLoader, ConfigError, SmartKeyRouterConfig, GlobalSettings, ProviderConfig, KeyConfig, ModelConfig

def test_config_loader_basic():
    # Create a temporary config file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_content = {
            "keyrouter": {
                "global": {
                    "log_file": "test.log",
                    "log_level": "INFO",
                    "max_retries_per_key": 1,
                    "backoff_strategy": "exponential",
                    "backoff_base_seconds": 1,
                    "respect_retry_after_header": True,
                    "context_overflow_strategy": "truncate_middle"
                },
                "providers": [
                    {
                        "name": "test_provider",
                        "provider_type": "generic_openai",
                        "priority": 10,
                        "enabled": True,
                        "keys": [
                            {"env": "TEST_KEY_1"},
                            {"env": "TEST_KEY_2"}
                        ],
                        "models": [
                            {"id": "gpt-4", "context_limit": 8192, "priority": 5}
                        ],
                        "base_url": "https://api.example.com/v1"
                    }
                ]
            }
        }
        yaml.dump(config_content, f)
        config_path = f.name

    try:
        loader = ConfigLoader(config_path=config_path)
        config = loader.load()
        
        # Verify config structure
        assert isinstance(config, SmartKeyRouterConfig)
        assert len(config.providers) == 1
        provider = config.providers[0]
        assert provider.name == "test_provider"
        assert provider.enabled is True
        assert len(provider.keys) == 2
        assert provider.models[0].id == "gpt-4"
        assert provider.models[0].context_limit == 8192
        
        # Verify resolved keys
        assert len(provider.resolved_keys) == 2
        # Check that keys are not None
        for key in provider.resolved_keys:
            assert isinstance(key, str)
            
        # Test reload
        config2 = loader.reload()
        assert config is config2  # Should be same object (cached)
        
    finally:
        os.unlink(config_path)

def test_config_loader_missing_file():
    loader = ConfigLoader(config_path="/nonexistent/config.yaml")
    try:
        loader.load()
        assert False, "Should have raised ConfigError"
    except ConfigError as e:
        assert "Config file not found" in str(e)

def test_config_loader_invalid_yaml():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("invalid yaml content")
        config_path = f.name
    
    try:
        loader = ConfigLoader(config_path=config_path)
        try:
            loader.load()
            assert False, "Should have raised ConfigError for invalid YAML"
        except ConfigError as e:
            assert "missing top-level 'keyrouter' key" in str(e)
    finally:
        os.unlink(config_path)

def test_config_loader_duplicate_names():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_content = {
            "keyrouter": {
                "providers": [
                    {"name": "provider1", "keys": [{"env": "KEY1"}]},
                    {"name": "provider1", "keys": [{"env": "KEY2"}]}  # duplicate name
                ]
            }
        }
        yaml.dump(config_content, f)
        config_path = f.name
    
    try:
        loader = ConfigLoader(config_path=config_path)
        try:
            loader.load()
            assert False, "Should have raised ConfigError for duplicate provider names"
        except ConfigError as e:
            assert "Duplicate provider names" in str(e)
    finally:
        os.unlink(config_path)

def test_config_loader_duplicate_priorities():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_content = {
            "keyrouter": {
                "providers": [
                    {"name": "p1", "priority": 10, "keys": [{"env": "K1"}]},
                    {"name": "p2", "priority": 10, "keys": [{"env": "K2"}]}  # duplicate priority
                ]
            }
        }
        yaml.dump(config_content, f)
        config_path = f.name
    
    try:
        loader = ConfigLoader(config_path=config_path)
        try:
            loader.load()
            assert False, "Should have raised ConfigError for duplicate priority values"
        except ConfigError as e:
            assert "Duplicate priority values" in str(e)
    finally:
        os.unlink(config_path)

def test_config_loader_model_context_limit():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        config_content = {
            "keyrouter": {
                "providers": [
                    {
                        "name": "p1",
                        "keys": [{"env": "K1"}],
                        "models": [
                            {"id": "model1", "context_limit": -1},  # invalid
                            {"id": "model2", "context_limit": 0}     # invalid
                        ]
                    }
                ]
            }
        }
        yaml.dump(config_content, f)
        config_path = f.name
    
    try:
        loader = ConfigLoader(config_path=config_path)
        try:
            loader.load()
            assert False, "Should have raised ConfigError for invalid context_limit"
        except ConfigError as e:
            assert "context_limit must be > 0" in str(e)
    finally:
        os.unlink(config_path)