# Card Ladder Auto-Comp

Chrome-extension helper for filling a workbook's `Value` column with Card Ladder values by certification number.

This follows the same style as the UPS Incoming Package Tracker:

- normal Chrome opens the site
- the extension presses through the real web UI
- helper scripts prepare input and apply output
- no Playwright browser automation is used

## Current target workbook

`C:\Users\User\Downloads\Blez x mikey MASTER SHEET.xlsx`

Target tab:

`612026`

## Step 1: Prepare the lookup queue

From the seller-determination workspace:

```powershell
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' cardladder-autocomp\src\prepare-cardladder-queue.mjs
```

This creates:

`C:\Users\User\Documents\Codex\2026-06-01\seller-determination\outputs\cardladder-queue.json`

Current queue status:

- blank `Value` rows: `49`
- runnable rows: `49`
- skipped rows: `0`

## Step 2: Load the Chrome extension

Load this folder as an unpacked Chrome extension:

`C:\Users\User\Documents\Codex\2026-06-01\seller-determination\cardladder-autocomp\extension`

Then open the extension popup.

## Step 3: Run Card Ladder

1. In the popup, choose `cardladder-queue.json`.
2. Click `Load Queue`.
3. Click `Run Window`.
4. The extension opens Card Ladder Sales History in normal Chrome and presses through the queue.
5. Click `Download Results` when finished.

Save the results as:

`cardladder-results.json`

## Step 4: Apply results to the workbook copy

```powershell
& 'C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe' cardladder-autocomp\src\apply-cardladder-results.mjs --results "C:\path\to\cardladder-results.json"
```

Default output workbook:

`C:\Users\User\Documents\Codex\2026-06-01\seller-determination\outputs\Blez x mikey MASTER SHEET - cardladder values.xlsx`

The original workbook is not overwritten.

## Files

- `src\prepare-cardladder-queue.mjs`: creates the lookup queue from the workbook.
- `src\apply-cardladder-results.mjs`: writes Card Ladder results into an output workbook copy.
- `extension\background.js`: opens the Card Ladder window and controls the run.
- `extension\content.js`: presses buttons, selects grader, enters cert number, and reads value.
- `extension\popup.*`: loads queues, starts runs, shows status, and downloads results.
