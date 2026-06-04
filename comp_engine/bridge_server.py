from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import asdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from cardladder_ocr import extract_cl_value_from_data_url
from workbook_io import WorkbookRow

BRIDGE_VERSION = "2026-06-01-cardladder-result-log-v3"
DEBUG_DIR = Path(__file__).resolve().parent.parent / "work" / "cardladder-bridge"
COMP_STRATEGY_AVERAGE = "average_last_5"
COMP_STRATEGY_HIGH = "highest_last_5"
COMP_STRATEGY_LOW = "lowest_last_5"
COMP_STRATEGY_STALE_NEWEST = "stale_newest_else_average"
COMP_STRATEGY_LABELS = {
    COMP_STRATEGY_AVERAGE: "Average last 5",
    COMP_STRATEGY_HIGH: "Highest of last 5",
    COMP_STRATEGY_LOW: "Lowest of last 5",
    COMP_STRATEGY_STALE_NEWEST: "Date weighted",
}


class BridgeState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.rows: list[WorkbookRow] = []
        self.command: dict | None = None
        self.command_id = 0
        self.last_seen_extension = ""
        self.cardladder_running = False
        self.comp_strategy = COMP_STRATEGY_AVERAGE
        self.on_update: Callable[[], None] | None = None

    def set_rows(self, rows: list[WorkbookRow]) -> None:
        with self.lock:
            self.rows = rows

    def set_comp_strategy(self, strategy: str) -> None:
        with self.lock:
            self.comp_strategy = strategy if strategy in COMP_STRATEGY_LABELS else COMP_STRATEGY_AVERAGE

    def start_all_comps(self) -> int:
        with self.lock:
            self.command_id += 1
            queue = [
                {
                    "excelRow": row.excel_row,
                    "certNumber": row.cert_number,
                    "grader": row.grader,
                    "cardTitle": row.card_title,
                }
                for row in self.rows
                if row.cert_number and row.grader and row.card_ladder_value is None
            ]
            for row in self.rows:
                if row.cert_number and row.grader and row.card_ladder_value is None:
                    row.status = "Queued"
            if not queue:
                self.command = None
                self.cardladder_running = False
                return self.command_id
            self.command = {
                "id": self.command_id,
                "type": "RUN_ALL_COMPS",
                "sources": ["cardladder"],
                "queue": queue,
                "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            self.cardladder_running = True
            return self.command_id

    def extension_poll(self) -> dict:
        with self.lock:
            self.last_seen_extension = time.strftime("%H:%M:%S")
            return {"command": self.command}

    def acknowledge_command(self, command_id: int) -> None:
        with self.lock:
            if self.command and self.command.get("id") == command_id:
                self.command = None

    def post_cardladder_result(self, result: dict) -> None:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        (DEBUG_DIR / f"result-{time.strftime('%Y%m%d-%H%M%S')}.json").write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )
        with self.lock:
            cert = str(result.get("certNumber") or "")
            excel_row = int(result.get("excelRow") or 0)
            for row in self.rows:
                if row.excel_row == excel_row or row.cert_number == cert:
                    value = parse_value(result.get("value"))
                    row.card_ladder_value = value
                    ocr = result.get("ocr") if isinstance(result.get("ocr"), dict) else {}
                    comps = ocr.get("comps") if isinstance(ocr.get("comps"), list) else []
                    profile_title = clean_profile_title(ocr.get("profileTitle") or ocr.get("profile_title") or ocr.get("profile"))
                    profile_grader = clean_grader(ocr.get("profileGrader") or ocr.get("profile_grader") or row.grader)
                    profile_grade = clean_grade(ocr.get("profileGrade") or ocr.get("profile_grade") or "")
                    if profile_title and is_blank_card_title(row.card_title, row.grader):
                        row.card_title = build_card_title(profile_title, profile_grader, profile_grade)
                    row.card_ladder_comps_average = comp_price(comps, self.comp_strategy)
                    row.card_ladder_comps = format_comps(comps, self.comp_strategy)
                    row.card_ladder_screenshot = str(ocr.get("debugImage") or "")
                    row.status = "Card Ladder OK" if value is not None else "Card Ladder review"
                    row.notes = str(result.get("error") or result.get("status") or "")
                    break
        if self.on_update:
            self.on_update()

    def finish_cardladder(self, payload: dict) -> None:
        with self.lock:
            self.cardladder_running = False
            for row in self.rows:
                if row.status == "Queued":
                    row.status = "Card Ladder not found"
        if self.on_update:
            self.on_update()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "bridgeVersion": BRIDGE_VERSION,
                "extensionLastSeen": self.last_seen_extension,
                "cardladderRunning": self.cardladder_running,
                "compStrategy": self.comp_strategy,
                "rows": [asdict(row) for row in self.rows],
            }


def parse_value(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace("$", "").replace(",", "").strip())
    except ValueError:
        return None


def is_blank_card_title(card_title: str, grader: str) -> bool:
    title = str(card_title or "").strip()
    company = str(grader or "").strip()
    if not title:
        return True
    return bool(company and title.upper() == company.upper())


def clean_profile_title(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^profile\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\s*\(pop\s*[^)]*\)\s*$", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def clean_grader(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip().upper()
    aliases = {"BECKETT": "BGS", "BVG": "BGS", "PSA": "PSA", "BGS": "BGS", "SGC": "SGC", "CGC": "CGC"}
    return aliases.get(text, text)


def clean_grade(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    matches = re.findall(r"\d+(?:\.\d+)?", text)
    return matches[-1] if matches else ""


def build_card_title(description: str, grader: str, grade: str) -> str:
    title = clean_profile_title(description)
    parts = [title] if title else []
    if grader and not re.search(rf"\b{re.escape(grader)}\b", title, re.I):
        parts.append(grader)
    if grade and not re.search(rf"(?<!\d){re.escape(grade)}(?!\d)", " ".join(parts)):
        parts.append(grade)
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def average_comp_prices(comps: list[dict]) -> float | None:
    values = [parse_value(comp.get("price")) for comp in comps if isinstance(comp, dict)]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def comp_price(comps: list[dict], strategy: str) -> float | None:
    values = comp_values(comps)
    if not values:
        return None
    if strategy == COMP_STRATEGY_HIGH:
        return max(values)
    if strategy == COMP_STRATEGY_LOW:
        return min(values)
    if strategy == COMP_STRATEGY_STALE_NEWEST:
        return stale_newest_else_average(comps, values)
    return round(sum(values) / len(values), 2)


def comp_values(comps: list[dict]) -> list[float]:
    values = [parse_value(comp.get("price")) for comp in comps[:5] if isinstance(comp, dict)]
    return [value for value in values if value is not None]


def stale_newest_else_average(comps: list[dict], values: list[float]) -> float | None:
    if not values:
        return None
    first_date = parse_comp_date(comps[0].get("date_sold")) if comps and isinstance(comps[0], dict) else None
    second_date = parse_comp_date(comps[1].get("date_sold")) if len(comps) > 1 and isinstance(comps[1], dict) else None
    if first_date and second_date and abs((first_date - second_date).days) > 7:
        newest_value = parse_value(comps[0].get("price"))
        return newest_value if newest_value is not None else round(sum(values) / len(values), 2)
    return round(sum(values) / len(values), 2)


def parse_comp_date(value) -> datetime | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text, flags=re.I)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def format_comps(comps: list[dict], strategy: str = COMP_STRATEGY_AVERAGE) -> str:
    lines: list[str] = []
    selected_value = comp_price(comps, strategy)
    label = COMP_STRATEGY_LABELS.get(strategy, COMP_STRATEGY_LABELS[COMP_STRATEGY_AVERAGE])
    if selected_value is not None:
        lines.append(f"Comp method: {label} -> ${selected_value:,.2f}")
    for index, comp in enumerate(comps[:5], start=1):
        if not isinstance(comp, dict):
            continue
        date = str(comp.get("date_sold") or "").strip()
        price = str(comp.get("price") or "").strip()
        sale_type = str(comp.get("sale_type") or "").strip()
        source = str(comp.get("source") or "").strip()
        title = str(comp.get("title") or "").strip()
        lines.append(f"{index}. {date} | {price} | {sale_type} | {source} | {title}".strip())
    return "\n".join(lines)


class BridgeServer:
    def __init__(self, state: BridgeState, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.state = state
        self.host = host
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self):
                self._send_json({})

            def do_GET(self):
                if self.path.startswith("/command"):
                    self._send_json(state.extension_poll())
                    return
                if self.path.startswith("/status"):
                    self._send_json(state.snapshot())
                    return
                self._send_json({"ok": True, "service": "comp-orchestrator"})

            def do_POST(self):
                payload = self._read_json()
                if self.path.startswith("/ack"):
                    state.acknowledge_command(int(payload.get("id") or 0))
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/result/cardladder"):
                    state.post_cardladder_result(payload)
                    self._send_json({"ok": True})
                    return
                if self.path.startswith("/ocr/cardladder"):
                    try:
                        self._send_json(extract_cl_value_from_data_url(str(payload.get("image") or "")))
                    except Exception as error:
                        self._send_json({"ok": False, "value": None, "error": str(error)})
                    return
                if self.path.startswith("/finish/cardladder"):
                    state.finish_cardladder(payload)
                    self._send_json({"ok": True})
                    return
                self._send_json({"ok": False, "error": "unknown endpoint"}, status=404)

            def _read_json(self) -> dict:
                length = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(length).decode("utf-8") if length else "{}"
                return json.loads(raw or "{}")

            def _send_json(self, payload: dict, status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("access-control-allow-origin", "*")
                self.send_header("access-control-allow-methods", "GET,POST,OPTIONS")
                self.send_header("access-control-allow-headers", "content-type")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
