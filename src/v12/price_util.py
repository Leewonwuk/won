"""Resolve USDT/USDC leg mids for v1.2 from CSV row + config."""
from __future__ import annotations


def v12_leg_mids(row: dict, cfg) -> tuple[float, float]:
    """Return (mid_usdt, mid_usdc) for signal, equity, and execution price proxy."""
    if getattr(cfg, "price_mode", "close") == "hl_mid":
        try:
            hut = float(row["btc_usdt_high"])
            lut = float(row["btc_usdt_low"])
            huc = float(row["btc_usdc_high"])
            luc = float(row["btc_usdc_low"])
            if min(hut, lut, huc, luc) > 0:
                return (hut + lut) / 2.0, (huc + luc) / 2.0
        except (KeyError, ValueError, TypeError):
            pass
    return float(row["btc_usdt_close"]), float(row["btc_usdc_close"])
