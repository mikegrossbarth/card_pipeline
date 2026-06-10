from __future__ import annotations

import queue
import base64
import json
import os
import shutil
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
    comp_price,
    format_comps,
    parse_formatted_comps,
    row_has_comp_data,
)
from workbook_io import WorkbookRow  # noqa: E402
from assignment_engine import AssignmentEngine  # noqa: E402
from assignment_config_ui import open_assignment_rules_dialog  # noqa: E402

from intake_io import (  # noqa: E402
    append_company_sheet_rows,
    build_card_title,
    clean_part,
    default_output_path,
    format_money,
    infer_grader,
    mark_received_in_workbooks,
    normalize_grader,
    read_photo_export,
    read_simple_spreadsheet,
    scan_to_cert,
    summarize_workbook,
    working_sheet_path,
    write_working_sheet,
    workbook_sheet_names,
    write_pipeline_output,
)


PHOTO_APP_ROOT = ROOT / "photo_tool"
PHOTO_APP_DIR = PHOTO_APP_ROOT / "app"
if PHOTO_APP_DIR.exists() and str(PHOTO_APP_DIR) not in sys.path:
    sys.path.insert(0, str(PHOTO_APP_DIR))
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None
if load_dotenv:
    load_dotenv(ROOT / ".env", override=False)
    load_dotenv(PHOTO_APP_DIR / ".env", override=False)
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
SETTINGS_PATH = ROOT / "lucas_settings.json"
DEFAULT_CARD_PIPELINE_DIR = ROOT / "CARD_PIPELINE"
CARD_PIPELINE_DIR = Path(os.environ.get("LUCAS_PIPELINE_DIR") or DEFAULT_CARD_PIPELINE_DIR)
WORKING_SHEETS_DIR = Path(os.environ.get("LUCAS_WORKING_SHEETS_DIR") or CARD_PIPELINE_DIR / "WORKING SHEETS")
INCOMING_SHEETS_DIR = CARD_PIPELINE_DIR / "INCOMING SHEETS"
RECEIVED_SHEETS_DIR = CARD_PIPELINE_DIR / "RECEIVED SHEETS"
COMPANY_SHEETS_DIR = CARD_PIPELINE_DIR / "COMPANY SHEETS"
SHEET_MARKERS_PATH = CARD_PIPELINE_DIR / "sheet_markers.json"
LUCAS_LOGO_PATH = ROOT / "assets" / "lucas.png"
APP_TITLE = "L.U.C.A.S"
APP_SUBTITLE = "Lot Upload, Comping & Assignment System"

COMP_STRATEGY_DISPLAY = {
    "Average last 5": COMP_STRATEGY_AVERAGE,
    "Highest of last 5": COMP_STRATEGY_HIGH,
    "Lowest of last 5": COMP_STRATEGY_LOW,
    "Date weighted": COMP_STRATEGY_STALE_NEWEST,
}
COMP_SCOPE_EMPTY = "Empty Comps Only"
COMP_SCOPE_ALL = "Recomp All"


def load_app_settings() -> dict[str, object]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def save_app_settings(settings: dict[str, object]) -> None:
    SETTINGS_PATH.write_text(json.dumps(settings, indent=2, sort_keys=True), encoding="utf-8")


def set_pipeline_root(path: Path, working_sheets_dir: Path | None = None) -> None:
    global CARD_PIPELINE_DIR, WORKING_SHEETS_DIR, INCOMING_SHEETS_DIR, RECEIVED_SHEETS_DIR, COMPANY_SHEETS_DIR, SHEET_MARKERS_PATH
    CARD_PIPELINE_DIR = Path(path).expanduser()
    WORKING_SHEETS_DIR = Path(working_sheets_dir).expanduser() if working_sheets_dir else CARD_PIPELINE_DIR / "WORKING SHEETS"
    INCOMING_SHEETS_DIR = CARD_PIPELINE_DIR / "INCOMING SHEETS"
    RECEIVED_SHEETS_DIR = CARD_PIPELINE_DIR / "RECEIVED SHEETS"
    COMPANY_SHEETS_DIR = CARD_PIPELINE_DIR / "COMPANY SHEETS"
    SHEET_MARKERS_PATH = CARD_PIPELINE_DIR / "sheet_markers.json"


def set_pipeline_from_working_dir(path: Path) -> None:
    working_dir = normalize_working_dir_selection(Path(path).expanduser())
    set_pipeline_root(working_dir.parent, working_dir)


def normalize_working_dir_selection(path: Path) -> Path:
    child = path / "WORKING SHEETS"
    if path.name.upper() != "WORKING SHEETS" and child.exists() and child.is_dir():
        return child
    return path


def initialize_pipeline_root() -> None:
    settings = load_app_settings()
    configured_working = str(settings.get("working_sheets_dir") or os.environ.get("LUCAS_WORKING_SHEETS_DIR") or "").strip()
    if configured_working:
        set_pipeline_from_working_dir(Path(configured_working))
        return
    configured = str(settings.get("pipeline_root") or "").strip()
    if configured:
        set_pipeline_root(Path(configured))


initialize_pipeline_root()

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

INTAKE_COLUMNS = (
    "excel_row",
    "source",
    "cert_number",
    "grader",
    "card_title",
    "purchase_price",
    "card_ladder_value",
    "card_ladder_comps_average",
    "status",
)

COMP_COLUMNS = (
    "excel_row",
    "source",
    "cert_number",
    "grader",
    "card_title",
    "purchase_price",
    "card_ladder_value",
    "card_ladder_comps_average",
    "best_company",
    "estimated_payout",
    "status",
    "sheet_source",
)

RECEIVE_COLUMNS = (
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
    "company_pile",
)

REVIEW_COLUMNS = DISPLAY_COLUMNS

ADD_REVIEW_ROW_IID = "__add_review_row__"

EDITABLE_COLUMNS = {
    "source",
    "cert_number",
    "grader",
    "card_title",
    "purchase_price",
    "card_ladder_value",
    "card_ladder_comps_average",
}

HEADINGS = {
    "excel_row": "Row",
    "source": "Source",
    "sheet_source": "Sheet Source",
    "cert_number": "Cert #",
    "grader": "Company",
    "card_title": "Card",
    "purchase_price": "Purchase",
    "card_ladder_value": "Card Ladder",
    "card_ladder_comps_average": "Comps",
    "best_company": "Best Company",
    "estimated_payout": "Est. Payout",
    "status": "Status",
    "company_pile": "Company Pile",
}

COLUMN_WIDTHS = {
    "excel_row": 52,
    "source": 130,
    "sheet_source": 150,
    "cert_number": 110,
    "grader": 86,
    "card_title": 390,
    "purchase_price": 90,
    "card_ladder_value": 100,
    "card_ladder_comps_average": 100,
    "best_company": 130,
    "estimated_payout": 100,
    "status": 160,
    "company_pile": 105,
}


class CardPipelineApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_TITLE} - {APP_SUBTITLE}")
        self.geometry("1420x820")
        self.minsize(1120, 680)
        self.logo_image: tk.PhotoImage | None = None

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
        self.comp_output_saved = True
        self.state = BridgeState()
        self.state.on_update = lambda: self.events.put("comp_refresh")
        self.bridge = BridgeServer(self.state)
        self.bridge.start()
        self.bridge_status_text = (
            f"Card Ladder bridge running at http://127.0.0.1:{self.bridge.port}"
            if self.bridge.started
            else f"Card Ladder bridge failed to start: {self.bridge.error}"
        )

        self.input_mode = tk.StringVar(value="Barcode Scanner")
        self.review_mode = tk.StringVar(value="Automatic Receive")
        self.review_input_mode = tk.StringVar(value="Barcode Scanner")
        self.comp_strategy_label = tk.StringVar(value="Average last 5")
        self.comp_scope_label = tk.StringVar(value=COMP_SCOPE_EMPTY)
        self.working_sheet_title = tk.StringVar()
        self.selected_working_sheet = tk.StringVar()
        self.summary_var = tk.StringVar(value="Choose a create mode to begin.")
        self.status_var = tk.StringVar(value="Card Ladder bridge starting...")
        self.bridge_status_var = tk.StringVar(value=self.bridge_status_text)
        self.pipeline_root_var = tk.StringVar(value=str(CARD_PIPELINE_DIR))

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
        self.review_scan_entry: ttk.Entry | None = None
        self.review_scanning_active = False
        self.review_status = tk.StringVar(value="Receive station is off.")
        self.assignment_progress_value = tk.DoubleVar(value=0)
        self.review_photo_paths: list[Path] = []
        self.review_photo_status = tk.StringVar(value="No receive photos selected.")
        self.review_photo_worker: threading.Thread | None = None
        self.assignment_engine = AssignmentEngine.load()
        self.assignment_recommendation_job = 0
        self.assignment_recommendation_running = False
        self.assignment_recommendation_after_id: str | None = None
        self.assignment_config_status = tk.StringVar(value=self._assignment_config_status())
        self._ensure_company_sheet_folders()
        self.received_sheet_paths: dict[str, Path] = {}
        self.selected_received_sheet = tk.StringVar()
        self.working_sheet_paths: dict[str, Path] = {}
        self.home_sheet_kind = tk.StringVar(value="Incoming")
        self.home_sheet_paths: dict[str, dict[str, Path]] = {"Incoming": {}, "Working": {}, "Received": {}}
        self.home_sheet_summaries: dict[str, dict[str, object]] = {}
        self.home_sheet_markers: dict[str, dict[str, object]] = self._load_sheet_markers()
        self.home_selected_sheet_key = ""
        self.payout_person_var = tk.StringVar()
        self.payout_status_var = tk.StringVar(value="No unpaid sheets loaded.")
        self.payout_detail_keys: dict[str, str] = {}

        self._build_ui()
        self._show_mode()
        self._poll_events()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.status_var.set(self.bridge_status_text)
        self.after(100, self._start_startup_refresh)

    def _on_close(self) -> None:
        self.destroy()

    def _build_ui(self) -> None:
        palette = {
            "bg": "#121212",
            "surface": "#181818",
            "panel": "#1f1f1f",
            "panel_high": "#242424",
            "field": "#2a2a2a",
            "border": "#333333",
            "muted": "#b3b3b3",
            "button": "#1ed760",
            "button_hover": "#1fdf64",
            "button_pressed": "#169c46",
            "soft_button": "#2a2a2a",
            "soft_button_hover": "#3a3a3a",
            "text": "#ffffff",
            "subtle_text": "#d9d9d9",
            "selection": "#1db954",
            "warning": "#5a4a14",
            "danger": "#5a1f1f",
        }
        self.configure(bg=palette["bg"])
        self.option_add("*TCombobox*Listbox.background", palette["field"])
        self.option_add("*TCombobox*Listbox.foreground", palette["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", palette["selection"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#000000")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10))
        style.configure("App.TFrame", background=palette["bg"])
        style.configure("Panel.TFrame", background=palette["panel"])
        style.configure("Header.TFrame", background=palette["surface"])
        style.configure("Header.TLabel", background=palette["surface"])
        style.configure("HeaderTitle.TLabel", background=palette["surface"], foreground=palette["text"], font=("Segoe UI Semibold", 22))
        style.configure("HeaderSub.TLabel", background=palette["surface"], foreground=palette["muted"])
        style.configure("BridgeBadge.TLabel", background=palette["panel_high"], foreground=palette["button"], font=("Segoe UI Semibold", 9), padding=(12, 7))
        style.configure("Panel.TLabel", background=palette["panel"], foreground=palette["text"])
        style.configure("Muted.TLabel", background=palette["panel"], foreground=palette["muted"])
        style.configure("Status.TLabel", background=palette["bg"], foreground=palette["muted"])
        style.configure("Panel.TCheckbutton", background=palette["panel"], foreground=palette["text"])
        style.map(
            "Panel.TCheckbutton",
            background=[("active", palette["panel"])],
            foreground=[("active", palette["text"]), ("disabled", "#777777")],
        )
        style.configure(
            "ChromeTab.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(12, 6),
            background=palette["soft_button"],
            foreground=palette["muted"],
            borderwidth=0,
            relief=tk.FLAT,
        )
        style.map(
            "ChromeTab.TButton",
            background=[("pressed", palette["border"]), ("active", palette["soft_button_hover"])],
            foreground=[("active", palette["text"])],
        )
        style.configure(
            "ChromeTabActive.TButton",
            font=("Segoe UI Semibold", 9),
            padding=(12, 6),
            background=palette["panel_high"],
            foreground=palette["text"],
            borderwidth=0,
            relief=tk.FLAT,
        )
        style.map(
            "ChromeTabActive.TButton",
            background=[("pressed", palette["panel_high"]), ("active", palette["panel_high"])],
            foreground=[("active", palette["text"])],
        )
        style.configure(
            "Primary.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(18, 9),
            background=palette["button"],
            foreground="#000000",
            borderwidth=0,
            focusthickness=0,
            relief=tk.FLAT,
        )
        style.map(
            "Primary.TButton",
            background=[("pressed", palette["button_pressed"]), ("active", palette["button_hover"]), ("disabled", "#535353")],
            foreground=[("disabled", "#b3b3b3")],
            relief=[("pressed", tk.FLAT), ("!pressed", tk.FLAT)],
        )
        style.configure(
            "Soft.TButton",
            font=("Segoe UI Semibold", 10),
            padding=(16, 9),
            background=palette["soft_button"],
            foreground=palette["text"],
            borderwidth=0,
            focusthickness=0,
            relief=tk.FLAT,
        )
        style.map(
            "Soft.TButton",
            background=[("pressed", palette["border"]), ("active", palette["soft_button_hover"]), ("disabled", "#1a1a1a")],
            foreground=[("disabled", "#777777")],
            relief=[("pressed", tk.FLAT), ("!pressed", tk.FLAT)],
        )
        style.configure(
            "TEntry",
            fieldbackground=palette["field"],
            background=palette["field"],
            foreground=palette["text"],
            insertcolor=palette["text"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            padding=(8, 7),
        )
        style.map("TEntry", bordercolor=[("focus", palette["selection"])])
        style.configure(
            "TCombobox",
            fieldbackground=palette["field"],
            background=palette["field"],
            foreground=palette["text"],
            arrowcolor=palette["muted"],
            bordercolor=palette["border"],
            lightcolor=palette["border"],
            darkcolor=palette["border"],
            padding=(8, 6),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", palette["field"])],
            foreground=[("readonly", palette["text"])],
            bordercolor=[("focus", palette["selection"])],
            arrowcolor=[("active", palette["text"])],
        )
        style.configure("TNotebook", background=palette["bg"], borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure(
            "TNotebook.Tab",
            background=palette["bg"],
            foreground=palette["muted"],
            padding=(18, 10),
            borderwidth=0,
            font=("Segoe UI Semibold", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", palette["panel"]), ("active", palette["panel_high"])],
            foreground=[("selected", palette["text"]), ("active", palette["text"])],
        )
        style.configure("Vertical.TScrollbar", background=palette["field"], troughcolor=palette["panel"], bordercolor=palette["panel"], arrowcolor=palette["muted"])
        style.configure("Horizontal.TScrollbar", background=palette["field"], troughcolor=palette["panel"], bordercolor=palette["panel"], arrowcolor=palette["muted"])
        style.configure(
            "Assignment.Horizontal.TProgressbar",
            background="#16a34a",
            troughcolor="#ffffff",
            bordercolor="#d7dde3",
            lightcolor="#16a34a",
            darkcolor="#15803d",
        )
        style.configure("Treeview", rowheight=34, font=("Segoe UI", 10), background=palette["panel"], fieldbackground=palette["panel"], foreground=palette["subtle_text"], borderwidth=0)
        style.configure("Treeview.Heading", font=("Segoe UI Semibold", 9), background=palette["panel_high"], foreground=palette["muted"], padding=(10, 8), borderwidth=0)
        style.map("Treeview", background=[("selected", palette["selection"])], foreground=[("selected", "#000000")])

        header = ttk.Frame(self, style="Header.TFrame", padding=(18, 16))
        header.pack(fill=tk.X)
        if LUCAS_LOGO_PATH.exists():
            try:
                self.logo_image = tk.PhotoImage(file=str(LUCAS_LOGO_PATH)).subsample(6, 6)
                self.iconphoto(False, self.logo_image)
                ttk.Label(header, image=self.logo_image, style="Header.TLabel").pack(side=tk.LEFT, padx=(0, 14))
            except tk.TclError:
                self.logo_image = None
        title_group = ttk.Frame(header, style="Header.TFrame")
        title_group.pack(side=tk.LEFT)
        ttk.Label(title_group, text=APP_TITLE, style="HeaderTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(title_group, text=APP_SUBTITLE, style="HeaderSub.TLabel").pack(anchor=tk.W, pady=(3, 0))
        ttk.Label(header, textvariable=self.bridge_status_var, style="BridgeBadge.TLabel").pack(side=tk.RIGHT, padx=(16, 0))
        ttk.Button(header, text="Working Folder", command=self.choose_working_folder, style="Soft.TButton").pack(side=tk.RIGHT, padx=(16, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill=tk.BOTH, expand=True, padx=18, pady=(16, 12))
        self.home_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.intake_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.comp_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.receive_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.review_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.payouts_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.profit_tab = ttk.Frame(self.tabs, style="App.TFrame", padding=0)
        self.tabs.add(self.home_tab, text="Home")
        self.tabs.add(self.intake_tab, text="Create")
        self.tabs.add(self.comp_tab, text="Comp")
        self.tabs.add(self.receive_tab, text="Receive")
        self.tabs.add(self.review_tab, text="Assignment")
        self.tabs.add(self.payouts_tab, text="Payouts/Tabs")
        self.tabs.add(self.profit_tab, text="Profit")
        self.row_trees: list[ttk.Treeview] = []

        self._build_home_tab(palette)

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
        ttk.Button(intake_controls, text="Delete Selected", command=self.delete_selected_intake_rows, style="Soft.TButton").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Button(intake_controls, text="Clear Rows", command=self.clear_rows, style="Soft.TButton").grid(row=0, column=3, sticky="w")
        intake_controls.columnconfigure(4, weight=1)
        ttk.Label(intake_controls, textvariable=self.summary_var, style="Muted.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))

        self.mode_host = ttk.Frame(self.intake_tab, style="Panel.TFrame", padding=(16, 12))
        self.mode_host.pack(fill=tk.X, pady=(0, 10))
        self.intake_tree = self._build_table(self.intake_tab, editable=True, columns=INTAKE_COLUMNS)
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
        self.working_sheet_list = tk.Listbox(
            sheet_panel,
            width=34,
            height=24,
            activestyle="none",
            exportselection=False,
            bg=palette["panel"],
            fg=palette["subtle_text"],
            selectbackground=palette["selection"],
            selectforeground="#000000",
            highlightthickness=1,
            highlightbackground=palette["border"],
            highlightcolor=palette["selection"],
            relief=tk.FLAT,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.working_sheet_list.pack(fill=tk.Y, expand=True, pady=(8, 8))
        self.working_sheet_list.bind("<Double-Button-1>", lambda _event: self.load_selected_working_sheet())
        ttk.Button(sheet_panel, text="Load Selected Sheet", command=self.load_selected_working_sheet, style="Primary.TButton").pack(fill=tk.X, pady=(0, 8))
        ttk.Button(sheet_panel, text="Refresh Sheets", command=self.refresh_pipeline, style="Soft.TButton").pack(fill=tk.X)
        comp_main = ttk.Frame(comp_body, style="App.TFrame")
        comp_main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.comp_tree = self._build_table(comp_main, editable=True, columns=COMP_COLUMNS)
        comp_controls = ttk.Frame(comp_main, style="Panel.TFrame", padding=(16, 12))
        comp_controls.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(comp_controls, text="Save Output", command=self.save_output, style="Soft.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(comp_controls, text="Run All Comps", command=self.run_all_comps, style="Primary.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(comp_controls, text="Stop Run", command=self.stop_comp_run, style="Soft.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(comp_controls, text="Clear Comp Rows", command=self.clear_comp_rows, style="Soft.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        self.comp_scope_combo = ttk.Combobox(
            comp_controls,
            textvariable=self.comp_scope_label,
            state="readonly",
            values=(COMP_SCOPE_EMPTY, COMP_SCOPE_ALL),
            width=17,
        )
        self.comp_scope_combo.pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Label(comp_controls, text="Run Scope", style="Panel.TLabel").pack(side=tk.RIGHT)
        self.comp_method_combo = ttk.Combobox(
            comp_controls,
            textvariable=self.comp_strategy_label,
            state="readonly",
            values=list(COMP_STRATEGY_DISPLAY.keys()),
            width=20,
        )
        self.comp_method_combo.pack(side=tk.RIGHT, padx=(8, 0))
        self.comp_method_combo.bind("<<ComboboxSelected>>", self.recalculate_comp_method)
        ttk.Label(comp_controls, text="Comp Method", style="Panel.TLabel").pack(side=tk.RIGHT)

        receive_controls = ttk.Frame(self.receive_tab, style="Panel.TFrame", padding=(16, 12))
        receive_controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(receive_controls, text="Receive Mode", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        review_mode = ttk.Combobox(
            receive_controls,
            textvariable=self.review_mode,
            state="readonly",
            values=["Automatic Receive", "Manual Receive"],
            width=20,
        )
        review_mode.grid(row=0, column=1, sticky="w", padx=(8, 16))
        review_mode.bind("<<ComboboxSelected>>", lambda _event: self._show_review_mode())
        ttk.Label(receive_controls, textvariable=self.review_status, style="Muted.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))
        receive_controls.columnconfigure(4, weight=1)

        self.review_mode_host = ttk.Frame(self.receive_tab, style="Panel.TFrame", padding=(16, 12))
        self.review_mode_host.pack(fill=tk.X, pady=(0, 10))
        self.receive_tree = self._build_table(self.receive_tab, editable=True, columns=RECEIVE_COLUMNS)
        receive_bottom = ttk.Frame(self.receive_tab, style="Panel.TFrame", padding=(16, 12))
        receive_bottom.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(receive_bottom, text="Mark Received in Sheets", command=self.mark_review_received_in_sheets, style="Primary.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(receive_bottom, text="Refresh Incoming Sheets", command=self.refresh_incoming_index, style="Soft.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(receive_bottom, text="Delete Selected", command=self.delete_selected_review_rows, style="Soft.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(receive_bottom, text="Clear Receive Rows", command=self.clear_review_rows, style="Soft.TButton").pack(side=tk.RIGHT)

        review_controls = ttk.Frame(self.review_tab, style="Panel.TFrame", padding=(16, 12))
        review_controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(review_controls, text="Received Sheet", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.received_sheet_combo = ttk.Combobox(review_controls, textvariable=self.selected_received_sheet, state="readonly", width=32)
        self.received_sheet_combo.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        ttk.Button(review_controls, text="Load", command=self.load_selected_received_sheet_for_review, style="Primary.TButton").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Button(review_controls, text="Refresh", command=self.refresh_received_sheets, style="Soft.TButton").grid(row=0, column=3, sticky="w")
        ttk.Button(review_controls, text="Assignment Rules", command=self.open_assignment_rules, style="Soft.TButton").grid(row=0, column=4, sticky="w", padx=(8, 0))
        review_controls.columnconfigure(1, weight=1)
        ttk.Label(review_controls, textvariable=self.review_status, style="Muted.TLabel").grid(row=1, column=0, columnspan=5, sticky="w", pady=(10, 0))
        ttk.Label(review_controls, textvariable=self.assignment_config_status, style="Muted.TLabel").grid(row=2, column=0, columnspan=5, sticky="w", pady=(4, 0))
        self.assignment_progress = ttk.Progressbar(
            review_controls,
            style="Assignment.Horizontal.TProgressbar",
            variable=self.assignment_progress_value,
            maximum=100,
            mode="determinate",
        )
        self.assignment_progress.grid(row=3, column=0, columnspan=5, sticky="ew", pady=(8, 0))
        self.review_tree = self._build_table(self.review_tab, editable=True, columns=REVIEW_COLUMNS)
        review_bottom = ttk.Frame(self.review_tab, style="Panel.TFrame", padding=(16, 12))
        review_bottom.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(review_bottom, text="Delete Selected", command=self.delete_selected_review_rows, style="Soft.TButton").pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(review_bottom, text="Clear Assignment Rows", command=self.clear_review_rows, style="Soft.TButton").pack(side=tk.RIGHT)
        self._show_review_mode()
        self._build_payouts_tab()
        self._build_profit_tab()

        bottom = ttk.Frame(self, style="App.TFrame", padding=(16, 0, 16, 14))
        bottom.pack(fill=tk.X)
        ttk.Label(bottom, textvariable=self.status_var, style="Status.TLabel").pack(side=tk.LEFT)

    def _build_table(self, parent: ttk.Frame, editable: bool = False, columns: tuple[str, ...] = DISPLAY_COLUMNS) -> ttk.Treeview:
        content = ttk.Frame(parent, style="Panel.TFrame", padding=(1, 1))
        content.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(content, columns=columns, show="headings", selectmode="extended")
        setattr(tree, "_display_columns", columns)
        for col in columns:
            tree.heading(col, text=HEADINGS[col], anchor=tk.W)
            tree.column(col, width=COLUMN_WIDTHS[col], minwidth=45, stretch=False)
        tree.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(content, orient=tk.VERTICAL, command=tree.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(content, orient=tk.HORIZONTAL, command=tree.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        tree.tag_configure("duplicate_cert", background="#4a3d12", foreground="#fff3b0")
        tree.tag_configure("no_sheet_found", background="#4a1717", foreground="#ffd1d1")
        tree.tag_configure("add_review_row", background="#242424", foreground="#1ed760")
        if editable:
            tree.bind("<Double-1>", self._begin_cell_edit)
            tree.bind("<Button-1>", self._handle_table_click, add="+")
            tree.bind("<Delete>", self._delete_selected_table_rows)
        tree.bind("<ButtonRelease-1>", lambda _event, target=tree: self._remember_column_widths(target), add="+")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        setattr(tree, "_table_frame", content)
        self.row_trees.append(tree)
        self.column_widths_by_tree[id(tree)] = {col: COLUMN_WIDTHS[col] for col in columns}
        return tree

    def _build_home_tab(self, palette: dict[str, str]) -> None:
        body = ttk.Frame(self.home_tab, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)

        sheet_panel = ttk.Frame(body, style="Panel.TFrame", padding=(12, 12))
        sheet_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        sheet_panel.configure(width=360)
        sheet_panel.pack_propagate(False)
        toggle_row = tk.Frame(sheet_panel, bg=palette["panel"])
        toggle_row.pack(fill=tk.X, pady=(0, 8))
        self.home_tab_palette = palette
        self.home_incoming_tab = self._build_home_tab_button(toggle_row, "Incoming", lambda: self._set_home_sheet_kind("Incoming"))
        self.home_incoming_tab.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.home_working_tab = self._build_home_tab_button(toggle_row, "Working", lambda: self._set_home_sheet_kind("Working"))
        self.home_working_tab.grid(row=0, column=1, sticky="ew", padx=(0, 4))
        self.home_received_tab = self._build_home_tab_button(toggle_row, "Received", lambda: self._set_home_sheet_kind("Received"))
        self.home_received_tab.grid(row=0, column=2, sticky="ew", padx=(0, 4))
        self.home_edit_markers_tab = self._build_home_tab_button(toggle_row, "Edit Markers", self.open_sheet_marker_editor)
        self.home_edit_markers_tab.grid(row=0, column=3, sticky="ew")
        for col in range(4):
            toggle_row.columnconfigure(col, weight=1, uniform="home_tabs")
        self.home_sheet_list = tk.Listbox(
            sheet_panel,
            width=1,
            height=28,
            activestyle="none",
            exportselection=False,
            bg=palette["panel"],
            fg=palette["subtle_text"],
            selectbackground=palette["selection"],
            selectforeground="#000000",
            highlightthickness=1,
            highlightbackground=palette["border"],
            highlightcolor=palette["selection"],
            relief=tk.FLAT,
            borderwidth=0,
            font=("Segoe UI", 10),
        )
        self.home_sheet_list.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.home_sheet_list.bind("<<ListboxSelect>>", lambda _event: self._load_home_selected_marker())
        ttk.Button(sheet_panel, text="Refresh Home", command=self.refresh_home, style="Primary.TButton").pack(fill=tk.X)

        right = ttk.Frame(body, style="App.TFrame")
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        metrics = ttk.Frame(right, style="App.TFrame")
        metrics.pack(fill=tk.BOTH, expand=True)
        volume_panel = ttk.Frame(metrics, style="Panel.TFrame", padding=(12, 12))
        volume_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        ttk.Label(volume_panel, text="Incoming Volume by Sheet", style="Panel.TLabel").pack(anchor=tk.W)
        self.incoming_volume_tree = self._build_home_tree(
            volume_panel,
            columns=("sheet", "person", "cards", "received", "volume", "status"),
            headings={"sheet": "Sheet", "person": "Person", "cards": "Cards", "received": "Received", "volume": "Price Volume", "status": "Status"},
            widths={"sheet": 320, "person": 130, "cards": 80, "received": 95, "volume": 130, "status": 150},
            height=9,
        )

        partial_panel = ttk.Frame(metrics, style="Panel.TFrame", padding=(12, 12))
        partial_panel.pack(fill=tk.BOTH, expand=True)
        ttk.Label(partial_panel, text="Partially Received Incoming Sheets", style="Panel.TLabel").pack(anchor=tk.W)
        self.partial_received_tree = self._build_home_tree(
            partial_panel,
            columns=("sheet", "progress", "volume", "person", "tracking", "all_received"),
            headings={"sheet": "Sheet", "progress": "Received", "volume": "Price Volume", "person": "Person", "tracking": "Tracking", "all_received": "All Received"},
            widths={"sheet": 280, "progress": 100, "volume": 130, "person": 130, "tracking": 180, "all_received": 110},
            height=8,
        )
        self.partial_received_tree.tag_configure("partial_sheet", background="#4a3d12", foreground="#fff3b0")

    def _build_home_tree(self, parent: ttk.Frame, columns: tuple[str, ...], headings: dict[str, str], widths: dict[str, int], height: int) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse", height=height)
        for col in columns:
            tree.heading(col, text=headings[col], anchor=tk.W)
            tree.column(col, width=widths[col], minwidth=60, stretch=col == "sheet", anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        return tree

    def _build_payouts_tab(self) -> None:
        controls = ttk.Frame(self.payouts_tab, style="Panel.TFrame", padding=(16, 12))
        controls.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(controls, text="Filter by Assigned Person", style="Panel.TLabel").grid(row=0, column=0, sticky="w")
        self.payout_person_combo = ttk.Combobox(controls, textvariable=self.payout_person_var, width=30)
        self.payout_person_combo.grid(row=0, column=1, sticky="w", padx=(8, 10))
        self._bind_person_autocomplete(self.payout_person_combo, refresh_callback=self.refresh_payouts_tab)
        self.payout_person_combo.bind("<<ComboboxSelected>>", lambda _event: self.refresh_payouts_tab(), add="+")
        controls.columnconfigure(2, weight=1)
        ttk.Label(controls, textvariable=self.payout_status_var, style="Muted.TLabel").grid(row=1, column=0, columnspan=3, sticky="w", pady=(10, 0))

        body = ttk.Frame(self.payouts_tab, style="App.TFrame")
        body.pack(fill=tk.BOTH, expand=True)
        summary_panel = ttk.Frame(body, style="Panel.TFrame", padding=(12, 12))
        summary_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        ttk.Label(summary_panel, text="Active Balances", style="Panel.TLabel").pack(anchor=tk.W)
        self.payout_summary_tree = self._build_home_tree(
            summary_panel,
            columns=("person", "sheets", "cards", "balance"),
            headings={"person": "Person", "sheets": "Sheets", "cards": "Cards", "balance": "Balance Owed"},
            widths={"person": 220, "sheets": 80, "cards": 80, "balance": 130},
            height=18,
        )

        detail_panel = ttk.Frame(body, style="Panel.TFrame", padding=(12, 12))
        detail_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ttk.Label(detail_panel, text="Unpaid Sheets", style="Panel.TLabel").pack(anchor=tk.W)
        self.payout_detail_tree = self._build_home_tree(
            detail_panel,
            columns=("sheet", "stage", "person", "cards", "received", "volume", "status"),
            headings={"sheet": "Sheet", "stage": "Stage", "person": "Person", "cards": "Cards", "received": "Received", "volume": "Balance", "status": "Status"},
            widths={"sheet": 280, "stage": 90, "person": 150, "cards": 80, "received": 95, "volume": 130, "status": 140},
            height=18,
        )
        self.payout_detail_tree.configure(selectmode="extended")
        self.payout_detail_tree.bind("<ButtonRelease-1>", self.open_payout_marker_editor)

    def _build_profit_tab(self) -> None:
        panel = ttk.Frame(self.profit_tab, style="Panel.TFrame", padding=(16, 12))
        panel.pack(fill=tk.BOTH, expand=True)
        ttk.Label(panel, text="Profit", style="Panel.TLabel", font=("Segoe UI Semibold", 13)).pack(anchor=tk.W)
        ttk.Label(panel, text="Profit calculations will live here.", style="Muted.TLabel").pack(anchor=tk.W, pady=(8, 0))

    def choose_working_folder(self) -> None:
        selected = filedialog.askdirectory(
            title="Choose WORKING SHEETS folder",
            initialdir=str(WORKING_SHEETS_DIR if WORKING_SHEETS_DIR.exists() else CARD_PIPELINE_DIR if CARD_PIPELINE_DIR.exists() else ROOT),
        )
        if not selected:
            return
        set_pipeline_from_working_dir(Path(selected))
        settings = load_app_settings()
        settings["pipeline_root"] = str(CARD_PIPELINE_DIR)
        settings["working_sheets_dir"] = str(WORKING_SHEETS_DIR)
        save_app_settings(settings)
        self.pipeline_root_var.set(str(CARD_PIPELINE_DIR))
        for directory in (WORKING_SHEETS_DIR, INCOMING_SHEETS_DIR, RECEIVED_SHEETS_DIR):
            directory.mkdir(parents=True, exist_ok=True)
        COMPANY_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
        self.home_sheet_markers = self._load_sheet_markers()
        self.status_var.set(f"Working folder set to {WORKING_SHEETS_DIR}")
        self.refresh_home()
        self.refresh_working_sheets()
        self.refresh_incoming_index()
        self.refresh_received_sheets()

    def choose_pipeline_root(self) -> None:
        self.choose_working_folder()

    def _build_home_tab_button(self, parent: tk.Frame, text: str, command) -> tk.Button:
        palette = self.home_tab_palette
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=palette["soft_button"],
            fg=palette["muted"],
            activebackground=palette["soft_button_hover"],
            activeforeground=palette["text"],
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=0,
            padx=8,
            pady=6,
            font=("Segoe UI Semibold", 9),
            cursor="hand2",
        )

    def _set_home_sheet_kind(self, kind: str) -> None:
        self.home_sheet_kind.set(kind)
        self._update_home_sheet_tabs()
        self._refresh_home_sheet_list()

    def _update_home_sheet_tabs(self) -> None:
        if not hasattr(self, "home_incoming_tab") or not hasattr(self, "home_working_tab"):
            return
        palette = self.home_tab_palette
        active_kind = self.home_sheet_kind.get()
        active = {"bg": palette["panel_high"], "fg": palette["text"], "activebackground": palette["panel_high"], "activeforeground": palette["text"]}
        inactive = {"bg": palette["soft_button"], "fg": palette["muted"], "activebackground": palette["soft_button_hover"], "activeforeground": palette["text"]}
        self.home_incoming_tab.configure(**(active if active_kind == "Incoming" else inactive))
        self.home_working_tab.configure(**(active if active_kind == "Working" else inactive))
        if hasattr(self, "home_received_tab"):
            self.home_received_tab.configure(**(active if active_kind == "Received" else inactive))
        if hasattr(self, "home_edit_markers_tab"):
            self.home_edit_markers_tab.configure(**inactive)

    def refresh_home(self) -> None:
        self.home_sheet_paths = {"Incoming": {}, "Working": {}, "Received": {}}
        self.home_sheet_summaries = {}
        errors: list[str] = []
        for kind, directory in (("Incoming", INCOMING_SHEETS_DIR), ("Working", WORKING_SHEETS_DIR), ("Received", RECEIVED_SHEETS_DIR)):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                paths = sorted(directory.glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
            except Exception as error:
                errors.append(f"{kind}: {error}")
                continue
            self.home_sheet_paths[kind] = {path.name: path for path in paths}
            for path in paths:
                key = self._home_sheet_key(kind, path.name)
                try:
                    summary = summarize_workbook(path)
                except Exception as error:
                    errors.append(f"{path.name}: {error}")
                    summary = {"name": path.name, "row_count": 0, "received_count": 0, "purchase_total": 0.0, "all_received": False, "partially_received": False}
                self.home_sheet_summaries[key] = summary
        self._refresh_home_sheet_list()
        self._refresh_home_metrics()
        self.refresh_payouts_tab()
        self._update_home_sheet_tabs()
        if errors:
            self.status_var.set(f"Home refreshed with {len(errors)} sheet issue(s).")
        else:
            self.status_var.set("Home metrics refreshed.")

    def _start_startup_refresh(self) -> None:
        self.status_var.set("Loading sheet lists...")
        thread = threading.Thread(target=self._startup_refresh_worker, daemon=True)
        thread.start()

    def _startup_refresh_worker(self) -> None:
        payload = {
            "working_paths": {},
            "received_paths": {},
            "incoming_index": {},
            "incoming_path_count": 0,
            "home_paths": {"Incoming": {}, "Working": {}, "Received": {}},
            "home_summaries": {},
            "errors": [],
        }
        errors: list[str] = payload["errors"]

        try:
            CARD_PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
            WORKING_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
            working_paths = sorted(WORKING_SHEETS_DIR.glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
            payload["working_paths"] = {path.name: path for path in working_paths}
            payload["home_paths"]["Working"] = {path.name: path for path in working_paths}
        except Exception as error:
            errors.append(f"Working: {error}")
            working_paths = []

        try:
            RECEIVED_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
            received_paths = sorted(RECEIVED_SHEETS_DIR.glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
            payload["received_paths"] = {path.name: path for path in received_paths}
            payload["home_paths"]["Received"] = {path.name: path for path in received_paths}
        except Exception as error:
            errors.append(f"Received: {error}")
            received_paths = []

        try:
            INCOMING_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
            incoming_paths = sorted(INCOMING_SHEETS_DIR.glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
            payload["home_paths"]["Incoming"] = {path.name: path for path in incoming_paths}
            payload["incoming_path_count"] = len(incoming_paths)
        except Exception as error:
            errors.append(f"Incoming: {error}")
            incoming_paths = []

        index: dict[str, dict[str, object]] = {}
        for path in sorted(incoming_paths, key=lambda path: path.name.lower()):
            try:
                rows = read_simple_spreadsheet(path)
            except Exception as error:
                errors.append(f"{path.name}: {error}")
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
                    "card_ladder_value": row.get("card_ladder_value"),
                    "card_ladder_comps_average": row.get("card_ladder_comps_average"),
                    "card_ladder_comps": row.get("card_ladder_comps") or "",
                    "best_company": row.get("best_company") or "",
                    "estimated_payout": row.get("estimated_payout"),
                }
        payload["incoming_index"] = index

        for kind, paths in (("Incoming", incoming_paths), ("Working", working_paths), ("Received", received_paths)):
            for path in paths:
                key = self._home_sheet_key(kind, path.name)
                try:
                    summary = summarize_workbook(path)
                except Exception as error:
                    errors.append(f"{path.name}: {error}")
                    summary = {"name": path.name, "row_count": 0, "received_count": 0, "purchase_total": 0.0, "all_received": False, "partially_received": False}
                payload["home_summaries"][key] = summary

        self.events.put(("startup_refresh", payload))

    def _apply_startup_refresh(self, payload: dict[str, object]) -> None:
        self.working_sheet_paths = dict(payload.get("working_paths") or {})
        if hasattr(self, "working_sheet_list"):
            self.working_sheet_list.delete(0, tk.END)
            for name in self.working_sheet_paths:
                self.working_sheet_list.insert(tk.END, name)
        if self.working_sheet_paths and self.selected_working_sheet.get() not in self.working_sheet_paths:
            self.selected_working_sheet.set(next(iter(self.working_sheet_paths)))
        self._select_working_sheet_in_list()

        self.received_sheet_paths = dict(payload.get("received_paths") or {})
        if hasattr(self, "received_sheet_combo"):
            received_names = list(self.received_sheet_paths)
            self.received_sheet_combo["values"] = received_names
            if received_names and self.selected_received_sheet.get() not in self.received_sheet_paths:
                self.selected_received_sheet.set(received_names[0])
            elif not received_names:
                self.selected_received_sheet.set("")

        self.incoming_cert_index = dict(payload.get("incoming_index") or {})
        self._match_all_review_rows()
        self._refresh_table()
        self.review_status.set(f"Indexed {len(self.incoming_cert_index)} cert(s) from {int(payload.get('incoming_path_count') or 0)} incoming sheet(s).")

        self.home_sheet_paths = dict(payload.get("home_paths") or {"Incoming": {}, "Working": {}, "Received": {}})
        self.home_sheet_summaries = dict(payload.get("home_summaries") or {})
        self._refresh_home_sheet_list()
        self._refresh_home_metrics()
        self.refresh_payouts_tab()
        self._update_home_sheet_tabs()

        errors = list(payload.get("errors") or [])
        if errors:
            self.status_var.set(f"Startup sheet refresh finished with {len(errors)} issue(s).")
        else:
            self.status_var.set("Sheet lists loaded.")

    def _refresh_home_sheet_list(self) -> None:
        if not hasattr(self, "home_sheet_list"):
            return
        kind = self.home_sheet_kind.get()
        self.home_sheet_list.delete(0, tk.END)
        for name in self.home_sheet_paths.get(kind, {}):
            self.home_sheet_list.insert(tk.END, name)
        if self.home_sheet_list.size():
            self.home_sheet_list.selection_set(0)
            self._load_home_selected_marker()
        else:
            self.home_selected_sheet_key = ""

    def _refresh_home_metrics(self) -> None:
        if not hasattr(self, "incoming_volume_tree"):
            return
        for tree in (self.incoming_volume_tree, self.partial_received_tree):
            tree.delete(*tree.get_children())
        incoming_names = self.home_sheet_paths.get("Incoming", {})
        for name in incoming_names:
            key = self._home_sheet_key("Incoming", name)
            summary = self.home_sheet_summaries.get(key, {})
            marker = self.home_sheet_markers.get(key, {})
            total = int(summary.get("row_count") or 0)
            received = int(summary.get("received_count") or 0)
            volume = float(summary.get("purchase_total") or 0.0)
            self.incoming_volume_tree.insert(
                "",
                tk.END,
                values=(
                    name,
                    str(marker.get("assigned_person") or ""),
                    total,
                    received,
                    format_money(volume),
                    self._incoming_sheet_status(marker, summary),
                ),
            )
            if summary.get("partially_received"):
                self.partial_received_tree.insert(
                    "",
                    tk.END,
                    tags=("partial_sheet",),
                    values=(
                        name,
                        f"{received}/{total}",
                        format_money(volume),
                        str(marker.get("assigned_person") or ""),
                        str(marker.get("tracking_number") or ""),
                        "Yes" if marker.get("all_received") else "",
                    ),
                )

    def _incoming_sheet_status(self, marker: dict[str, object], summary: dict[str, object]) -> str:
        has_tracking = bool(str(marker.get("tracking_number") or "").strip())
        received = int(summary.get("received_count") or 0)
        if has_tracking or received:
            return "Awaiting Receive"
        return "Awaiting tracking"

    def refresh_payouts_tab(self) -> None:
        if not hasattr(self, "payout_summary_tree"):
            return
        self._refresh_person_combo_values()
        self.payout_summary_tree.delete(*self.payout_summary_tree.get_children())
        self.payout_detail_tree.delete(*self.payout_detail_tree.get_children())
        self.payout_detail_keys = {}

        balances: dict[str, dict[str, float | int]] = {}
        detail_count = 0
        filter_person = self.payout_person_var.get().strip().lower()
        for item in self._unpaid_payout_sheet_items():
            person = item["person"] or "Unassigned"
            if filter_person and filter_person not in person.lower():
                continue
            balance = balances.setdefault(person, {"sheets": 0, "cards": 0, "balance": 0.0})
            balance["sheets"] = int(balance["sheets"]) + 1
            balance["cards"] = int(balance["cards"]) + int(item["row_count"])
            balance["balance"] = float(balance["balance"]) + float(item["purchase_total"])
            iid = f"payout:{detail_count}"
            self.payout_detail_keys[iid] = str(item["key"])
            self.payout_detail_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    item["name"],
                    item["stage"],
                    item["person"],
                    item["row_count"],
                    f"{item['received_count']}/{item['row_count']}",
                    format_money(float(item["purchase_total"])),
                    item["status"],
                ),
            )
            detail_count += 1

        for person, values in sorted(balances.items(), key=lambda pair: (-float(pair[1]["balance"]), pair[0].lower())):
            self.payout_summary_tree.insert(
                "",
                tk.END,
                values=(
                    person,
                    int(values["sheets"]),
                    int(values["cards"]),
                    format_money(float(values["balance"])),
                ),
            )

        total_balance = sum(float(values["balance"]) for values in balances.values())
        filter_label = self.payout_person_var.get().strip()
        suffix = f" | Filter: {filter_label}" if filter_label else ""
        self.payout_status_var.set(f"{detail_count} unpaid sheet(s) | Active balance: {format_money(total_balance)}{suffix}")

    def _unpaid_payout_sheet_items(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for stage in ("Incoming", "Received"):
            for name in self.home_sheet_paths.get(stage, {}):
                key = self._home_sheet_key(stage, name)
                marker = self.home_sheet_markers.get(key, {})
                summary = self.home_sheet_summaries.get(key, {})
                if bool(marker.get("paid")):
                    continue
                row_count = int(summary.get("row_count") or 0)
                received_count = int(summary.get("received_count") or 0)
                if stage == "Received":
                    received_count = int(summary.get("received_count") or row_count)
                status = self._payout_sheet_status(stage, marker, summary)
                items.append(
                    {
                        "key": key,
                        "stage": stage,
                        "name": name,
                        "person": str(marker.get("assigned_person") or "").strip(),
                        "row_count": row_count,
                        "received_count": received_count,
                        "purchase_total": float(summary.get("purchase_total") or 0.0),
                        "status": status,
                    }
                )
        return items

    def _payout_sheet_status(self, stage: str, marker: dict[str, object], summary: dict[str, object]) -> str:
        received_count = int(summary.get("received_count") or 0)
        if stage == "Received" or marker.get("all_received") or summary.get("all_received"):
            return "Unpaid"
        if received_count:
            return "Partially Received"
        return "Unreceived"

    def _known_assigned_people(self) -> list[str]:
        people = {
            str(marker.get("assigned_person") or "").strip()
            for marker in self.home_sheet_markers.values()
            if str(marker.get("assigned_person") or "").strip()
        }
        return sorted(people, key=str.lower)

    def _refresh_person_combo_values(self, filter_text: str = "") -> None:
        people = self._known_assigned_people()
        if filter_text:
            needle = filter_text.strip().lower()
            people = [person for person in people if needle in person.lower()]
        if hasattr(self, "payout_person_combo"):
            self.payout_person_combo["values"] = people

    def _bind_person_autocomplete(self, combo: ttk.Combobox, refresh_callback=None) -> None:
        combo["values"] = self._known_assigned_people()
        combo.bind("<KeyRelease>", lambda event, widget=combo: self._filter_person_combo(widget, event, refresh_callback=refresh_callback), add="+")

    def _filter_person_combo(self, combo: ttk.Combobox, event, refresh_callback=None) -> None:
        if event.keysym in {"Up", "Down", "Left", "Right", "Return", "KP_Enter", "Escape", "Tab"}:
            return
        typed = combo.get()
        people = self._known_assigned_people()
        if typed.strip():
            people = [person for person in people if typed.strip().lower() in person.lower()]
        combo["values"] = people
        if people:
            try:
                combo.event_generate("<Down>")
            except tk.TclError:
                pass
        if refresh_callback:
            refresh_callback()

    def _selected_payout_keys(self) -> list[str]:
        if not hasattr(self, "payout_detail_tree"):
            return []
        return [self.payout_detail_keys.get(iid, "") for iid in self.payout_detail_tree.selection() if self.payout_detail_keys.get(iid)]

    def open_payout_marker_editor(self, event=None) -> None:
        if event is not None:
            row_id = self.payout_detail_tree.identify_row(event.y)
            if not row_id:
                return
            self.payout_detail_tree.selection_set(row_id)
        keys = self._selected_payout_keys()
        if not keys:
            return
        key = keys[0]
        kind, name = self._split_home_sheet_key(key)
        marker = self.home_sheet_markers.get(key, {})
        summary = self.home_sheet_summaries.get(key, {})
        paid_var = tk.BooleanVar(value=bool(marker.get("paid")))
        person_var = tk.StringVar(value=str(marker.get("assigned_person") or "").strip())

        popup = tk.Toplevel(self)
        popup.title("Payout Sheet")
        popup.configure(bg="#1f1f1f")
        popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)

        frame = ttk.Frame(popup, style="Panel.TFrame", padding=(18, 16))
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=name, style="Panel.TLabel", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        ttk.Label(frame, text=f"{kind} | Balance: {format_money(float(summary.get('purchase_total') or 0.0))}", style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Label(frame, text="Assigned Person", style="Panel.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 10), pady=(0, 10))
        person_combo = ttk.Combobox(frame, textvariable=person_var, width=34)
        person_combo.grid(row=2, column=1, sticky="ew", pady=(0, 10))
        self._bind_person_autocomplete(person_combo)
        ttk.Checkbutton(frame, text="Paid", variable=paid_var, style="Panel.TCheckbutton").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 14))
        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=popup.destroy, style="Soft.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            buttons,
            text="Save",
            command=lambda: self.save_payout_sheet_marker(key, person_var.get().strip(), bool(paid_var.get()), popup),
            style="Primary.TButton",
        ).pack(side=tk.LEFT)
        frame.columnconfigure(1, weight=1)
        popup.update_idletasks()
        x = self.winfo_rootx() + max(80, (self.winfo_width() - popup.winfo_width()) // 2)
        y = self.winfo_rooty() + max(80, (self.winfo_height() - popup.winfo_height()) // 2)
        popup.geometry(f"+{x}+{y}")

    def save_payout_sheet_marker(self, key: str, person: str, paid: bool, popup: tk.Toplevel | None = None) -> None:
        marker = dict(self.home_sheet_markers.get(key, {}))
        kind, _name = self._split_home_sheet_key(key)
        summary = self.home_sheet_summaries.get(key, {})
        marker["assigned_person"] = person.strip()
        marker["paid"] = bool(paid)
        marker["all_received"] = bool(marker.get("all_received") or summary.get("all_received") or kind == "Received")
        marker["tracking_number"] = str(marker.get("tracking_number") or "")
        self.home_sheet_markers[key] = marker
        self._save_sheet_markers()
        self.refresh_home()
        if popup is not None:
            popup.destroy()
        self.status_var.set(f"Updated payout marker for {self._split_home_sheet_key(key)[1]}.")

    def _load_home_selected_marker(self) -> None:
        if not hasattr(self, "home_sheet_list"):
            return
        selected = self.home_sheet_list.curselection()
        if not selected:
            return
        kind = self.home_sheet_kind.get()
        name = str(self.home_sheet_list.get(selected[0]))
        key = self._home_sheet_key(kind, name)
        self.home_selected_sheet_key = key

    def open_sheet_marker_editor(self) -> None:
        if not self.home_selected_sheet_key:
            messagebox.showinfo("Choose sheet", "Choose a sheet on Home before editing markers.")
            return
        kind, name = self._split_home_sheet_key(self.home_selected_sheet_key)
        marker = self.home_sheet_markers.get(self.home_selected_sheet_key, {})
        summary = self.home_sheet_summaries.get(self.home_selected_sheet_key, {})
        incoming_proper_var = tk.BooleanVar(value=(kind == "Incoming"))
        all_received_var = tk.BooleanVar(value=bool(marker.get("all_received") or summary.get("all_received")))
        tracking_var = tk.StringVar(value=str(marker.get("tracking_number") or ""))
        person_var = tk.StringVar(value=str(marker.get("assigned_person") or ""))

        popup = tk.Toplevel(self)
        popup.title("Edit Sheet Markers")
        popup.configure(bg="#1f1f1f")
        popup.transient(self)
        popup.grab_set()
        popup.resizable(False, False)

        frame = ttk.Frame(popup, style="Panel.TFrame", padding=(18, 16))
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text=name, style="Panel.TLabel", font=("Segoe UI Semibold", 12)).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))
        ttk.Label(frame, text=kind, style="Muted.TLabel").grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 14))
        ttk.Checkbutton(frame, text="Incoming Proper", variable=incoming_proper_var, style="Panel.TCheckbutton").grid(row=2, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="Tracking Number", style="Panel.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 10), pady=(0, 10))
        ttk.Entry(frame, textvariable=tracking_var, width=34).grid(row=3, column=1, sticky="ew", pady=(0, 10))
        ttk.Checkbutton(frame, text="All Received", variable=all_received_var, style="Panel.TCheckbutton").grid(row=4, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(frame, text="Assigned Person", style="Panel.TLabel").grid(row=5, column=0, sticky="w", padx=(0, 10), pady=(0, 14))
        person_combo = ttk.Combobox(frame, textvariable=person_var, width=34)
        person_combo.grid(row=5, column=1, sticky="ew", pady=(0, 14))
        self._bind_person_autocomplete(person_combo)
        buttons = ttk.Frame(frame, style="Panel.TFrame")
        buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Cancel", command=popup.destroy, style="Soft.TButton").pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            buttons,
            text="Save Markers",
            command=lambda: self.save_home_sheet_markers(
                {
                    "incoming_proper": bool(incoming_proper_var.get()),
                    "tracking_number": tracking_var.get().strip(),
                    "all_received": bool(all_received_var.get()),
                    "assigned_person": person_var.get().strip(),
                },
                popup,
            ),
            style="Primary.TButton",
        ).pack(side=tk.LEFT)
        frame.columnconfigure(1, weight=1)
        popup.update_idletasks()
        x = self.winfo_rootx() + max(80, (self.winfo_width() - popup.winfo_width()) // 2)
        y = self.winfo_rooty() + max(80, (self.winfo_height() - popup.winfo_height()) // 2)
        popup.geometry(f"+{x}+{y}")

    def save_home_sheet_markers(self, marker: dict[str, object], popup: tk.Toplevel | None = None) -> None:
        if not self.home_selected_sheet_key:
            messagebox.showinfo("Choose sheet", "Choose a sheet on Home before saving markers.")
            return
        existing_marker = dict(self.home_sheet_markers.get(self.home_selected_sheet_key, {}))
        incoming_proper = bool(marker.get("incoming_proper"))
        marker = {
            "paid": bool(existing_marker.get("paid")),
            "tracking_number": str(marker.get("tracking_number") or "").strip(),
            "all_received": bool(marker.get("all_received")),
            "assigned_person": str(marker.get("assigned_person") or "").strip(),
        }
        key = self.home_selected_sheet_key
        moved = False
        try:
            selected_kind, _selected_name = self._split_home_sheet_key(key)
            if selected_kind == "Received" and not marker["all_received"]:
                moved_key = self._move_received_sheet_to_incoming(key)
                if moved_key:
                    self.home_sheet_markers.pop(key, None)
                    key = moved_key
                    self.home_selected_sheet_key = key
                    self.home_sheet_kind.set("Incoming")
                    moved = True
            elif marker["all_received"]:
                moved_key = self._move_sheet_to_received(key)
                if moved_key:
                    self.home_sheet_markers.pop(key, None)
                    key = moved_key
                    self.home_selected_sheet_key = key
                    moved = True
            elif incoming_proper:
                moved_key = self._move_working_sheet_to_incoming(key)
                if moved_key:
                    self.home_sheet_markers.pop(key, None)
                    key = moved_key
                    self.home_selected_sheet_key = key
                    self.home_sheet_kind.set("Incoming")
                    moved = True
            self.home_sheet_markers[key] = marker
            self._save_sheet_markers()
        except Exception as error:
            messagebox.showerror("Save failed", str(error))
            return
        self.refresh_working_sheets()
        self.refresh_received_sheets()
        self.refresh_home()
        if popup is not None:
            popup.destroy()
        self.status_var.set("Sheet markers saved and moved." if moved else "Sheet markers saved.")

    def _home_sheet_key(self, kind: str, name: str) -> str:
        return f"{kind}|{name}"

    def _split_home_sheet_key(self, key: str) -> tuple[str, str]:
        if "|" not in key:
            return "", key
        kind, name = key.split("|", 1)
        return kind, name

    def _move_working_sheet_to_incoming(self, key: str) -> str:
        kind, name = self._split_home_sheet_key(key)
        if kind != "Working" or not name:
            return ""
        source = self.home_sheet_paths.get("Working", {}).get(name) or WORKING_SHEETS_DIR / name
        if not source.exists():
            raise FileNotFoundError(f"Working sheet not found: {source}")
        INCOMING_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
        destination = INCOMING_SHEETS_DIR / source.name
        if destination.exists():
            raise FileExistsError(f"Incoming sheet already exists: {destination.name}")
        shutil.move(str(source), str(destination))
        return self._home_sheet_key("Incoming", destination.name)

    def _move_sheet_to_received(self, key: str) -> str:
        kind, name = self._split_home_sheet_key(key)
        if kind not in {"Working", "Incoming"} or not name:
            return ""
        source = self._sheet_path_for_stage(kind, name)
        if not source.exists():
            raise FileNotFoundError(f"{kind} sheet not found: {source}")
        RECEIVED_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
        destination = RECEIVED_SHEETS_DIR / source.name
        if destination.exists():
            raise FileExistsError(f"Received sheet already exists: {destination.name}")
        shutil.move(str(source), str(destination))
        return self._home_sheet_key("Received", destination.name)

    def _move_received_sheet_to_incoming(self, key: str) -> str:
        kind, name = self._split_home_sheet_key(key)
        if kind != "Received" or not name:
            return ""
        source = self._sheet_path_for_stage(kind, name)
        if not source.exists():
            raise FileNotFoundError(f"Received sheet not found: {source}")
        INCOMING_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
        destination = INCOMING_SHEETS_DIR / source.name
        if destination.exists():
            raise FileExistsError(f"Incoming sheet already exists: {destination.name}")
        shutil.move(str(source), str(destination))
        return self._home_sheet_key("Incoming", destination.name)

    def _sheet_path_for_stage(self, kind: str, name: str) -> Path:
        if kind == "Working":
            return self.home_sheet_paths.get("Working", {}).get(name) or WORKING_SHEETS_DIR / name
        if kind == "Incoming":
            return self.home_sheet_paths.get("Incoming", {}).get(name) or INCOMING_SHEETS_DIR / name
        if kind == "Received":
            return self.received_sheet_paths.get(name) or RECEIVED_SHEETS_DIR / name
        return Path(name)

    def _move_fully_received_sheets_to_received(self, paths: list[Path]) -> list[str]:
        moved: list[str] = []
        for path in paths:
            if not path.exists():
                continue
            try:
                summary = summarize_workbook(path)
            except Exception:
                continue
            if not summary.get("all_received"):
                continue
            parent = path.parent.resolve()
            kind = "Incoming" if parent == INCOMING_SHEETS_DIR.resolve() else "Working" if parent == WORKING_SHEETS_DIR.resolve() else ""
            if not kind:
                continue
            old_key = self._home_sheet_key(kind, path.name)
            marker = dict(self.home_sheet_markers.get(old_key, {}))
            marker["all_received"] = True
            new_key = self._move_sheet_to_received(old_key)
            if new_key:
                self.home_sheet_markers.pop(old_key, None)
                self.home_sheet_markers[new_key] = marker
                moved.append(path.name)
        return moved

    def _load_sheet_markers(self) -> dict[str, dict[str, object]]:
        try:
            if not SHEET_MARKERS_PATH.exists():
                return {}
            raw = json.loads(SHEET_MARKERS_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}
        except Exception:
            return {}
        return {}

    def _save_sheet_markers(self) -> None:
        SHEET_MARKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SHEET_MARKERS_PATH.write_text(json.dumps(self.home_sheet_markers, indent=2, sort_keys=True), encoding="utf-8")

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
        if self.review_mode.get() == "Manual Receive":
            self._build_manual_review_mode()
        else:
            self._build_automatic_review_mode()
        self._refresh_table()

    def _build_manual_review_mode(self) -> None:
        self.review_mode_host.columnconfigure(8, weight=1)
        ttk.Label(self.review_mode_host, text="Double-click cells in the Receive table to enter certs or adjust matched details.", style="Muted.TLabel").grid(row=0, column=0, columnspan=9, sticky="w")

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
        self.review_station_button = ttk.Button(self.review_mode_host, text="Enter Receive Scanning Mode", command=self.toggle_review_scanning, style="Primary.TButton")
        self.review_station_button.grid(row=0, column=start_col, sticky="w", padx=(0, 14))
        ttk.Label(self.review_mode_host, text="Scan", style="Panel.TLabel").grid(row=0, column=start_col + 1, sticky="w")
        self.review_scan_entry = ttk.Entry(self.review_mode_host, textvariable=self.review_scan_cert, width=28)
        self.review_scan_entry.grid(row=0, column=start_col + 2, sticky="w", padx=(8, 14))
        self.review_scan_entry.bind("<Return>", lambda _event: self.add_review_scanned_row())
        self.review_scan_entry.bind("<KP_Enter>", lambda _event: self.add_review_scanned_row())
        self._set_review_station_controls()
        if self.review_scanning_active:
            self.after(100, self._arm_review_scanner)

    def _build_review_photo_controls(self, start_col: int) -> None:
        self.review_scanning_active = False
        self.review_scan_entry = None
        ttk.Button(self.review_mode_host, text="Add Receive Photos", command=self.add_review_photos, style="Soft.TButton").grid(row=0, column=start_col, sticky="w", padx=(0, 8))
        ttk.Button(self.review_mode_host, text="Scan Receive Photos", command=self.scan_review_photos, style="Primary.TButton").grid(row=0, column=start_col + 1, sticky="w", padx=(0, 8))
        ttk.Button(self.review_mode_host, text="Clear Receive Photos", command=self.clear_review_photos, style="Soft.TButton").grid(row=0, column=start_col + 2, sticky="w")
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
        card = self.scan_card.get().strip()
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
            messagebox.showerror("Missing GOOGLE_API_KEY", "Create .env in the L.U.C.A.S project folder or set GOOGLE_API_KEY.")
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
            "notes": clean_part(card.get("position") or ""),
        }

    def _photo_card_has_inventory(self, card: dict) -> bool:
        return any(card.get(key) for key in ("cert_number", "player", "year", "set", "card_number", "parallel", "subset", "grade", "label_text"))

    def _load_photo_env(self) -> None:
        if not load_dotenv:
            return
        load_dotenv(ROOT / ".env", override=False)
        load_dotenv(PHOTO_APP_DIR / ".env", override=False)
        load_dotenv(PHOTO_APP_ROOT / ".env", override=False)

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
                    "card_ladder_value": row.get("card_ladder_value"),
                    "card_ladder_comps_average": row.get("card_ladder_comps_average"),
                    "card_ladder_comps": row.get("card_ladder_comps") or "",
                    "best_company": row.get("best_company") or "",
                    "estimated_payout": row.get("estimated_payout"),
                }
        self.incoming_cert_index = index
        self._match_all_review_rows()
        self._refresh_table()
        self.review_status.set(f"Indexed {len(index)} cert(s) from {len(paths)} incoming sheet(s).")

    def refresh_received_sheets(self) -> None:
        try:
            RECEIVED_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
            paths = sorted(RECEIVED_SHEETS_DIR.glob("*.xlsx"), key=lambda path: path.stat().st_mtime, reverse=True)
        except Exception as error:
            self.received_sheet_paths = {}
            if hasattr(self, "received_sheet_combo"):
                self.received_sheet_combo["values"] = []
            self.review_status.set(f"Received sheets unavailable: {error}")
            return
        self.received_sheet_paths = {path.name: path for path in paths}
        if hasattr(self, "received_sheet_combo"):
            names = list(self.received_sheet_paths)
            self.received_sheet_combo["values"] = names
            if names and self.selected_received_sheet.get() not in self.received_sheet_paths:
                self.selected_received_sheet.set(names[0])
            elif not names:
                self.selected_received_sheet.set("")

    def load_selected_received_sheet_for_review(self) -> None:
        name = self.selected_received_sheet.get()
        path = self.received_sheet_paths.get(name)
        if not path:
            messagebox.showinfo("Choose sheet", "Choose a received sheet to load into Assignment.")
            return
        self.review_status.set(f"Loading received sheet: {name}...")
        self.status_var.set(f"Loading received sheet: {name}...")
        threading.Thread(target=self._load_received_sheet_worker, args=(name, path), daemon=True).start()

    def _load_received_sheet_worker(self, name: str, path: Path) -> None:
        try:
            rows = read_simple_spreadsheet(path)
        except Exception as error:
            self.events.put(("load_received_sheet_error", {"name": name, "error": str(error)}))
            return
        self.events.put(("load_received_sheet_done", {"name": name, "rows": rows}))

    def _apply_loaded_received_sheet(self, name: str, rows: list[dict[str, object]]) -> None:
        review_rows = []
        for row in rows:
            review_rows.append(
                {
                    "cert_number": row.get("cert_number"),
                    "grader": row.get("grader"),
                    "card_title": row.get("card_title"),
                    "purchase_price": row.get("purchase_price"),
                    "card_ladder_value": row.get("card_ladder_value"),
                    "card_ladder_comps_average": row.get("card_ladder_comps_average"),
                    "card_ladder_comps": row.get("card_ladder_comps") or "",
                    "best_company": row.get("best_company") or "",
                    "estimated_payout": row.get("estimated_payout"),
                    "source": f"Received Sheet: {name}",
                    "sheet_source": name,
                    "status": "Received",
                    "notes": "Loaded from received sheet",
                }
            )
        added = self._append_review_rows(review_rows, schedule_recommendations=True)
        self.review_status.set(f"Loaded {len(added)} row(s) from {name}.")
        self.status_var.set(f"Loaded received sheet: {name}")

    def add_manual_review_row(self) -> int | None:
        added_rows = self._append_review_rows([
            {
                "cert_number": "",
                "grader": "",
                "card_title": "",
                "purchase_price": None,
                "source": "Manual",
                "notes": "Manual assignment",
            }
        ])
        if added_rows:
            row_id = str(added_rows[-1])
            target_tree = self.receive_tree if hasattr(self, "receive_tree") else self.review_tree
            target_tree.selection_set(row_id)
            target_tree.focus(row_id)
            target_tree.see(row_id)
            self.review_status.set("Manual row added. Double-click cells to edit it.")
            return added_rows[-1]
        return None

    def toggle_review_scanning(self) -> None:
        self.review_scanning_active = not self.review_scanning_active
        self._set_review_station_controls()
        if self.review_scanning_active:
            self.review_status.set("Receive scanning mode armed. Scan received certs now.")
            self._arm_review_scanner()
        else:
            self.review_status.set("Receive station is off.")

    def _set_review_station_controls(self) -> None:
        if not hasattr(self, "review_station_button"):
            return
        self.review_station_button.configure(text="Exit Receive Scanning Mode" if self.review_scanning_active else "Enter Receive Scanning Mode")
        if self.review_scan_entry is not None:
            self.review_scan_entry.configure(state=tk.NORMAL if self.review_scanning_active else tk.DISABLED)

    def add_review_scanned_row(self) -> None:
        if not self.review_scanning_active:
            self.review_status.set("Click Enter Receive Scanning Mode before scanning.")
            return
        cert = scan_to_cert(self.review_scan_cert.get())
        if not cert:
            self.review_status.set("No cert detected. Scan again.")
            self._arm_review_scanner()
            return
        self._append_review_rows([
            {
                "cert_number": cert,
                "grader": "",
                "card_title": "",
                "purchase_price": None,
                "source": "Receive Barcode",
                "notes": "Received",
            }
        ])
        self.review_scan_cert.set("")
        self.review_status.set(f"Received {cert}. Ready for next scan.")
        self._arm_review_scanner()

    def add_review_photos(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Choose receive photos",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All files", "*.*")],
        )
        self._add_review_photo_paths([Path(path) for path in paths])

    def clear_review_photos(self) -> None:
        if self.review_photo_worker and self.review_photo_worker.is_alive():
            messagebox.showinfo("Scan running", "Wait for the receive photo scan to finish before clearing photos.")
            return
        self.review_photo_paths = []
        self.review_photo_status.set("No receive photos selected.")

    def _add_review_photo_paths(self, paths: list[Path]) -> None:
        existing = {path.resolve() for path in self.review_photo_paths if path.exists()}
        added = 0
        for path in paths:
            if not path.exists() or path.resolve() in existing:
                continue
            self.review_photo_paths.append(path)
            existing.add(path.resolve())
            added += 1
        self.review_photo_status.set(f"{len(self.review_photo_paths)} receive photo(s) selected. Added {added}.")

    def scan_review_photos(self) -> None:
        if self.review_photo_worker and self.review_photo_worker.is_alive():
            messagebox.showinfo("Scan running", "Receive photo scan is already running.")
            return
        if not self.review_photo_paths:
            messagebox.showinfo("No photos", "Add receive photos before scanning.")
            return
        if genai is None or identify_cards_sync is None:
            messagebox.showerror("Missing dependency", "Photo OCR dependencies are not available.")
            return
        self._load_photo_env()
        api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
        if not api_key:
            messagebox.showerror("Missing GOOGLE_API_KEY", "Create .env in the L.U.C.A.S project folder or set GOOGLE_API_KEY.")
            return
        self.photo_client = genai.Client(api_key=api_key)
        self.review_photo_status.set(f"Scanning 0/{len(self.review_photo_paths)} receive photo(s)...")
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
                self.events.put(("review_status", f"Scanning {index}/{total}: {path.name} -> {len(rows)} receive row(s)."))
            except Exception as error:
                self.events.put(("review_status", f"{path.name}: {error}"))
        self.events.put(("review_status", f"Receive photo scan complete. Added {detected_total} row(s)."))

    def _photo_card_to_review_row(self, path: Path, card: dict) -> dict[str, object]:
        row = self._photo_card_to_row(path, card)
        row["source"] = f"Receive Photo: {path.name}"
        row["notes"] = "Received"
        return row

    def _append_review_rows(self, rows: list[dict[str, object]], schedule_recommendations: bool = False) -> list[int]:
        existing = list(self.review_rows)
        start = len(existing) + 2
        added_excel_rows: list[int] = []
        for offset, row in enumerate(rows):
            cert = scan_to_cert(row.get("cert_number"))
            match = self._incoming_match(cert)
            grader = str(row.get("grader") or match.get("grader") or infer_grader(str(row.get("card_title") or ""))).upper()
            card = str(row.get("card_title") or match.get("card_title") or "").strip()
            purchase_price = row.get("purchase_price") if row.get("purchase_price") is not None else match.get("purchase_price")
            card_ladder_value = row.get("card_ladder_value") if row.get("card_ladder_value") is not None else match.get("card_ladder_value")
            comps_average = row.get("card_ladder_comps_average") if row.get("card_ladder_comps_average") is not None else match.get("card_ladder_comps_average")
            comp_details = str(row.get("card_ladder_comps") or match.get("card_ladder_comps") or "")
            best_company = str(row.get("best_company") or match.get("best_company") or "").strip()
            estimated_payout = row.get("estimated_payout") if row.get("estimated_payout") is not None else match.get("estimated_payout")
            sheet_source = str(row.get("sheet_source") or match.get("sheet") or ("NO SHEET FOUND" if cert else ""))
            status = str(row.get("status") or ("Needs setup" if not cert else ("Received" if match else "Received - no incoming match")))
            excel_row = start + offset
            existing.append(
                WorkbookRow(
                    excel_row=excel_row,
                    cert_number=cert,
                    card_title=card,
                    grader=grader,
                    existing_value=purchase_price,
                    card_ladder_value=card_ladder_value,
                    card_ladder_comps_average=comps_average,
                    card_ladder_comps=comp_details,
                    best_company=best_company,
                    estimated_payout=estimated_payout,
                    status=status,
                    notes=str(row.get("notes") or ""),
                )
            )
            self.review_sources[excel_row] = str(row.get("source") or "")
            self.review_sheet_sources[excel_row] = sheet_source
            added_excel_rows.append(excel_row)
        self.review_rows = existing
        self._refresh_table(schedule_recommendations=schedule_recommendations)
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
                if row.card_ladder_value is None and match.get("card_ladder_value") is not None:
                    row.card_ladder_value = match.get("card_ladder_value")
                if row.card_ladder_comps_average is None and match.get("card_ladder_comps_average") is not None:
                    row.card_ladder_comps_average = match.get("card_ladder_comps_average")
                if not row.card_ladder_comps and match.get("card_ladder_comps"):
                    row.card_ladder_comps = str(match.get("card_ladder_comps") or "")
                if not row.best_company and match.get("best_company"):
                    row.best_company = str(match.get("best_company") or "")
                if row.estimated_payout is None and match.get("estimated_payout") is not None:
                    row.estimated_payout = match.get("estimated_payout")
                row.status = "Received"
            elif row.status == "Received":
                row.status = "Received - no incoming match"

    def clear_review_rows(self) -> None:
        self.review_rows = []
        self.review_sources = {}
        self.review_sheet_sources = {}
        self._refresh_table()
        self.review_status.set("Receive/assignment rows cleared.")

    def delete_selected_review_rows(self) -> None:
        tree = self.review_tree
        if hasattr(self, "receive_tree") and self.receive_tree.selection():
            tree = self.receive_tree
        elif self.review_tree.selection():
            tree = self.review_tree
        deleted = self._delete_selected_rows(
            tree,
            self.review_rows,
            self.review_sources,
            self.review_sheet_sources,
        )
        if deleted:
            self.review_status.set(f"Deleted {deleted} receive/assignment row(s).")
            self.status_var.set(f"Deleted {deleted} receive/assignment row(s).")
        else:
            self.review_status.set("Select receive or assignment rows to delete.")

    def mark_review_received_in_sheets(self) -> None:
        certs = {scan_to_cert(row.cert_number) for row in self.review_rows if scan_to_cert(row.cert_number)}
        if not certs:
            messagebox.showinfo("No received certs", "Scan or load received cards in Receive before marking sheets.")
            return
        paths: list[Path] = []
        errors: list[str] = []
        for directory in (INCOMING_SHEETS_DIR, WORKING_SHEETS_DIR):
            try:
                directory.mkdir(parents=True, exist_ok=True)
                paths.extend(sorted(directory.glob("*.xlsx"), key=lambda path: path.name.lower()))
            except Exception as error:
                errors.append(f"{directory}: {error}")
        if not paths:
            messagebox.showinfo("No sheets found", "No incoming or working sheets were found to update.")
            return
        result = mark_received_in_workbooks(paths, certs)
        errors.extend(result.get("errors") or [])
        rows_marked = int(result.get("rows_marked") or 0)
        files_updated = int(result.get("files_updated") or 0)
        certs_marked = len(result.get("certs_marked") or set())
        company_rows_added = 0
        company_rows_missing_company = 0
        if rows_marked:
            company_rows = [
                row
                for row in self.review_rows
                if row.company_pile and scan_to_cert(row.cert_number) in result.get("certs_marked", set())
            ]
            self._apply_recommendations_to_rows(company_rows)
            eligible_company_rows = [row for row in company_rows if str(row.best_company or "").strip()]
            company_rows_missing_company = len(company_rows) - len(eligible_company_rows)
            if eligible_company_rows:
                company_result = append_company_sheet_rows(
                    COMPANY_SHEETS_DIR,
                    eligible_company_rows,
                    self.review_sources,
                    self.review_sheet_sources,
                )
                company_rows_added = int(company_result.get("rows_added") or 0)
                errors.extend(company_result.get("errors") or [])
        moved_received: list[str] = []
        try:
            moved_received = self._move_fully_received_sheets_to_received(paths)
            if moved_received:
                self._save_sheet_markers()
        except Exception as error:
            errors.append(f"Move to received failed: {error}")
        self.refresh_incoming_index()
        self.refresh_working_sheets()
        self.refresh_received_sheets()
        if rows_marked:
            self.review_status.set(f"Marked {rows_marked} row(s) received across {files_updated} sheet file(s).")
            self.status_var.set(f"Marked {certs_marked}/{len(certs)} received cert(s) in sheets.")
        else:
            self.review_status.set("No matching cert rows were found in incoming or working sheets.")
            self.status_var.set("No sheet rows marked received.")
        if moved_received:
            self.status_var.set(f"Moved {len(moved_received)} fully received sheet(s) to RECEIVED SHEETS.")
        if company_rows_added:
            self.status_var.set(f"Added {company_rows_added} card(s) to weekly company sheet(s).")
        elif company_rows_missing_company:
            self.status_var.set(f"{company_rows_missing_company} checked company pile card(s) had no Best Company.")
        self.refresh_home()
        if errors:
            messagebox.showwarning("Some sheets were skipped", "\n".join(errors[:8]))

    def _apply_recommendations_to_rows(self, rows: list[WorkbookRow]) -> None:
        for row in rows:
            if row.best_company and row.estimated_payout is not None:
                continue
            recommendation = self.assignment_engine.recommend(row)
            if recommendation.payout is None:
                continue
            row.best_company = recommendation.company
            row.estimated_payout = recommendation.payout

    def _ensure_company_sheet_folders(self) -> None:
        try:
            COMPANY_SHEETS_DIR.mkdir(parents=True, exist_ok=True)
            for company in self.assignment_engine.companies:
                folder_name = self._safe_company_folder_name(company.name)
                if folder_name:
                    (COMPANY_SHEETS_DIR / folder_name).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

    def _safe_company_folder_name(self, name: str) -> str:
        return re.sub(r"[<>:\"/\\|?*]+", " ", str(name or "")).strip()[:140].strip()

    def _arm_review_scanner(self) -> None:
        if self.review_mode.get() != "Automatic Receive" or self.review_scan_entry is None:
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
        requery_all = self.comp_scope_label.get() == COMP_SCOPE_ALL
        eligible = [
            row
            for row in self.state.rows
            if row.cert_number and row.grader and (requery_all or not row_has_comp_data(row))
        ]
        if not eligible:
            if requery_all:
                message = "No rows have both a cert number and company ready for Card Ladder."
            else:
                message = "No rows are missing comp data. Switch Run Scope to Recomp All if you want to refresh every row."
            messagebox.showinfo("No eligible rows", message)
            self.status_var.set(message)
            return
        self.state.set_comp_strategy(COMP_STRATEGY_DISPLAY.get(self.comp_strategy_label.get(), COMP_STRATEGY_AVERAGE))
        command_id = self.state.start_all_comps(requery_all=requery_all)
        self.comp_output_saved = False
        self._refresh_table()
        self.after(12000, lambda queued_command_id=command_id: self._warn_if_extension_not_checked_in(queued_command_id))
        self.status_var.set(f"Queued {len(eligible)} Card Ladder row(s) using {self.comp_scope_label.get()} with {self.comp_strategy_label.get()} as command #{command_id}.")

    def _warn_if_extension_not_checked_in(self, command_id: int) -> None:
        with self.state.lock:
            command_pending = bool(self.state.command and self.state.command.get("id") == command_id)
        if not command_pending:
            return
        messagebox.showwarning(
            "Card Ladder extension not connected",
            "The rows were queued, but the Card Ladder Chrome extension has not checked in. Make sure the extension is loaded and Chrome is open.",
        )

    def stop_comp_run(self) -> None:
        self.state.request_cancel()
        self.comp_output_saved = False
        self._refresh_table()
        self.status_var.set("Stop requested. Card Ladder will stop after the current row.")

    def clear_comp_rows(self) -> None:
        if self.state.rows and not self.comp_output_saved:
            confirmed = messagebox.askyesno(
                "Clear unsaved comp rows?",
                "These comp rows have not been saved as an output. Clear them anyway?",
                icon=messagebox.WARNING,
            )
            if not confirmed:
                self.status_var.set("Clear comp rows cancelled.")
                return
        self.state.set_rows([])
        self.row_sources = {}
        self.comp_sheet_sources = {}
        self.selected_working_sheet.set("")
        self.comp_output_saved = True
        self._cancel_cell_edit()
        try:
            self.working_sheet_list.selection_clear(0, tk.END)
        except tk.TclError:
            pass
        self._refresh_table()
        self.status_var.set("Comp rows cleared.")

    def recalculate_comp_method(self, _event=None) -> None:
        strategy = COMP_STRATEGY_DISPLAY.get(self.comp_strategy_label.get(), COMP_STRATEGY_AVERAGE)
        self.state.set_comp_strategy(strategy)
        updated = 0
        with self.state.lock:
            for row in self.state.rows:
                comps = parse_formatted_comps(row.card_ladder_comps)
                if not comps:
                    continue
                row.card_ladder_comps_average = comp_price(comps, strategy)
                row.card_ladder_comps = format_comps(comps, strategy)
                updated += 1
        if updated:
            self.comp_output_saved = False
        self._refresh_table(schedule_recommendations=bool(updated))
        if updated:
            self.status_var.set(f"Recalculated {updated} comp row(s) with {self.comp_strategy_label.get()}.")
        elif self.state.rows:
            self.status_var.set("Comp method updated. No stored comp details were available to recalculate.")
        else:
            self.status_var.set("Comp method updated.")

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
        self.comp_output_saved = True
        self.status_var.set(f"Saved {path}")

    def save_working_sheet(self) -> None:
        if not self.intake_rows:
            messagebox.showinfo("No create rows", "Scan or load cards in Create before saving a working sheet.")
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
        self.refresh_home()

    def refresh_pipeline(self) -> None:
        self.refresh_working_sheets()
        self.refresh_home()
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
        self.status_var.set(f"Loading working sheet: {name}...")
        threading.Thread(target=self._load_working_sheet_worker, args=(name, path), daemon=True).start()

    def _load_working_sheet_worker(self, name: str, path: Path) -> None:
        try:
            rows = read_simple_spreadsheet(path)
        except Exception as error:
            self.events.put(("load_working_sheet_error", {"name": name, "error": str(error)}))
            return
        self.events.put(("load_working_sheet_done", {"name": name, "rows": rows}))

    def _apply_loaded_working_sheet(self, name: str, rows: list[dict[str, object]]) -> None:
        workbook_rows: list[WorkbookRow] = []
        sources: dict[int, str] = {}
        for offset, row in enumerate(rows, start=2):
            cert = str(row.get("cert_number") or "")
            grader = str(row.get("grader") or infer_grader(str(row.get("card_title") or "")) or "PSA").upper()
            card = str(row.get("card_title") or "").strip()
            workbook_rows.append(
                WorkbookRow(
                    excel_row=offset,
                    cert_number=cert,
                    card_title=card,
                    grader=grader,
                    existing_value=row.get("purchase_price"),
                    card_ladder_value=row.get("card_ladder_value"),
                    card_ladder_comps_average=row.get("card_ladder_comps_average"),
                    card_ladder_comps=str(row.get("card_ladder_comps") or ""),
                    best_company=str(row.get("best_company") or ""),
                    estimated_payout=row.get("estimated_payout"),
                    status=str(row.get("status") or ("Ready" if cert and grader else "Needs setup")),
                    notes=str(row.get("notes") or ""),
                )
            )
            sources[offset] = str(row.get("source") or name)
        self.state.set_rows(workbook_rows)
        self.row_sources = sources
        self.comp_sheet_sources = {}
        self.comp_output_saved = True
        self._refresh_table(schedule_recommendations=any(row.card_ladder_comps_average is not None for row in workbook_rows))
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
        self.status_var.set("Create rows cleared.")

    def delete_selected_intake_rows(self) -> None:
        deleted = self._delete_selected_rows(
            self.intake_tree,
            self.intake_rows,
            self.intake_sources,
            self.intake_sheet_sources,
        )
        if deleted:
            self.status_var.set(f"Deleted {deleted} create row(s).")
        else:
            self.status_var.set("Select create rows to delete.")

    def _append_rows(self, rows: list[dict[str, object]]) -> list[int]:
        existing = list(self.intake_rows)
        start = len(existing) + 2
        added_excel_rows: list[int] = []
        for offset, row in enumerate(rows):
            cert = str(row.get("cert_number") or "")
            grader = str(row.get("grader") or infer_grader(str(row.get("card_title") or ""))).upper()
            card = str(row.get("card_title") or "").strip()
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
        for row in [*self.state.rows, *self.review_rows]:
            recommendation = self.assignment_engine.recommend(row)
            if recommendation.payout is None:
                row.best_company = ""
                row.estimated_payout = None
                continue
            row.best_company = recommendation.company
            row.estimated_payout = recommendation.payout

    def _queue_assignment_recommendations(self) -> None:
        rows = [*self.state.rows, *self.review_rows]
        if not rows or not self.assignment_engine.companies:
            self.assignment_progress_value.set(0)
            return
        self.assignment_recommendation_after_id = None
        self.assignment_recommendation_job += 1
        job_id = self.assignment_recommendation_job
        self.assignment_recommendation_running = True
        self.assignment_progress_value.set(0)
        total = len(rows)
        self.review_status.set(f"Calculating assignment recommendations: 0/{total}...")
        self.status_var.set("Calculating assignment recommendations...")
        threading.Thread(target=self._assignment_recommendations_worker, args=(job_id, rows), daemon=True).start()

    def _schedule_assignment_recommendations(self, delay_ms: int = 700) -> None:
        if not self.assignment_engine.companies:
            self.assignment_progress_value.set(0)
            return
        if self.assignment_recommendation_after_id is not None:
            try:
                self.after_cancel(self.assignment_recommendation_after_id)
            except tk.TclError:
                pass
        self.assignment_recommendation_after_id = self.after(delay_ms, self._queue_assignment_recommendations)

    def _assignment_recommendations_worker(self, job_id: int, rows: list[WorkbookRow]) -> None:
        total = len(rows)
        results: list[tuple[int, str, float | None]] = []
        progress_step = max(1, total // 25)
        for index, row in enumerate(rows, start=1):
            recommendation = self.assignment_engine.recommend(row)
            results.append((id(row), recommendation.company, recommendation.payout))
            if index == total or index % progress_step == 0:
                self.events.put(("assignment_recommendations_progress", {"job_id": job_id, "done": index, "total": total}))
        self.events.put(("assignment_recommendations_done", {"job_id": job_id, "total": total, "results": results}))

    def _apply_assignment_recommendation_results(self, payload: dict[str, object]) -> None:
        if int(payload.get("job_id") or 0) != self.assignment_recommendation_job:
            return
        results = {
            int(row_id): (str(company or ""), payout)
            for row_id, company, payout in list(payload.get("results") or [])
        }
        filled = 0
        comp_rows_updated = False
        state_row_ids = {id(row) for row in self.state.rows}
        for row in [*self.state.rows, *self.review_rows]:
            company, payout = results.get(id(row), ("", None))
            row.best_company = company if payout is not None else ""
            row.estimated_payout = payout if payout is not None else None
            if payout is not None:
                filled += 1
                if id(row) in state_row_ids:
                    comp_rows_updated = True
        if comp_rows_updated:
            self.comp_output_saved = False
        total = int(payload.get("total") or 0)
        self.assignment_recommendation_running = False
        self.assignment_progress_value.set(100 if total else 0)
        self.review_status.set(f"Assignment recommendations complete: {filled}/{total} row(s) populated.")
        self.status_var.set(f"Assignment recommendations complete: {filled}/{total} row(s) populated.")
        self._refresh_table(schedule_recommendations=False)

    def _update_assignment_recommendation_progress(self, payload: dict[str, object]) -> None:
        if int(payload.get("job_id") or 0) != self.assignment_recommendation_job:
            return
        done = int(payload.get("done") or 0)
        total = int(payload.get("total") or 0)
        percent = (done / total * 100) if total else 0
        self.assignment_progress_value.set(percent)
        self.review_status.set(f"Calculating assignment recommendations: {done}/{total}...")

    def reload_assignment_rules(self) -> None:
        self.assignment_engine = AssignmentEngine.load()
        self._ensure_company_sheet_folders()
        self.assignment_config_status.set(self._assignment_config_status())
        self._refresh_table(schedule_recommendations=True)
        self.review_status.set("Assignment rules reloaded.")
        self.status_var.set("Assignment rules reloaded.")

    def open_assignment_rules(self) -> None:
        open_assignment_rules_dialog(self, CARD_PIPELINE_DIR, self.reload_assignment_rules)

    def _assignment_config_status(self) -> str:
        if self.assignment_engine.error:
            return f"Assignment config error: {self.assignment_engine.error}"
        count = len(self.assignment_engine.companies)
        if not count:
            return "Assignment companies: none configured. Add assignment_companies.json to enable best-company payouts."
        return f"Assignment companies loaded: {count}"

    def _refresh_table(self, schedule_recommendations: bool = False) -> None:
        self._render_rows(self.intake_tree, self.intake_rows, self.intake_sources)
        self._render_rows(self.comp_tree, self.state.rows, self.row_sources, self.comp_sheet_sources)
        self._render_rows(self.receive_tree, self.review_rows, self.review_sources, self.review_sheet_sources)
        self._render_rows(self.review_tree, self.review_rows, self.review_sources, self.review_sheet_sources)
        completed = sum(1 for row in self.state.rows if row.card_ladder_value is not None)
        self.summary_var.set(f"{len(self.intake_rows)} create rows | Loaded comp rows: {len(self.state.rows)} | Card Ladder values: {completed}")
        if schedule_recommendations:
            self._schedule_assignment_recommendations()

    def _render_rows(self, tree: ttk.Treeview, rows: list[WorkbookRow], sources: dict[int, str], sheet_sources: dict[int, str] | None = None) -> None:
        self._remember_column_widths(tree)
        tree.delete(*tree.get_children())
        duplicate_certs = self._duplicate_certs(rows)
        columns = self._tree_columns(tree)
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
                values=tuple(self._row_display_value(row, col, sources, sheet_sources) for col in columns),
            )
        if self._is_receive_tree(tree) and self.review_mode.get() == "Manual Receive":
            add_values = []
            for col in columns:
                if col == "excel_row":
                    add_values.append("+")
                elif col == "card_title":
                    add_values.append("Add row")
                else:
                    add_values.append("")
            tree.insert(
                "",
                tk.END,
                iid=ADD_REVIEW_ROW_IID,
                tags=("add_review_row",),
                values=tuple(add_values),
            )
        self._restore_column_widths(tree)

    def _tree_columns(self, tree: ttk.Treeview) -> tuple[str, ...]:
        return tuple(getattr(tree, "_display_columns", DISPLAY_COLUMNS))

    def _is_receive_tree(self, tree: ttk.Treeview) -> bool:
        return hasattr(self, "receive_tree") and tree is self.receive_tree

    def _is_review_row_tree(self, tree: ttk.Treeview) -> bool:
        return self._is_receive_tree(tree) or (hasattr(self, "review_tree") and tree is self.review_tree)

    def _row_display_value(
        self,
        row: WorkbookRow,
        column: str,
        sources: dict[int, str],
        sheet_sources: dict[int, str] | None,
    ) -> object:
        if column == "excel_row":
            return row.excel_row
        if column == "source":
            return sources.get(row.excel_row, "")
        if column == "sheet_source":
            return (sheet_sources or {}).get(row.excel_row, "")
        if column == "cert_number":
            return row.cert_number
        if column == "grader":
            return row.grader
        if column == "card_title":
            return row.card_title
        if column == "purchase_price":
            return format_money(row.existing_value if isinstance(row.existing_value, (int, float)) else None)
        if column == "card_ladder_value":
            return format_money(row.card_ladder_value)
        if column == "card_ladder_comps_average":
            return format_money(row.card_ladder_comps_average)
        if column == "best_company":
            return row.best_company
        if column == "estimated_payout":
            return format_money(row.estimated_payout)
        if column == "status":
            return row.status
        if column == "company_pile":
            return "[x]" if row.company_pile else "[ ]"
        return ""

    def _delete_selected_table_rows(self, event) -> str | None:
        tree = event.widget
        if tree is self.intake_tree:
            self.delete_selected_intake_rows()
            return "break"
        if self._is_review_row_tree(tree):
            self.delete_selected_review_rows()
            return "break"
        return None

    def _delete_selected_rows(
        self,
        tree: ttk.Treeview,
        rows: list[WorkbookRow],
        sources: dict[int, str],
        sheet_sources: dict[int, str],
    ) -> int:
        selected_rows = {
            int(iid)
            for iid in tree.selection()
            if str(iid).isdigit() and str(iid) != ADD_REVIEW_ROW_IID
        }
        if not selected_rows:
            return 0
        remaining: list[WorkbookRow] = []
        new_sources: dict[int, str] = {}
        new_sheet_sources: dict[int, str] = {}
        for next_excel_row, row in enumerate((row for row in rows if row.excel_row not in selected_rows), start=2):
            old_excel_row = row.excel_row
            row.excel_row = next_excel_row
            remaining.append(row)
            if old_excel_row in sources:
                new_sources[next_excel_row] = sources[old_excel_row]
            if old_excel_row in sheet_sources:
                new_sheet_sources[next_excel_row] = sheet_sources[old_excel_row]
        if tree is self.intake_tree:
            self.intake_rows = remaining
            self.intake_sources = new_sources
            self.intake_sheet_sources = new_sheet_sources
        elif self._is_review_row_tree(tree):
            self.review_rows = remaining
            self.review_sources = new_sources
            self.review_sheet_sources = new_sheet_sources
        else:
            return 0
        self._cancel_cell_edit()
        self._refresh_table(schedule_recommendations=(tree is self.comp_tree or tree is self.review_tree))
        return len(selected_rows)

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
        for col in self._tree_columns(tree):
            try:
                widths[col] = int(tree.column(col, "width"))
            except tk.TclError:
                pass

    def _restore_column_widths(self, tree: ttk.Treeview) -> None:
        widths = self.column_widths_by_tree.get(id(tree), {})
        for col in self._tree_columns(tree):
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
        column_id = tree.identify_column(event.x)
        if self._is_receive_tree(tree) and row_id == ADD_REVIEW_ROW_IID:
            self.add_manual_review_row()
            return "break"
        if self._is_receive_tree(tree) and row_id and column_id:
            column_index = int(column_id.replace("#", "")) - 1
            columns = self._tree_columns(tree)
            if 0 <= column_index < len(columns) and columns[column_index] == "company_pile":
                self._toggle_company_pile(row_id)
                return "break"
        return None

    def _toggle_company_pile(self, row_id: str) -> None:
        if not str(row_id).isdigit():
            return
        excel_row = int(row_id)
        for row in self.review_rows:
            if row.excel_row != excel_row:
                continue
            row.company_pile = not row.company_pile
            self._refresh_table()
            self.review_status.set("Company pile checked." if row.company_pile else "Company pile unchecked.")
            return

    def _begin_cell_edit(self, event) -> None:
        tree = event.widget
        row_id = tree.identify_row(event.y)
        column_id = tree.identify_column(event.x)
        if self._is_receive_tree(tree) and row_id == ADD_REVIEW_ROW_IID:
            self.add_manual_review_row()
            return
        if not row_id or not column_id:
            return
        column_index = int(column_id.replace("#", "")) - 1
        columns = self._tree_columns(tree)
        if column_index < 0 or column_index >= len(columns):
            return
        column = columns[column_index]
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
        current = tree.set(row_id, column)
        self._destroy_cell_editor()
        if value.strip() == str(current or "").strip():
            return
        excel_row = int(row_id)
        self._apply_cell_value(tree, excel_row, column, value)
        if tree is self.comp_tree:
            self.comp_output_saved = False
        self._refresh_table(schedule_recommendations=self._edit_affects_assignment(tree, column))
        if tree.exists(row_id):
            tree.selection_set(row_id)
            tree.focus(row_id)
            tree.see(row_id)
        self.status_var.set(f"Updated row {excel_row}.")

    def _edit_affects_assignment(self, tree: ttk.Treeview, column: str) -> bool:
        if tree is not self.comp_tree and tree is not self.review_tree:
            return False
        return column in {
            "cert_number",
            "grader",
            "card_title",
            "card_ladder_value",
            "card_ladder_comps_average",
        }

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
        elif self._is_review_row_tree(tree):
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
            previous_cert = scan_to_cert(row.cert_number)
            if column == "cert_number":
                row.cert_number = scan_to_cert(clean_value)
            elif column == "grader":
                row.grader = normalize_grader(clean_value) or clean_value.upper()
            elif column == "card_title":
                row.card_title = clean_value
                inferred = infer_grader(row.card_title)
                if inferred:
                    row.grader = inferred
            elif column == "purchase_price":
                row.existing_value = self._parse_money_text(clean_value)
            elif column == "card_ladder_value":
                row.card_ladder_value = self._parse_money_text(clean_value)
            elif column == "card_ladder_comps_average":
                row.card_ladder_comps_average = self._parse_money_text(clean_value)
            row.status = "Ready" if row.cert_number and row.grader else "Needs setup"
            if self._is_review_row_tree(tree) and column == "cert_number" and scan_to_cert(row.cert_number) != previous_cert:
                match = self._incoming_match(row.cert_number)
                target_sheet_sources[excel_row] = str(match.get("sheet") or "NO SHEET FOUND")
                if match:
                    row.status = "Received"
                    if is_placeholder_title(row.card_title, row.grader) and match.get("card_title"):
                        row.card_title = str(match.get("card_title") or "")
                    if row.existing_value is None and match.get("purchase_price") is not None:
                        row.existing_value = match.get("purchase_price")
                    if row.card_ladder_value is None and match.get("card_ladder_value") is not None:
                        row.card_ladder_value = match.get("card_ladder_value")
                    if row.card_ladder_comps_average is None and match.get("card_ladder_comps_average") is not None:
                        row.card_ladder_comps_average = match.get("card_ladder_comps_average")
                    if not row.card_ladder_comps and match.get("card_ladder_comps"):
                        row.card_ladder_comps = str(match.get("card_ladder_comps") or "")
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
                elif event == "comp_refresh":
                    self.comp_output_saved = False
                    self._refresh_table(schedule_recommendations=True)
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
                    elif kind == "startup_refresh":
                        self._apply_startup_refresh(payload)
                    elif kind == "load_working_sheet_done":
                        self._apply_loaded_working_sheet(str(payload.get("name") or ""), list(payload.get("rows") or []))
                    elif kind == "load_working_sheet_error":
                        self.status_var.set(f"Working sheet load failed: {payload.get('error')}")
                        messagebox.showerror("Load failed", str(payload.get("error") or "Unknown error"))
                    elif kind == "load_received_sheet_done":
                        self._apply_loaded_received_sheet(str(payload.get("name") or ""), list(payload.get("rows") or []))
                    elif kind == "load_received_sheet_error":
                        self.review_status.set(f"Received sheet load failed: {payload.get('error')}")
                        self.status_var.set(f"Received sheet load failed: {payload.get('error')}")
                        messagebox.showerror("Load failed", str(payload.get("error") or "Unknown error"))
                    elif kind == "assignment_recommendations_progress":
                        self._update_assignment_recommendation_progress(payload)
                    elif kind == "assignment_recommendations_done":
                        self._apply_assignment_recommendation_results(payload)
        except queue.Empty:
            pass
        self.after(200, self._poll_events)

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
