from __future__ import annotations

import json
import re
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any, Callable

from assignment_engine import CONFIG_PATH, read_source_text


GRADE_COMPANIES = ("psa", "bgs", "sgc", "cgc")
SPORT_OPTIONS = ("basketball", "football", "baseball", "soccer", "hockey", "pokemon", "one piece")


class AssignmentRulesDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, pipeline_root: Path, on_saved: Callable[[], None]) -> None:
        super().__init__(parent)
        self.title("Assignment Rules")
        self.geometry("1120x720")
        self.minsize(980, 620)
        self.transient(parent)
        self.on_saved = on_saved
        self.pipeline_root = Path(pipeline_root)
        self.rules_dir = self.pipeline_root / "ASSIGNMENT RULES"
        self.config_path = CONFIG_PATH
        self.companies = self._load_config()
        self.selected_index: int | None = None
        self.rule_rows: list[dict[str, Any]] = []
        self.payout_rows: list[dict[str, tk.StringVar]] = []

        self.company_name = tk.StringVar()
        self.status = tk.StringVar(value="Create or edit a company, then save.")

        self._build_ui()
        self._refresh_company_list()
        if self.companies:
            self.company_list.selection_set(0)
            self._select_company(0)
        else:
            self._new_company()

    def _build_ui(self) -> None:
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        side = ttk.Frame(shell, padding=(0, 0, 12, 0))
        side.grid(row=0, column=0, sticky="ns")
        ttk.Label(side, text="Companies").pack(anchor=tk.W)
        self.company_list = tk.Listbox(side, width=26, height=24, exportselection=False)
        self.company_list.pack(fill=tk.Y, expand=True, pady=(6, 8))
        self.company_list.bind("<<ListboxSelect>>", self._on_company_select)
        ttk.Button(side, text="New Company", command=self._new_company).pack(fill=tk.X, pady=(0, 6))
        ttk.Button(side, text="Delete Company", command=self._delete_company).pack(fill=tk.X)

        main = ttk.Frame(shell)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(3, weight=1)

        top = ttk.Frame(main)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="Company Name").grid(row=0, column=0, sticky=tk.W, padx=(0, 8))
        ttk.Entry(top, textvariable=self.company_name).grid(row=0, column=1, sticky="ew")

        rule_header = ttk.Frame(main)
        rule_header.grid(row=1, column=0, sticky="ew", pady=(14, 6))
        ttk.Label(rule_header, text="Acceptance Rules").pack(side=tk.LEFT)
        ttk.Button(rule_header, text="Add Rule", command=self._add_rule_row).pack(side=tk.RIGHT)

        self.rules_canvas = tk.Canvas(main, height=260, highlightthickness=0)
        self.rules_canvas.grid(row=2, column=0, sticky="ew")
        rules_scroll = ttk.Scrollbar(main, orient=tk.VERTICAL, command=self.rules_canvas.yview)
        rules_scroll.grid(row=2, column=1, sticky="ns")
        self.rules_canvas.configure(yscrollcommand=rules_scroll.set)
        self.rules_frame = ttk.Frame(self.rules_canvas)
        self.rules_window = self.rules_canvas.create_window((0, 0), window=self.rules_frame, anchor="nw")
        self.rules_frame.bind("<Configure>", lambda _event: self.rules_canvas.configure(scrollregion=self.rules_canvas.bbox("all")))
        self.rules_canvas.bind("<Configure>", lambda event: self.rules_canvas.itemconfigure(self.rules_window, width=event.width))

        lower = ttk.Frame(main)
        lower.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        lower.columnconfigure(0, weight=1)
        lower.columnconfigure(1, weight=1)
        lower.rowconfigure(1, weight=1)

        payout_header = ttk.Frame(lower)
        payout_header.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        ttk.Label(payout_header, text="Payout Tiers").pack(side=tk.LEFT)
        ttk.Button(payout_header, text="Add Tier", command=self._add_payout_row).pack(side=tk.RIGHT)
        self.payout_frame = ttk.Frame(lower)
        self.payout_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))

        notes = ttk.Frame(lower)
        notes.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(8, 0))
        notes.columnconfigure(0, weight=1)
        notes.rowconfigure(1, weight=1)
        ttk.Label(notes, text="Block / Never-Buy Rules").grid(row=0, column=0, sticky=tk.W)
        self.blocks_text = tk.Text(notes, height=8, wrap=tk.WORD)
        self.blocks_text.grid(row=1, column=0, sticky="nsew", pady=(6, 0))

        footer = ttk.Frame(shell)
        footer.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status).grid(row=0, column=0, sticky=tk.W)
        ttk.Button(footer, text="Save Company", command=self._save_company).grid(row=0, column=1, padx=(8, 0))
        ttk.Button(footer, text="Save & Reload", command=self._save_and_reload).grid(row=0, column=2, padx=(8, 0))
        ttk.Button(footer, text="Close", command=self.destroy).grid(row=0, column=3, padx=(8, 0))

    def _load_config(self) -> list[dict[str, Any]]:
        if not self.config_path.exists():
            return []
        try:
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        companies = raw.get("companies", raw) if isinstance(raw, dict) else raw
        return [company for company in companies if isinstance(company, dict)]

    def _write_config(self) -> None:
        self.config_path.write_text(json.dumps({"companies": self.companies}, indent=2), encoding="utf-8")

    def _refresh_company_list(self) -> None:
        self.company_list.delete(0, tk.END)
        for company in self.companies:
            self.company_list.insert(tk.END, str(company.get("name") or "Untitled"))

    def _on_company_select(self, _event=None) -> None:
        selection = self.company_list.curselection()
        if selection:
            self._select_company(selection[0])

    def _select_company(self, index: int) -> None:
        self.selected_index = index
        company = self.companies[index]
        self.company_name.set(str(company.get("name") or ""))
        rules_payload = self._load_json_source(company.get("rules") or company.get("rules_source") or company.get("rulesSource"))
        payout_payload = self._load_json_source(company.get("payout") or company.get("payout_source") or company.get("payoutSource"))
        self._set_rule_rows(rules_payload.get("rules") if isinstance(rules_payload, dict) else [])
        self._set_blocks(rules_payload.get("blocks") if isinstance(rules_payload, dict) else [])
        self._set_payout_rows(payout_payload.get("tiers") if isinstance(payout_payload, dict) else [])
        self.status.set(f"Editing {company.get('name') or 'company'}.")

    def _load_json_source(self, source: Any) -> dict[str, Any]:
        try:
            text = read_source_text(source, self.config_path.parent)
            payload = json.loads(text) if text.strip() else {}
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    def _new_company(self) -> None:
        self.selected_index = None
        self.company_list.selection_clear(0, tk.END)
        self.company_name.set("")
        self._set_rule_rows([])
        self._set_blocks([])
        self._set_payout_rows([])
        self.status.set("New company ready.")

    def _delete_company(self) -> None:
        if self.selected_index is None:
            return
        name = self.companies[self.selected_index].get("name") or "this company"
        if not messagebox.askyesno("Delete company", f"Delete {name}?"):
            return
        del self.companies[self.selected_index]
        self.selected_index = None
        self._write_config()
        self._refresh_company_list()
        self._new_company()
        self.status.set(f"Deleted {name}.")

    def _set_rule_rows(self, rules: Any) -> None:
        for child in self.rules_frame.winfo_children():
            child.destroy()
        self.rule_rows = []
        if not isinstance(rules, list) or not rules:
            self._add_rule_row()
            return
        for rule in rules:
            self._add_rule_row(rule if isinstance(rule, dict) else None)

    def _add_rule_row(self, data: dict[str, Any] | None = None) -> None:
        index = len(self.rule_rows)
        frame = ttk.LabelFrame(self.rules_frame, text=f"Rule {index + 1}", padding=8)
        frame.pack(fill=tk.X, pady=(0, 8))
        frame.columnconfigure(0, weight=1)

        sports = set(data.get("sports") or split_values(data.get("sport")) if data else [])
        sport_vars = {sport: tk.BooleanVar(value=sport in sports) for sport in SPORT_OPTIONS}
        sport_frame = ttk.Frame(frame)
        sport_frame.grid(row=0, column=0, sticky="ew")
        for col, sport in enumerate(SPORT_OPTIONS):
            ttk.Checkbutton(sport_frame, text=title_case(sport), variable=sport_vars[sport]).grid(row=0, column=col, sticky=tk.W, padx=(0, 8))

        price_frame = ttk.Frame(frame)
        price_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        price_frame.columnconfigure(1, weight=1)
        price_frame.columnconfigure(3, weight=1)
        price_ranges = data.get("priceRanges") if data else None
        first_range = price_ranges[0] if isinstance(price_ranges, list) and price_ranges else {}
        min_var = tk.StringVar(value=str(first_range.get("min") or ""))
        max_var = tk.StringVar(value=str(first_range.get("max") or ""))
        ttk.Label(price_frame, text="Min CL/Comps").grid(row=0, column=0, sticky=tk.W, padx=(0, 6))
        ttk.Entry(price_frame, textvariable=min_var, width=12).grid(row=0, column=1, sticky=tk.W)
        ttk.Label(price_frame, text="Max").grid(row=0, column=2, sticky=tk.W, padx=(12, 6))
        ttk.Entry(price_frame, textvariable=max_var, width=12).grid(row=0, column=3, sticky=tk.W)
        ttk.Button(price_frame, text="Remove Rule", command=lambda: self._remove_rule_row(frame)).grid(row=0, column=4, sticky=tk.E)

        grades_frame = ttk.Frame(frame)
        grades_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        grade_payload = data.get("grades") if data else {}
        grade_vars: dict[str, dict[str, Any]] = {}
        for col, company in enumerate(GRADE_COMPANIES):
            payload = grade_payload.get(company) if isinstance(grade_payload, dict) else {}
            allowed = tk.BooleanVar(value=(payload or {}).get("allowed") is not False)
            min_grade = tk.StringVar(value=str((payload or {}).get("min") or ""))
            max_grade = tk.StringVar(value=str((payload or {}).get("max") or ""))
            cell = ttk.Frame(grades_frame)
            cell.grid(row=0, column=col, sticky=tk.W, padx=(0, 16))
            ttk.Checkbutton(cell, text=company.upper(), variable=allowed).grid(row=0, column=0, columnspan=2, sticky=tk.W)
            ttk.Entry(cell, textvariable=min_grade, width=5).grid(row=1, column=0, sticky=tk.W)
            ttk.Entry(cell, textvariable=max_grade, width=5).grid(row=1, column=1, sticky=tk.W, padx=(4, 0))
            grade_vars[company] = {"allowed": allowed, "min": min_grade, "max": max_grade}

        self.rule_rows.append({
            "frame": frame,
            "sports": sport_vars,
            "min": min_var,
            "max": max_var,
            "grades": grade_vars,
        })

    def _remove_rule_row(self, frame: ttk.Frame) -> None:
        self.rule_rows = [row for row in self.rule_rows if row["frame"] is not frame]
        frame.destroy()
        if not self.rule_rows:
            self._add_rule_row()

    def _set_blocks(self, blocks: Any) -> None:
        self.blocks_text.delete("1.0", tk.END)
        if isinstance(blocks, list):
            self.blocks_text.insert("1.0", "\n".join(str(block) for block in blocks))

    def _set_payout_rows(self, tiers: Any) -> None:
        for child in self.payout_frame.winfo_children():
            child.destroy()
        self.payout_rows = []
        if not isinstance(tiers, list) or not tiers:
            self._add_payout_row({"min": "", "max": "", "rate": ""})
            return
        for tier in tiers:
            self._add_payout_row(tier if isinstance(tier, dict) else None)

    def _add_payout_row(self, data: dict[str, Any] | None = None) -> None:
        row_index = len(self.payout_rows)
        min_var = tk.StringVar(value=str((data or {}).get("min") or ""))
        max_var = tk.StringVar(value=str((data or {}).get("max") or ""))
        rate_var = tk.StringVar(value=str((data or {}).get("rate") or ""))
        ttk.Label(self.payout_frame, text="Min").grid(row=row_index, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(self.payout_frame, textvariable=min_var, width=10).grid(row=row_index, column=1, sticky=tk.W, pady=3)
        ttk.Label(self.payout_frame, text="Max").grid(row=row_index, column=2, sticky=tk.W, padx=(10, 6), pady=3)
        ttk.Entry(self.payout_frame, textvariable=max_var, width=10).grid(row=row_index, column=3, sticky=tk.W, pady=3)
        ttk.Label(self.payout_frame, text="Rate").grid(row=row_index, column=4, sticky=tk.W, padx=(10, 6), pady=3)
        ttk.Entry(self.payout_frame, textvariable=rate_var, width=10).grid(row=row_index, column=5, sticky=tk.W, pady=3)
        self.payout_rows.append({"min": min_var, "max": max_var, "rate": rate_var})

    def _save_company(self) -> bool:
        name = self.company_name.get().strip()
        if not name:
            messagebox.showinfo("Company name", "Name the company before saving.")
            return False
        self.rules_dir.mkdir(parents=True, exist_ok=True)
        stem = safe_stem(name)
        rules_path = self.rules_dir / f"{stem}-rules.json"
        payout_path = self.rules_dir / f"{stem}-payout.json"
        rules_path.write_text(json.dumps(self._rules_payload(), indent=2), encoding="utf-8")
        payout_path.write_text(json.dumps(self._payout_payload(), indent=2), encoding="utf-8")

        company = {
            "name": name,
            "rules": str(rules_path),
            "payout": str(payout_path),
        }
        if self.selected_index is None:
            self.companies.append(company)
            self.selected_index = len(self.companies) - 1
        else:
            self.companies[self.selected_index] = company
        self._write_config()
        self._refresh_company_list()
        self.company_list.selection_clear(0, tk.END)
        self.company_list.selection_set(self.selected_index)
        self.status.set(f"Saved {name}.")
        return True

    def _save_and_reload(self) -> None:
        if self._save_company():
            self.on_saved()
            self.status.set("Saved and reloaded Assignment rules.")

    def _rules_payload(self) -> dict[str, Any]:
        return {
            "rules": [self._rule_payload(row) for row in self.rule_rows],
            "blocks": [
                line.strip()
                for line in self.blocks_text.get("1.0", tk.END).splitlines()
                if line.strip()
            ],
        }

    def _rule_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "sports": [sport for sport, var in row["sports"].items() if var.get()],
            "priceRanges": [{
                "min": row["min"].get().strip(),
                "max": row["max"].get().strip(),
            }],
            "grades": {
                company: {
                    "allowed": values["allowed"].get(),
                    "min": values["min"].get().strip(),
                    "max": values["max"].get().strip(),
                }
                for company, values in row["grades"].items()
            },
        }

    def _payout_payload(self) -> dict[str, Any]:
        return {
            "tiers": [
                {
                    "min": row["min"].get().strip(),
                    "max": row["max"].get().strip(),
                    "rate": row["rate"].get().strip(),
                }
                for row in self.payout_rows
                if row["rate"].get().strip()
            ]
        }


def open_assignment_rules_dialog(parent: tk.Tk, pipeline_root: Path, on_saved: Callable[[], None]) -> None:
    dialog = AssignmentRulesDialog(parent, pipeline_root, on_saved)
    dialog.focus_set()
    dialog.grab_set()


def safe_stem(value: str) -> str:
    stem = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return stem or "company"


def title_case(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split())


def split_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]
