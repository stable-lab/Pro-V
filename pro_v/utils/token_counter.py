"""
Token Counter Utilities

This module provides utilities for counting tokens in text,
which is useful for managing LLM API costs and limits.
"""

import re
from typing import Dict, Any, Optional, List, Union


class TokenCounter:
    """Token counter for various text inputs"""
    
    def __init__(self, model: str = "gpt-3.5-turbo"):
        """Initialize the token counter
        
        Args:
            model: Model name for token counting (affects token calculation)
        """
        self.model = model
        
        # Approximate token ratios for different models
        self.token_ratios = {
            "gpt-3.5-turbo": 0.75,  # ~0.75 tokens per word
            "gpt-4": 0.75,
            "claude": 0.8,
            "default": 0.75
        }
        
    def count_tokens_approximate(self, text: str) -> int:
        """Count tokens using approximate method
        
        Args:
            text: Text to count tokens for
            
        Returns:
            Approximate token count
        """
        if not text:
            return 0
            
        # Simple word-based approximation
        words = len(text.split())
        
        # Get token ratio for the model
        ratio = self.token_ratios.get(self.model, self.token_ratios["default"])
        
        # Calculate approximate tokens
        tokens = int(words * ratio)
        
        # Add some tokens for special characters and formatting
        special_chars = len(re.findall(r'[^\w\s]', text))
        tokens += special_chars // 4
        
        return max(1, tokens)  # Minimum 1 token
        
    def count_characters(self, text: str) -> Dict[str, int]:
        """Count various character statistics
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with character statistics
        """
        if not text:
            return {
                "total_chars": 0,
                "chars_no_spaces": 0,
                "words": 0,
                "lines": 0,
                "paragraphs": 0
            }
            
        return {
            "total_chars": len(text),
            "chars_no_spaces": len(text.replace(" ", "")),
            "words": len(text.split()),
            "lines": len(text.splitlines()),
            "paragraphs": len([p for p in text.split('\n\n') if p.strip()])
        }
        
    def estimate_cost(self, text: str, input_price_per_1k: float = 0.002, output_price_per_1k: float = 0.002) -> Dict[str, float]:
        """Estimate API cost for the text
        
        Args:
            text: Text to estimate cost for
            input_price_per_1k: Price per 1000 input tokens
            output_price_per_1k: Price per 1000 output tokens (for response)
            
        Returns:
            Dictionary with cost estimates
        """
        tokens = self.count_tokens_approximate(text)
        
        input_cost = (tokens / 1000) * input_price_per_1k
        
        # Assume output is roughly 20% of input length
        estimated_output_tokens = tokens * 0.2
        output_cost = (estimated_output_tokens / 1000) * output_price_per_1k
        
        total_cost = input_cost + output_cost
        
        return {
            "input_tokens": tokens,
            "estimated_output_tokens": int(estimated_output_tokens),
            "input_cost": round(input_cost, 6),
            "output_cost": round(output_cost, 6),
            "total_cost": round(total_cost, 6)
        }
        
    def analyze_text(self, text: str) -> Dict[str, Any]:
        """Comprehensive text analysis
        
        Args:
            text: Text to analyze
            
        Returns:
            Dictionary with comprehensive analysis
        """
        char_stats = self.count_characters(text)
        token_count = self.count_tokens_approximate(text)
        cost_estimate = self.estimate_cost(text)
        
        return {
            "model": self.model,
            "character_stats": char_stats,
            "token_count": token_count,
            "cost_estimate": cost_estimate,
            "text_length": len(text),
            "is_empty": len(text.strip()) == 0
        }
        
    def batch_analyze(self, texts: List[str]) -> Dict[str, Any]:
        """Analyze multiple texts in batch
        
        Args:
            texts: List of texts to analyze
            
        Returns:
            Dictionary with batch analysis results
        """
        if not texts:
            return {
                "total_texts": 0,
                "total_tokens": 0,
                "total_characters": 0,
                "total_cost": 0.0,
                "individual_results": []
            }
            
        individual_results = []
        total_tokens = 0
        total_characters = 0
        total_cost = 0.0
        
        for i, text in enumerate(texts):
            result = self.analyze_text(text)
            result["text_index"] = i
            individual_results.append(result)
            
            total_tokens += result["token_count"]
            total_characters += result["character_stats"]["total_chars"]
            total_cost += result["cost_estimate"]["total_cost"]
            
        return {
            "total_texts": len(texts),
            "total_tokens": total_tokens,
            "total_characters": total_characters,
            "total_cost": round(total_cost, 6),
            "average_tokens_per_text": round(total_tokens / len(texts), 2),
            "individual_results": individual_results
        }


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """Convenience function for token counting
    
    Args:
        text: Text to count tokens for
        model: Model name for token counting
        
    Returns:
        Approximate token count
    """
    counter = TokenCounter(model)
    return counter.count_tokens_approximate(text)


def analyze_text(text: str, model: str = "gpt-3.5-turbo") -> Dict[str, Any]:
    """Convenience function for text analysis
    
    Args:
        text: Text to analyze
        model: Model name for analysis
        
    Returns:
        Analysis results dictionary
    """
    counter = TokenCounter(model)
    return counter.analyze_text(text)

