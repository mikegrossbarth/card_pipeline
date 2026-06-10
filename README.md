# L.U.C.A.S

Lot Upload, Comping & Assignment System.

L.U.C.A.S is a desktop workflow app for intake, receiving, working-sheet tracking, Card Ladder comping, and assignment routing.

## Install

1. Install Python 3.11 or newer and Google Chrome. When installing Python, check `Add python.exe to PATH`.
2. Download this project or clone the repository.
3. Double-click `install_dependencies.bat`.
4. Open `.env`, which the installer creates from `.env.example`.
5. Add `GOOGLE_API_KEY` in `.env` if you use Photo OCR or Card Ladder screenshot OCR fallback.
6. Launch with `Run Card Pipeline.vbs` for the no-console app, or `Run Card Pipeline.bat` if you want to see console output.

## Local Configuration

`.env` is intentionally local and should not be committed. A typical setup looks like:

```env
GOOGLE_API_KEY=your_google_ai_studio_key
LUCAS_WORKING_SHEETS_DIR=G:\My Drive\CARD_PIPELINE\WORKING SHEETS
```

`GOOGLE_API_KEY` can be created or copied from Google AI Studio's API key page. `LUCAS_WORKING_SHEETS_DIR` is optional because the same folder can be selected with the in-app `Working Folder` button. `LUCAS_PIPELINE_DIR` is still supported for older setups that point at the parent pipeline folder.

## Data Folder

On first run, click `Working Folder` in the top-right header and choose your working-sheets folder. The app uses that folder for working sheets and creates sibling folders/files beside it:

- `WORKING SHEETS`
- `INCOMING SHEETS`
- `RECEIVED SHEETS`

The chosen working folder is saved locally in `lucas_settings.json`, which is intentionally not committed. To preconfigure this for another user, set `LUCAS_WORKING_SHEETS_DIR` in `.env`.

## Card Ladder Extension

Card Ladder comping requires a Card Ladder account and an active Chrome login session.

1. Open Chrome and go to `chrome://extensions`.
2. Turn on `Developer mode`.
3. Click `Load unpacked`.
4. Select `cardladder-autocomp\extension` from this project.
5. Log into Card Ladder in Chrome before running comps.

The app starts the local Card Ladder bridge automatically when L.U.C.A.S opens.

## Input Modes

Use the `Intake` tab for all card entry.

- `Barcode Scanner`: enter scanning station mode, then scan certs continuously.
- `Photo OCR`: add photos or a folder, scan them inside this app, and append detected card rows.
- `Existing Spreadsheet`: load a simple workbook where column 1 is cert number, column 2 is card description, and column 3 is purchase price.

Enter a title, then click `Save as Working Sheet`. Working sheets are saved to the configured `WORKING SHEETS` folder.

## Comping

Use the `Comp` tab for Card Ladder comping. Select a saved sheet, choose the comp method and run scope, then click `Run All Comps`.

The app stores Card Ladder value, comps, confidence, and status in the active workbook output. Rows marked `invalid_cert` are skipped by empty-comps-only runs.

Use `Stop Run` to request cancellation of an active Card Ladder run. The Chrome extension checks this signal between rows and stops before starting the next card.

## Assignment

Use the `Assignment` tab for receiving and source matching. Assignment rows are checked against sheets in `INCOMING SHEETS`, marked received when matched, and can be loaded from `RECEIVED SHEETS` for follow-up assignment work.

Assignment can calculate `Best Company` and `Est. Payout` from the Card Ladder comps average, falling back to Card Ladder value when comps are blank. To enable this, copy `assignment_companies.example.json` to local-only `assignment_companies.json` and point each company at a rules file and payout file.

Supported local source files include `.txt`, `.md`, `.json`, `.csv`, `.xlsx`, and `.xlsm`. Files in synced Google Drive folders work directly, for example:

```json
{
  "name": "Arena Club",
  "rules": "G:\\My Drive\\CARD_PIPELINE\\ASSIGNMENT RULES\\arena-club-rules.xlsx",
  "payout": "G:\\My Drive\\CARD_PIPELINE\\ASSIGNMENT RULES\\arena-club-payout.xlsx"
}
```

Native Google Sheets shortcuts (`.gsheet`) are recognized and converted to CSV export URLs when the sheet is accessible to the app. Private Google Keep notes do not expose local file contents to a desktop Python app, so Keep-backed rules should be exported or copied to a synced local text file for now. After editing source files, click `Reload Assignment Rules` in the Assignment tab.

## Included Photo Tool

The photo OCR helper used by L.U.C.A.S is bundled in `photo_tool`. It uses the same project `.env`, so there is no separate photo-tool setup or private machine path required.

## Troubleshooting

If the app does not open, run `Run Card Pipeline.bat` instead of the `.vbs` launcher so Windows keeps the console visible. The most common cause is Python not being installed or not being on PATH. Reinstall Python from python.org, make sure `Add python.exe to PATH` is checked, then run `install_dependencies.bat` again.

The app launcher uses `.venv` first. If `.venv` is missing, `install_dependencies.bat` recreates it and installs the packages from `requirements.txt`.
