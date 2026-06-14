# L.U.C.A.S

Lot Upload, Comping & Assignment System.

L.U.C.A.S is a desktop workflow app for intake, receiving, working-sheet tracking, Card Ladder comping, and assignment routing.

For a click-by-click setup walkthrough for a brand-new user, start with [FIRST_RUN_SETUP.md](FIRST_RUN_SETUP.md).

## Install

1. Install Google Chrome.
2. Download this project or clone the repository.
3. Double-click `install_dependencies.bat`. If Python 3.11 or newer is missing, the installer tries to install Python 3.11 with Windows Package Manager (`winget`) before creating the app environment.
4. Open `.env`, which the installer creates from `.env.example`.
5. Add `GOOGLE_API_KEY`, `GOOGLE_SHEETS_OAUTH_CLIENT_ID`, `GOOGLE_SHEETS_OAUTH_CLIENT_SECRET`, and `LUCAS_WORKING_SHEETS_DIR` in `.env`.
6. Complete Google billing, payment method, spend cap, and budget alert setup from `FIRST_RUN_SETUP.md`.
7. Launch with `Run Card Pipeline.vbs` for the no-console app, or `Run Card Pipeline.bat` if you want to see console output.

If automatic Python install is not available on that computer, install Python 3.11 or newer from python.org, include Tcl/Tk support, and check `Add python.exe to PATH`, then run `install_dependencies.bat` again.

## Local Configuration

`.env` is intentionally local and should not be committed. A typical setup looks like:

```env
GOOGLE_API_KEY=your_google_ai_studio_key
LUCAS_WORKING_SHEETS_DIR=G:\My Drive\CARD_PIPELINE\WORKING SHEETS
GOOGLE_SHEETS_OAUTH_CLIENT_ID=your_desktop_oauth_client_id
GOOGLE_SHEETS_OAUTH_CLIENT_SECRET=your_desktop_oauth_client_secret
```

`GOOGLE_API_KEY` can be created or copied from Google AI Studio's API key page. `LUCAS_WORKING_SHEETS_DIR` should point at the user's `WORKING SHEETS` folder. `LUCAS_PIPELINE_DIR` is still supported for older setups that point at the parent pipeline folder. `GOOGLE_SHEETS_OAUTH_CLIENT_ID` and `GOOGLE_SHEETS_OAUTH_CLIENT_SECRET` should come from a Google Cloud OAuth client with application type `Desktop app`.

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

Use the `Create` tab for all card entry.

- `Barcode Scanner`: enter scanning station mode, then scan certs continuously.
- `Photo OCR`: add photos or a folder, scan them inside this app, and append detected card rows.
- `Existing Spreadsheet`: load a simple workbook where column 1 is cert number, column 2 is card description, and column 3 is purchase price.

Enter a title, then click `Save as Working Sheet`. Working sheets are saved to the configured `WORKING SHEETS` folder.

## Comping

Use the `Comp` tab for Card Ladder comping. Select a saved sheet, choose the comp method and run scope, then click `Run All Comps`.

The app stores Card Ladder value, comps, assignment, payout, and status in the active workbook output. Rows marked `invalid_cert` are skipped by empty-comps-only runs.

Use `Stop Run` to request cancellation of an active Card Ladder run. The Chrome extension checks this signal between rows and stops before starting the next card.

## Assignment

Use the `Receive` tab for receiving cards and source matching. Receive rows are checked against sheets in `INCOMING SHEETS`, marked received when matched, and can be added to weekly company sheets when `Company Pile` is checked.

Use the `Assignment` tab for pure assignment review and fallback assignment work. Assignment can load received sheets and calculate or recalculate `Best Company` and `Est. Payout`.

Assignment can calculate `Best Company` and `Est. Payout` from the Card Ladder comps average, falling back to Card Ladder value when comps are blank. Individual companies can be configured to require Card Ladder value instead; when that is selected, the company is ignored if the row has no Card Ladder value. Click `Assignment Rules` to create companies, acceptance rule files, and payout files. L.U.C.A.S writes manual files under the configured pipeline folder and updates local-only `assignment_companies.json`. Companies can be toggled Active or Inactive in the rules manager; inactive companies are ignored when recommendations are calculated. If no company can take a priced row, `Best Company` shows `NOBODY TAKES`.

Supported local source files include `.txt`, `.md`, `.json`, `.csv`, `.xlsx`, and `.xlsm`. Files in synced Google Drive folders work directly, for example:

```json
{
  "name": "Arena Club",
  "rules": "G:\\My Drive\\CARD_PIPELINE\\ASSIGNMENT RULES\\arena-club-rules.xlsx",
  "payout": "G:\\My Drive\\CARD_PIPELINE\\ASSIGNMENT RULES\\arena-club-payout.xlsx"
}
```

The Assignment Rules manager supports three rule sources: manual rules, a local Google Keep export/text file, or a local synced Google Sheets/workbook file from Google Drive. Payouts can be manual tiers, a local payout file, or the same rules workbook when `Link Payouts to Same File` is selected and that workbook has a `Payouts` tab. `Payouts` tabs may use `CATEGORY`, `VALUE RANGE`, and `YOUR PAYOUT %`; L.U.C.A.S matches category by player, sport, or insert name and multiplies the card's comp value by the matched payout percentage. When a native Google Sheets shortcut (`.gsheet`) is selected, L.U.C.A.S stores the sheet URL and reads it through the Google Sheets API, matching the authenticated approach used by the Sheet Filtering Tool extension. Click `Connect Google` once in Assignment Rules to create the local token cache. If Google Drive exposes the shortcut as an unreadable placeholder, the app asks for the Google Sheet URL and then reads that same live sheet through the authenticated connection. Saved Google Sheet URL sources are refreshed from Google Sheets when L.U.C.A.S opens and when assignment rules load, with the latest local XLSX cache used as the fallback copy. The built-in manager uses the same basic custom-filter shape as the Sheet Filtering Tool: categories, value ranges, grade-company allow/block settings, block rules, and payout tiers.

## Payouts And Profit

Use `Payouts/Tabs` to track active balances by assigned person and mark person-level balances paid.

Use `Profit` to review sold cards and sold sheets. The Profit tab can filter by assigned person, shows a daily profit line chart, and can toggle between individual sold-card rows and grouped sold-sheet summaries.

## Tests

Run the committed offline test suite with:

```bat
python -m unittest discover -s tests -v
```

The tests cover shared-folder locks, atomic JSON writes, marker merging, Google Sheet cache export/discovery, company-sheet append deduping, assignment recommendation behavior, unassigned-player capture, photo OCR recovery behavior, and profit ledger/person grouping.

## Included Photo Tool

The photo OCR helper used by L.U.C.A.S is bundled in `photo_tool`. It uses the same project `.env`, so there is no separate photo-tool setup or private machine path required.

## Troubleshooting

If the app does not open, run `Run Card Pipeline.bat` instead of the `.vbs` launcher so Windows keeps the console visible. The most common cause is Python not being installed, not being on PATH, or missing Tcl/Tk support. Run `install_dependencies.bat` first; if automatic Python install is unavailable, install Python from python.org, include Tcl/Tk support, make sure `Add python.exe to PATH` is checked, then run `install_dependencies.bat` again.

The app launcher uses `.venv` first. If `.venv` is missing, `install_dependencies.bat` recreates it and installs the packages from `requirements.txt`.
