"""
Configuration Generation Utilities

This module provides utilities for generating and managing configurations
for the Pro-V system.
"""

import json
import yaml
from typing import Dict, Any, Optional, List, Union
from pathlib import Path


class ConfigGenerator:
    """Generator for Pro-V system configurations"""
    
    def __init__(self, base_config: Optional[Dict[str, Any]] = None):
        """Initialize the config generator
        
        Args:
            base_config: Base configuration dictionary
        """
        self.base_config = base_config or {}
        
    def generate_default_config(self) -> Dict[str, Any]:
        """Generate default configuration for Pro-V system
        
        Returns:
            Default configuration dictionary
        """
        config = {
            "system": {
                "name": "pro-v",
                "version": "1.0.0",
                "debug": False
            },
            "agent": {
                "gen_tb": {
                    "max_iterations": 3,
                    "timeout": 300
                },
                "pychecker": {
                    "strict_mode": True,
                    "check_imports": True
                },
                "refine_python_agent": {
                    "auto_fix": True,
                    "style_check": True
                }
            },
            "utils": {
                "flexible_parser": {
                    "auto_detect": True,
                    "encoding": "utf-8"
                },
                "token_counter": {
                    "model": "gpt-3.5-turbo",
                    "max_tokens": 4096
                },
                "eval_logger": {
                    "level": "INFO",
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                }
            },
            "tools": {
                "simulate_ray": {
                    "num_workers": 4,
                    "timeout": 600
                }
            },
            "back_up": {
                "check_consistency": {
                    "strict": True
                },
                "judge_for_RTL": {
                    "threshold": 0.8
                }
            }
        }
        
        # Merge with base config if provided
        if self.base_config:
            config = self._merge_configs(config, self.base_config)
            
        return config
        
    def _merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two configuration dictionaries
        
        Args:
            base: Base configuration
            override: Override configuration
            
        Returns:
            Merged configuration
        """
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
                
        return result
        
    def save_config(self, config: Dict[str, Any], file_path: Union[str, Path], format_type: str = "json") -> None:
        """Save configuration to file
        
        Args:
            config: Configuration to save
            file_path: Path to save the configuration
            format_type: Format type ('json' or 'yaml')
        """
        file_path = Path(file_path)
        
        if format_type.lower() == "json":
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        elif format_type.lower() in ["yaml", "yml"]:
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        else:
            raise ValueError(f"Unsupported format type: {format_type}")
            
    def load_config(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Load configuration from file
        
        Args:
            file_path: Path to configuration file
            
        Returns:
            Loaded configuration dictionary
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")
            
        suffix = file_path.suffix.lower()
        
        if suffix == ".json":
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        elif suffix in [".yaml", ".yml"]:
            with open(file_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        else:
            raise ValueError(f"Unsupported configuration file format: {suffix}")


def generate_config(base_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function for generating configuration
    
    Args:
        base_config: Optional base configuration
        
    Returns:
        Generated configuration dictionary
    """
    generator = ConfigGenerator(base_config)
    return generator.generate_default_config()


def save_config(config: Dict[str, Any], file_path: Union[str, Path], format_type: str = "json") -> None:
    """Convenience function for saving configuration
    
    Args:
        config: Configuration to save
        file_path: Path to save the configuration
        format_type: Format type ('json' or 'yaml')
    """
    generator = ConfigGenerator()
    generator.save_config(config, file_path, format_type)


def load_config(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Convenience function for loading configuration
    
    Args:
        file_path: Path to configuration file
        
    Returns:
        Loaded configuration dictionary
    """
    generator = ConfigGenerator()
    return generator.load_config(file_path)

