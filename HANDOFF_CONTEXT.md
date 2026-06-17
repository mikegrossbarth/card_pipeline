# L.U.C.A.S Windows Handoff Context

L.U.C.A.S means Lot Upload, Comping & Assignment System.

## Current Snapshot

- Repo: `C:\Users\User\Documents\Codex\2026-06-04\card_pipeline`
- Remote: `https://github.com/mikegrossbarth/card_pipeline.git`
- Branches kept current: `main` and `master`
- Latest commit at handoff time: this recovery handoff commit
- Current visible tabs: `Home`, `Create`, `Comp`, `Receive`, `Assignment`, `Payouts/Tabs`, `Profit`
- Setup walkthrough: `FIRST_RUN_SETUP.md`

The old visible `Review` workflow was split into `Receive` and `Assignment`. Many internal names still use `review_*`; that is intentional legacy naming to avoid risky churn.

## Latest Completed Work

- Arena Club assignment sheets now support both the old sheet format and the newer Arena workbook/sheet format.
- Rules handle broad labels like `Pre-1989` and `ALL Grades`.
- Obvious duplicated-player parse mistakes such as `Tom Tom Brady` are treated as the intended player.
- Tiger Woods is recognized as golf.
- CY-style sheets can be ingested without confusing `Estimate` with `Purchase`.
- `CY Estimate` and `CY Confidence` are preserved in imported sheets, working sheets, output sheets, company sheets, and display tables.
- Assignment rules can choose their value source per company:
  - `Comps`
  - `Card Ladder value`
  - `CY Estimate`
- Windows does not run CourtYard/CY lookup automation. It only reads CY values that already exist in sheets.
- Mac keeps CourtYard comp lookup as a Mac-only ability in the separate Mac repo.
- Company sheets now use one workbook per company with weekly tabs:
  - `COMPANY SHEETS\<Company>\<Company>.xlsx`
  - weekly tab name: `Week of YYYY-MM-DD`
- Old legacy weekly company files remain readable for profit backfill.
- Sunday at midnight rolls forward to the next Monday's company-sheet tab.
- Received sheets archive after two weeks only if fully received and marked paid.
- Home right-click delete for incoming/working/received sheets includes a confirmation prompt.
- Comping no longer recalculates assignments on load. Assignment recalculates only for rows involved in the user-chosen comp run or when explicitly needed.
- Create now has `Manual Entry` mode. Use the `+ Add row` line in the Create table, then double-click cells to edit. The extra toolbar button was removed.
- Recovery note, 2026-06-17: Card Ladder was rolled back to the last working comping flow after the later DOM-sweep/grader-verification changes broke real usage. Do not reapply those changes without live browser QA against actual Card Ladder cert searches.

## Platform Split

Windows repo intentionally has no CourtYard automation:

- no `comp_engine/cy_automation`
- no `lookup_cy_buy_price`
- no `Card Ladder + CY` comp-source selector
- no CY lookup calls during comping

Windows can still read and use `CY Estimate`/`CY Confidence` from imported sheets for assignment logic.

## Project Layout

- `app.py`: main Tkinter desktop app and UI workflows.
- `assignment_engine.py`: company rules, payout parsing, category/player matching, and recommendation logic.
- `assignment_config_ui.py`: Assignment Rules popup.
- `intake_io.py`: spreadsheet import/export, receive marking, company-sheet append, weekly tabs, archive/profit extraction helpers.
- `shared_state.py`: atomic JSON writes and shared-folder locks.
- `google_sheets_import.py`: OAuth and Google Sheets export/read helpers.
- `comp_engine`: Card Ladder bridge, workbook row model, comp strategy, screenshot OCR fallback.
- `photo_tool`: photo OCR helper used by Create and Receive.
- `cardladder-autocomp\extension`: unpacked Chrome extension for Card Ladder automation.
- `tests\test_shared_workflows.py`: offline regression suite.

## Shared Pipeline Folder

The user chooses the actual `WORKING SHEETS` folder with the `Working Folder` button. L.U.C.A.S uses that folder's parent as the pipeline root.

Expected shared root:

```text
CARD_PIPELINE
  WORKING SHEETS
  INCOMING SHEETS
  RECEIVED SHEETS
  ARCHIVED SHEETS
  COMPANY SHEETS
  ASSIGNMENT RULES
  sheet_markers.json
  weekly_company_sheets.json
  profit_ledger.json
  unassigned_players.json
  assignment_player_overrides.json
  .locks
```

For teams, every user can point their local app at the same synced Google Drive pipeline folder. Each user still keeps their own app folder, `.env`, OAuth token, local app settings, and Card Ladder extension install.

## Local-Only Files

Do not commit:

- `.env`
- `.venv`
- `lucas_settings.json`
- `lucas_user_identity.json`
- `lucas_google_sheets_token.json`
- `assignment_companies.json`
- generated debug screenshots/logs
- generated `work/` or `outputs/` content

## Workflow Notes

### Home

Home lists `Incoming`, `Working`, and `Received` sheets. It supports right-click delete with confirmation. Received sheets move to `ARCHIVED SHEETS` only after they are fully received, marked paid, and at least two weeks old.

### Create

Create supports:

- `Barcode Scanner`
- `Manual Entry`
- `Photo OCR`
- `Existing Spreadsheet`

Manual Entry uses the `+ Add row` line in the Create table. Double-click table cells to edit cert, grader, card, purchase, Card Ladder, comps, CY Estimate, or CY Confidence.

### Comp

Comp runs Card Ladder through the local bridge and Chrome extension. Best-company assignment recalculates for rows touched by the current comp run, not every row merely because a sheet loaded.

### Receive

Receive marks cards received in source sheets. If `Company Pile` is checked and the row has a real Best Company, marking received appends that card to the current weekly tab in the company workbook. `NOBODY TAKES` rows are not appended.

### Assignment

Assignment can recalculate best company and payout using the configured value source. Failed valued assignments are recorded in `unassigned_players.json`.

### Payouts/Tabs

Tracks active balances by assigned person and can mark matching person sheets paid.

### Profit

Profit reads `profit_ledger.json`, current company workbook tabs, and legacy weekly company files. It includes person filters, daily profit chart, `Sold Cards`, and grouped `Sold Sheets`.

## Assignment Rules

Assignment companies live in local-only `assignment_companies.json`.

Important behavior:

- Companies can choose `Comps`, `Card Ladder value`, or `CY Estimate` as assignment value source.
- If a company requires Card Ladder value and the row has none, that company is ignored.
- If a company requires CY Estimate and the row has none, that company is ignored.
- Default value source remains comps first, then Card Ladder value, then CY Estimate.
- A company must accept the card and have a matching payout tier/rate.
- Highest estimated payout wins.
- If no company can take the card, Best Company becomes `NOBODY TAKES`.

## Card Ladder

Chrome extension folder:

```text
cardladder-autocomp\extension
```

Current comping flow uses the normal Chrome profile/session with the unpacked extension loaded. The app queues rows through the local desktop bridge; the extension checks in, opens Card Ladder Sales History, selects the requested grader with the restored simple DOM click flow, and submits cert searches. No dedicated Chrome profile or Chrome debugger permission is used.

The desktop bridge binds to the first available port from `8765` to `8772`. The extension manifest grants access to the same local range.

Common gotchas:

- User must be logged into Card Ladder in the Chrome profile where the unpacked extension is loaded.
- Old unpacked extension versions should be removed or disabled.
- Current restored extension/background version: `2026-06-17-simple-grader-flow-v12`.
- Current restored content-script version: `2026-06-17-simple-grader-flow-v12`.
- App warns if the extension version seen by the bridge is stale.
- No-results pages preserve the Card Ladder title when available.
- Old partial Card Ladder captures request extension reload/manual review.

## Tests And Verification

Recent verification:

```text
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m py_compile app.py
C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe -m unittest tests.test_shared_workflows -v
```

Last full Windows result after recovery: `40 tests OK`.

Useful broader sanity checks:

```bat
python -m unittest discover -s tests -v
python -m compileall -q .
python -c "import app; root = app.CardPipelineApp(); root.update_idletasks(); root.destroy(); print('app startup ok')"
```

## Current Git State At Handoff

- `main` and `master` should both point at this recovery handoff commit.
- Working tree was clean after this handoff file update was committed.
