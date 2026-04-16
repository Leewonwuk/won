#!/usr/bin/env python3
"""One-shot: merge v1.2 live_v2 keys into ~/arb/.env (idempotent). Run on EC2."""
from __future__ import annotations

from pathlib import Path

p = Path.home() / "arb" / ".env"
if not p.is_file():
    raise SystemExit(f"missing: {p}")

keys = {
    "ARB_SERVICE_LINE": "v1.2",
    "ARB_APP_VERSION": "v1.2",
    "ARB_V12_LIVE": "true",
    "ARB_V12_CONFIG": "configs/v12/v12_btc_v2.yaml",
    "ARB_V12_POLL": "0.5",
    "ARB_V12_TIMEOUT": "15",
    "ARB_CLOUD_HOST_LABEL": "ec2-arb-v1.2",
}
lines = p.read_text(encoding="utf-8").splitlines()
out = [ln for ln in lines if not any(ln.startswith(k + "=") for k in keys)]
out.extend([f"{k}={v}" for k, v in keys.items()])
p.write_text("\n".join(out) + "\n", encoding="utf-8")
print("patched", p)
