# L.U.C.A.S

Lot Upload, Comping & Assignment System.

Combined intake, receiving, sheet tracking, and comping desktop app.

## Setup

Download or clone the repo, then launch the app from the project folder. On first run, click `Folders` in the top-right header and choose the folder where L.U.C.A.S should store sheet data. The app creates and uses these subfolders:

- `WORKING SHEETS`
- `INCOMING SHEETS`
- `RECEIVED SHEETS`

The chosen folder is saved locally in `lucas_settings.json`, which is intentionally not committed. If no folder has been selected and `G:\My Drive\CARD_PIPELINE` exists, the app uses that as the default; otherwise it falls back to a local `CARD_PIPELINE` folder inside the project.

## Input Modes

Use the `Intake` tab for all card entry.

- `Barcode Scanner`: enter scanning station mode, then scan certs continuously. Each scan appends the next row.
- `Photo OCR`: add photos or a folder, scan them inside this app, and append detected card rows.
- `Existing Spreadsheet`: load a simple workbook where:
  - Column 1 = cert number
  - Column 2 = card description
  - Column 3 = purchase price

Enter a title such as `mikey x blez 6/2/26`, then click `Save as Working Sheet`.
After the working sheet is saved, the Intake rows clear so the next lot can begin.

Working sheets are saved to the configured `WORKING SHEETS` folder.

## Comping

Use the `Comp` tab for all comping controls. The left side lists active working sheets from the working sheets folder. Select a saved sheet, then use the buttons below the sheet list to load or refresh sheets. The comp table is editable like the Intake table.

`Refresh Sheets` rescans the L.U.C.A.S folders and refreshes the active sheet list.

After a working sheet is loaded, use the bottom-right comp controls to choose a comp method and click `Run All Comps`. If a row has no card description and Card Ladder returns a profile title, grader, and grade, the app fills the `Card` field as `Description Grader Grade`.

## Review

Use the `Review` tab for receiving and source matching.

- `Automatic Review`: choose barcode scanning or photo OCR, then receive cards from that input mode.
- `Manual Review`: click the `+` row at the bottom of the Review table to add rows, then type directly into the table.

Review rows are independent from Intake and Comp. Each reviewed card is checked against incoming sheets in the configured `INCOMING SHEETS` folder.

When a cert is found, the `Sheet Source` column is filled with the matching incoming sheet name and the row is marked `Received`.
When no incoming sheet match is found, `Sheet Source` is set to `NO SHEET FOUND` and the row is highlighted red.
`Refresh Incoming Sheets` and `Clear Review Rows` live at the bottom of the Review tab.

The included Card Ladder extension folder is:

`cardladder-autocomp\extension`

## Launch

Double-click `Run Card Pipeline.vbs` for the no-console app.
