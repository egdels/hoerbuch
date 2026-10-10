"""Kleine Helfer ohne Abhängigkeiten."""
from __future__ import annotations

def fmt_dur(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}"
