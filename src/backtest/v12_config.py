"""Compatibility shim — v1.2 설정은 ``src.v12.config``."""
from src.v12.config import V12Config, load_v12_config, slippage_pair_from_multi_yaml

__all__ = ["V12Config", "load_v12_config", "slippage_pair_from_multi_yaml"]
