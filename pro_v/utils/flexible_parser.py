"""
Flexible Parser Utilities

This module provides flexible parsing capabilities for various file formats
and data structures used in the Pro-V system.
"""

import logging
import json
import yaml
import re
from typing import Dict, Any, Optional, List, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class FlexibleParser:
    """A flexible parser that can handle multiple file formats and data structures"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the flexible parser
        
        Args:
            config: Configuration dictionary for the parser
        """
        self.config = config or {}
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
    def parse_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Parse a file based on its extension
        
        Args:
            file_path: Path to the file to parse
            
        Returns:
            Parsed data as dictionary
        """
        file_path = Path(file_path)
        self.logger.info(f"Parsing file: {file_path}")
        
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
            
        suffix = file_path.suffix.lower()
        
        try:
            if suffix == '.json':
                return self._parse_json(file_path)
            elif suffix in ['.yaml', '.yml']:
                return self._parse_yaml(file_path)
            elif suffix == '.txt':
                return self._parse_text(file_path)
            elif suffix in ['.v', '.sv']:
                return self._parse_verilog(file_path)
            else:
                # Default to text parsing
                return self._parse_text(file_path)
                
        except Exception as e:
            self.logger.error(f"Error parsing file {file_path}: {str(e)}")
            raise
            
    def _parse_json(self, file_path: Path) -> Dict[str, Any]:
        """Parse JSON file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    def _parse_yaml(self, file_path: Path) -> Dict[str, Any]:
        """Parse YAML file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
            
    def _parse_text(self, file_path: Path) -> Dict[str, Any]:
        """Parse text file"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        return {
            "content": content,
            "lines": content.splitlines(),
            "line_count": len(content.splitlines()),
            "char_count": len(content)
        }
        
    def _parse_verilog(self, file_path: Path) -> Dict[str, Any]:
        """Parse Verilog file and extract basic information"""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Extract module information
        modules = []
        module_pattern = r'module\s+(\w+)\s*(?:\(([^)]*)\))?\s*;'
        
        for match in re.finditer(module_pattern, content, re.MULTILINE):
            module_name = match.group(1)
            ports = match.group(2) if match.group(2) else ""
            modules.append({
                "name": module_name,
                "ports": [p.strip() for p in ports.split(',') if p.strip()]
            })
            
        return {
            "content": content,
            "modules": modules,
            "line_count": len(content.splitlines()),
            "char_count": len(content)
        }
        
    def parse_string(self, data: str, format_type: str = "auto") -> Dict[str, Any]:
        """Parse string data in various formats
        
        Args:
            data: String data to parse
            format_type: Format type ('json', 'yaml', 'text', 'auto')
            
        Returns:
            Parsed data as dictionary
        """
        self.logger.info(f"Parsing string data (format: {format_type})")
        
        if format_type == "auto":
            # Try to detect format
            data_stripped = data.strip()
            if data_stripped.startswith('{') or data_stripped.startswith('['):
                format_type = "json"
            elif ':' in data_stripped and ('-' in data_stripped or data_stripped.count('\n') > 0):
                format_type = "yaml"
            else:
                format_type = "text"
                
        try:
            if format_type == "json":
                return json.loads(data)
            elif format_type == "yaml":
                return yaml.safe_load(data) or {}
            else:
                return {
                    "content": data,
                    "lines": data.splitlines(),
                    "line_count": len(data.splitlines()),
                    "char_count": len(data)
                }
        except Exception as e:
            self.logger.error(f"Error parsing string data: {str(e)}")
            # Fallback to text parsing
            return {
                "content": data,
                "lines": data.splitlines(),
                "line_count": len(data.splitlines()),
                "char_count": len(data),
                "parse_error": str(e)
            }


def parse_file(file_path: Union[str, Path], config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function for file parsing
    
    Args:
        file_path: Path to file to parse
        config: Optional configuration
        
    Returns:
        Parsed data dictionary
    """
    parser = FlexibleParser(config)
    return parser.parse_file(file_path)


def parse_string(data: str, format_type: str = "auto", config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function for string parsing
    
    Args:
        data: String data to parse
        format_type: Format type
        config: Optional configuration
        
    Returns:
        Parsed data dictionary
    """
    parser = FlexibleParser(config)
    return parser.parse_string(data, format_type)

