from __future__ import annotations

import queue
import base64
import os
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

ROOT = Path(__file__).resolve().parent
ENGINE_DIR = ROOT / "comp_engine"
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

from bridge_server import (  # noqa: E402
    COMP_STRATEGY_AVERAGE,
    COMP_STRATEGY_HIGH,
    COMP_STRATEGY_LOW,
    COMP_STRATEGY_STALE_NEWEST,
    BridgeServer,
    BridgeState,
)
from workbook_io import WorkbookRow  # noqa: E402

from intake_io import (  # noqa: E402
    build_card_title,
    clean_part,
    default_output_path,
    format_money,
    infer_grader,
    normalize_grader,
    read_photo_export,
    read_simple_spreadsheet,
    scan_to_cert,
    working_sheet_path,
    write_working_sheet,
    workbook_sheet_names,
    write_pipeline_output,
)


PHOTO_APP_ROOT = Path(r"C:\Users\User\Documents\Codex\2026-05-27\photo_to_sheet_conversion")
PHOTO_APP_DIR = PHOTO_APP_ROOT / "app"
PHOTO_SITE_PACKAGES = PHOTO_APP_ROOT / ".venv" / "Lib" / "site-packages"
if PHOTO_SITE_PACKAGES.exists() and str(PHOTO_SITE_PACKAGES) not in sys.path:
    sys.path.insert(0, str(PHOTO_SITE_PACKAGES))
if PHOTO_APP_DIR.exists() and str(PHOTO_APP_DIR) not in sys.path:
    sys.path.insert(0, str(PHOTO_APP_DIR))
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None
try:
    from google import genai
    from multi_card_extraction import (
        ModelQuotaExceeded,
        ModelResponseParseError,
        TemporaryModelUnavailable,
        identify_cards_sync,
    )
except Exception:
    genai = None
    identify_cards_sync = None
    TemporaryModelUnavailable = ModelQuotaExceeded = ModelResponseParseError = Exception
WORKING_SHEETS_DIR = Path(r"G:\My Drive\CARD_PIPELINE\WORKING SHEETS")
CARD_PIPELINE_DIR = Path(r"G:\My Drive\CARD_PIPELINE")
INCOMING_SHEETS_DIR = Path(r"G:\My Drive\CARD_PIPELINE\INCOMING SHEETS")

PAYOUT_RATES = {"Arena Club": 0.82, "Courtyard": 0.78, "ALT": 0.76}
COMP_STRATEGY_DISPLAY = {
    "Average last 5": COMP_STRATEGY_AVERAGE,
    "Highest of last 5": COMP_STRATEGY_HIGH,
    "Lowest of last 5": COMP_STRATEGY_LOW,
    "Date weighted": COMP_STRATEGY_STALE_NEWEST,
}

DISPLAY_COLUMNS = (
    "excel_row",
    "source",
    "sheet_source",
    "cert_number",
    "grader",
    "card_title",
    "purchase_price",
    "card_ladder_value",
    "card_ladder_comps_average",
    "best_company",
    "estimated_payout",
    "status",
)

ADD_REVIEW_ROW_IID = "__add_review_row__"

EDITABLE_COLUMNS = {
    "source",
    "sheet_source",
    "cert_number",
    "grader",
    "card_title",
    "purchase_price",
}

HEADINGS = {
    "excel_row": "Row",
    "source": "Source",
    "sheet_source": "Sheet Source",
    "cert_number": "Cert #",
    "grader": "Co.",
    "card_title": "Card",
    "purchase_price": "Purchase",
    "card_ladder_value": "Card Ladder",
    "card_ladder_comps_average": "Comps",
    "best_company": "Best Company",
    "estimated_payout": "Est. Payout",
    "status": "Status",
}

COLUMN_WIDTHS = {
    "excel_row": 52,
    "source": 130,
    "sheet_source": 150,
    "cert_number": 110,
    "grader": 54,
    "card_title": 390,
    "purchase_price": 90,
    "card_ladder_value": 100,
    "card_ladder_comps_average": 100,
    "best_company": 130,
    "estimated_payout": 100,
    "status": 160,
}


class CardPipelineApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Card Pipeline")
        self.geometry("1420x820")
        self.minsize(1120, 680)

        self.events: queue.Queue[str] = queue.Queue()
        self.intake_rows: list[WorkbookRow] = []
        self.intake_sources: dict[int, str] = {}
        self.intake_sheet_sources: dict[int, str] = {}
        self.row_sources: dict[int, str] = {}
        self.comp_sheet_sources: dict[int, str] = {}
        self.review_rows: list[WorkbookRow] = []
        self.review_sources: dict[int, str] = {}
        self.review_sheet_sources: dict[int, str] = {}
        self.incoming_cert_index: dict[str, dict[str, object]] = {}
        self.state = BridgeState()
        self.state.on_update = lambda: self.events.put("refresh")
        self.bridge = BridgeServer(self.state)
        self.bridge.start()

        self.input_mode = tk.StringVar(value="Barcode Scanner")
        self.review_mode = tk.StringVar(value="Automatic Review")
        self.review_input_mode = tk.StringVar(value="Barcode Scanner")
        self.comp_strategy_label = tk.StringVar(value="Average last 5")
        self.working_sheet_title = tk.StringVar()
        self.selected_working_sheet = tk.StringVar()
        self.summary_var = tk.StringVar(value="Choose an intake mode to begin.")
        self.status_var = tk.StringVar(value="Bridge starting...")

        self.scan_cert = tk.StringVar()
        self.scan_grader = tk.StringVar(value="PSA")
        self.scan_card = tk.StringVar()
        self.scan_status = tk.StringVar(value="Scanning station is off.")
        self.scan_entry: ttk.Entry | None = None
        self.cell_editor: ttk.Entry | None = None
        self.cell_edit: tuple[ttk.Treeview, str, str] | None = None
        self.column_widths_by_tree: dict[int, dict[str, int]] = {}
        self.scanning_station_active = False

        self.file_path = tk.StringVar()
        self.sheet_name = tk.StringVar()
        self.photo_paths: list[Path] = []
        self.photo_status = tk.StringVar(value="No photos selected.")
        self.photo_worker: threading.Thread | None = None
        self.photo_client = None
        self.review_scan_cert = tk.StringVar()
        self.review_scan_grader = tk.StringVar(value="PSA")
        self.review_scan_entry: ttk.Entry | None = None
        self.review_scanning_active = False
        self.review_status = tk.StringVar(value="Review station is off.")
        self.review_photo_paths: list[Path] = []
        self.review_photo_status = tk.StringVar(value="No review photos selected.")
        self.review_photo_worker: threading.Thread | None = None
        self.working_sheet_paths: dict[str, Path] = {}

        self._build_ui()
        self._show_mode()
        self._poll_events()
        self.status_var.set("Bridge running at http://127.0.0.1:8765")

    def _build_ui(self) -> None:
        palette = {
            "bg": "#eef1f4",
            "header": "#17212b",
            "header_text": "#f8fafc",
            "panel": "#ffffff",
            "muted": "#64748b",
            "button": "#2563eb",
            "button_hover": "#1d4ed8",
            "text": "#0f172a",
        }
        self.configure(bg=palette["bg"])
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background=palette["bg"])
        style.configure("Panel.TFrame", background=palette["panel"])
        style.configure("Header.TFrame", background=palette["header"])
        style.configure("HeaderTitle.TLabel", background=palette["header"], foreground=palette["header_text"], font=("Segoe UI Semibold", 20))
        style.configure("HeaderSub.TLabel", background=palette["header"], foreground="#cbd5e1")
        style.configure("Panel.TLabel", background=palette["panel"], foreground=palette["text"])
        style.configure("Muted.TLabel", background=palette["panel"], foreground=palette["muted"])
        style.configure("Primary.TButton", font=("Segoe UI Semibold", 10), padding=(14, 8), background=palette["button"], foreground="#ffffff", borderwidth=0)
        style.map("Primary.TButton", background=[("active", palette["button_hover"]), ("disabled", "#94a3b8")])
        style.configure("Soft.TButton", padding=(12, 8), background="#f8fafc", foreground=palette["text"])
        style.configure("Treeview", rowheight=32, font=("Segoe UI", 10), background=palette["panel"], fieldbackground=palette["panel"], foreground=palette["text"], borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), background="#e2e8f0", foreground="#334155", padding=(8, 7), borderwidth=0)
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", palette["text"])])

        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 16))
        header.pack(fill=tk.X)
        title_group = ttk.Frame(header, style="Header.TFrame")
        title_group.pack(side=tk.LEFT)
        ttk.Label(title_group, text="Card Pipeline", style="HeaderTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(title_group, text="Intake cards by scanner, photos, or spreadsheet, then run comps.", style="HeaderSub.TLabel").pack(anchor=tk.W, pady=(3, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=16, pady=(14, 12))
        self.intake_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.comp_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.review_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.tabs.add(self.intake_tab, text="Intake")
        self.tabs.add(self.comp_tab, text="Comp")
        self.tabs.add(self.review_tab, text="Review")
        self.row_trees: list[ttk.Treeview] = []

        intake_controls = ttk.Frame(self.intake_tab, style="Panel.TFrame", padding=(16, 12))
        intake_controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(intake_controls, text="Input Mode", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        mode = ttk.Combobox(
            intake_controls,
            textvariable=self.input_mode,
            state="readonly",
            values=["Barcode Scanner", "Photo OCR", "Existing Spreadsheet"],
            width=22,
        )
        mode.grid(row=0, column=1, sticky="w", padx=(8, 16))
        mode.bind("<<ComboboxSelected>>", lambda _event: self._show_mode())
        ttk.Button(intake_controls, text="Clear Rows", command=self.clear_rows, style="Soft.TButton").grid(row=0, column=2, sticky="w")
        intake_controls.columnconfigure(3, weight=1)
        ttk.Label(intake_controls, textvariable=self.summary_var, style="Muted.TLabel").grid(row=1, column=0, columnspan=4, sticky="w", pady=(10, 0))

        self.mode_host = ttk.Frame(self.intake_tab, style="Panel.TFrame", padding=(16, 12))
        self.mode_host.pack(fill=tk.X, pady=(0, 10))
        self.intake_tree = self._build_table(self.intake_tab, editable=True)
        intake_save = ttk.Frame(self.intake_tab, style="Panel.TFrame", padding=(16, 12))
        intake_save.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(intake_save, text="Working Sheet Title", style="Panel.TLabel").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Entry(intake_save, textvariable=self.working_sheet_title, width=42).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(intake_save, text="Save as Working Sheet", command=self.save_working_sheet, style="Primary.TButton").pack(side=tk.LEFT)

        comp_body = ttk.Frame(self.comp_tab, style="App.TFrame")
        comp_body.pack(fill=tk.BOTH, expand=True)
        sheet_panel = ttk.Frame(comp_body, style="Panel.TFrame", padding=(12, 12))
        sheet_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        ttk.Label(sheet_panel, text="Active Sheets", style="Panel.TLabel").pack(anchor=tk.W)
        self.working_sheet_list = tk.Listbox(sheet_panel, width=34, height=24, activestyle="dotbox", exportselection=False)
        self.working_sheet_list.pack(fill=tk.Y, expand=True, pady=(8, 8))
        self.working_sheet_list.bind("<Double-Button-1>", lambda _event: self.load_selected_working_sheet())
        ttk.Button(sheet_panel, text="Load Selected Sheet", command=self.load_selected_working_sheet, style="Primary.TButton").pack(fill=tk.X, pady=(0, 8))
        ttk.Button(sheet_panel, text="Refresh Sheets", command=self.refresh_pipeline, style="Soft.TButton").pack(fill=tk.X)
        comp_main = ttk.Frame(comp_body, style="App.TFrame")
        comp_main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.comp_tree = self._build_table(comp_main, editable=True)
        comp_controls = ttk.Frame(comp_main, style="Panel.TFrame", padding=(16, 12))
        comp_controls.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(comp_controls, text="Save Output", command=self.save_output, style="Soft.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(comp_controls, text="Run All Comps", command=self.run_all_comps, style="Primary.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Combobox(
            comp_controls,
            textvariable=self.comp_strategy_label,
            state="readonly",
            values=list(COMP_STRATEGY_DISPLAY.keys()),
            width=20,
        ).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(comp_controls, text="Comp Method", style="Panel.TLabel").pack(side=tk.RIGHT)
        self.refresh_working_sheets()

        review_controls = ttk.Frame(self.review_tab, style="Panel.TFrame", padding=(16, 12))
        review_controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(review_controls, text="Review Mode", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        review_mode = ttk.Combobox(
            review_controls,
            textvariable=self.review_mode,
            state="readonly",
            values=["Automatic Review", "Manual Review"],
            width=20,
        )
        review_mode.grid(row=0, column=1, sticky="w", padx=(8, 16))
        review_mode.bind("<<ComboboxSelected>>", lambda _event: self._show_review_mode())
        review_controls.columnconfigure(4, weight=1)
        ttk.Label(review_controls, textvariable=self.review_status, style="Muted.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))
        self.review_mode_host = ttk.Frame(self.review_tab, style="Panel.TFrame", padding=(16, 12))
        self.review_mode_host.pack(fill=tk.X, pady=(0, 10))
        self.review_tree = self._build_table(self.review_tab, editable=True)
        review_bottom = ttk.Frame(self.review_tab, style="Panel.TFrame", padding=(16, 12))
        review_bottom.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(review_bottom, text="Refresh Incoming Sheets", command=self.refresh_incoming_index, style="Soft.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(review_bottom, text="Clear Review Rows", command=self.clear_review_rows, style="Soft.TButton").pack(side=tk.RIGHT)
        self._show_review_mode()
        self.refresh_incoming_index()

        bottom = ttk.Frame(self, style="App.TFrame", padding=(16, 0, 16, 14))
        bottom.pack(fill=tk.X)
        ttk.Label(bottom, textvariable=self.status_var).pack(side=tk.LEFT)

    def _build_table(self, parent: ttk.Frame, editable: bool = False) -> ttk.Treeview:
        content = ttk.Frame(parent, style="Panel.TFrame", padding=(1, 1))
        content.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(content, columns=DISPLAY_COLUMNS, show="headings", selectmode="extended")
        for col in DISPLAY_COLUMNS:
            tree.heading(col, text=HEADINGS[col])
            tree.column(col, width=COLUMN_WIDTHS[col], minwidth=45, stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(content, orient=tk.VERTICAL, command=tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(content, orient=tk.HORIZONTAL, command=tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.tag_configure("duplicate_cert", background="#fef3c7")
        tree.tag_configure("no_sheet_found", background="#fecaca")
        tree.tag_configure("add_review_row", background="#f8fafc", foreground="#2563eb")
        if editable:
            tree.bind("<Double-1>", self._begin_cell_edit)
            tree.bind("<Button-1>", self._handle_table_click, add="+")
        tree.bind("<ButtonRelease-1>", lambda _event, target=tree: self._remember_column_widths(target), add="+")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        setattr(tree, "_table_frame", content)
        self.row_trees.append(tree)
        self.column_widths_by_tree[id(tree)] = dict(COLUMN_WIDTHS)
        return tree

    def _show_mode(self) -> None:
        for child in self.mode_host.winfo_children():
            child.destroy()
        mode = self.input_mode.get()
        if mode == "Barcode Scanner":
            self._build_barcode_mode()
            self.after(100, self._arm_scanner)
        elif mode == "Photo OCR":
            self._build_file_mode(photo=True)
        else:
            self._build_file_mode(photo=False)

    def _show_review_mode(self) -> None:
        if not hasattr(self, "review_mode_host"):
            return
        for child in self.review_mode_host.winfo_children():
            child.destroy()
        if self.review_mode.get() == "Manual Review":
            self._build_manual_review_mode()
        else:
            self._build_automatic_review_mode()
        self._refresh_table()

    def _build_manual_review_mode(self) -> None:
        self.review_mode_host.columnconfigure(8, weight=1)
        ttk.Label(self.review_mode_host, text="Double-click cells in the Review table to enter cert, grader, card, and purchase price.", style="Muted.TLabel").grid(row=0, column=0, columnspan=9, sticky="w")

    def _build_automatic_review_mode(self) -> None:
        self.review_mode_host.columnconfigure(8, weight=1)
        ttk.Label(self.review_mode_host, text="Input", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        selector = ttk.Combobox(
            self.review_mode_host,
            textvariable=self.review_input_mode,
            state="readonly",
            values=["Barcode Scanner", "Photo OCR"],
            width=18,
        )
        selector.grid(row=0, column=1, sticky="w", padx=(8, 16))
        selector.bind("<<ComboboxSelected>>", lambda _event: self._show_review_mode())
        if self.review_input_mode.get() == "Photo OCR":
            self._build_review_photo_controls(start_col=2)
        else:
            self._build_review_barcode_controls(start_col=2)

    def _build_review_barcode_controls(self, start_col: int) -> None:
        self.review_station_button = ttk.Button(self.review_mode_host, text="Enter Review Scanning Mode", command=self.toggle_review_scanning, style="Primary.TButton")
        self.review_station_button.grid(row=0, column=start_col, sticky="w", padx=(0, 14))
        ttk.Label(self.review_mode_host, text="Scan", style="Panel.TLabel").grid(row=0, column=start_col + 1, sticky="w")
        self.review_scan_entry = ttk.Entry(self.review_mode_host, textvariable=self.review_scan_cert, width=28)
        self.review_scan_entry.grid(row=0, column=start_col + 2, sticky="w", padx=(8, 14))
        self.review_scan_entry.bind("<Return>", lambda _event: self.add_review_scanned_row())
        self.review_scan_entry.bind("<KP_Enter>", lambda _event: self.add_review_scanned_row())
        ttk.Label(self.review_mode_host, text="Grader", style="Panel.TLabel").grid(row=0, column=start_col + 3, sticky="w")
        ttk.Combobox(self.review_mode_host, textvariable=self.review_scan_grader, values=["PSA", "BGS", "SGC", "CGC"], state="readonly", width=8).grid(row=0, column=start_col + 4, sticky="w", padx=(8, 14))
        self._set_review_station_controls()
        if self.review_scanning_active:
            self.after(100, self._arm_review_scanner)

    def _build_review_photo_controls(self, start_col: int) -> None:
        self.review_scanning_active = False
        self.review_scan_entry = None
        ttk.Button(self.review_mode_host, text="Add Review Photos", command=self.add_review_photos, style="Soft.TButton").grid(row=0, column=start_col, sticky="w", padx=(0, 8))
        ttk.Button(self.review_mode_host, text="Scan Review Photos", command=self.scan_review_photos, style="Primary.TButton").grid(row=0, column=start_col + 1, sticky="w", padx=(0, 8))
        ttk.Button(self.review_mode_host, text="Clear Review Photos", command=self.clear_review_photos, style="Soft.TButton").grid(row=0, column=start_col + 2, sticky="w")
        ttk.Label(self.review_mode_host, textvariable=self.review_photo_status, style="Muted.TLabel").grid(row=1, column=0, columnspan=9, sticky="w", pady=(10, 0))

    def _build_barcode_mode(self) -> None:
        self.mode_host.columnconfigure(7, weight=1)
        self.station_button = ttk.Button(self.mode_host, text="Enter Scanning Station Mode", command=self.toggle_scanning_station, style="Primary.TButton")
        self.station_button.grid(row=0, column=0, sticky="w", padx=(0, 14))
        ttk.Label(self.mode_host, text="Scan", style="Panel.TLabel").grid(row=0, column=1, sticky="w")
        self.scan_entry = ttk.Entry(self.mode_host, textvariable=self.scan_cert, width=28)
        self.scan_entry.grid(row=0, column=2, sticky="w", padx=(8, 14))
        self.scan_entry.bind("<Return>", lambda _event: self.add_scanned_row())
        self.scan_entry.bind("<KP_Enter>", lambda _event: self.add_scanned_row())
        ttk.Label(self.mode_host, text="Grader", style="Panel.TLabel").grid(row=0, column=3, sticky="w")
        ttk.Combobox(self.mode_host, textvariable=self.scan_grader, values=["PSA", "BGS", "SGC", "CGC"], state="readonly", width=8).grid(row=0, column=4, sticky="w", padx=(8, 14))
        ttk.Label(self.mode_host, textvariable=self.scan_status, style="Muted.TLabel").grid(row=1, column=0, columnspan=8, sticky="w", pady=(10, 0))
        self._set_station_controls()

    def _build_file_mode(self, photo: bool) -> None:
        if photo:
            self._build_photo_mode()
            return
        label = "Photo OCR Export" if photo else "Spreadsheet"
        self.mode_host.columnconfigure(1, weight=1)
        ttk.Label(self.mode_host, text=label, style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(self.mode_host, textvariable=self.file_path).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        ttk.Button(self.mode_host, text="Browse", command=self.browse_file, style="Soft.TButton").grid(row=0, column=2, sticky="e")
        ttk.Label(self.mode_host, text="Sheet", style="Panel.TLabel").grid(row=0, column=3, sticky="w", padx=(14, 8))
        self.sheet_combo = ttk.Combobox(self.mode_host, textvariable=self.sheet_name, state="readonly", width=18)
        self.sheet_combo.grid(row=0, column=4, sticky="w")
        ttk.Button(self.mode_host, text="Load Rows", command=self.load_file_rows, style="Primary.TButton").grid(row=0, column=5, sticky="e", padx=(14, 0))

    def _build_photo_mode(self) -> None:
        self.mode_host.columnconfigure(4, weight=1)
        ttk.Button(self.mode_host, text="Add Photos", command=self.add_photos, style="Soft.TButton").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Button(self.mode_host, text="Add Folder", command=self.add_photo_folder, style="Soft.TButton").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Button(self.mode_host, text="Scan Photos", command=self.scan_photos, style="Primary.TButton").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Button(self.mode_host, text="Clear Photos", command=self.clear_photos, style="Soft.TButton").grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Label(self.mode_host, textvariable=self.photo_status, style="Muted.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))

    def add_scanned_row(self) -> None:
        if not self.scanning_station_active:
            self.scan_status.set("Click Enter Scanning Station Mode before scanning.")
            return
        cert = scan_to_cert(self.scan_cert.get())
        if not cert:
            self.scan_status.set("No cert detected. Scan again.")
            self._arm_scanner()
            return
        grader = self.scan_grader.get().strip().upper()
        card = self.scan_card.get().strip() or grader
        added_rows = self._append_rows([
            {
                "cert_number": cert,
                "grader": grader,
                "card_title": card,
                "purchase_price": None,
                "source": "Barcode",
                "notes": "" if cert and grader else "Missing cert or grader",
            }
        ])
        self.scan_cert.set("")
        self.scan_card.set("")
        self.scan_status.set(f"Added row {len(self.intake_rows) + 1}: {cert}. Scanner ready for next cert.")
        self.status_var.set(f"Added scanned card {cert}.")
        if added_rows:
            self._select_excel_row(added_rows[-1])
        self._arm_scanner()

    def browse_file(self) -> None:
        path = filedialog.askopenfilename(title="Choose workbook", filetypes=[("Excel workbook", "*.xlsx")])
        if not path:
            return
        self.file_path.set(path)
        try:
            names = workbook_sheet_names(Path(path))
            self.sheet_combo["values"] = names
            if names:
                self.sheet_name.set(names[0])
        except Exception as error:
            messagebox.showerror("Workbook error", str(error))

    def load_file_rows(self) -> None:
        path = Path(self.file_path.get())
        if not path.exists():
            messagebox.showinfo("Choose file", "Choose a workbook first.")
            return
        try:
            if self.input_mode.get() == "Photo OCR":
                rows = read_photo_export(path, self.sheet_name.get() or None)
            else:
                rows = read_simple_spreadsheet(path, self.sheet_name.get() or None)
        except Exception as error:
            messagebox.showerror("Load failed", str(error))
            return
        self._append_rows(rows)
        self.status_var.set(f"Loaded {len(rows)} row(s) from {path.name}.")

    def toggle_scanning_station(self) -> None:
        self.scanning_station_active = not self.scanning_station_active
        self._set_station_controls()
        if self.scanning_station_active:
            self.scan_status.set("Scanning station armed. Scan certs now; each scan adds the next row.")
            self._arm_scanner()
        else:
            self.scan_status.set("Scanning station is off.")

    def _set_station_controls(self) -> None:
        if not hasattr(self, "station_button"):
            return
        self.station_button.configure(text="Exit Scanning Station Mode" if self.scanning_station_active else "Enter Scanning Station Mode")
        if self.scan_entry is not None:
            self.scan_entry.configure(state=tk.NORMAL if self.scanning_station_active else tk.DISABLED)

    def add_photos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose card photos",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")],
        )
        self._add_photo_paths([Path(path) for path in paths])

    def add_photo_folder(self) -> None:
        folder = filedialog.askdirectory(title="Choose photo folder")
        if not folder:
            return
        extensions = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
        self._add_photo_paths([path for path in Path(folder).iterdir() if path.suffix.lower() in extensions])

    def clear_photos(self) -> None:
        if self.photo_worker and self.photo_worker.is_alive():
            messagebox.showinfo("Scan running", "Wait for the photo scan to finish before clearing photos.")
            return
        self.photo_paths = []
        self.photo_status.set("No photos selected.")

    def _add_photo_paths(self, paths: list[Path]) -> None:
        existing = {path.resolve() for path in self.photo_paths if path.exists()}
        added = 0
        for path in paths:
            if not path.exists() or path.resolve() in existing:
                continue
            self.photo_paths.append(path)
            existing.add(path.resolve())
            added += 1
        self.photo_status.set(f"{len(self.photo_paths)} photo(s) selected. Added {added}.")

    def scan_photos(self) -> None:
        if self.photo_worker and self.photo_worker.is_alive():
            messagebox.showinfo("Scan running", "Photo scan is already running.")
            return
        if not self.photo_paths:
            messagebox.showinfo("No photos", "Add photos before scanning.")
            return
        if genai is None or identify_cards_sync is None:
            messagebox.showerror("Missing dependency", "Photo OCR dependencies are not available.")
            return
        self._load_photo_env()
        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if not api_key:
            messagebox.showerror("Missing GOOGLE_API_KEY", "Create app\\.env in the photo tool or set GOOGLE_API_KEY.")
            return
        self.photo_client = genai.Client(api_key=api_key)
        self.photo_status.set(f"Scanning 0/{len(self.photo_paths)} photo(s)...")
        self.photo_worker = threading.Thread(target=self._photo_scan_worker, daemon=True)
        self.photo_worker.start()

    def _photo_scan_worker(self) -> None:
        total = len(self.photo_paths)
        detected_total = 0
        for index, path in enumerate(list(self.photo_paths), start=1):
            try:
                image_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
                cards = identify_cards_sync(self.photo_client, image_b64)
                rows = [self._photo_card_to_row(path, card) for card in cards if self._photo_card_has_inventory(card)]
                detected_total += len(rows)
                self.events.put(("photo_rows", rows))
                self.events.put(("photo_status", f"Scanning {index}/{total}: {path.name} -> {len(rows)} card row(s)."))
            except (TemporaryModelUnavailable, ModelQuotaExceeded, ModelResponseParseError) as error:
                self.events.put(("photo_status", f"{path.name}: {error}"))
            except Exception as error:
                self.events.put(("photo_status", f"{path.name}: {error}"))
        self.events.put(("photo_status", f"Photo scan complete. Added {detected_total} card row(s)."))

    def _photo_card_to_row(self, path: Path, card: dict) -> dict[str, object]:
        grader = normalize_grader(card.get("grading_company"))
        title = build_card_title(
            {
                "description": "",
                "year": card.get("year"),
                "set": card.get("set"),
                "player": card.get("player"),
                "card_number": card.get("card_number"),
                "parallel": card.get("parallel"),
                "subset": card.get("subset") or card.get("attributes"),
                "grader": grader,
                "grade": card.get("grade"),
            }
        )
        cert = scan_to_cert(card.get("cert_number"))
        return {
            "cert_number": cert,
            "grader": grader or infer_grader(title),
            "card_title": title,
            "purchase_price": None,
            "source": f"Photo: {path.name}",
            "notes": clean_part(card.get("position") or card.get("confidence") or ""),
        }

    def _photo_card_has_inventory(self, card: dict) -> bool:
        return any(card.get(key) for key in ("cert_number", "player", "year", "set", "card_number", "parallel", "subset", "grade", "label_text"))

    def _load_photo_env(self) -> None:
        if not load_dotenv:
            return
        load_dotenv(PHOTO_APP_DIR / ".env", override=False)
        load_dotenv(PHOTO_APP_ROOT / ".env", override=False)
        load_dotenv(Path(r"C:\Users\User\Documents\Codex\2026-05-21\automatic-sheet-review\live-comps\.env"), override=False)

    def refresh_incoming_index(self) -> None:
        try:
            INCOMING_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
            paths = sorted(INCOMING_SHEETS_DIR.glob("*.xlsx"), key=lambda path: path.name.lower())
        except Exception as error:
            self.incoming_cert_index = {}
            self.review_status.set(f"Incoming sheets unavailable: {error}")
            return
        index: dict[str, dict[str, object]] = {}
        for path in paths:
            try:
                rows = read_simple_spreadsheet(path)
            except Exception:
                continue
            for row in rows:
                cert = scan_to_cert(row.get("cert_number"))
                if not cert or cert in index:
                    continue
                index[cert] = {
                    "sheet": path.name,
                    "path": path,
                    "card_title": row.get("card_title") or "",
                    "grader": row.get("grader") or "",
                    "purchase_price": row.get("purchase_price"),
                }
        self.incoming_cert_index = index
        self._match_all_review_rows()
        self.review_status.set(f"Indexed {len(index)} cert(s) from {len(paths)} incoming sheet(s).")

    def add_manual_review_row(self) -> int | None:
        added_rows = self._append_review_rows([
            {
                "cert_number": "",
                "grader": "",
                "card_title": "",
                "purchase_price": None,
                "source": "Manual",
                "notes": "Manual review",
            }
        ])
        if added_rows:
            row_id = str(added_rows[-1])
            self.review_tree.selection_set(row_id)
            self.review_tree.focus(row_id)
            self.review_tree.see(row_id)
            self.review_status.set("Manual row added. Double-click cells to edit it.")
            return added_rows[-1]
        return None

    def toggle_review_scanning(self) -> None:
        self.review_scanning_active = not self.review_scanning_active
        self._set_review_station_controls()
        if self.review_scanning_active:
            self.review_status.set("Review scanning mode armed. Scan received certs now.")
            self._arm_review_scanner()
        else:
            self.review_status.set("Review station is off.")

    def _set_review_station_controls(self) -> None:
        if not hasattr(self, "review_station_button"):
            return
        self.review_station_button.configure(text="Exit Review Scanning Mode" if self.review_scanning_active else "Enter Review Scanning Mode")
        if self.review_scan_entry is not None:
            self.review_scan_entry.configure(state=tk.NORMAL if self.review_scanning_active else tk.DISABLED)

    def add_review_scanned_row(self) -> None:
        if not self.review_scanning_active:
            self.review_status.set("Click Enter Review Scanning Mode before scanning.")
            return
        cert = scan_to_cert(self.review_scan_cert.get())
        if not cert:
            self.review_status.set("No cert detected. Scan again.")
            self._arm_review_scanner()
            return
        grader = self.review_scan_grader.get().strip().upper()
        self._append_review_rows([
            {
                "cert_number": cert,
                "grader": grader,
                "card_title": grader,
                "purchase_price": None,
                "source": "Review Barcode",
                "notes": "Received",
            }
        ])
        self.review_scan_cert.set("")
        self.review_status.set(f"Received {cert}. Ready for next scan.")
        self._arm_review_scanner()

    def add_review_photos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose review photos",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")],
        )
        self._add_review_photo_paths([Path(path) for path in paths])

    def clear_review_photos(self) -> None:
        if self.review_photo_worker and self.review_photo_worker.is_alive():
            messagebox.showinfo("Scan running", "Wait for the review photo scan to finish before clearing photos.")
            return
        self.review_photo_paths = []
        self.review_photo_status.set("No review photos selected.")

    def _add_review_photo_paths(self, paths: list[Path]) -> None:
        existing = {path.resolve() for path in self.review_photo_paths if path.exists()}
        added = 0
        for path in paths:
            if not path.exists() or path.resolve() in existing:
                continue
            self.review_photo_paths.append(path)
            existing.add(path.resolve())
            added += 1
        self.review_photo_status.set(f"{len(self.review_photo_paths)} review photo(s) selected. Added {added}.")

    def scan_review_photos(self) -> None:
        if self.review_photo_worker and self.review_photo_worker.is_alive():
            messagebox.showinfo("Scan running", "Review photo scan is already running.")
            return
        if not self.review_photo_paths:
            messagebox.showinfo("No photos", "Add review photos before scanning.")
            return
        if genai is None or identify_cards_sync is None:
            messagebox.showerror("Missing dependency", "Photo OCR dependencies are not available.")
            return
        self._load_photo_env()
        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if not api_key:
            messagebox.showerror("Missing GOOGLE_API_KEY", "Create app\\.env in the photo tool or set GOOGLE_API_KEY.")
            return
        self.photo_client = genai.Client(api_key=api_key)
        self.review_photo_status.set(f"Scanning 0/{len(self.review_photo_paths)} review photo(s)...")
        self.review_photo_worker = threading.Thread(target=self._review_photo_scan_worker, daemon=True)
        self.review_photo_worker.start()

    def _review_photo_scan_worker(self) -> None:
        total = len(self.review_photo_paths)
        detected_total = 0
        for index, path in enumerate(list(self.review_photo_paths), start=1):
            try:
                image_b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
                cards = identify_cards_sync(self.photo_client, image_b64)
                rows = [self._photo_card_to_review_row(path, card) for card in cards if self._photo_card_has_inventory(card)]
                detected_total += len(rows)
                self.events.put(("review_rows", rows))
                self.events.put(("review_status", f"Scanning {index}/{total}: {path.name} -> {len(rows)} review row(s)."))
            except Exception as error:
                self.events.put(("review_status", f"{path.name}: {error}"))
        self.events.put(("review_status", f"Review photo scan complete. Added {detected_total} row(s)."))

    def _photo_card_to_review_row(self, path: Path, card: dict) -> dict[str, object]:
        row = self._photo_card_to_row(path, card)
        row["source"] = f"Review Photo: {path.name}"
        row["notes"] = "Received"
        return row

    def _append_review_rows(self, rows: list[dict[str, object]]) -> list[int]:
        existing = list(self.review_rows)
        start = len(existing) + 2
        added_excel_rows: list[int] = []
        for offset, row in enumerate(rows):
            cert = scan_to_cert(row.get("cert_number"))
            match = self._incoming_match(cert)
            grader = str(row.get("grader") or match.get("grader") or infer_grader(str(row.get("card_title") or ""))).upper()
            card = str(row.get("card_title") or match.get("card_title") or "").strip() or grader
            purchase_price = row.get("purchase_price") if row.get("purchase_price") is not None else match.get("purchase_price")
            status = "Needs setup" if not cert else ("Received" if match else "Received - no incoming match")
            excel_row = start + offset
            existing.append(
                WorkbookRow(
                    excel_row=excel_row,
                    cert_number=cert,
                    card_title=card,
                    grader=grader,
                    existing_value=purchase_price,
                    status=status,
                    notes=str(row.get("notes") or ""),
                )
            )
            self.review_sources[excel_row] = str(row.get("source") or "")
            self.review_sheet_sources[excel_row] = str(match.get("sheet") or ("NO SHEET FOUND" if cert else ""))
            added_excel_rows.append(excel_row)
        self.review_rows = existing
        self._refresh_table()
        return added_excel_rows

    def _incoming_match(self, cert: str) -> dict[str, object]:
        return self.incoming_cert_index.get(scan_to_cert(cert), {})

    def _match_all_review_rows(self) -> None:
        for row in self.review_rows:
            match = self._incoming_match(row.cert_number)
            self.review_sheet_sources[row.excel_row] = str(match.get("sheet") or "NO SHEET FOUND")
            if match:
                if is_placeholder_title(row.card_title, row.grader) and match.get("card_title"):
                    row.card_title = str(match.get("card_title") or "")
                if not row.grader and match.get("grader"):
                    row.grader = str(match.get("grader") or "")
                if row.existing_value is None and match.get("purchase_price") is not None:
                    row.existing_value = match.get("purchase_price")
                row.status = "Received"
            elif row.status == "Received":
                row.status = "Received - no incoming match"

    def clear_review_rows(self) -> None:
        self.review_rows = []
        self.review_sources = {}
        self.review_sheet_sources = {}
        self._refresh_table()
        self.review_status.set("Review rows cleared.")

    def _arm_review_scanner(self) -> None:
        if self.review_mode.get() != "Automatic Review" or self.review_scan_entry is None:
            return
        try:
            self.review_scan_entry.focus_set()
            self.review_scan_entry.icursor(tk.END)
        except tk.TclError:
            pass

    def run_all_comps(self) -> None:
        if not self.state.rows:
            messagebox.showinfo("No comp sheet loaded", "Choose and load a working sheet in the Comp tab first.")
            return
        self.state.set_comp_strategy(COMP_STRATEGY_DISPLAY.get(self.comp_strategy_label.get(), COMP_STRATEGY_AVERAGE))
        command_id = self.state.start_all_comps()
        self._refresh_table()
        self.status_var.set(f"Run all comps queued with {self.comp_strategy_label.get()} as command #{command_id}.")

    def save_output(self) -> None:
        if not self.state.rows:
            messagebox.showinfo("No rows", "Load or scan cards before saving.")
            return
        self._apply_recommendations()
        default = default_output_path(ROOT)
        path = filedialog.asksaveasfilename(
            title="Save pipeline workbook",
            initialdir=str(default.parent),
            initialfile=default.name,
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not path:
            return
        write_pipeline_output(Path(path), self.state.rows, self.row_sources)
        self.status_var.set(f"Saved {path}")

    def save_working_sheet(self) -> None:
        if not self.intake_rows:
            messagebox.showinfo("No intake rows", "Scan or load cards in Intake before saving a working sheet.")
            return
        title = self.working_sheet_title.get().strip()
        if not title:
            messagebox.showinfo("Title required", "Enter a working sheet title first.")
            return
        try:
            path = working_sheet_path(WORKING_SHEETS_DIR, title)
            write_working_sheet(path, self.intake_rows, self.intake_sources)
        except Exception as error:
            messagebox.showerror("Save failed", str(error))
            return
        self.status_var.set(f"Saved working sheet: {path}")
        self.intake_rows = []
        self.intake_sources = {}
        self.intake_sheet_sources = {}
        self.working_sheet_title.set("")
        self._refresh_table()

    def refresh_pipeline(self) -> None:
        self.refresh_working_sheets()
        self._refresh_table()

    def refresh_working_sheets(self) -> None:
        try:
            CARD_PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
            WORKING_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
            paths = sorted(WORKING_SHEETS_DIR.glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
        except Exception as error:
            self.working_sheet_paths = {}
            if hasattr(self, "working_sheet_list"):
                self.working_sheet_list.delete(0, tk.END)
            self.status_var.set(f"Working sheets unavailable: {error}")
            return
        self.working_sheet_paths = {path.name: path for path in paths}
        if hasattr(self, "working_sheet_list"):
            self.working_sheet_list.delete(0, tk.END)
            for name in self.working_sheet_paths:
                self.working_sheet_list.insert(tk.END, name)
        if paths and self.selected_working_sheet.get() not in self.working_sheet_paths:
            self.selected_working_sheet.set(paths[0].name)
        self._select_working_sheet_in_list()
        self.status_var.set(f"Found {len(paths)} working sheet(s).")

    def load_selected_working_sheet(self) -> None:
        name = self._selected_working_sheet_name()
        path = self.working_sheet_paths.get(name)
        if not path:
            messagebox.showinfo("Choose sheet", "Choose a working sheet first.")
            return
        try:
            rows = read_simple_spreadsheet(path)
        except Exception as error:
            messagebox.showerror("Load failed", str(error))
            return
        workbook_rows: list[WorkbookRow] = []
        sources: dict[int, str] = {}
        for offset, row in enumerate(rows, start=2):
            cert = str(row.get("cert_number") or "")
            grader = str(row.get("grader") or infer_grader(str(row.get("card_title") or ""))).upper()
            card = str(row.get("card_title") or "").strip() or grader
            workbook_rows.append(
                WorkbookRow(
                    excel_row=offset,
                    cert_number=cert,
                    card_title=card,
                    grader=grader,
                    existing_value=row.get("purchase_price"),
                    status="Ready" if cert and grader else "Needs setup",
                    notes=str(row.get("notes") or ""),
                )
            )
            sources[offset] = str(row.get("source") or name)
        self.state.set_rows(workbook_rows)
        self.row_sources = sources
        self.comp_sheet_sources = {}
        self._refresh_table()
        self.selected_working_sheet.set(name)
        self._select_working_sheet_in_list()
        self.status_var.set(f"Loaded working sheet: {name}")

    def _selected_working_sheet_name(self) -> str:
        if hasattr(self, "working_sheet_list"):
            selected = self.working_sheet_list.curselection()
            if selected:
                return str(self.working_sheet_list.get(selected[0]))
        return self.selected_working_sheet.get()

    def _select_working_sheet_in_list(self) -> None:
        if not hasattr(self, "working_sheet_list"):
            return
        target = self.selected_working_sheet.get()
        self.working_sheet_list.selection_clear(0, tk.END)
        for index, name in enumerate(self.working_sheet_list.get(0, tk.END)):
            if name == target:
                self.working_sheet_list.selection_set(index)
                self.working_sheet_list.see(index)
                break

    def clear_rows(self) -> None:
        self.intake_rows = []
        self.intake_sources = {}
        self.intake_sheet_sources = {}
        self._refresh_table()
        self.status_var.set("Intake rows cleared.")

    def _append_rows(self, rows: list[dict[str, object]]) -> list[int]:
        existing = list(self.intake_rows)
        start = len(existing) + 2
        added_excel_rows: list[int] = []
        for offset, row in enumerate(rows):
            cert = str(row.get("cert_number") or "")
            grader = str(row.get("grader") or infer_grader(str(row.get("card_title") or ""))).upper()
            card = str(row.get("card_title") or "").strip() or grader
            status = "Ready" if cert and grader else "Needs setup"
            notes = str(row.get("notes") or "")
            excel_row = start + offset
            existing.append(
                WorkbookRow(
                    excel_row=excel_row,
                    cert_number=cert,
                    card_title=card,
                    grader=grader,
                    existing_value=row.get("purchase_price"),
                    status=status,
                    notes=notes,
                )
            )
            self.intake_sources[excel_row] = str(row.get("source") or "")
            self.intake_sheet_sources[excel_row] = ""
            added_excel_rows.append(excel_row)
        self.intake_rows = existing
        self._refresh_table()
        return added_excel_rows

    def _apply_recommendations(self) -> None:
        for row in self.state.rows:
            source_value = first_number(row.card_ladder_value, row.alt_value, row.cy_value)
            if source_value is None:
                row.best_company = ""
                row.estimated_payout = None
                continue
            best_name, best_rate = max(PAYOUT_RATES.items(), key=lambda item: item[1])
            row.best_company = best_name
            row.estimated_payout = round(source_value * best_rate, 2)

    def _refresh_table(self) -> None:
        self._apply_recommendations()
        self._render_rows(self.intake_tree, self.intake_rows, self.intake_sources)
        self._render_rows(self.comp_tree, self.state.rows, self.row_sources, self.comp_sheet_sources)
        self._render_rows(self.review_tree, self.review_rows, self.review_sources, self.review_sheet_sources)
        completed = sum(1 for row in self.state.rows if row.card_ladder_value is not None)
        self.summary_var.set(f"{len(self.intake_rows)} intake rows | Loaded comp rows: {len(self.state.rows)} | Card Ladder values: {completed}")

    def _render_rows(self, tree: ttk.Treeview, rows: list[WorkbookRow], sources: dict[int, str], sheet_sources: dict[int, str] | None = None) -> None:
        self._remember_column_widths(tree)
        tree.delete(*tree.get_children())
        duplicate_certs = self._duplicate_certs(rows)
        for row in rows:
            tags = []
            if row.cert_number and row.cert_number in duplicate_certs:
                tags.append("duplicate_cert")
            if (sheet_sources or {}).get(row.excel_row) == "NO SHEET FOUND":
                tags.append("no_sheet_found")
            tree.insert(
                "",
                tk.END,
                iid=str(row.excel_row),
                tags=tuple(tags),
                values=(
                        row.excel_row,
                        sources.get(row.excel_row, ""),
                        (sheet_sources or {}).get(row.excel_row, ""),
                        row.cert_number,
                    row.grader,
                    row.card_title,
                    format_money(row.existing_value if isinstance(row.existing_value, (int, float)) else None),
                    format_money(row.card_ladder_value),
                    format_money(row.card_ladder_comps_average),
                    row.best_company,
                    format_money(row.estimated_payout),
                    row.status,
                ),
            )
        if tree is self.review_tree and self.review_mode.get() == "Manual Review":
            tree.insert(
                "",
                tk.END,
                iid=ADD_REVIEW_ROW_IID,
                tags=("add_review_row",),
                values=("+", "", "", "", "", "Add row", "", "", "", "", "", ""),
            )
        self._restore_column_widths(tree)

    def _duplicate_certs(self, rows: list[WorkbookRow]) -> set[str]:
        counts: dict[str, int] = {}
        for row in rows:
            cert = str(row.cert_number or "").strip().upper()
            if not cert:
                continue
            counts[cert] = counts.get(cert, 0) + 1
        return {cert for cert, count in counts.items() if count > 1}

    def _remember_column_widths(self, tree: ttk.Treeview) -> None:
        widths = self.column_widths_by_tree.setdefault(id(tree), {})
        for col in DISPLAY_COLUMNS:
            try:
                widths[col] = int(tree.column(col, "width"))
            except tk.TclError:
                pass

    def _restore_column_widths(self, tree: ttk.Treeview) -> None:
        widths = self.column_widths_by_tree.get(id(tree), {})
        for col in DISPLAY_COLUMNS:
            if col in widths:
                tree.column(col, width=widths[col])

    def _select_excel_row(self, excel_row: int) -> None:
        iid = str(excel_row)
        if self.intake_tree.exists(iid):
            self.intake_tree.selection_set(iid)
            self.intake_tree.focus(iid)
            self.intake_tree.see(iid)

    def _handle_table_click(self, event):
        tree = event.widget
        row_id = tree.identify_row(event.y)
        if tree is self.review_tree and row_id == ADD_REVIEW_ROW_IID:
            self.add_manual_review_row()
            return "break"
        return None

    def _begin_cell_edit(self, event) -> None:
        tree = event.widget
        row_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if tree is self.review_tree and row_id == ADD_REVIEW_ROW_IID:
            self.add_manual_review_row()
            return
        if not row_id or not column_id:
            return
        column_index = int(column_id.replace("#", "")) - 1
        if column_index < 0 or column_index >= len(DISPLAY_COLUMNS):
            return
        column = DISPLAY_COLUMNS[column_index]
        if column not in EDITABLE_COLUMNS:
            return
        bbox = tree.bbox(row_id, column_id)
        if not bbox:
            return
        self._cancel_cell_edit()
        x, y, width, height = bbox
        current = tree.set(row_id, column)
        editor = ttk.Entry(tree)
        editor.insert(0, current)
        editor.select_range(0, tk.END)
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()
        self.cell_editor = editor
        self.cell_edit = (tree, row_id, column)
        editor.bind("<Return>", lambda _event: self._commit_cell_edit())
        editor.bind("<KP_Enter>", lambda _event: self._commit_cell_edit())
        editor.bind("<Escape>", lambda _event: self._cancel_cell_edit())
        editor.bind("<FocusOut>", lambda _event: self._commit_cell_edit())

    def _commit_cell_edit(self) -> None:
        if not self.cell_editor or not self.cell_edit:
            return
        tree, row_id, column = self.cell_edit
        value = self.cell_editor.get()
        self._destroy_cell_editor()
        excel_row = int(row_id)
        self._apply_cell_value(tree, excel_row, column, value)
        self._refresh_table()
        if tree.exists(row_id):
            tree.selection_set(row_id)
            tree.focus(row_id)
            tree.see(row_id)
        self.status_var.set(f"Updated row {excel_row}.")

    def _cancel_cell_edit(self) -> None:
        self._destroy_cell_editor()

    def _destroy_cell_editor(self) -> None:
        if self.cell_editor is not None:
            try:
                self.cell_editor.destroy()
            except tk.TclError:
                pass
        self.cell_editor = None
        self.cell_edit = None

    def _apply_cell_value(self, tree: ttk.Treeview, excel_row: int, column: str, value: str) -> None:
        clean_value = value.strip()
        if tree is self.comp_tree:
            target_rows = self.state.rows
            target_sources = self.row_sources
            target_sheet_sources = self.comp_sheet_sources
        elif tree is self.review_tree:
            target_rows = self.review_rows
            target_sources = self.review_sources
            target_sheet_sources = self.review_sheet_sources
        else:
            target_rows = self.intake_rows
            target_sources = self.intake_sources
            target_sheet_sources = self.intake_sheet_sources
        if column == "source":
            target_sources[excel_row] = clean_value
            return
        if column == "sheet_source":
            target_sheet_sources[excel_row] = clean_value
            return
        for row in target_rows:
            if row.excel_row != excel_row:
                continue
            if column == "cert_number":
                row.cert_number = scan_to_cert(clean_value)
            elif column == "grader":
                row.grader = normalize_grader(clean_value) or clean_value.upper()
            elif column == "card_title":
                row.card_title = clean_value or row.grader
                inferred = infer_grader(row.card_title)
                if inferred:
                    row.grader = inferred
            elif column == "purchase_price":
                row.existing_value = self._parse_money_text(clean_value)
            row.status = "Ready" if row.cert_number and row.grader else "Needs setup"
            if tree is self.review_tree and column in {"cert_number", "grader", "card_title"}:
                match = self._incoming_match(row.cert_number)
                target_sheet_sources[excel_row] = str(match.get("sheet") or "NO SHEET FOUND")
                if match:
                    row.status = "Received"
                    if is_placeholder_title(row.card_title, row.grader) and match.get("card_title"):
                        row.card_title = str(match.get("card_title") or "")
                    if row.existing_value is None and match.get("purchase_price") is not None:
                        row.existing_value = match.get("purchase_price")
                elif row.cert_number:
                    target_sheet_sources[excel_row] = "NO SHEET FOUND"
                    row.status = "Received - no incoming match"
            if not row.cert_number:
                row.notes = "Missing cert"
            elif not row.grader:
                row.notes = "Missing grader"
            elif row.notes in {"Missing cert", "Missing grader", "Missing cert or grader"}:
                row.notes = ""
            return

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event == "refresh":
                    self._refresh_table()
                elif isinstance(event, tuple):
                    kind, payload = event
                    if kind == "photo_rows":
                        self._append_rows(payload)
                    elif kind == "photo_status":
                        self.photo_status.set(str(payload))
                        self.status_var.set(str(payload))
                    elif kind == "review_rows":
                        self._append_review_rows(payload)
                    elif kind == "review_status":
                        self.review_photo_status.set(str(payload))
                        self.review_status.set(str(payload))
                        self.status_var.set(str(payload))
        except queue.Empty:
            pass
        snapshot = self.state.snapshot()
        if snapshot["extensionLastSeen"]:
            self.status_var.set(f"Bridge running. Extension last seen {snapshot['extensionLastSeen']}.")
        self.after(1000, self._poll_events)

    def _parse_money_text(self, value: str) -> float | None:
        text = value.strip().replace("$", "").replace(",", "")
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _arm_scanner(self) -> None:
        if self.input_mode.get() != "Barcode Scanner" or self.scan_entry is None:
            return
        try:
            self.scan_entry.focus_set()
            self.scan_entry.icursor(tk.END)
        except tk.TclError:
            pass

    def destroy(self) -> None:
        self.bridge.stop()
        super().destroy()


def first_number(*values: float | None) -> float | None:
    for value in values:
        if value is not None:
            return value
    return None


def is_placeholder_title(card_title: str, grader: str) -> bool:
    title = str(card_title or "").strip()
    company = str(grader or "").strip()
    if not title:
        return True
    return bool(company and title.upper() == company.upper())


if __name__ == "__main__":
    CardPipelineApp().mainloop()
