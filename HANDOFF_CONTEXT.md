# L.U.C.A.S Handoff Context

L.U.C.A.S means Lot Upload, Comping & Assignment System.

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
- `LUCAS_PIPELINE_DIR`: optional preconfigured sheet root. Users can also set this in-app with `Folders`.

The selected sheet root is saved in `lucas_settings.json`, which is local-only and ignored by git.

The launcher order is:

1. Use `.venv\Scripts\pythonw.exe` or `.venv\Scripts\python.exe` when present.
2. Fall back to `pythonw.exe` on PATH.
3. Show a message if Python is missing.

## Sheet Folders

The configured sheet root contains:

- `WORKING SHEETS`
- `INCOMING SHEETS`
- `RECEIVED SHEETS`

Sheet marker data is stored in `sheet_markers.json` inside the configured sheet root.

## Card Ladder

Card Ladder automation requires Chrome, the unpacked extension, and a logged-in Card Ladder account.

Load the extension from `cardladder-autocomp\extension` using `chrome://extensions` with Developer Mode enabled. The L.U.C.A.S app starts the local bridge automatically when the app opens.

The bridge binds to the first open port from `8765` through `8772`. The extension manifest includes host permissions for that full local range. The Comp tab's `Stop Run` button sets a bridge cancellation flag; the extension checks that flag between rows.

## Notes For Future Work

- Keep machine-specific folders out of source. Use `.env`, `lucas_settings.json`, or the `Folders` button.
- Do not commit `.env`, `.venv`, `work`, `outputs`, or generated debug screenshots.
- Rows with `invalid_cert` are intentional non-empty statuses and should be skipped by empty-comps-only comp runs.
- The Card Ladder extension is plain unpacked Chrome extension code. There is no Node/npm build step for normal install.
