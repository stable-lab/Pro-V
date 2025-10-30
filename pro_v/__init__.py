"""
Pro-V: An Efficient Program Generation Multi-Agent System for Automatic RTL Verification

This package provides a multi-agent system for automatic RTL verification,
including testbench generation, Python checking, and simulation tools.
"""

__version__ = "1.0.0"
__author__ = "Pro-V Team"

# Import main modules
from . import agent
from . import utils
from . import tools
from . import back_up

__all__ = [
    "agent",
    "utils", 
    "tools",
    "back_up"
]

