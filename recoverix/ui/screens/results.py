"""Results browser: a virtualized file table with filters, sort, selection,
preview and an automatic openability check.

Why a ``ttk.Treeview``?
-----------------------
A scan can return thousands of files. Building one CustomTkinter widget per row
froze the window ("Not responding") because creating/laying out hundreds of
widgets costs seconds. ``ttk.Treeview`` is *virtualized* — it only renders the
visible rows — so inserting thousands of items and sorting them is effectively
instant, and the UI never blocks.
"""
from __future__ import annotations

import io
import threading
import tkinter as tk
from tkinter import TclError, ttk

import customtkinter as ctk

from .. import theme
from ..base import Screen
from ..i18n import t
from ..widgets import Card, Heading, ghost_button, primary_button
from ...core.devices import describe_size
from ...core.recovery import read_preview
from ...core.validation import CORRUPT, OK, PARTIAL, UNKNOWN, validate

try:
    from PIL import Image
    _HAS_PIL = True
except Exception:  # noqa: BLE001
    _HAS_PIL = False

MAX_ITEMS = 20000        # safety cap on rows inserted into the table
_TEXT_EXT = {"txt", "csv", "json", "xml", "log", "rtf"}

# Bytes read per file when previewing / verifying openability.
_PREVIEW_READ = 24 * 1024 * 1024
_VERIFY_READ = 48 * 1024 * 1024
_VERIFY_TICK_MS = 300
_SEARCH_DEBOUNCE_MS = 250

_VERIFIABLE = {"Images", "Documents"}

_OPEN_LABEL = {OK: "Opens", PARTIAL: "Partial", CORRUPT: "Won't open"}
_OPEN_TAG = {OK: "ok", PARTIAL: "partial", CORRUPT: "corrupt"}
_OPEN_TEXT = {
    OK: "Yes - opens correctly",
    PARTIAL: "Partially - opens but truncated",
    CORRUPT: "No - cannot be opened",
    UNKNOWN: "Not checked for this type",
}

_REC_RANK = {"Excellent": 0, "Good": 1, "Average": 2, "Poor": 3, "Unknown": 4}
_OPEN_RANK = {OK: 0, PARTIAL: 1, "": 2, UNKNOWN: 3, CORRUPT: 4}

_CHECKED, _UNCHECKED = "☑", "☐"
_TXT_COLOR = ("#1a1f29", "#e6e6e6")   # primary table text (light, dark)


def _open_text(status: str) -> str:
    return t(_OPEN_TEXT.get(status, "Unknown"))


def _open_label(status: str) -> str:
    return t(_OPEN_LABEL.get(status, "")) if status in _OPEN_LABEL else ""


def _c(color):
    """Resolve a (light, dark) theme tuple to the current appearance mode."""
    if isinstance(color, (tuple, list)):
        return color[1] if ctk.get_appearance_mode() == "Dark" else color[0]
    return color


class ResultsScreen(Screen):
    name = "results"

    def build(self) -> None:
        self._all = []
        self._filtered = []
        self._by_id: dict = {}
        self._selected: set[str] = set()       # checked candidate ids (to recover)
        self._loaded_session: str = ""
        self._sort_col: str | None = None
        self._sort_rev = False
        self._search_after_id = None
        self._preview_img = None

        self._verifying = False
        self._verify_gen = 0
        self._verify_cancel: threading.Event | None = None
        self._verify_done = 0
        self._verify_total = 0

        # Logical keys for data menus (display is translated; logic stays English).
        self._rec_keys = ["All", "Excellent", "Good", "Average", "Poor", "Unknown"]
        self._open_keys = ["Open: all", "Openable", "Won't open", "Unverified"]

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(18, 4))
        self.heading = Heading(top, t("Results"), "")
        self.heading.pack(side="left", anchor="w")

        # filter bar
        fbar = ctk.CTkFrame(self, fg_color="transparent")
        fbar.pack(fill="x", padx=24, pady=(0, 4))
        self.search = ctk.CTkEntry(fbar, placeholder_text=t("Search filename..."), width=220, height=34)
        self.search.pack(side="left")
        self.search.bind("<KeyRelease>", self._on_search_key)
        self.ext_menu = ctk.CTkOptionMenu(fbar, values=[t("All types")], width=120, height=34,
                                          command=lambda _v: self._apply())
        self.ext_menu.pack(side="left", padx=(8, 0))
        self.rec_menu = ctk.CTkOptionMenu(
            fbar, values=[t(k) for k in self._rec_keys],
            width=120, height=34, command=lambda _v: self._apply())
        self.rec_menu.pack(side="left", padx=(8, 0))
        self.cat_menu = ctk.CTkOptionMenu(fbar, values=[t("All categories")], width=140, height=34,
                                          command=lambda _v: self._apply())
        self.cat_menu.pack(side="left", padx=(8, 0))
        self.open_menu = ctk.CTkOptionMenu(
            fbar, values=[t(k) for k in self._open_keys],
            width=120, height=34, command=lambda _v: self._apply())
        self.open_menu.pack(side="left", padx=(8, 0))

        # action bar
        abar = ctk.CTkFrame(self, fg_color="transparent")
        abar.pack(fill="x", padx=24, pady=(0, 6))
        self.shown_lbl = ctk.CTkLabel(abar, text="", font=theme.font(11), text_color=theme.MUTED)
        self.shown_lbl.pack(side="left")
        ghost_button(abar, t("Select all"), self._select_all_visible, width=100).pack(side="right")
        ghost_button(abar, t("Clear"), self._clear_selection, width=80).pack(side="right", padx=6)
        self.verify_btn = ghost_button(abar, t("Re-check openability"), self._start_verify, width=180)
        self.verify_btn.pack(side="right", padx=6)

        # body: table + preview
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=6)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        table = ctk.CTkFrame(body, fg_color=theme.SURFACE, corner_radius=12)
        table.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        table.grid_rowconfigure(0, weight=1)
        table.grid_columnconfigure(0, weight=1)

        cols = ("sel", "name", "type", "size", "rec", "open")
        self.tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="browse",
                                 style="Recoverix.Treeview")
        headings = {"sel": "", "name": t("File name"), "type": t("Type"), "size": t("Size"),
                    "rec": t("Recoverability"), "open": t("Opens")}
        widths = {"sel": 40, "name": 300, "type": 120, "size": 90, "rec": 120, "open": 100}
        anchors = {"sel": "center", "size": "e"}
        for col in cols:
            cmd = self._toggle_all_visible if col == "sel" else (lambda c=col: self._sort_by_col(c))
            self.tree.heading(col, text=headings[col], command=cmd,
                              anchor="center" if col == "sel" else "w")
            self.tree.column(col, width=widths[col], anchor=anchors.get(col, "w"),
                             stretch=(col == "name"), minwidth=40)
        self.tree.grid(row=0, column=0, sticky="nsew", padx=2, pady=2)
        sb = ctk.CTkScrollbar(table, command=self.tree.yview)
        sb.grid(row=0, column=1, sticky="ns", pady=4)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.bind("<ButtonRelease-1>", self._on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Double-1>", self._on_tree_double)
        self.tree.bind("<space>", self._on_space)
        self._setup_style()

        self.preview = Card(body)
        self.preview.grid(row=0, column=1, sticky="nsew")
        ctk.CTkLabel(self.preview, text=t("Preview"), font=theme.font(13, "bold"),
                     fg_color=theme.CARD).pack(anchor="w", padx=14, pady=(12, 4))
        self.preview_img_lbl = ctk.CTkLabel(self.preview, text=t("Select a file to preview"),
                                            fg_color=theme.CARD)
        self.preview_img_lbl.pack(padx=14, pady=6)
        self.preview_text = ctk.CTkTextbox(self.preview, font=theme.font(11), height=200)
        self.preview_text.pack(fill="both", expand=True, padx=12, pady=(4, 12))
        self.preview_text.configure(state="disabled")

        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", padx=24, pady=(6, 18))
        ghost_button(nav, f"< {t('New Scan')}", lambda: self.app.show("welcome"), width=140).pack(side="left")
        self.count_lbl = ctk.CTkLabel(nav, text=t("{n} selected", n=0), font=theme.font(12),
                                      text_color=theme.MUTED)
        self.count_lbl.pack(side="left", padx=16)
        self.recover_btn = primary_button(nav, f"{t('Recover Selected')} >", self._recover, width=200,
                                          state="disabled")
        self.recover_btn.pack(side="right")

    # -- ttk styling -------------------------------------------------------
    def _setup_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")   # 'clam' honours custom colours reliably
        except TclError:
            pass
        card, surface, txt = _c(theme.CARD), _c(theme.SURFACE), _c(_TXT_COLOR)
        style.configure("Recoverix.Treeview", background=card, fieldbackground=card,
                        foreground=txt, rowheight=30, borderwidth=0,
                        font=("Segoe UI", 10))
        style.map("Recoverix.Treeview",
                  background=[("selected", theme.ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.configure("Recoverix.Treeview.Heading", background=surface, foreground=txt,
                        relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Recoverix.Treeview.Heading", background=[("active", surface)])
        dark = ctk.get_appearance_mode() == "Dark"
        self.tree.tag_configure("ok", background="#16331f" if dark else "#e7f6ec")
        self.tree.tag_configure("partial", background="#3a2e12" if dark else "#fef3c7")
        self.tree.tag_configure("corrupt", background="#3a1717" if dark else "#fee2e2")

    def on_theme_changed(self) -> None:
        self._setup_style()

    # -- navigation --------------------------------------------------------
    def on_show(self) -> None:
        sc = self.app.scanner
        same_scan = sc is not None and sc.session_id == self._loaded_session

        if same_scan:
            self._selected.clear()
            self._populate_tree()
            self._start_verify(auto=True)
            return

        self._cancel_verify()
        self._loaded_session = sc.session_id if sc else ""
        self._all = list(sc.results) if sc else []
        self._by_id = {c.id: c for c in self._all}
        self._selected.clear()
        self._sort_col, self._sort_rev = None, False
        exts = sorted({c.extension for c in self._all})
        cats = sorted({c.category for c in self._all})
        self.ext_menu.configure(values=[t("All types")] + exts)
        self.ext_menu.set(t("All types"))
        self.cat_menu.configure(values=[t("All categories")] + cats)
        self.cat_menu.set(t("All categories"))
        self.rec_menu.set(t("All"))
        self.open_menu.set(t("Open: all"))
        self.search.delete(0, "end")
        self.heading.winfo_children()[0].configure(
            text=t("Results - {n} file(s) found", n=len(self._all)))
        self._apply()
        self._start_verify(auto=True)

    # -- filtering & sorting ----------------------------------------------
    def _on_search_key(self, _event) -> None:
        if self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
            except (TclError, ValueError):
                pass
        self._search_after_id = self.after(_SEARCH_DEBOUNCE_MS, self._apply)

    def _sel_key(self, menu, keys) -> str:
        """Map a translated menu selection back to its English logic key."""
        disp = menu.get()
        for k in keys:
            if t(k) == disp:
                return k
        return disp

    def _apply(self) -> None:
        self._search_after_id = None
        q = self.search.get().strip().lower()
        ext = self.ext_menu.get()
        rec = self._sel_key(self.rec_menu, self._rec_keys)
        cat = self.cat_menu.get()
        opn = self._sel_key(self.open_menu, self._open_keys)
        res = []
        for c in self._all:
            if q and q not in c.name.lower():
                continue
            if ext != t("All types") and c.extension != ext:
                continue
            if rec != "All" and c.recoverability != rec:
                continue
            if cat != t("All categories") and c.category != cat:
                continue
            if opn == "Openable" and c.open_status not in (OK, PARTIAL):
                continue
            if opn == "Won't open" and c.open_status != CORRUPT:
                continue
            if opn == "Unverified" and c.open_status:
                continue
            res.append(c)
        if self._sort_col:
            res.sort(key=lambda c: self._sort_value(c), reverse=self._sort_rev)
        self._filtered = res
        self._populate_tree()

    def _sort_value(self, c):
        col = self._sort_col
        if col == "name":
            return c.name.lower()
        if col == "type":
            return (c.category, c.extension)
        if col == "size":
            return c.size_bytes
        if col == "rec":
            return _REC_RANK.get(c.recoverability, 9)
        if col == "open":
            return _OPEN_RANK.get(c.open_status, 5)
        return c.offset_start

    def _sort_by_col(self, col: str) -> None:
        if self._sort_col == col:
            self._sort_rev = not self._sort_rev
        else:
            self._sort_col, self._sort_rev = col, (col == "size")  # size: largest first
        self._apply()

    # -- table population --------------------------------------------------
    def _populate_tree(self) -> None:
        tree = self.tree
        tree.delete(*tree.get_children(""))
        shown = self._filtered[:MAX_ITEMS]
        for c in shown:
            glyph = _CHECKED if c.id in self._selected else _UNCHECKED
            tag = _OPEN_TAG.get(c.open_status)
            tree.insert("", "end", iid=c.id,
                        values=(glyph, c.name, f"{c.category} / .{c.extension}",
                                describe_size(c.size_bytes), c.recoverability,
                                _open_label(c.open_status)),
                        tags=((tag,) if tag else ()))
        self._update_count()
        self._update_shown_label(len(shown))

    def _refresh_tree_status(self) -> None:
        """Update the Opens column + row colour from candidate open_status."""
        tree = self.tree
        for iid in tree.get_children(""):
            c = self._by_id.get(iid)
            if c is None:
                continue
            tree.set(iid, "open", _open_label(c.open_status))
            tag = _OPEN_TAG.get(c.open_status)
            tree.item(iid, tags=((tag,) if tag else ()))

    def _update_shown_label(self, shown_count: int) -> None:
        total = len(self._all)
        if shown_count >= len(self._filtered) and len(self._filtered) == total:
            self.shown_lbl.configure(text=t("{n} file(s)", n=f"{total:,}"))
        elif shown_count < len(self._filtered):
            self.shown_lbl.configure(text=t("Showing first {shown} of {total}", shown=f"{shown_count:,}", total=f"{len(self._filtered):,}"))
        else:
            self.shown_lbl.configure(text=t("Showing {shown} of {total}", shown=f"{len(self._filtered):,}", total=f"{total:,}"))

    # -- selection (checkboxes) -------------------------------------------
    def _toggle_item(self, iid: str) -> None:
        if not iid or not self.tree.exists(iid):
            return
        if iid in self._selected:
            self._selected.discard(iid)
            self.tree.set(iid, "sel", _UNCHECKED)
        else:
            self._selected.add(iid)
            self.tree.set(iid, "sel", _CHECKED)
        self._update_count()

    def _toggle_all_visible(self) -> None:
        children = self.tree.get_children("")
        # if everything visible is checked, clear; else select all visible
        all_checked = all(i in self._selected for i in children) and children
        for iid in children:
            if all_checked:
                self._selected.discard(iid)
                self.tree.set(iid, "sel", _UNCHECKED)
            else:
                self._selected.add(iid)
                self.tree.set(iid, "sel", _CHECKED)
        self._update_count()

    def _select_all_visible(self) -> None:
        for iid in self.tree.get_children(""):
            self._selected.add(iid)
            self.tree.set(iid, "sel", _CHECKED)
        self._update_count()

    def _clear_selection(self) -> None:
        self._selected.clear()
        for iid in self.tree.get_children(""):
            self.tree.set(iid, "sel", _UNCHECKED)
        self._update_count()

    def _on_tree_click(self, event) -> None:
        if self.tree.identify("region", event.x, event.y) != "cell":
            return
        if self.tree.identify_column(event.x) == "#1":   # the checkbox column
            iid = self.tree.identify_row(event.y)
            if iid:
                self._toggle_item(iid)

    def _on_tree_double(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            self._toggle_item(iid)

    def _on_space(self, _event) -> str:
        sel = self.tree.selection()
        if sel:
            self._toggle_item(sel[0])
        return "break"

    def _on_tree_select(self, _event) -> None:
        sel = self.tree.selection()
        if sel:
            c = self._by_id.get(sel[0])
            if c is not None:
                self._show_preview(c)

    def _update_count(self) -> None:
        n = len(self._selected)
        self.count_lbl.configure(text=t("{n} selected", n=n))
        self.recover_btn.configure(state="normal" if n else "disabled")

    def selected_candidates(self) -> list:
        return [self._by_id[i] for i in self._selected if i in self._by_id]

    # -- openability verification (background, batched) -------------------
    def _start_verify(self, auto: bool = False) -> None:
        src = self.app.source
        if not src:
            return
        if self._verify_cancel is not None:
            self._verify_cancel.set()
        self._verify_gen += 1
        gen = self._verify_gen
        cancel = threading.Event()
        self._verify_cancel = cancel

        seen: set[str] = set()
        work = []
        for c in self._filtered + self._all:   # visible files first
            if c.id in seen or c.category not in _VERIFIABLE or c.size_bytes <= 0:
                continue
            if auto and c.open_status:
                continue
            seen.add(c.id)
            work.append(c)
        if not work:
            self.verify_btn.configure(text=t("Re-check openability"), state="normal")
            return

        self._verify_total = len(work)
        self._verify_done = 0
        self._verifying = True
        self.verify_btn.configure(state="disabled", text=t("Checking {d}/{t}...", d=0, t=self._verify_total))

        def run() -> None:
            for i, c in enumerate(work, 1):
                if cancel.is_set():
                    return
                try:
                    data = read_preview(src["path"], src["size"], src["sector"], c,
                                        max_bytes=_VERIFY_READ)
                    c.open_status = validate(data, c.key, c.extension).status
                except Exception:  # noqa: BLE001
                    c.open_status = ""
                self._verify_done = i
            self._safe_after(lambda: self._verify_finish(gen))

        threading.Thread(target=run, daemon=True).start()
        self.after(_VERIFY_TICK_MS, lambda: self._verify_tick(gen))

    def _verify_tick(self, gen: int) -> None:
        if gen != self._verify_gen or not self._verifying:
            return
        try:
            self.verify_btn.configure(text=t("Checking {d}/{t}...", d=self._verify_done, t=self._verify_total))
            self._refresh_tree_status()
        except TclError:
            return
        self.after(_VERIFY_TICK_MS, lambda: self._verify_tick(gen))

    def _verify_finish(self, gen: int) -> None:
        if gen != self._verify_gen:
            return
        self._verifying = False
        try:
            self._refresh_tree_status()
            self.verify_btn.configure(text=t("Re-check openability"), state="normal")
        except TclError:
            return
        if self._sel_key(self.open_menu, self._open_keys) != "Open: all":
            self._apply()

    def _cancel_verify(self) -> None:
        self._verify_gen += 1
        if self._verify_cancel is not None:
            self._verify_cancel.set()
        self._verifying = False
        try:
            self.verify_btn.configure(text=t("Re-check openability"), state="normal")
        except TclError:
            pass

    def _safe_after(self, fn) -> None:
        try:
            self.after(0, fn)
        except TclError:
            pass

    # -- preview -----------------------------------------------------------
    def _show_preview(self, cand) -> None:
        if cand is None:
            return
        src = self.app.source
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_img_lbl.configure(image=None, text="")
        self._preview_img = None

        cap = _PREVIEW_READ if cand.category in ("Images", "Documents") else 2_000_000
        try:
            data = read_preview(src["path"], src["size"], src["sector"], cand, max_bytes=cap)
            preview_err = ""
        except Exception as exc:  # noqa: BLE001
            data = b""
            preview_err = str(exc)

        vr = validate(data, cand.key, cand.extension) if data else None
        if vr is not None and vr.status != UNKNOWN:
            cand.open_status = vr.status
            if self.tree.exists(cand.id):
                self.tree.set(cand.id, "open", _open_label(cand.open_status))
                tag = _OPEN_TAG.get(cand.open_status)
                self.tree.item(cand.id, tags=((tag,) if tag else ()))

        meta = (f"{t('Name')}: {cand.name}\n"
                f"{t('Format')}: {cand.category} / .{cand.extension}\n"
                f"{t('Size')}: {describe_size(cand.size_bytes)} ({cand.size_bytes:,} bytes)\n")
        if vr is not None and vr.dimensions:
            meta += f"{t('Dimensions')}: {vr.dimensions} px\n"
        meta += (f"{t('Confidence')}: {cand.confidence}\n"
                 f"{t('Recoverability')}: {t(cand.recoverability)}\n")
        if vr is not None:
            meta += f"{t('Opens')}: {_open_text(vr.status)}  -  {vr.detail}\n"
        meta += f"{t('Offset')}: {cand.offset_start:,} - {cand.offset_end:,}\n"
        if preview_err:
            meta += "\n" + t("[Preview unavailable: {err}]", err=preview_err)

        if cand.category == "Images" and _HAS_PIL and data:
            from PIL import ImageFile
            prev_trunc = ImageFile.LOAD_TRUNCATED_IMAGES
            try:
                ImageFile.LOAD_TRUNCATED_IMAGES = True
                img = Image.open(io.BytesIO(data))
                img.load()
                img.thumbnail((320, 320))
                self._preview_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                self.preview_img_lbl.configure(image=self._preview_img, text="")
            except Exception:  # noqa: BLE001
                self.preview_img_lbl.configure(text=t("[Image could not be decoded]"))
            finally:
                ImageFile.LOAD_TRUNCATED_IMAGES = prev_trunc
        elif cand.extension in _TEXT_EXT and data:
            text = data[:8000].decode("utf-8", errors="replace")
            meta += "\n" + t("--- Content preview ---") + "\n" + text
            self.preview_img_lbl.configure(text="")
        else:
            self.preview_img_lbl.configure(text=t("No visual preview for this type"))

        self.preview_text.insert("1.0", meta)
        self.preview_text.configure(state="disabled")

    # -- recover -----------------------------------------------------------
    def _recover(self) -> None:
        sel = self.selected_candidates()
        if not sel:
            return
        self._cancel_verify()
        self.app.pending_recovery = sel
        self.app.show("recovery_dest")
