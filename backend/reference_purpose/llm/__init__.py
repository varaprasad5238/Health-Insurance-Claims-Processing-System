"""
LLM Configuration

Provides LLM configuration for language model API connections.
Used by Context Store (module identification) and App Modernization (agents).
"""

from src.platform.llm.config import LLMConfig, get_llm_config

__all__ = ["LLMConfig", "get_llm_config"]
