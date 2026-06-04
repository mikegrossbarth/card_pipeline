# Card Pipeline Handoff Context

## Project Location

- Local project: `C:\Users\User\Documents\Codex\2026-06-04\card_pipeline`
- GitHub remote: `https://github.com/mikegrossbarth/card_pipeline`
- App launchers:
  - `Run Card Pipeline.vbs` launches without a terminal window.
  - `Run Card Pipeline.bat` is the visible-console fallback.

## Purpose

Card Pipeline combines card intake, Card Ladder auto-comping, and receiving/review workflows into one desktop app.

The app is currently stage one of a larger card operations pipeline:

1. Intake cards from scanner, photos, or spreadsheet.
2. Save intake rows as working sheets.
3. Select a working sheet and run Card Ladder comps.
4. Review received cards against incoming sheets.
5. Later stages will add payout decisions, payment handling, logging across users, and seller/company optimization.

## Important Folders

The app expects Google Drive to be mapped locally:

- Pipeline root: `G:\My Drive\CARD_PIPELINE`
- Working sheets: `G:\My Drive\CARD_PIPELINE\WORKING SHEETS`
- Incoming sheets: `G:\My Drive\CARD_PIPELINE\INCOMING SHEETS`

The sandbox may not be able to read/write `G:\`, but the app is coded to use those paths on the user machine.

## Main Files

- `app.py`: Tkinter desktop UI and workflow orchestration.
- `intake_io.py`: Spreadsheet/photo-export normalization, sheet reading/writing, cert/grader helpers.
- `comp_engine/bridge_server.py`: Local bridge server for Card Ladder extension.
- `comp_engine/cardladder_ocr.py`: OCR/parsing helpers for CL Value, comps, and profile title.
- `comp_engine/workbook_io.py`: Workbook row model and workbook utilities for comping.
- `cardladder-autocomp/extension`: Chrome extension/helper used to automate Card Ladder sales history through the browser.

## Current UI

Top-level tabs:

- `Intake`
- `Comp`
- `Review`

### Intake Tab

Input modes:

- `Barcode Scanner`: scanning station mode; each scan appends the next row.
- `Photo OCR`: embedded photo-to-spreadsheet flow inside this app.
- `Existing Spreadsheet`: reads sheets in photo export style:
  - column 1 = cert number
  - column 2 = card description
  - column 3 = purchase price

The intake table is editable by double-clicking cells. Duplicate certs are highlighted yellow.

Users enter a working sheet title, then click `Save as Working Sheet`.

After saving:

- Rows clear.
- The app stays on Intake.
- It does not auto-refresh Comp; the user refreshes manually.

### Comp Tab

Comp tab does not carry rows from Intake directly. It scans `WORKING SHEETS`.

Left panel:

- Active sheets list.
- `Load Selected Sheet`
- `Refresh Sheets`

Bottom-right comp controls:

- `Comp Method`
- `Run All Comps`
- `Save Output`

Comp methods:

- `Average last 5`
- `Highest of last 5`
- `Lowest of last 5`
- `Date weighted`

Card Ladder behavior:

- Uses the Card Ladder sales-history cert search.
- Grader selection supports PSA, BGS/BECKETT, SGC, CGC.
- OCR captures `CL Value`.
- OCR also captures up to the most recent 5 comps and averages/chooses values based on selected comp method.
- If the sheet row has no card description, Card Ladder profile text fills the table card field as `Description Grader Grade`.
- Pop text such as `(Pop 24)` is stripped from the filled card description.

### Review Tab

Review rows are independent from Intake and Comp.

Modes:

- `Automatic Review`
- `Manual Review`

Automatic Review has an input selector:

- `Barcode Scanner`
- `Photo OCR`

Manual Review:

- The Review table renders a bottom `+` row.
- Clicking the `+` row adds a new manual row at the bottom.
- Users edit the table directly.

Review matching:

- Incoming certs are indexed from `G:\My Drive\CARD_PIPELINE\INCOMING SHEETS`.
- If a cert is found, `Sheet Source` becomes the incoming sheet filename and status becomes `Received`.
- If no cert match is found, `Sheet Source` becomes `NO SHEET FOUND`, the row is highlighted red, and status becomes `Received - no incoming match`.
- `Refresh Incoming Sheets` and `Clear Review Rows` live at the bottom of the Review tab.

## Development Notes

- Use `apply_patch` for manual file edits.
- Use `rg` for searching.
- Use bundled Python for syntax checks:

```powershell
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile app.py
```

- Runtime output is intentionally ignored:
  - `work/`
  - `outputs/`
  - `__pycache__/`

## Recent User Preferences

- Keep the app polished and uncluttered.
- Avoid clunky large buttons when table-native controls make more sense.
- Tables should behave like editable Excel-style grids.
- Column widths should be resizable and stay where the user puts them.
- Photo OCR should live inside the app rather than opening a separate tool window.
- Comp/Review should not automatically inherit rows from prior tabs; they should scan their proper folders.
- Prefer slow/reliable Card Ladder automation over fast/brittle behavior.

## Verification Before Handoff

Latest syntax check passed for:

```powershell
python -m py_compile app.py
```
