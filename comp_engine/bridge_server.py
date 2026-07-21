from __future__ import annotations

import json
import re
import socket
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, unquote, urlparse

from cardladder_ocr import extract_cl_value_from_data_url
from workbook_io import WorkbookRow
import assignment_engine

BRIDGE_VERSION = "2026-07-21-cardladder-visible-cert-result-v24"
EXPECTED_CARDLADDER_EXTENSION_VERSION = "2026-07-21-visible-cert-result-v24"
EXPECTED_CARDLADDER_MANIFEST_VERSION = "0.1.7"
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


def fill_missing_category_from_title(row: WorkbookRow) -> None:
    if str(getattr(row, "category", "") or "").strip():
        return
    parsed = assignment_engine.parse_card_for_matching(getattr(row, "card_title", "") or "")
    sport = str(parsed.get("sport") or "").strip()
    if sport:
        row.category = sport


def normalize_result_cert(value: object) -> str:
    cert = re.sub(r"\D", "", str(value or ""))
    return cert if len(cert) >= 6 else ""


class BridgeState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.instance_id = uuid.uuid4().hex
        self.rows: list[WorkbookRow] = []
        self.command: dict | None = None
        self.command_id = int(time.time() * 1000)
        self.last_seen_extension = ""
        self.extension_version = ""
        self.extension_manifest_version = ""
        self.extension_name = ""
        self.extension_url = ""
        self.last_result_extension_version = ""
        self.cardladder_running = False
        self.cancel_requested = False
        self.comp_strategy = COMP_STRATEGY_AVERAGE
        self.comp_low_outlier_pct: float | None = None
        self.updated_row_ids: set[int] = set()
        self.keep_note_sources: list[dict[str, str]] = []
        self.last_keep_sync: dict[str, str] = {}
        self.on_update: Callable[[], None] | None = None

    def set_rows(self, rows: list[WorkbookRow]) -> None:
        with self.lock:
            self.rows = rows
            self.updated_row_ids = set()

    def set_comp_strategy(self, strategy: str, low_outlier_pct: float | None = None) -> None:
        with self.lock:
            self.comp_strategy = strategy if strategy in COMP_STRATEGY_LABELS else COMP_STRATEGY_AVERAGE
            self.comp_low_outlier_pct = low_outlier_pct if isinstance(low_outlier_pct, (int, float)) and low_outlier_pct > 0 else None

    def register_keep_note_sources(self, sources: list[dict[str, object]]) -> None:
        normalized: list[dict[str, str]] = []
        for source in sources:
            url = str(source.get("url") or "").strip()
            path = str(source.get("path") or source.get("file") or "").strip()
            name = str(source.get("name") or Path(path).stem or "Google Keep note")
            if url and path:
                normalized.append({"url": url, "path": path, "name": name})
        with self.lock:
            self.keep_note_sources = normalized

    def post_google_keep_note(self, payload: dict) -> dict:
        text = str(payload.get("text") or "").strip()
        url = str(payload.get("url") or "").strip()
        title = str(payload.get("title") or "").strip() or "Google Keep note"
        synced_at = str(payload.get("synced_at") or payload.get("syncedAt") or "").strip() or datetime.now(timezone.utc).isoformat()
        if not text:
            return {"ok": False, "saved": 0, "error": "Google Keep note text was empty."}
        with self.lock:
            sources = list(self.keep_note_sources)
        matches = [source for source in sources if keep_urls_match(url, source.get("url", ""))]
        saved_paths: list[str] = []
        for source in matches:
            path = Path(source["path"]).expanduser()
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text + "\n", encoding="utf-8")
                saved_paths.append(str(path))
            except OSError:
                continue
        with self.lock:
            self.last_keep_sync = {"url": url, "title": title, "syncedAt": synced_at, "saved": str(len(saved_paths))}
        return {"ok": bool(saved_paths), "saved": len(saved_paths), "paths": saved_paths}

    def start_all_comps(self, requery_all: bool = False) -> int:
        with self.lock:
            self.command_id += 1
            eligible_rows = [
                row
                for row in self.rows
                if row.cert_number and row.grader and (requery_all or not row_has_comp_data(row))
            ]
            queue = [
                {
                    "excelRow": row.excel_row,
                    "certNumber": row.cert_number,
                    "grader": row.grader,
                    "cardTitle": row.card_title,
                }
                for row in eligible_rows
            ]
            for row in eligible_rows:
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
            self.cancel_requested = False
            return self.command_id

    def request_cancel(self) -> None:
        with self.lock:
            self.cancel_requested = True
            self.command = None
            self.cardladder_running = False
            for row in self.rows:
                if row.status == "Queued":
                    row.status = "Card Ladder cancelled"
        if self.on_update:
            self.on_update()

    def extension_poll(self, metadata: dict[str, str] | None = None) -> dict:
        with self.lock:
            self.last_seen_extension = time.strftime("%H:%M:%S")
            extension_version = ""
            if metadata:
                extension_version = metadata.get("extensionVersion") or ""
                self.extension_version = metadata.get("extensionVersion") or self.extension_version
                self.extension_manifest_version = metadata.get("manifestVersion") or self.extension_manifest_version
                self.extension_name = metadata.get("extensionName") or self.extension_name
                self.extension_url = metadata.get("extensionUrl") or self.extension_url
            command = self.command if extension_version == EXPECTED_CARDLADDER_EXTENSION_VERSION else None
            return {
                "instanceId": self.instance_id,
                "command": command,
                "lastKeepSync": dict(self.last_keep_sync),
            }

    def acknowledge_command(self, command_id: int) -> None:
        with self.lock:
            if self.command and self.command.get("id") == command_id:
                self.command = None

    def post_cardladder_result(self, result: dict) -> None:
        DEBUG_DIR.mkdir(parents=True, exist_ok=True)
        debug_stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}"
        (DEBUG_DIR / f"result-{debug_stamp}.json").write_text(
            json.dumps(result, indent=2),
            encoding="utf-8",
        )
        with self.lock:
            result_extension_version = str(result.get("extensionVersion") or "")
            if result_extension_version:
                self.last_result_extension_version = result_extension_version
                self.extension_version = result_extension_version
            cert = str(result.get("certNumber") or "")
            excel_row = int(result.get("excelRow") or 0)
            target_row = next((row for row in self.rows if excel_row and row.excel_row == excel_row), None)
            if target_row is None and cert:
                target_row = next((row for row in self.rows if row.cert_number == cert), None)
            if target_row is not None:
                self._apply_cardladder_result_to_row(target_row, result)
                self.updated_row_ids.add(id(target_row))
        if self.on_update:
            self.on_update()

    def _apply_cardladder_result_to_row(self, row: WorkbookRow, result: dict) -> None:
        result_status = str(result.get("status") or "")
        value = parse_value(result.get("value"))
        row.card_ladder_value = value
        ocr = result.get("ocr") if isinstance(result.get("ocr"), dict) else {}
        result_cert = (
            normalize_result_cert(result.get("certNumber"))
            or normalize_result_cert(result.get("cert_number"))
            or normalize_result_cert(ocr.get("certNumber"))
            or normalize_result_cert(ocr.get("cert_number"))
        )
        if result_cert and not normalize_result_cert(row.cert_number):
            row.cert_number = result_cert
        comps = ocr.get("comps") if isinstance(ocr.get("comps"), list) else []
        profile_title = clean_profile_title(ocr.get("profileTitle") or ocr.get("profile_title") or ocr.get("profile"))
        profile_grader = clean_grader(ocr.get("profileGrader") or ocr.get("profile_grader") or row.grader)
        profile_grade = clean_grade(ocr.get("profileGrade") or ocr.get("profile_grade") or "")
        raw_comp_count = len(comps)
        comps = filter_comps_for_card(comps, profile_title or row.card_title)
        filtered_comp_count = raw_comp_count - len(comps)
        generic_profile_reason = generic_profile_review_reason(profile_title, profile_grader, profile_grade, ocr)
        if result_status == "partial_comp_capture":
            if not ocr and result_extension_is_stale(result.get("extensionVersion")):
                row.card_ladder_value = None
                row.card_ladder_comps_average = None
                row.card_ladder_comps = ""
                row.card_ladder_screenshot = ""
                row.status = "Reload Card Ladder extension"
                row.notes = (
                    "Partial capture came from an older Card Ladder extension that does not preserve "
                    "partial diagnostics. Reload the unpacked extension, then rerun this row."
                )
                return
            if profile_title:
                row.card_title = build_card_title(profile_title, profile_grader, profile_grade)
                fill_missing_category_from_title(row)
            if row_has_comp_data(row):
                row.notes = str(result.get("error") or "Partial Card Ladder capture skipped; kept existing comps.")
                return
            row.card_ladder_value = None
            row.card_ladder_comps_average = None
            row.card_ladder_comps = ""
            row.card_ladder_screenshot = ""
            row.status = "Card Ladder partial capture"
            row.notes = str(result.get("error") or "Card Ladder comp capture was incomplete.")
            return
        if result_status == "invalid_cert":
            row.card_title = ""
            row.card_ladder_value = None
            row.card_ladder_comps_average = None
            row.card_ladder_comps = ""
            row.card_ladder_screenshot = ""
            row.status = "Card Ladder invalid cert"
            row.notes = str(result.get("error") or "Card Ladder showed no information with this cert.")
            return
        if (
            result_status == "no_results"
            and not result.get("extensionVersion")
            and not profile_title
            and not ocr
        ):
            row.status = "Reload Card Ladder extension"
            row.notes = (
                "The Card Ladder result came from an older Chrome extension that cannot capture "
                "profile names on no-result pages. Reload the bundled Card Ladder Auto-Comp extension."
            )
            return
        if result_status == "extension_error":
            row.card_ladder_value = None
            row.card_ladder_comps_average = None
            row.card_ladder_comps = ""
            row.card_ladder_screenshot = str(ocr.get("debugImage") or "")
            row.status = "Card Ladder extension error"
            row.notes = str(result.get("error") or "Card Ladder lookup failed before a result could be captured.")
            return
        if generic_profile_reason:
            row.card_title = ""
            row.card_ladder_value = None
            row.card_ladder_comps_average = None
            row.card_ladder_comps = ""
            row.card_ladder_screenshot = str(ocr.get("debugImage") or "")
            row.status = "Card Ladder review"
            row.notes = generic_profile_reason
            return
        if profile_title:
            row.card_title = build_card_title(profile_title, profile_grader, profile_grade)
            fill_missing_category_from_title(row)
        row.card_ladder_comps_average = comp_price(comps, self.comp_strategy, self.comp_low_outlier_pct)
        row.card_ladder_comps = format_comps(comps, self.comp_strategy, self.comp_low_outlier_pct)
        row.card_ladder_screenshot = str(ocr.get("debugImage") or "")
        if result_status == "no_results":
            row.status = "Card Ladder no results"
        elif raw_comp_count and not comps:
            row.status = "Card Ladder review"
        else:
            row.status = "Card Ladder OK" if value is not None else "Card Ladder review"
        filter_note = f"Rejected {filtered_comp_count} likely wrong-card comp(s)." if filtered_comp_count else ""
        row.notes = " ".join(part for part in (str(result.get("error") or result.get("status") or ""), filter_note) if part).strip()

    def finish_cardladder(self, payload: dict) -> None:
        with self.lock:
            self.cardladder_running = False
            self.cancel_requested = False
            for row in self.rows:
                if row.status == "Queued":
                    row.status = "Card Ladder not found"
        if self.on_update:
            self.on_update()

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "bridgeVersion": BRIDGE_VERSION,
                "instanceId": self.instance_id,
                "extensionLastSeen": self.last_seen_extension,
                "extensionVersion": self.extension_version,
                "extensionManifestVersion": self.extension_manifest_version,
                "extensionName": self.extension_name,
                "extensionUrl": self.extension_url,
                "expectedExtensionVersion": EXPECTED_CARDLADDER_EXTENSION_VERSION,
                "expectedManifestVersion": EXPECTED_CARDLADDER_MANIFEST_VERSION,
                "lastResultExtensionVersion": self.last_result_extension_version,
                "cardladderRunning": self.cardladder_running,
                "cancelRequested": self.cancel_requested,
                "compStrategy": self.comp_strategy,
                "lastKeepSync": dict(self.last_keep_sync),
                "rows": [asdict(row) for row in self.rows],
            }


def parse_value(value) -> float | None:
    if value is None or value == "":
        return None
    text = str(value).replace("$", "").replace(",", "").strip()
    multiplier = 1
    if text.lower().endswith("k"):
        multiplier = 1000
        text = text[:-1].strip()
    if re.fullmatch(r"-?\d{1,3}\.\d{3}", text):
        text = text.replace(".", "")
    try:
        return float(text) * multiplier
    except ValueError:
        return None


def keep_urls_match(first: str, second: str) -> bool:
    first_key = keep_url_key(first)
    second_key = keep_url_key(second)
    if first_key and second_key:
        return first_key == second_key
    first_norm = normalize_keep_url(first)
    second_norm = normalize_keep_url(second)
    return bool(first_norm and second_norm and (first_norm == second_norm or first_norm.startswith(second_norm) or second_norm.startswith(first_norm)))


def keep_url_key(value: str) -> str:
    raw = str(value or "")
    parsed = urlparse(raw)
    haystack = f"{parsed.path}#{parsed.fragment}"
    match = re.search(r"/notes/([^/?#]+)", haystack)
    if match:
        return unquote(match.group(1)).strip().lower()
    match = re.search(r"#NOTE/([^/?#]+)", haystack, flags=re.I)
    if match:
        return unquote(match.group(1)).strip().lower()
    match = re.search(r"(?:note|id|text)%3D([^&#]+)", haystack, flags=re.I)
    return unquote(match.group(1)).strip().lower() if match else ""


def normalize_keep_url(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if not parsed.netloc.lower().endswith("keep.google.com"):
        return ""
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}#{parsed.fragment}".rstrip("/#").lower()


def is_blank_card_title(card_title: str, grader: str) -> bool:
    title = str(card_title or "").strip()
    company = str(grader or "").strip()
    if not title:
        return True
    return bool(company and title.upper() == company.upper())


def row_has_comp_data(row: WorkbookRow) -> bool:
    status = str(row.status or "").strip().lower().replace("_", " ")
    notes = str(row.notes or "").strip().lower().replace("_", " ")
    has_terminal_empty_result = any(
        token in f"{status} {notes}"
        for token in (
            "invalid cert",
            "no information with this cert",
            "no results",
        )
    )
    return (
        row.card_ladder_comps_average is not None
        or bool(str(row.card_ladder_comps or "").strip())
        or has_terminal_empty_result
    )


def result_extension_is_stale(extension_version: object) -> bool:
    version = str(extension_version or "").strip()
    return version != EXPECTED_CARDLADDER_EXTENSION_VERSION


def clean_profile_title(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"^profile\s*:\s*", "", text, flags=re.I)
    tail_patterns = [
        r"\s+\bclose\s+\$?\d[\d,]*(?:\.\d{1,2})?.*$",
        r"\s+\bclose\s+search[_\s-]*off\b.*$",
        r"\s+\bclose\b\s*$",
        r"\s+\bclose\b\s+(?=\b(?:PSA|BGS|SGC|CGC|BECKETT|BVG)\b|\d+(?:\.\d+)?\b).*$",
        r"\s+[x×]\s*$",
        r"\s+\bthere\s+are\s+no\s+results\b.*$",
        r"\s+\btry\s+searching\b.*$",
        r"\s+\bhelp[_\s-]*outline\b.*$",
        r"\s+\b(?:date\s+sold|type|price)\b.*$",
        r"\s+\$\d[\d,]*(?:\.\d{1,2})?\s+\b(?:help[_\s-]*outline|ebay|fanatics|pwcc|goldin|alt|myslabs|heritage|pristine|auction)\b.*$",
    ]
    for pattern in tail_patterns:
        text = re.sub(pattern, "", text, flags=re.I)
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


def generic_profile_review_reason(profile_title: str, grader: str, grade: str, ocr: dict) -> str:
    title = clean_profile_title(profile_title)
    if not title:
        return ""
    result_count = safe_int(ocr.get("resultCount") or ocr.get("result_count"))
    if not is_generic_cardladder_profile_title(title, grader, grade):
        return ""
    return (
        f"Card Ladder returned an overly broad profile title ({build_card_title(title, grader, grade) or title})"
        + (f" with {result_count} results" if result_count is not None else "")
        + ". Re-run or verify manually before saving comps."
    )


def is_generic_cardladder_profile_title(title: str, grader: str = "", grade: str = "") -> bool:
    cleaned = clean_profile_title(title)
    cleaned = re.sub(rf"\b{re.escape(clean_grader(grader))}\b", " ", cleaned, flags=re.I) if grader else cleaned
    cleaned = re.sub(rf"(?<!\d){re.escape(clean_grade(grade))}(?!\d)", " ", cleaned) if grade else cleaned
    cleaned = re.sub(r"\b(?:psa|bgs|sgc|cgc|gem|mint|mt)\b", " ", cleaned, flags=re.I)
    words = [word for word in re.findall(r"[A-Za-z0-9#'-]+", cleaned) if word]
    if len(words) <= 2 and any(re.fullmatch(r"19\d{2}|20\d{2}", word) for word in words):
        return True
    has_player_or_number = any(re.search(r"#|[A-Za-z]{2,}\d|\d+[A-Za-z]", word) for word in words)
    has_enough_detail = len(words) >= 4 or has_player_or_number
    return not has_enough_detail


def safe_int(value) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return None


def average_comp_prices(comps: list[dict]) -> float | None:
    comps = dedupe_comps(comps)
    values = [parse_value(comp.get("price")) for comp in comps if isinstance(comp, dict)]
    values = [value for value in values if value is not None]
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def filter_comps_for_card(comps: list[dict], card_title: str) -> list[dict]:
    if not comps:
        return []
    target_tokens = comp_match_tokens(card_title)
    target_years = {token for token in target_tokens if re.fullmatch(r"(?:19|20)\d{2}", token)}
    target_numbers = comp_card_number_tokens(target_tokens)
    target_parallel_tokens = target_tokens & {
        "gold",
        "silver",
        "orange",
        "red",
        "blue",
        "green",
        "yellow",
        "black",
        "white",
        "purple",
        "pink",
        "holo",
        "laser",
        "shimmer",
        "fluorescent",
        "optic",
        "mosaic",
        "prizm",
        "refractor",
        "wave",
        "cracked",
        "ice",
        "choice",
    }
    if len(target_tokens) < 4:
        return comps
    filtered: list[dict] = []
    for comp in comps:
        if not isinstance(comp, dict):
            continue
        title = clean_comp_title(comp.get("title"))
        tokens = comp_match_tokens(title)
        if len(tokens) < 3:
            filtered.append(comp)
            continue
        comp_years = {token for token in tokens if re.fullmatch(r"(?:19|20)\d{2}", token)}
        if target_years and comp_years and target_years.isdisjoint(comp_years):
            continue
        comp_numbers = comp_card_number_tokens(tokens)
        if target_numbers and comp_numbers and target_numbers.isdisjoint(comp_numbers):
            continue
        comp_parallel_tokens = tokens & target_parallel_tokens
        if len(target_parallel_tokens) >= 2 and not comp_parallel_tokens:
            continue
        overlap = target_tokens & tokens
        required = 2 if len(target_tokens) < 7 else 3
        if len(overlap) >= required:
            filtered.append(comp)
            continue
        ratio = len(overlap) / max(1, min(len(target_tokens), len(tokens)))
        if ratio >= 0.42:
            filtered.append(comp)
    return filtered


def comp_match_tokens(value: object) -> set[str]:
    text = clean_comp_title(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    raw_tokens = re.findall(r"[a-z0-9]+", text)
    stop = {
        "psa",
        "bgs",
        "sgc",
        "cgc",
        "gem",
        "mint",
        "rookie",
        "rc",
        "card",
        "cards",
        "auto",
        "autograph",
        "autographs",
        "refractor",
        "refractors",
        "chrome",
        "panini",
        "topps",
        "donruss",
        "bowman",
        "upper",
        "deck",
    }
    return {token for token in raw_tokens if len(token) >= 3 and token not in stop}


def comp_card_number_tokens(tokens: set[str]) -> set[str]:
    return {token for token in tokens if token.isdigit() and len(token) >= 3 and not re.fullmatch(r"(?:19|20)\d{2}", token)}


def dedupe_comps(comps: list[dict]) -> list[dict]:
    cleaned: list[dict] = []
    for comp in comps:
        if not isinstance(comp, dict):
            continue
        normalized = dict(comp)
        normalized["title"] = clean_comp_title(normalized.get("title"))
        normalized["source"] = clean_comp_source(normalized.get("source"))
        if is_junk_comp_title(normalized.get("title")):
            continue
        cleaned.append(normalized)

    best_by_key: dict[tuple[str, str, str, str], dict] = {}
    order: list[tuple[str, str, str, str]] = []
    for comp in cleaned:
        date = normalized_comp_date_key(comp.get("date_sold"))
        price = str(comp.get("price") or "").replace("$", "").replace(",", "").strip()
        sale_type = re.sub(r"\s+", " ", str(comp.get("sale_type") or "")).strip().lower()
        key_base = (date, price, sale_type)
        title_key = compact_comp_title(comp.get("title"))[:80]
        target_key = None
        for existing_key, existing in best_by_key.items():
            same_price = existing_key[1] == price
            same_sale_type = existing_key[2] == sale_type
            same_date_price_type = existing_key[:3] == key_base
            same_date = existing_key[0] == key_base[0]
            existing_title_key = compact_comp_title(existing.get("title"))[:80]
            same_source = clean_comp_source(existing.get("source")).lower() == clean_comp_source(comp.get("source")).lower()
            similar_title = bool(title_key and existing_title_key and (title_key in existing_title_key or existing_title_key in title_key))
            if same_date and same_source and similar_title:
                target_key = existing_key
                break
            if not same_price:
                continue
            if same_date_price_type and (same_source or similar_title):
                target_key = existing_key
                break
            if same_sale_type and same_source and similar_title:
                target_key = existing_key
                break
        target_key = target_key or (*key_base, title_key or str(len(order)))
        if target_key not in best_by_key:
            order.append(target_key)
            best_by_key[target_key] = comp
            continue
        existing = best_by_key[target_key]
        existing_date = parse_comp_date(existing.get("date_sold"))
        comp_date = parse_comp_date(comp.get("date_sold"))
        if existing_date and comp_date and existing_date != comp_date:
            if comp_date < existing_date:
                best_by_key[target_key] = comp
            continue
        if comp_quality(comp) > comp_quality(existing):
            best_by_key[target_key] = comp
    return [best_by_key[key] for key in order][:5]


def clean_comp_source(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"\s*\(confirmed paid\)\s*", "", text, flags=re.I)
    return text


def clean_comp_title(value) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"\b(?:close|help[_\s-]*outline|Date Sold|Type|Price)\b", " ", text, flags=re.I)
    text = re.sub(r"^\s*[-|:]+\s*", "", text)
    text = re.sub(r"\s*[-|:]+\s*$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def compact_comp_title(value) -> str:
    text = clean_comp_title(value).lower()
    text = re.sub(r"\$\s*[\d,]+(?:\.\d{1,2})?", " ", text)
    text = re.sub(r"\b(psa|bgs|sgc|cgc|gem|mint|mt|pop|rookie|rc)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def is_junk_comp_title(value) -> bool:
    text = clean_comp_title(value)
    if not text:
        return True
    alnum = re.sub(r"[^A-Za-z0-9]", "", text)
    if len(alnum) < 8:
        return True
    return not re.search(r"[A-Za-z]{3,}", text)


def comp_quality(comp: dict) -> int:
    title = clean_comp_title(comp.get("title"))
    score = min(len(title), 160)
    if re.search(r"\b\d{4}\b", title):
        score += 20
    if re.search(r"#\s*[A-Za-z0-9-]+|\b[A-Za-z]{1,5}\d{1,4}\b", title):
        score += 10
    if comp_price_conflicts_with_title(comp):
        score -= 120
    elif re.search(r"\$\s*[\d,]+(?:\.\d{1,2})?", title):
        score -= 40
    if is_junk_comp_title(title):
        score -= 200
    return score


def comp_price_conflicts_with_title(comp: dict) -> bool:
    price = parse_value(comp.get("price"))
    if price is None:
        return False
    title_values = [
        parse_value(match.group(0))
        for match in re.finditer(r"\$\s*[\d,]+(?:\.\d{1,2})?", clean_comp_title(comp.get("title")))
    ]
    title_values = [value for value in title_values if value is not None]
    return bool(title_values and all(abs(value - price) > 0.01 for value in title_values))


def comp_price(comps: list[dict], strategy: str, low_outlier_pct: float | None = None) -> float | None:
    comps, _removed, _cutoff = filter_low_outlier_comps(comps, low_outlier_pct)
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
    comps = dedupe_comps(comps)
    values = [parse_value(comp.get("price")) for comp in comps[:5] if isinstance(comp, dict)]
    return [value for value in values if value is not None]


def filter_low_outlier_comps(comps: list[dict], low_outlier_pct: float | None = None) -> tuple[list[dict], int, float | None]:
    deduped = dedupe_comps(comps)
    if not isinstance(low_outlier_pct, (int, float)) or low_outlier_pct <= 0:
        return deduped, 0, None
    first_five = [comp for comp in deduped[:5] if isinstance(comp, dict)]
    values = [parse_value(comp.get("price")) for comp in first_five]
    numeric_values = [value for value in values if value is not None]
    if len(numeric_values) < 2:
        return deduped, 0, None
    mean = sum(numeric_values) / len(numeric_values)
    cutoff = mean * (float(low_outlier_pct) / 100.0)
    filtered_first: list[dict] = []
    removed = 0
    for comp in first_five:
        value = parse_value(comp.get("price"))
        if value is not None and value < cutoff:
            removed += 1
            continue
        filtered_first.append(comp)
    if not filtered_first:
        return deduped, 0, cutoff
    return [*filtered_first, *deduped[5:]], removed, cutoff


def newest_comp_date(comps: list[dict]) -> datetime | None:
    comps = dedupe_comps(comps)
    dates = []
    for comp in comps[:5]:
        if not isinstance(comp, dict):
            continue
        parsed = parse_comp_date(comp.get("date_sold"))
        if parsed:
            dates.append(parsed)
    return max(dates) if dates else None


def stale_newest_else_average(comps: list[dict], values: list[float]) -> float | None:
    comps = dedupe_comps(comps)
    values = comp_values(comps)
    if not values:
        return None
    dated_values: list[tuple[datetime, float]] = []
    for comp in comps[:5]:
        if not isinstance(comp, dict):
            continue
        value = parse_value(comp.get("price"))
        if value is None:
            continue
        sold_date = parse_comp_date(comp.get("date_sold"))
        if sold_date:
            dated_values.append((sold_date, value))
    dated_values.sort(key=lambda item: item[0], reverse=True)
    if dated_values and (datetime.now() - dated_values[0][0]).days > 7:
        return best_value_for_comp_date(comps, dated_values[0][0])
    if len(dated_values) >= 2 and (dated_values[0][0] - dated_values[1][0]).days > 7:
        return best_value_for_comp_date(comps, dated_values[0][0])
    average_values = [value for _sold_date, value in dated_values] if dated_values else values
    return round(sum(average_values) / len(average_values), 2)


def best_value_for_comp_date(comps: list[dict], sold_date: datetime) -> float | None:
    same_day: list[dict] = []
    for comp in comps[:5]:
        if not isinstance(comp, dict):
            continue
        value = parse_value(comp.get("price"))
        comp_date = parse_comp_date(comp.get("date_sold"))
        if value is not None and comp_date == sold_date:
            same_day.append(comp)
    if not same_day:
        return None
    best = max(same_day, key=comp_quality)
    return parse_value(best.get("price"))


def normalized_comp_date_key(value) -> str:
    parsed = parse_comp_date(value)
    if parsed:
        return parsed.strftime("%Y-%m-%d")
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def parse_comp_date(value) -> datetime | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text, flags=re.I)
    text = re.sub(r"\bSept\.?\b", "Sep", text, flags=re.I)
    text = re.sub(r"\b([A-Za-z]{3,9})\.", r"\1", text)
    date_match = re.search(
        r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b"
        r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b"
        r"|\b\d{4}-\d{1,2}-\d{1,2}\b",
        text,
        flags=re.I,
    )
    if date_match:
        text = date_match.group(0)
    text = re.sub(r"\bSept\.?\b", "Sep", text, flags=re.I)
    text = re.sub(r"\b([A-Za-z]{3,9})\.", r"\1", text)
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    return None


def format_comps(comps: list[dict], strategy: str = COMP_STRATEGY_AVERAGE, low_outlier_pct: float | None = None) -> str:
    comps, removed, cutoff = filter_low_outlier_comps(comps, low_outlier_pct)
    lines: list[str] = []
    selected_value = comp_price(comps, strategy)
    label = COMP_STRATEGY_LABELS.get(strategy, COMP_STRATEGY_LABELS[COMP_STRATEGY_AVERAGE])
    if selected_value is not None:
        lines.append(f"Comp method: {label} -> ${selected_value:,.2f}")
    if removed and cutoff is not None:
        lines.append(f"Low comp filter: removed {removed} comp(s) below ${cutoff:,.2f}")
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


def parse_formatted_comps(text: str) -> list[dict]:
    comps: list[dict] = []
    for line in str(text or "").splitlines():
        if re.match(r"^\s*comp method\s*:", line, flags=re.I):
            continue
        match = re.match(r"^\s*\d+\.\s*(.*)$", line)
        if not match:
            continue
        parts = [part.strip() for part in match.group(1).split("|")]
        if len(parts) < 2:
            continue
        comps.append(
            {
                "date_sold": parts[0],
                "price": parts[1],
                "sale_type": parts[2] if len(parts) > 2 else "",
                "source": parts[3] if len(parts) > 3 else "",
                "title": " | ".join(parts[4:]) if len(parts) > 4 else "",
            }
        )
    return comps


class BridgeServer:
    def __init__(self, state: BridgeState, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.state = state
        self.host = host
        self.port = port
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.started = False
        self.error = ""

    def start(self) -> None:
        state = self.state

        class Handler(BaseHTTPRequestHandler):
            def do_OPTIONS(self):
                self._send_json({})

            def do_GET(self):
                if self.path.startswith("/command"):
                    parsed = urlparse(self.path)
                    query = parse_qs(parsed.query)
                    metadata = {
                        "extensionVersion": query.get("extensionVersion", [""])[0],
                        "manifestVersion": query.get("manifestVersion", [""])[0],
                        "extensionName": query.get("extensionName", [""])[0],
                        "extensionUrl": query.get("extensionUrl", [""])[0],
                    }
                    self._send_json(state.extension_poll(metadata))
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
                if self.path.startswith("/source/google-keep"):
                    self._send_json(state.post_google_keep_note(payload))
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

        class ReusableThreadingHTTPServer(ThreadingHTTPServer):
            allow_reuse_address = True

        last_error = ""
        for candidate_port in range(self.port, self.port + 8):
            if self._port_has_listener(candidate_port):
                last_error = f"{self.host}:{candidate_port} already has a listener"
                continue
            try:
                self.httpd = ReusableThreadingHTTPServer((self.host, candidate_port), Handler)
                self.port = candidate_port
                self.error = ""
                break
            except OSError as error:
                last_error = str(error)
                self.httpd = None
        if self.httpd is None:
            self.started = False
            self.error = last_error or "Could not bind local bridge port."
            return
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.started = True

    def _port_has_listener(self, port: int) -> bool:
        try:
            with socket.create_connection((self.host, port), timeout=0.2):
                return True
        except OSError:
            return False

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
        self.started = False
