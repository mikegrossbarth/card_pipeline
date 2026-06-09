# Card Ladder Auto-Comp Helper

This folder contains the Chrome extension and optional workbook utility scripts used by L.U.C.A.S for Card Ladder comping.

Most users should run comps from the L.U.C.A.S `Comp` tab. The app starts the local bridge and sends queued rows to the extension.

## Chrome Setup

1. Open Chrome and go to `chrome://extensions`.
2. Turn on `Developer mode`.
3. Click `Load unpacked`.
4. Select this folder: `cardladder-autocomp\extension`.
5. Log into Card Ladder in the same Chrome profile.

Card Ladder requires an active account session. If Chrome is not logged in, the extension can load but the run will not complete.

The main L.U.C.A.S app uses the project `.env` for OCR fallback. The Card Ladder extension itself does not need the Google API key, but screenshot OCR fallback in the app does.

## Optional CLI Utilities

The scripts in `src` are kept for manual queue/result workflows. They require explicit workbook paths:

```powershell
node cardladder-autocomp\src\prepare-cardladder-queue.mjs --workbook "C:\path\to\workbook.xlsx" --sheet "Sheet1"
node cardladder-autocomp\src\apply-cardladder-results.mjs --workbook "C:\path\to\workbook.xlsx" --sheet "Sheet1" --results "C:\path\to\cardladder-results.json"
```

Generated files are written to the project `outputs` folder unless `--output` is supplied.

## Files

- `src\prepare-cardladder-queue.mjs`: creates a lookup queue from a workbook.
- `src\apply-cardladder-results.mjs`: writes Card Ladder results into an output workbook copy.
- `extension\background.js`: opens and controls the Card Ladder run window.
- `extension\content.js`: interacts with Card Ladder pages and reads values/comps.
- `extension\popup.*`: provides manual queue loading, run status, and result download tools.
