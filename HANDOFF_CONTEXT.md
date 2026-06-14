# L.U.C.A.S Handoff Context

L.U.C.A.S means Lot Upload, Comping & Assignment System.

## Current Snapshot

- Repo: `C:\Users\User\Documents\Codex\2026-06-04\card_pipeline`
- Branch: `main`
- Remote: `https://github.com/mikegrossbarth/card_pipeline.git`
- Current visible tabs: `Home`, `Create`, `Comp`, `Receive`, `Assignment`, `Payouts/Tabs`, `Profit`.
- Current setup walkthrough: `FIRST_RUN_SETUP.md`
- Latest feature commits before this handoff update:
  - `f57d3e6 Move profit sold view switch below chart`
  - `2dc426a Add profit person filters and sold sheet view`
  - `f72931e Show no-buyer assignment results`
  - `5dba0ee Capture failed assignments as unassigned players`

The old visible `Review` workflow was split into `Receive` and `Assignment`. Many internal Python names still use `review_*`; that is intentional legacy naming to avoid risky churn.

## Project Layout

- `app.py`: main Tkinter desktop app and UI workflows.
- `assignment_engine.py`: company rule parsing, payout parsing, category/player matching, and best-company recommendation.
- `assignment_config_ui.py`: Assignment Rules popup.
- `intake_io.py`: spreadsheet import/export, receive marking, company-sheet append, and profit record extraction.
- `shared_state.py`: atomic JSON writes and shared-folder lock helpers.
- `google_sheets_import.py`: desktop OAuth flow and Google Sheets export/read helpers.
- `comp_engine`: Card Ladder bridge, workbook rows, comp strategy, and screenshot OCR fallback.
- `photo_tool`: bundled photo OCR helper used by Create and Receive.
- `cardladder-autocomp\extension`: unpacked Chrome extension for Card Ladder automation.
- `tests\test_shared_workflows.py`: committed offline regression suite.

## Required Setup

For a full setup, nothing is optional. Each user/computer needs:

- Google Chrome.
- Python 3.11+ with Tkinter.
- Project `.venv` created by `install_dependencies.bat`.
- Local `.env` created from `.env.example`.
- `GOOGLE_API_KEY` for Photo OCR and Card Ladder screenshot OCR fallback.
- Google billing, payment method, spend cap, and billing budget alerts.
- Google Sheets OAuth desktop credentials in `.env`.
- `Connect Google` completed once inside Assignment Rules.
- Google Drive for desktop.
- Card Ladder account, active Chrome login, and the unpacked extension loaded from `cardladder-autocomp\extension`.
- Shared pipeline folder selected through the `Working Folder` button.
- Active assignment companies with rule and payout sources.

The key setup URLs and click-by-click flow live in `FIRST_RUN_SETUP.md`.

## Local-Only Files

Do not commit these:

- `.env`
- `.venv`
- `lucas_settings.json`
- `lucas_user_identity.json`
- `lucas_google_sheets_token.json`
- `assignment_companies.json`
- generated debug screenshots/logs

The repo now includes `.env.example`; `install_dependencies.bat` copies it to `.env` if `.env` is missing.

## Shared Pipeline Folder

The user chooses the actual `WORKING SHEETS` folder with the `Working Folder` button. L.U.C.A.S uses that folder's parent as the pipeline root.

Expected shared root shape:

```text
CARD_PIPELINE
  WORKING SHEETS
  INCOMING SHEETS
  RECEIVED SHEETS
  COMPANY SHEETS
  ASSIGNMENT RULES
  sheet_markers.json
  profit_ledger.json
  unassigned_players.json
  assignment_player_overrides.json
  .locks
```

For teams, every user can point their local app at the same synced Google Drive pipeline folder. Each user still keeps their own app folder, `.env`, OAuth token, and Card Ladder extension install. Shared writes use `.locks` plus atomic JSON writes to reduce Drive conflict risk.

## Tab Workflows

### Home

Home lists `Incoming`, `Working`, and `Received` sheets. `Edit Markers` handles:

- `Incoming`
- tracking number
- `All Received`
- assigned person

Payment state is handled in `Payouts/Tabs`, not Home marker buttons.

### Create

Create supports:

- barcode scanner rows
- photo OCR rows
- existing spreadsheet import

Existing spreadsheet import expects either a simple sheet with cert/card/purchase columns or a Photo OCR-style export. Output is saved as a working sheet.

### Comp

Comp runs Card Ladder through the local bridge and Chrome extension. It writes Card Ladder value, comps, assignment results, and statuses. Best-company assignment is recalculated when comp values are added or edited.

### Receive

Receive is for physically receiving cards and marking them received in sheets. It no longer owns assignment-rule loading. If `Company Pile` is checked for a row and the row has a real Best Company, marking received appends that card to the company's weekly sheet under `COMPANY SHEETS\<Company Name>`.

Rows marked `NOBODY TAKES` are not appended to company sheets.

### Assignment

Assignment is for loading received/unassigned sheets and recalculating best company/payout when needed. Assignment progress uses a visible green progress bar.

### Payouts/Tabs

Tracks active balances by assigned person. It includes incoming/unreceived and received/unpaid sheets. Clicking active balances can mark all matching person sheets paid.

### Profit

Profit reads `profit_ledger.json` and backfills from company sheets. It has:

- person filter
- daily profit line chart
- `Sold Cards` view
- `Sold Sheets` grouped view

Profit records are enriched from sheet markers by `source_sheet -> assigned_person`.

## Assignment Rules And Payouts

Assignment companies live in local-only `assignment_companies.json`. The rules manager supports:

- active/inactive companies
- company folders created under `COMPANY SHEETS`
- manual rules
- local rules files
- local Google Keep export/text files
- local workbook/CSV files
- Google Sheets through OAuth
- manual payout tiers
- payout files
- `Link Payouts to Same File`, reading a `Payouts` tab
- per-company value source: comps or Card Ladder value

Important behavior:

- If a company is set to use Card Ladder value and the row has no Card Ladder value, that company is ignored. It does not fall back to comps.
- Default value source is comps first, then Card Ladder value.
- A company must accept the card and have a matching payout tier/rate.
- Highest estimated payout wins.
- If no company can take the card, Best Company becomes `NOBODY TAKES`.
- Failed valued assignments are recorded in `unassigned_players.json` for review.
- Saving a player/category override removes the unassigned entry and schedules assignment recalculation.

Recent matching hardening:

- Shintaro Fujinami is baseball, not Tatsumi Fujinami/WWE.
- Sports titles no longer get hijacked by one-word Disney/Marvel/Pokemon/etc. partials such as `Aqua`, `Max`, or `series` unless the title has that category context.
- Yusniel Diaz, Jasson Dominguez, Ricardo Olivar, and Chipper Jones are built-in baseball hints.

## Google Sheets

Google Sheet sources can be saved as structured sources with URL and local XLSX cache path. On app startup and assignment-rule load, L.U.C.A.S refreshes saved Google Sheet sources through the Google Sheets API so the cache reflects edits made between app sessions.

OAuth files:

- credentials come from `.env`
- token cache is `lucas_google_sheets_token.json`

If a `.gsheet` shortcut cannot be opened locally, the UI asks for the Google Sheet URL and saves that URL-backed source.

## Card Ladder

Chrome extension folder:

```text
cardladder-autocomp\extension
```

The desktop bridge binds to the first available port from `8765` to `8772`. The extension manifest grants access to the same local range.

Common Card Ladder gotchas:

- user must be logged into Card Ladder in Chrome
- old unpacked extension versions should be removed/disabled
- app warns if the extension version seen by the bridge is stale
- no-results pages should still preserve the Card Ladder card title when available
- BGS OCR rejects subgrades as slab grades

## Tests And Verification

Primary offline test suite:

```bat
python -m unittest discover -s tests -v
```

Useful sanity checks:

```bat
python -m compileall -q .
python -c "import app; root = app.CardPipelineApp(); root.update_idletasks(); root.destroy(); print('app startup ok')"
```

For Codex desktop sessions, the bundled Python path used recently was:

```text
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe
```

Current committed tests cover:

- shared locks and atomic JSON writes
- sheet marker merging and tombstones
- Google Sheet cache export/startup refresh
- company-sheet append dedupe
- profit ledger dedupe and delta recording
- profit person enrichment and sold-sheet grouping
- assignment payout selection and Card Ladder value-source behavior
- GOAT payout-tier matching
- unassigned player capture and auto-categorization
- photo OCR region speed/recovery behavior

## Last Sweep Notes

The most recent final sweep checked:

- missing `.env.example` setup bug
- stale handoff/setup documentation
- syntax/compile pass across the project
- full offline test suite
- app startup smoke

Known environmental limitation: in Codex sandboxed shells, direct access to `G:\My Drive\...` may fail with Windows access errors even when the app can access it normally outside the sandbox.
