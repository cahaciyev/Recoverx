"""Base screen class for navigation."""
from __future__ import annotations

import customtkinter as ctk


class Screen(ctk.CTkFrame):
    """A navigable screen. Subclasses implement build() and may override on_show()."""

    name: str = "screen"

    def __init__(self, master, app):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.build()

    def build(self) -> None:  # pragma: no cover - UI
        raise NotImplementedError

    def on_show(self) -> None:
        """Called every time the screen becomes visible."""
