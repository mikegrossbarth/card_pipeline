from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app


class InventorySyncApp:
    _money_value = app.CardPipelineApp._money_value
    _inventory_record_key = app.CardPipelineApp._inventory_record_key
    _normalize_inventory_record = app.CardPipelineApp._normalize_inventory_record
    _load_inventory_ledger = app.CardPipelineApp._load_inventory_ledger
    _save_inventory_ledger = app.CardPipelineApp._save_inventory_ledger
    _next_raw_item_id = app.CardPipelineApp._next_raw_item_id
    _inventory_sport_from_value = app.CardPipelineApp._inventory_sport_from_value
    _received_inventory_candidate_records_for_sheet = app.CardPipelineApp._received_inventory_candidate_records_for_sheet
    add_inventory_records = app.CardPipelineApp.add_inventory_records

    def _company_sheet_source_cert_keys(self) -> set[tuple[str, str]]:
        return set()

    def _enrich_inventory_record_assignment(self, record: dict[str, object], force: bool = False) -> dict[str, object]:
        return self._normalize_inventory_record(record)

    def refresh_inventory_tab(self, *args, **kwargs) -> None:
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync one received LUCAS workbook into inventory.")
    parser.add_argument("root", help="LUCAS root folder")
    parser.add_argument("sheet", help="Received workbook filename")
    parser.add_argument("person", help="Assigned person")
    parser.add_argument("--replace-source", action="store_true", help="Remove existing inventory rows from this source sheet first.")
    args = parser.parse_args()

    root = Path(args.root)
    sheet_path = root / "RECEIVED SHEETS" / args.sheet
    if not sheet_path.exists():
        raise SystemExit(f"Received sheet not found: {sheet_path}")

    app.CARD_PIPELINE_DIR = root
    app.INVENTORY_LEDGER_PATH = root / "inventory_ledger.json"
    app.COMPANY_SHEETS_DIR = root / "COMPANY SHEETS"
    app.RECEIVED_SHEETS_DIR = root / "RECEIVED SHEETS"

    ledger_path = app.INVENTORY_LEDGER_PATH
    backup_path = None
    if ledger_path.exists():
        backup_path = root / f"inventory_ledger.json.backup-before-received-sync-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        shutil.copy2(ledger_path, backup_path)

    if args.replace_source and ledger_path.exists():
        payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        source_name = args.sheet.lower()
        payload["items"] = [
            item
            for item in payload.get("items", [])
            if str(item.get("source_sheet") or "").strip().lower() != source_name
        ]
        ledger_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    syncer = InventorySyncApp()
    records = syncer._received_inventory_candidate_records_for_sheet("Received", sheet_path, args.person)
    added = syncer.add_inventory_records(records, refresh=False)
    final_items = json.loads(ledger_path.read_text(encoding="utf-8")).get("items", []) if ledger_path.exists() else []
    source_items = [
        item
        for item in final_items
        if str(item.get("source_sheet") or "").strip().lower() == args.sheet.lower()
    ]
    print(
        json.dumps(
            {
                "root": str(root),
                "sheet": args.sheet,
                "person": args.person,
                "backup": str(backup_path) if backup_path else "",
                "candidates": len(records),
                "added": added,
                "source_inventory_rows": len(source_items),
                "total_inventory_rows": len(final_items),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
