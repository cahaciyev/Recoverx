"""Recovery destination screen with safety checks."""
from __future__ import annotations

import threading
from tkinter import filedialog

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..widgets import Banner, Card, Heading, ghost_button, primary_button
from ...core.devices import describe_size
from ...core import recovery


class RecoveryDestScreen(Screen):
    name = "recovery_dest"

    def build(self) -> None:
        self._dest = ""
        self._running = False

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=30, pady=(24, 8))
        Heading(top, "Recovery destination",
                "Choose a SAFE folder on a DIFFERENT disk than the source.").pack(anchor="w")

        card = Card(self)
        card.pack(fill="x", padx=30, pady=10)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=20)

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        self.path_entry = ctk.CTkEntry(row, placeholder_text="Select a destination folder...", height=38)
        self.path_entry.pack(side="left", fill="x", expand=True)
        ghost_button(row, "Browse...", self._browse, width=120).pack(side="left", padx=(10, 0))

        self.info_lbl = ctk.CTkLabel(inner, text="", font=theme.font(12), text_color=theme.MUTED,
                                     anchor="w", justify="left")
        self.info_lbl.pack(anchor="w", pady=(12, 0))

        self.same_disk_warn = Banner(self, "", kind="danger")
        self.same_disk_warn.pack(fill="x", padx=30, pady=6)
        self.same_disk_warn.pack_forget()

        self.space_warn = Banner(self, "", kind="warning")
        self.space_warn.pack(fill="x", padx=30, pady=6)
        self.space_warn.pack_forget()

        self.override_var = ctk.BooleanVar(value=False)
        self.override = ctk.CTkCheckBox(
            self, text="I understand the risk - allow recovery to the same disk (not recommended)",
            variable=self.override_var, command=self._validate, font=theme.font(12))

        # progress (hidden until running)
        self.prog_card = Card(self)
        ctk.CTkLabel(self.prog_card, text="Recovering...", font=theme.font(13, "bold")).pack(
            anchor="w", padx=16, pady=(12, 4))
        self.bar = ctk.CTkProgressBar(self.prog_card, height=14)
        self.bar.pack(fill="x", padx=16, pady=4)
        self.bar.set(0)
        self.prog_lbl = ctk.CTkLabel(self.prog_card, text="", font=theme.font(11),
                                     text_color=theme.MUTED)
        self.prog_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(side="bottom", fill="x", padx=30, pady=(8, 20))
        ghost_button(nav, "< Back", lambda: self.app.show("results"), width=120).pack(side="left")
        self.start_btn = primary_button(nav, "Start Recovery", self._start, width=200, state="disabled")
        self.start_btn.pack(side="right")

    def on_show(self) -> None:
        sel = self.app.pending_recovery or []
        total = recovery.estimate_total(sel)
        self.info_lbl.configure(text=f"{len(sel)} file(s) selected   |   estimated size {describe_size(total)}")
        self._dest = ""
        self.path_entry.delete(0, "end")
        self.override.pack_forget()
        self.same_disk_warn.pack_forget()
        self.space_warn.pack_forget()
        self.prog_card.pack_forget()
        self.start_btn.configure(state="disabled")

    def _browse(self) -> None:
        path = filedialog.askdirectory(title="Select recovery destination")
        if path:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, path)
            self._dest = path
            self._validate()

    def _validate(self) -> None:
        dest = self.path_entry.get().strip()
        self._dest = dest
        if not dest:
            self.start_btn.configure(state="disabled")
            return
        src_device = self.app.source.get("device") if self.app.source else None
        on_source = recovery.is_destination_on_source(dest, src_device)
        free = recovery.free_space(dest)
        needed = recovery.estimate_total(self.app.pending_recovery or [])

        self.info_lbl.configure(
            text=f"{len(self.app.pending_recovery or [])} file(s)   |   need {describe_size(needed)}"
                 f"   |   free {describe_size(free)}")

        ok = True
        if on_source:
            self.same_disk_warn.set_text(
                "DANGER: This destination is on the SOURCE disk. Writing here can overwrite the very "
                "data you are trying to recover. Choose another disk.")
            self.same_disk_warn.pack(fill="x", padx=30, pady=6)
            self.override.pack(anchor="w", padx=30, pady=(0, 4))
            ok = self.override_var.get()
        else:
            self.same_disk_warn.pack_forget()
            self.override.pack_forget()

        if needed > free:
            self.space_warn.set_text(
                f"Not enough free space: need {describe_size(needed)}, only {describe_size(free)} available.")
            self.space_warn.pack(fill="x", padx=30, pady=6)
            ok = False
        else:
            self.space_warn.pack_forget()

        self.start_btn.configure(state="normal" if ok else "disabled")

    def _start(self) -> None:
        if self._running:
            return
        self._running = True
        self.start_btn.configure(state="disabled")
        self.prog_card.pack(fill="x", padx=30, pady=6)
        sel = self.app.pending_recovery or []
        src = self.app.source
        self.app.recovery_cancel.clear()

        def on_progress(i, total, name):
            def upd():
                self.bar.set(i / total if total else 0)
                self.prog_lbl.configure(text=f"{i}/{total}  -  {name}")
            self.after(0, upd)

        def worker():
            try:
                result = recovery.recover_files(
                    source_path=src["path"], source_size=src["size"], sector_size=src["sector"],
                    candidates=sel, dest_dir=self._dest, db=self.app.db,
                    session_id=self.app.scanner.session_id if self.app.scanner else "",
                    cancel=self.app.recovery_cancel, on_progress=on_progress,
                    on_log=lambda m: self.app.scan_logs.append(m),
                )
                self.after(0, lambda: self._done(result))
            except Exception as exc:  # noqa: BLE001
                self.after(0, lambda: self._error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, result) -> None:
        self._running = False
        self.app.recovery_result = result
        self.app.show("complete")

    def _error(self, msg: str) -> None:
        self._running = False
        self.space_warn.set_text(f"Recovery error: {msg}")
        self.space_warn.pack(fill="x", padx=30, pady=6)
        self.start_btn.configure(state="normal")
