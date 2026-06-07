"""Results browser with filters, selection and preview."""
from __future__ import annotations

import io

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..widgets import Card, Heading, ghost_button, primary_button
from ...core.devices import describe_size
from ...core.recovery import read_preview

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:  # noqa: BLE001
    _HAS_PIL = False

MAX_ROWS = 600
_TEXT_EXT = {"txt", "csv", "json", "xml", "log", "rtf"}


class ResultsScreen(Screen):
    name = "results"

    def build(self) -> None:
        self._all = []
        self._filtered = []
        self._selected: set[str] = set()
        self._loaded_session: str = ""   # session_id of currently loaded scan
        self._row_vars: dict[str, ctk.BooleanVar] = {}
        self._preview_img = None

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(20, 6))
        self.heading = Heading(top, "Results", "")
        self.heading.pack(side="left", anchor="w")

        # filter bar
        fbar = ctk.CTkFrame(self, fg_color="transparent")
        fbar.pack(fill="x", padx=24, pady=(0, 6))
        self.search = ctk.CTkEntry(fbar, placeholder_text="Search filename...", width=240, height=34)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", lambda _e: self._apply())
        self.ext_menu = ctk.CTkOptionMenu(fbar, values=["All types"], width=140, height=34,
                                          command=lambda _v: self._apply())
        self.ext_menu.pack(side="left", padx=8)
        self.rec_menu = ctk.CTkOptionMenu(
            fbar, values=["All", "Excellent", "Good", "Average", "Poor", "Unknown"],
            width=130, height=34, command=lambda _v: self._apply())
        self.rec_menu.pack(side="left", padx=(0, 8))
        self.cat_menu = ctk.CTkOptionMenu(fbar, values=["All categories"], width=150, height=34,
                                          command=lambda _v: self._apply())
        self.cat_menu.pack(side="left")
        ghost_button(fbar, "Select all", self._select_all_visible, width=100).pack(side="right")
        ghost_button(fbar, "Clear", self._clear_selection, width=80).pack(side="right", padx=6)

        # body: list + preview
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=6)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        self.list = ctk.CTkScrollableFrame(body, fg_color=theme.SURFACE, corner_radius=12)
        self.list.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        self.preview = Card(body)
        self.preview.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.preview, text="Preview", font=theme.font(13, "bold")).pack(
            anchor="w", padx=14, pady=(12, 4))
        self.preview_img_lbl = ctk.CTkLabel(self.preview, text="Select a file to preview")
        self.preview_img_lbl.pack(padx=14, pady=6)
        self.preview_text = ctk.CTkTextbox(self.preview, font=theme.font(11), height=200)
        self.preview_text.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.preview_text.configure(state="disabled")

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=(6, 18))
        ghost_button(nav, "< New Scan", lambda: self.app.show("welcome"), width=140).pack(side="left")
        self.count_lbl = ctk.CTkLabel(nav, text="0 selected", font=theme.font(12),
                                      text_color=theme.MUTED)
        self.count_lbl.pack(side="left", padx=16)
        self.recover_btn = primary_button(nav, "Recover Selected >", self._recover, width=200,
                                          state="disabled")
        self.recover_btn.pack(side="right")

    def on_show(self) -> None:
        sc = self.app.scanner
        same_scan = sc is not None and sc.session_id == self._loaded_session

        if same_scan:
            # Coming back from recovery — keep results & filters, just clear selection.
            self._selected.clear()
            self._update_count()
            self._render()          # re-render rows so checkboxes reflect cleared state
            return

        # New scan: full reload.
        self._loaded_session = sc.session_id if sc else ""
        self._all = list(sc.results) if sc else []
        self._selected.clear()
        exts = sorted({c.extension for c in self._all})
        cats = sorted({c.category for c in self._all})
        self.ext_menu.configure(values=["All types"] + exts)
        self.ext_menu.set("All types")
        self.cat_menu.configure(values=["All categories"] + cats)
        self.cat_menu.set("All categories")
        self.rec_menu.set("All")
        self.search.delete(0, "end")
        self.heading.winfo_children()[0].configure(
            text=f"Results - {len(self._all)} file(s) found")
        self._apply()

    # -- filtering ---------------------------------------------------------
    def _apply(self) -> None:
        q = self.search.get().strip().lower()
        ext = self.ext_menu.get()
        rec = self.rec_menu.get()
        cat = self.cat_menu.get()
        res = []
        for c in self._all:
            if q and q not in c.name.lower():
                continue
            if ext != "All types" and c.extension != ext:
                continue
            if rec != "All" and c.recoverability != rec:
                continue
            if cat != "All categories" and c.category != cat:
                continue
            res.append(c)
        self._filtered = res
        self._render()

    def _render(self) -> None:
        for w in self.list.winfo_children():
            w.destroy()
        self._row_vars = {}
        shown = self._filtered[:MAX_ROWS]
        for c in shown:
            self._render_row(c)
        if len(self._filtered) > MAX_ROWS:
            ctk.CTkLabel(self.list, text=f"Showing first {MAX_ROWS} of {len(self._filtered)}. "
                         "Use filters to narrow down.", font=theme.font(11),
                         text_color=theme.MUTED).pack(pady=8)
        self._update_count()

    def _render_row(self, c) -> None:
        row = ctk.CTkFrame(self.list, fg_color=theme.CARD, corner_radius=8)
        row.pack(fill="x", padx=6, pady=3)
        var = ctk.BooleanVar(value=c.id in self._selected)
        self._row_vars[c.id] = var

        def toggle():
            if var.get():
                self._selected.add(c.id)
            else:
                self._selected.discard(c.id)
            self._update_count()

        cb = ctk.CTkCheckBox(row, text="", width=24, variable=var, command=toggle)
        cb.pack(side="left", padx=(10, 4), pady=8)

        info = ctk.CTkFrame(row, fg_color="transparent")
        info.pack(side="left", fill="x", expand=True)
        name = ctk.CTkLabel(info, text=c.name, font=theme.font(12, "bold"), anchor="w")
        name.pack(anchor="w")
        sub = ctk.CTkLabel(info, text=f"{c.category} / {c.extension}   |   {describe_size(c.size_bytes)}"
                           f"   |   offset {c.offset_start:,}",
                           font=theme.font(10), text_color=theme.MUTED, anchor="w")
        sub.pack(anchor="w")

        badge = ctk.CTkLabel(row, text=c.recoverability, font=theme.font(10, "bold"),
                             text_color="#ffffff",
                             fg_color=theme.REC_COLORS.get(c.recoverability, "#6b7280"),
                             corner_radius=6, width=78, height=22)
        badge.pack(side="right", padx=10)

        for w in (info, name, sub):
            w.bind("<Button-1>", lambda _e, cand=c: self._show_preview(cand))

    # -- selection ---------------------------------------------------------
    def _select_all_visible(self) -> None:
        for c in self._filtered[:MAX_ROWS]:
            self._selected.add(c.id)
            if c.id in self._row_vars:
                self._row_vars[c.id].set(True)
        self._update_count()

    def _clear_selection(self) -> None:
        self._selected.clear()
        for var in self._row_vars.values():
            var.set(False)
        self._update_count()

    def _update_count(self) -> None:
        n = len(self._selected)
        self.count_lbl.configure(text=f"{n} selected")
        self.recover_btn.configure(state="normal" if n else "disabled")

    def selected_candidates(self) -> list:
        ids = self._selected
        return [c for c in self._all if c.id in ids]

    # -- preview -----------------------------------------------------------
    def _show_preview(self, cand) -> None:
        src = self.app.source
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_img_lbl.configure(image=None, text="")
        self._preview_img = None

        meta = (f"Name: {cand.name}\nType: {cand.category} / {cand.extension}\n"
                f"Size: {describe_size(cand.size_bytes)}\n"
                f"Confidence: {cand.confidence}\nRecoverability: {cand.recoverability}\n"
                f"Offset: {cand.offset_start:,} - {cand.offset_end:,}\n")

        try:
            data = read_preview(src["path"], src["size"], src["sector"], cand, max_bytes=2_000_000)
        except Exception as exc:  # noqa: BLE001
            data = b""
            meta += f"\n[Preview unavailable: {exc}]"

        if cand.category == "Images" and _HAS_PIL and data:
            try:
                img = Image.open(io.BytesIO(data))
                img.thumbnail((320, 320))
                self._preview_img = ctk.CTkImage(light_image=img, dark_image=img,
                                                 size=img.size)
                self.preview_img_lbl.configure(image=self._preview_img, text="")
            except Exception:  # noqa: BLE001
                self.preview_img_lbl.configure(text="[Image could not be decoded]")
        elif cand.extension in _TEXT_EXT and data:
            text = data[:8000].decode("utf-8", errors="replace")
            meta += "\n--- Content preview ---\n" + text
            self.preview_img_lbl.configure(text="")
        else:
            self.preview_img_lbl.configure(text="No visual preview for this type")

        self.preview_text.insert("1.0", meta)
        self.preview_text.configure(state="disabled")

    # -- recover -----------------------------------------------------------
    def _recover(self) -> None:
        sel = self.selected_candidates()
        if not sel:
            return
        self.app.pending_recovery = sel
        self.app.show("recovery_dest")
