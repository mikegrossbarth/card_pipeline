# L.U.C.A.S Handoff Context

L.U.C.A.S means Lot Upload, Comping & Assignment System.

## Current State

- Repo: `C:\Users\User\Documents\Codex\2026-06-04\card_pipeline`
- Branch: `main`
- Remote: `https://github.com/mikegrossbarth/card_pipeline.git`
- Current UI tabs: `Home`, `Intake`, `Comp`, `Assignment`.
- The old visible `Review` workflow has been renamed to `Assignment`; most internal Python names still use `review_*` intentionally to avoid churn.
- The Home header button is `Working Folder`. Users choose their actual `WORKING SHEETS` folder, and L.U.C.A.S uses that folder's parent for `INCOMING SHEETS`, `RECEIVED SHEETS`, and `sheet_markers.json`.
- Latest feature commit before this handoff update: `0814ff1 Configure pipeline from working folder`.

## Project Layout

- `app.py`: main Tkinter desktop app.
- `comp_engine`: workbook IO, Card Ladder bridge, comp math, and screenshot OCR fallback.
- `cardladder-autocomp\extension`: Chrome extension for Card Ladder automation.
- `photo_tool`: bundled photo OCR helper used by Intake and Assignment.
- `assets`: app logo and visual assets.

## Runtime Setup

Install dependencies with `install_dependencies.bat`. The script creates `.venv` and installs `requirements.txt`.

Python must be a normal Python 3.11+ install with Tkinter available. The Windows installer from python.org is the expected path; bundled app-specific Python runtimes may not include usable Tkinter support.

Copy `.env.example` to `.env` for local configuration:

- `GOOGLE_API_KEY`: required for Photo OCR and Card Ladder screenshot OCR fallback.
- `GOOGLE_SHEETS_OAUTH_CLIENT_ID` and `GOOGLE_SHEETS_OAUTH_CLIENT_SECRET`: optional unless Assignment Rules must read private Google Sheets rule/payout files. Use a Google Cloud OAuth client with application type `Desktop app`.
- `LUCAS_WORKING_SHEETS_DIR`: optional preconfigured working-sheets folder. Users can also set this in-app with `Working Folder`.
- `LUCAS_PIPELINE_DIR`: legacy optional preconfigured sheet root for setups that keep the default folder names under one parent.

The selected working folder and derived sheet root are saved in `lucas_settings.json`, which is local-only and ignored by git.

The launcher order is:

1. Use `.venv\Scripts\pythonw.exe` or `.venv\Scripts\python.exe` when present.
2. Fall back to `pythonw.exe` on PATH.
3. Show a message if Python is missing.

## Sheet Folders

The selected working folder is used directly. Its parent contains:

- `WORKING SHEETS`
- `INCOMING SHEETS`
- `RECEIVED SHEETS`

Sheet marker data is stored in `sheet_markers.json` inside the configured sheet root.

Home supports sheet markers for `Paid`, `Tracking Number`, `All Received`, and `Assigned Person`.

Sheet movement rules:

- Marking a Working sheet as `Paid` moves it to `INCOMING SHEETS`.
- Marking any Working or Incoming sheet as `All Received` moves it to `RECEIVED SHEETS`.
- Home has a `Received` tab. Select a received sheet, open `Edit Markers`, uncheck `All Received`, and save to move it back to `INCOMING SHEETS`.
- Fully received sheets are also moved to `RECEIVED SHEETS` automatically after receive marking when all rows have been received.

## Assignment Company Recommendations

Assignment supports local company recommendation config through `assignment_companies.json` (ignored by git; example file is `assignment_companies.example.json`). The Assignment tab has an `Assignment Rules` button that opens a L.U.C.A.S-styled local manager for creating companies plus their rule and payout sources.

For each company, configure:

- `name`
- `active` (optional; defaults to active. Inactive companies are skipped by recommendations.)
- `rules` or `rules_source`
- `payout` or `payout_source`
- optional `accept_all` and `rate` fallback

The app reads local `.txt`, `.md`, `.json`, `.csv`, `.xlsx`, and `.xlsm` files, including synced Google Drive paths such as `G:\My Drive\...`. The manager exposes three rule source modes: manual rules, Google Keep local file, and Google Sheets local file. Google Keep means a local synced/exported text/markdown file. Google Sheets can be a local `.xlsx`/`.csv` or a native `.gsheet` shortcut. When `.gsheet` is selected, L.U.C.A.S stores the Google Sheet URL plus a local cache path and reads the live workbook through the Google Sheets API using a desktop OAuth token cached in `lucas_google_sheets_token.json` (ignored by git). Saved Google Sheet URL sources refresh from the live Google Sheet each time assignment rules load; the local workbook path is retained as fallback only. The shortcut reader supports common metadata (`url`, `doc_id`, `resource_id`). If Google Drive exposes the shortcut as an unreadable placeholder, the manager asks for the Google Sheet URL and reads that URL through the authenticated connection. `Link Payouts to Same File` stores the payout source as the same rules file with `sheet_name: "Payouts"`, so local workbooks and authenticated Google Sheets can use a dedicated `Payouts` tab for rates. Arena Club-style payout tabs with `CATEGORY`, `VALUE RANGE`, and `YOUR PAYOUT %` are parsed as category-aware tiers; category matching ports the Sheet Filtering Tool's rule matching concepts for sports, known players, GOATS, and insert names such as Kaboom/Downtown/Manga/Color Blast.

The built-in manager writes manual custom-filter-style JSON under `<pipeline root>\ASSIGNMENT RULES`, using the Sheet Filtering Tool concepts of sports, value ranges, PSA/BGS/SGC/CGC grade allow/ranges, block rules, and payout tiers. It can also link an external local rule file and a local payout file to the same company. This is copied into L.U.C.A.S as standalone Python/Tk code; runtime does not depend on the Chrome extension folder.

Recommendation value uses Card Ladder comps average first, then Card Ladder value. A company must accept the card by rules and have a matching payout tier/rate; the highest estimated payout wins.

## Card Ladder

Card Ladder automation requires Chrome, the unpacked extension, and a logged-in Card Ladder account.

Load the extension from `cardladder-autocomp\extension` using `chrome://extensions` with Developer Mode enabled. The L.U.C.A.S app starts the local bridge automatically when the app opens.

The bridge binds to the first open port from `8765` through `8772`. The extension manifest includes host permissions for that full local range. The Comp tab's `Stop Run` button sets a bridge cancellation flag; the extension checks that flag between rows.

Comping behavior notes:

- `Empty Comps Only` skips rows that already have comp data or intentional terminal statuses like `invalid_cert`.
- `Recomp All` queues all eligible rows.
- Card Ladder no-comp/no-results paths should still capture and write the Card Ladder profile/card description when the page provides one.
- Invalid certs clear stale Card Ladder/card data and mark the row `Card Ladder invalid cert`.
- BGS/Beckett OCR now rejects subgrades such as Centering, Corners, Edges, Surface, Auto, and Autograph as the slab grade. If only subgrades are readable, grade should be blank.
- Date weighted comping uses recent comp behavior already implemented in `comp_engine\bridge_server.py`; be careful changing comp math because accuracy regressions were a major recent concern.

## Recent Commits

- `0814ff1 Configure pipeline from working folder`
- `5f7806e Rename review workflow to assignment`
- `754086d Allow received sheets to return to incoming`
- `bea5d8f Keep Card Ladder titles when comps are missing`
- `a1a5d1c Guard BGS OCR against subgrades`
- `5e0dda4 Harden release setup and Card Ladder bridge`

## Verification Notes

Use the Codex bundled Python for syntax-only checks when needed:

`C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile app.py`

The bundled Codex Python can import/compile the app but cannot create the Tk window because its Tcl/Tk files are incomplete. Full GUI smoke tests should use the project `.venv` or a normal python.org Windows Python install with Tkinter.

Useful checks used recently:

- `python -m py_compile app.py`
- `node --check cardladder-autocomp\extension\content.js`
- Temp-folder helper tests for sheet movement and working-folder normalization.

## Notes For Future Work

- Keep machine-specific folders out of source. Use `.env`, `lucas_settings.json`, or the `Working Folder` button.
- Do not commit `.env`, `.venv`, `work`, `outputs`, or generated debug screenshots.
- Rows with `invalid_cert` are intentional non-empty statuses and should be skipped by empty-comps-only comp runs.
- The Card Ladder extension is plain unpacked Chrome extension code. There is no Node/npm build step for normal install.
- Be conservative with Card Ladder comp extraction. The current mechanism was repaired to avoid stale-page bleed and missed/no-comp description loss; prefer targeted fixes over rewrites.
