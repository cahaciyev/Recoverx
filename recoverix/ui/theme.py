"""Theme constants and helpers for a clean, professional desktop look."""
from __future__ import annotations

import customtkinter as ctk

# Accent / semantic colours (tuples = (light, dark))
ACCENT = "#2563eb"
ACCENT_HOVER = "#1d4ed8"
SUCCESS = "#16a34a"
WARNING = "#d97706"
DANGER = "#dc2626"
MUTED = ("#6b7280", "#9ca3af")

CARD = ("#ffffff", "#1f2430")
CARD_BORDER = ("#e5e7eb", "#2d3340")
SURFACE = ("#f3f4f6", "#161a22")
WARN_BG = ("#fef3c7", "#3a2e12")
DANGER_BG = ("#fee2e2", "#3a1717")

# Recoverability -> colour
REC_COLORS = {
    "Excellent": SUCCESS,
    "Good": "#22c55e",
    "Average": WARNING,
    "Poor": DANGER,
    "Unknown": "#6b7280",
}


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(family="Segoe UI", size=size, weight=weight)


def init_appearance(mode: str = "dark") -> None:
    ctk.set_appearance_mode(mode)
    ctk.set_default_color_theme("blue")


def toggle_mode() -> str:
    new = "light" if ctk.get_appearance_mode().lower() == "dark" else "dark"
    ctk.set_appearance_mode(new)
    return new
