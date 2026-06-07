"""Reusable UI widgets."""
from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from . import theme


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("fg_color", theme.CARD)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault("border_color", theme.CARD_BORDER)
        kwargs.setdefault("corner_radius", 12)
        super().__init__(master, **kwargs)


class Banner(ctk.CTkFrame):
    """A coloured info/warning/danger banner with an icon glyph."""

    def __init__(self, master, text: str, kind: str = "warning"):
        bg = theme.WARN_BG if kind != "danger" else theme.DANGER_BG
        super().__init__(master, fg_color=bg, corner_radius=10)
        glyph = {"warning": "!", "danger": "X", "info": "i"}.get(kind, "!")
        color = theme.WARNING if kind == "warning" else (theme.DANGER if kind == "danger" else theme.ACCENT)
        ctk.CTkLabel(self, text=glyph, font=theme.font(15, "bold"), text_color=color,
                     width=24).pack(side="left", padx=(12, 6), pady=8)
        self.label = ctk.CTkLabel(self, text=text, font=theme.font(12), justify="left",
                                  wraplength=820, anchor="w")
        self.label.pack(side="left", fill="x", expand=True, padx=(0, 12), pady=8)

    def set_text(self, text: str) -> None:
        self.label.configure(text=text)


class StatChip(ctk.CTkFrame):
    def __init__(self, master, label: str, value: str = "-"):
        super().__init__(master, fg_color=theme.SURFACE, corner_radius=10)
        ctk.CTkLabel(self, text=label, font=theme.font(11), text_color=theme.MUTED).pack(
            anchor="w", padx=14, pady=(10, 0))
        self.value = ctk.CTkLabel(self, text=value, font=theme.font(20, "bold"))
        self.value.pack(anchor="w", padx=14, pady=(0, 10))

    def set(self, value: str) -> None:
        self.value.configure(text=value)


def primary_button(master, text: str, command: Callable, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("fg_color", theme.ACCENT)
    kwargs.setdefault("hover_color", theme.ACCENT_HOVER)
    kwargs.setdefault("height", 40)
    kwargs.setdefault("corner_radius", 9)
    kwargs.setdefault("font", theme.font(13, "bold"))
    return ctk.CTkButton(master, text=text, command=command, **kwargs)


def ghost_button(master, text: str, command: Callable, **kwargs) -> ctk.CTkButton:
    kwargs.setdefault("fg_color", "transparent")
    kwargs.setdefault("border_width", 1)
    kwargs.setdefault("border_color", theme.CARD_BORDER)
    kwargs.setdefault("text_color", theme.MUTED)
    kwargs.setdefault("hover_color", theme.SURFACE)
    kwargs.setdefault("height", 40)
    kwargs.setdefault("corner_radius", 9)
    kwargs.setdefault("font", theme.font(13))
    return ctk.CTkButton(master, text=text, command=command, **kwargs)


class Heading(ctk.CTkFrame):
    def __init__(self, master, title: str, subtitle: str = ""):
        super().__init__(master, fg_color="transparent")
        ctk.CTkLabel(self, text=title, font=theme.font(24, "bold"), anchor="w").pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(self, text=subtitle, font=theme.font(13), text_color=theme.MUTED,
                         anchor="w", justify="left").pack(anchor="w", pady=(2, 0))
