from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WorkbookRow:
    excel_row: int
    cert_number: str
    card_title: str
    grader: str
    existing_value: Any = None
    card_ladder_value: float | None = None
    card_ladder_comps_average: float | None = None
    card_ladder_comp_confidence: str = ""
    card_ladder_comps: str = ""
    card_ladder_screenshot: str = ""
    alt_value: float | None = None
    cy_value: float | None = None
    best_company: str = ""
    estimated_payout: float | None = None
    status: str = "Ready"
    notes: str = ""
