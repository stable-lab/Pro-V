"""
Consistency Checking Utilities

This module provides utilities for checking consistency between
different components of the verification system.
"""

import re
from typing import Dict, Any, Optional, List, Tuple, Union
from pathlib import Path


class ConsistencyChecker:
    """Checker for consistency between RTL, testbench, and specifications"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the consistency checker
        
        Args:
            config: Configuration dictionary for the checker
        """
        self.config = config or {}
        self.strict_mode = self.config.get("strict", True)
        
    def check_rtl_testbench_consistency(self, rtl_code: str, testbench: str) -> Dict[str, Any]:
        """Check consistency between RTL and testbench
        
        Args:
            rtl_code: RTL code to check
            testbench: Testbench code to check
            
        Returns:
            Consistency check results
        """
        result = {
            "consistent": True,
            "issues": [],
            "warnings": [],
            "module_match": False,
            "port_match": False,
            "signal_match": False
        }
        
        # Extract module information from RTL
        rtl_modules = self._extract_modules(rtl_code)
        tb_modules = self._extract_modules(testbench)
        
        if not rtl_modules:
            result["issues"].append("No modules found in RTL code")
            result["consistent"] = False
            return result
            
        if not tb_modules:
            result["issues"].append("No modules found in testbench")
            result["consistent"] = False
            return result
            
        # Check if testbench instantiates RTL modules
        rtl_module_names = [m["name"] for m in rtl_modules]
        tb_instantiations = self._find_module_instantiations(testbench)
        
        instantiated_modules = [inst["module"] for inst in tb_instantiations]
        
        # Check module matching
        common_modules = set(rtl_module_names) & set(instantiated_modules)
        if common_modules:
            result["module_match"] = True
        else:
            result["issues"].append("Testbench does not instantiate any RTL modules")
            result["consistent"] = False
            
        # Check port consistency for matched modules
        for module_name in common_modules:
            rtl_module = next(m for m in rtl_modules if m["name"] == module_name)
            tb_inst = next(inst for inst in tb_instantiations if inst["module"] == module_name)
            
            port_check = self._check_port_consistency(rtl_module, tb_inst)
            if not port_check["consistent"]:
                result["issues"].extend(port_check["issues"])
                result["consistent"] = False
            else:
                result["port_match"] = True
                
        # Check signal consistency
        signal_check = self._check_signal_consistency(rtl_code, testbench)
        result["signal_match"] = signal_check["consistent"]
        if not signal_check["consistent"]:
            result["warnings"].extend(signal_check["warnings"])
            
        return result
        
    def _extract_modules(self, verilog_code: str) -> List[Dict[str, Any]]:
        """Extract module information from Verilog code
        
        Args:
            verilog_code: Verilog code to analyze
            
        Returns:
            List of module dictionaries
        """
        modules = []
        
        # Pattern to match module declarations
        module_pattern = r'module\s+(\w+)\s*(?:\(([^)]*)\))?\s*;'
        
        for match in re.finditer(module_pattern, verilog_code, re.MULTILINE):
            module_name = match.group(1)
            ports_str = match.group(2) if match.group(2) else ""
            
            # Parse ports
            ports = []
            if ports_str:
                port_list = [p.strip() for p in ports_str.split(',') if p.strip()]
                ports = port_list
                
            modules.append({
                "name": module_name,
                "ports": ports,
                "port_string": ports_str
            })
            
        return modules
        
    def _find_module_instantiations(self, verilog_code: str) -> List[Dict[str, Any]]:
        """Find module instantiations in Verilog code
        
        Args:
            verilog_code: Verilog code to analyze
            
        Returns:
            List of instantiation dictionaries
        """
        instantiations = []
        
        # Pattern to match module instantiations
        inst_pattern = r'(\w+)\s+(\w+)\s*\(([^)]*)\)\s*;'
        
        for match in re.finditer(inst_pattern, verilog_code, re.MULTILINE):
            module_name = match.group(1)
            instance_name = match.group(2)
            connections = match.group(3)
            
            # Skip built-in Verilog constructs
            if module_name.lower() in ['initial', 'always', 'assign', 'wire', 'reg', 'integer']:
                continue
                
            instantiations.append({
                "module": module_name,
                "instance": instance_name,
                "connections": connections.strip()
            })
            
        return instantiations
        
    def _check_port_consistency(self, rtl_module: Dict[str, Any], tb_inst: Dict[str, Any]) -> Dict[str, Any]:
        """Check port consistency between RTL module and testbench instantiation
        
        Args:
            rtl_module: RTL module information
            tb_inst: Testbench instantiation information
            
        Returns:
            Port consistency check results
        """
        result = {
            "consistent": True,
            "issues": []
        }
        
        rtl_ports = rtl_module.get("ports", [])
        tb_connections = tb_inst.get("connections", "")
        
        if not rtl_ports and not tb_connections:
            return result
            
        if rtl_ports and not tb_connections:
            result["issues"].append(f"Module {rtl_module['name']} has ports but instantiation has no connections")
            result["consistent"] = False
            
        if not rtl_ports and tb_connections:
            result["issues"].append(f"Module {rtl_module['name']} has no ports but instantiation has connections")
            result["consistent"] = False
            
        return result
        
    def _check_signal_consistency(self, rtl_code: str, testbench: str) -> Dict[str, Any]:
        """Check signal consistency between RTL and testbench
        
        Args:
            rtl_code: RTL code
            testbench: Testbench code
            
        Returns:
            Signal consistency check results
        """
        result = {
            "consistent": True,
            "warnings": []
        }
        
        # Extract signal declarations
        rtl_signals = self._extract_signals(rtl_code)
        tb_signals = self._extract_signals(testbench)
        
        # Check for common signal names (basic check)
        common_signals = set(rtl_signals) & set(tb_signals)
        
        if not common_signals:
            result["warnings"].append("No common signal names found between RTL and testbench")
            result["consistent"] = False
            
        return result
        
    def _extract_signals(self, verilog_code: str) -> List[str]:
        """Extract signal names from Verilog code
        
        Args:
            verilog_code: Verilog code to analyze
            
        Returns:
            List of signal names
        """
        signals = []
        
        # Pattern to match signal declarations
        signal_patterns = [
            r'(?:input|output|inout)\s+(?:\w+\s+)?(\w+)',
            r'(?:wire|reg)\s+(?:\[\d+:\d+\]\s+)?(\w+)',
        ]
        
        for pattern in signal_patterns:
            for match in re.finditer(pattern, verilog_code):
                signal_name = match.group(1)
                if signal_name not in signals:
                    signals.append(signal_name)
                    
        return signals
        
    def check_specification_consistency(self, specification: str, rtl_code: str, testbench: str) -> Dict[str, Any]:
        """Check consistency between specification and implementation
        
        Args:
            specification: Specification text
            rtl_code: RTL implementation
            testbench: Testbench code
            
        Returns:
            Specification consistency check results
        """
        result = {
            "consistent": True,
            "issues": [],
            "warnings": [],
            "coverage": 0.0
        }
        
        # Extract key terms from specification
        spec_terms = self._extract_specification_terms(specification)
        
        # Check if terms appear in RTL and testbench
        rtl_coverage = self._check_term_coverage(spec_terms, rtl_code)
        tb_coverage = self._check_term_coverage(spec_terms, testbench)
        
        overall_coverage = (rtl_coverage + tb_coverage) / 2
        result["coverage"] = overall_coverage
        
        if overall_coverage < 0.5:
            result["warnings"].append(f"Low specification coverage: {overall_coverage:.2%}")
            
        if overall_coverage < 0.2:
            result["issues"].append("Very low specification coverage - implementation may not match specification")
            result["consistent"] = False
            
        return result
        
    def _extract_specification_terms(self, specification: str) -> List[str]:
        """Extract key terms from specification text
        
        Args:
            specification: Specification text
            
        Returns:
            List of key terms
        """
        # Simple term extraction - could be enhanced with NLP
        words = re.findall(r'\b[a-zA-Z_]\w*\b', specification.lower())
        
        # Filter out common words
        common_words = {'the', 'and', 'or', 'of', 'to', 'a', 'an', 'is', 'are', 'be', 'have', 'has', 'will', 'should', 'must'}
        terms = [word for word in words if word not in common_words and len(word) > 2]
        
        # Remove duplicates while preserving order
        unique_terms = []
        for term in terms:
            if term not in unique_terms:
                unique_terms.append(term)
                
        return unique_terms
        
    def _check_term_coverage(self, terms: List[str], code: str) -> float:
        """Check how many specification terms appear in code
        
        Args:
            terms: List of terms to check
            code: Code to check against
            
        Returns:
            Coverage ratio (0.0 to 1.0)
        """
        if not terms:
            return 1.0
            
        code_lower = code.lower()
        found_terms = sum(1 for term in terms if term in code_lower)
        
        return found_terms / len(terms)


def check_consistency(rtl_code: str, testbench: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function for consistency checking
    
    Args:
        rtl_code: RTL code to check
        testbench: Testbench code to check
        config: Optional configuration
        
    Returns:
        Consistency check results
    """
    checker = ConsistencyChecker(config)
    return checker.check_rtl_testbench_consistency(rtl_code, testbench)

