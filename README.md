# L.U.C.A.S

Lot Upload, Comping & Assignment System.

L.U.C.A.S is a desktop workflow app for intake, receiving, working-sheet tracking, Card Ladder comping, and review routing.

## Install

1. Install Python 3.11 or newer and Google Chrome. Install Node.js too if you plan to use the optional Card Ladder CLI scripts.
2. Download this project or clone the repository.
3. Double-click `install_dependencies.bat`.
4. Open `.env`, which the installer creates from `.env.example`.
5. Add `GOOGLE_API_KEY` in `.env` if you use Photo OCR or Card Ladder screenshot OCR fallback.
6. Launch with `Run Card Pipeline.vbs` for the no-console app, or `Run Card Pipeline.bat` if you want to see console output.

## Data Folder

On first run, click `Folders` in the top-right header and choose the folder where L.U.C.A.S should store sheet data. The app creates and uses:

- `WORKING SHEETS`
- `INCOMING SHEETS`
- `RECEIVED SHEETS`

The chosen folder is saved locally in `lucas_settings.json`, which is intentionally not committed. To preconfigure this for another user, set `LUCAS_PIPELINE_DIR` in `.env`.

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

## Review

Use the `Review` tab for receiving and source matching. Reviewed cards are checked against sheets in `INCOMING SHEETS`, marked received when matched, and can be loaded from `RECEIVED SHEETS` for follow-up review.

## Included Photo Tool

The photo OCR helper used by L.U.C.A.S is bundled in `photo_tool`. It uses the same project `.env`, so there is no separate photo-tool setup or private machine path required.
