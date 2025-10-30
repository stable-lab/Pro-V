"""
RTL Judgment Utilities

This module provides utilities for judging and evaluating RTL code quality and correctness.
"""

import re
from typing import Dict, Any, Optional, List, Tuple, Union


class RTLJudge:
    """Judge for evaluating RTL code quality and correctness"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the RTL judge
        
        Args:
            config: Configuration dictionary for the judge
        """
        self.config = config or {}
        self.threshold = self.config.get("threshold", 0.8)
        
    def judge_rtl_quality(self, rtl_code: str) -> Dict[str, Any]:
        """Judge the overall quality of RTL code
        
        Args:
            rtl_code: RTL code to evaluate
            
        Returns:
            Quality judgment results
        """
        result = {
            "overall_score": 0.0,
            "quality_level": "poor",
            "issues": [],
            "suggestions": [],
            "metrics": {}
        }
        
        # Run various quality checks
        syntax_check = self._check_syntax_quality(rtl_code)
        structure_check = self._check_structure_quality(rtl_code)
        style_check = self._check_style_quality(rtl_code)
        completeness_check = self._check_completeness(rtl_code)
        
        # Calculate weighted score
        weights = {
            "syntax": 0.3,
            "structure": 0.3,
            "style": 0.2,
            "completeness": 0.2
        }
        
        scores = {
            "syntax": syntax_check["score"],
            "structure": structure_check["score"],
            "style": style_check["score"],
            "completeness": completeness_check["score"]
        }
        
        overall_score = sum(scores[key] * weights[key] for key in scores)
        result["overall_score"] = overall_score
        result["metrics"] = scores
        
        # Determine quality level
        if overall_score >= 0.8:
            result["quality_level"] = "excellent"
        elif overall_score >= 0.6:
            result["quality_level"] = "good"
        elif overall_score >= 0.4:
            result["quality_level"] = "fair"
        else:
            result["quality_level"] = "poor"
            
        # Collect issues and suggestions
        for check in [syntax_check, structure_check, style_check, completeness_check]:
            result["issues"].extend(check.get("issues", []))
            result["suggestions"].extend(check.get("suggestions", []))
            
        return result
        
    def _check_syntax_quality(self, rtl_code: str) -> Dict[str, Any]:
        """Check syntax quality of RTL code
        
        Args:
            rtl_code: RTL code to check
            
        Returns:
            Syntax quality check results
        """
        result = {
            "score": 1.0,
            "issues": [],
            "suggestions": []
        }
        
        # Check for basic syntax issues
        issues_found = 0
        
        # Check for missing semicolons
        lines = rtl_code.split('\n')
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if line and not line.startswith('//') and not line.startswith('/*'):
                # Check for statements that should end with semicolon
                if (line.endswith(')') or 
                    line.startswith('assign') or 
                    line.startswith('wire') or 
                    line.startswith('reg')) and not line.endswith(';'):
                    result["issues"].append(f"Line {i}: Missing semicolon")
                    issues_found += 1
                    
        # Check for unmatched parentheses/brackets
        paren_count = rtl_code.count('(') - rtl_code.count(')')
        bracket_count = rtl_code.count('[') - rtl_code.count(']')
        brace_count = rtl_code.count('{') - rtl_code.count('}')
        
        if paren_count != 0:
            result["issues"].append(f"Unmatched parentheses: {paren_count}")
            issues_found += 1
            
        if bracket_count != 0:
            result["issues"].append(f"Unmatched brackets: {bracket_count}")
            issues_found += 1
            
        if brace_count != 0:
            result["issues"].append(f"Unmatched braces: {brace_count}")
            issues_found += 1
            
        # Calculate score based on issues
        if issues_found == 0:
            result["score"] = 1.0
        elif issues_found <= 2:
            result["score"] = 0.8
        elif issues_found <= 5:
            result["score"] = 0.6
        else:
            result["score"] = 0.3
            
        return result
        
    def _check_structure_quality(self, rtl_code: str) -> Dict[str, Any]:
        """Check structural quality of RTL code
        
        Args:
            rtl_code: RTL code to check
            
        Returns:
            Structure quality check results
        """
        result = {
            "score": 1.0,
            "issues": [],
            "suggestions": []
        }
        
        # Check for module structure
        modules = re.findall(r'module\s+(\w+)', rtl_code)
        endmodules = re.findall(r'endmodule', rtl_code)
        
        if len(modules) != len(endmodules):
            result["issues"].append("Mismatched module/endmodule pairs")
            result["score"] -= 0.3
            
        if not modules:
            result["issues"].append("No modules found")
            result["score"] -= 0.5
            
        # Check for proper port declarations
        for module in modules:
            module_pattern = rf'module\s+{module}\s*\(([^)]*)\)'
            match = re.search(module_pattern, rtl_code)
            if match:
                ports = match.group(1).strip()
                if not ports:
                    result["suggestions"].append(f"Module {module} has no ports - consider if this is intentional")
                    
        # Check for always blocks structure
        always_blocks = re.findall(r'always\s*@\s*\([^)]+\)', rtl_code)
        if always_blocks:
            for block in always_blocks:
                if 'posedge' not in block and 'negedge' not in block and '*' not in block:
                    result["suggestions"].append("Consider using proper sensitivity lists in always blocks")
                    
        return result
        
    def _check_style_quality(self, rtl_code: str) -> Dict[str, Any]:
        """Check style quality of RTL code
        
        Args:
            rtl_code: RTL code to check
            
        Returns:
            Style quality check results
        """
        result = {
            "score": 1.0,
            "issues": [],
            "suggestions": []
        }
        
        lines = rtl_code.split('\n')
        
        # Check indentation consistency
        indentations = []
        for line in lines:
            if line.strip():
                leading_spaces = len(line) - len(line.lstrip())
                if leading_spaces > 0:
                    indentations.append(leading_spaces)
                    
        if indentations:
            # Check if indentation is consistent (multiples of 2 or 4)
            inconsistent_indent = any(indent % 2 != 0 for indent in indentations)
            if inconsistent_indent:
                result["suggestions"].append("Consider using consistent indentation (2 or 4 spaces)")
                result["score"] -= 0.1
                
        # Check for very long lines
        long_lines = [i+1 for i, line in enumerate(lines) if len(line) > 120]
        if long_lines:
            result["suggestions"].append(f"Consider breaking long lines (lines: {long_lines[:5]})")
            result["score"] -= 0.1
            
        # Check for comments
        comment_lines = sum(1 for line in lines if '//' in line or '/*' in line)
        total_code_lines = sum(1 for line in lines if line.strip() and not line.strip().startswith('//'))
        
        if total_code_lines > 0:
            comment_ratio = comment_lines / total_code_lines
            if comment_ratio < 0.1:
                result["suggestions"].append("Consider adding more comments for better readability")
                result["score"] -= 0.1
                
        return result
        
    def _check_completeness(self, rtl_code: str) -> Dict[str, Any]:
        """Check completeness of RTL code
        
        Args:
            rtl_code: RTL code to check
            
        Returns:
            Completeness check results
        """
        result = {
            "score": 1.0,
            "issues": [],
            "suggestions": []
        }
        
        # Check for basic RTL elements
        has_module = bool(re.search(r'module\s+\w+', rtl_code))
        has_ports = bool(re.search(r'(?:input|output|inout)', rtl_code))
        has_logic = bool(re.search(r'(?:always|assign|wire|reg)', rtl_code))
        
        if not has_module:
            result["issues"].append("No module declaration found")
            result["score"] -= 0.4
            
        if not has_ports:
            result["suggestions"].append("No input/output ports found - consider if this is intentional")
            result["score"] -= 0.2
            
        if not has_logic:
            result["issues"].append("No logic implementation found")
            result["score"] -= 0.4
            
        # Check for clock and reset (common in sequential logic)
        has_clock = bool(re.search(r'\b(?:clk|clock)\b', rtl_code, re.IGNORECASE))
        has_reset = bool(re.search(r'\b(?:rst|reset)\b', rtl_code, re.IGNORECASE))
        
        has_sequential = bool(re.search(r'always\s*@\s*\([^)]*(?:posedge|negedge)', rtl_code))
        
        if has_sequential and not has_clock:
            result["suggestions"].append("Sequential logic found but no clock signal detected")
            
        if has_sequential and not has_reset:
            result["suggestions"].append("Sequential logic found but no reset signal detected")
            
        return result
        
    def judge_testbench_quality(self, testbench: str) -> Dict[str, Any]:
        """Judge the quality of testbench code
        
        Args:
            testbench: Testbench code to evaluate
            
        Returns:
            Testbench quality judgment results
        """
        result = {
            "overall_score": 0.0,
            "quality_level": "poor",
            "issues": [],
            "suggestions": [],
            "coverage_estimate": 0.0
        }
        
        # Check for testbench structure
        has_initial = bool(re.search(r'initial\s+begin', testbench))
        has_clock_gen = bool(re.search(r'always\s+#\d+\s+\w+\s*=\s*~\w+', testbench))
        has_stimulus = bool(re.search(r'#\d+', testbench))  # Delays indicate stimulus
        has_monitoring = bool(re.search(r'\$monitor|\$display', testbench))
        
        score = 0.0
        
        if has_initial:
            score += 0.3
        else:
            result["issues"].append("No initial block found for test stimulus")
            
        if has_clock_gen:
            score += 0.2
        else:
            result["suggestions"].append("Consider adding clock generation for sequential designs")
            
        if has_stimulus:
            score += 0.3
        else:
            result["issues"].append("No test stimulus timing found")
            
        if has_monitoring:
            score += 0.2
        else:
            result["suggestions"].append("Consider adding monitoring/display statements")
            
        result["overall_score"] = score
        
        # Determine quality level
        if score >= 0.8:
            result["quality_level"] = "excellent"
        elif score >= 0.6:
            result["quality_level"] = "good"
        elif score >= 0.4:
            result["quality_level"] = "fair"
        else:
            result["quality_level"] = "poor"
            
        # Estimate coverage based on test patterns
        test_patterns = len(re.findall(r'#\d+', testbench))
        if test_patterns > 10:
            result["coverage_estimate"] = 0.8
        elif test_patterns > 5:
            result["coverage_estimate"] = 0.6
        elif test_patterns > 2:
            result["coverage_estimate"] = 0.4
        else:
            result["coverage_estimate"] = 0.2
            
        return result
        
    def compare_implementations(self, rtl1: str, rtl2: str) -> Dict[str, Any]:
        """Compare two RTL implementations
        
        Args:
            rtl1: First RTL implementation
            rtl2: Second RTL implementation
            
        Returns:
            Comparison results
        """
        result = {
            "similarity_score": 0.0,
            "differences": [],
            "recommendations": []
        }
        
        # Judge both implementations
        quality1 = self.judge_rtl_quality(rtl1)
        quality2 = self.judge_rtl_quality(rtl2)
        
        # Compare quality scores
        score_diff = abs(quality1["overall_score"] - quality2["overall_score"])
        
        if quality1["overall_score"] > quality2["overall_score"]:
            result["recommendations"].append("First implementation has higher quality score")
        elif quality2["overall_score"] > quality1["overall_score"]:
            result["recommendations"].append("Second implementation has higher quality score")
        else:
            result["recommendations"].append("Both implementations have similar quality scores")
            
        # Simple similarity check based on common keywords
        keywords1 = set(re.findall(r'\b\w+\b', rtl1.lower()))
        keywords2 = set(re.findall(r'\b\w+\b', rtl2.lower()))
        
        common_keywords = keywords1 & keywords2
        total_keywords = keywords1 | keywords2
        
        if total_keywords:
            similarity = len(common_keywords) / len(total_keywords)
            result["similarity_score"] = similarity
            
        return result


def judge_rtl(rtl_code: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function for RTL quality judgment
    
    Args:
        rtl_code: RTL code to judge
        config: Optional configuration
        
    Returns:
        Quality judgment results
    """
    judge = RTLJudge(config)
    return judge.judge_rtl_quality(rtl_code)


def judge_testbench(testbench: str, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convenience function for testbench quality judgment
    
    Args:
        testbench: Testbench code to judge
        config: Optional configuration
        
    Returns:
        Testbench quality judgment results
    """
    judge = RTLJudge(config)
    return judge.judge_testbench_quality(testbench)

