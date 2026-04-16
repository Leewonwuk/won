"""Compatibility shim — v1.2 allocator는 ``src.v12.allocator``."""
from src.v12.allocator import DecisionV12, decide_v12

__all__ = ["DecisionV12", "decide_v12"]
