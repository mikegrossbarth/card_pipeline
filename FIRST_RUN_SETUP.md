# L.U.C.A.S First Run Setup

This guide assumes you are setting up L.U.C.A.S on a Windows computer for the first time and do not already know what the app needs.

L.U.C.A.S stands for Lot Upload, Comping & Assignment System. It helps you create card sheets, comp cards through Card Ladder, receive cards, assign cards to buying companies, and track payouts.

## Quick Answer

For a complete L.U.C.A.S setup, the computer needs:

- Google Chrome
- the L.U.C.A.S project folder
- Python 3.11 or newer, installed automatically by `install_dependencies.bat` when possible
- a local data folder with `WORKING SHEETS`, `INCOMING SHEETS`, and `RECEIVED SHEETS`
- a Card Ladder account and Chrome extension setup for comping
- a Google AI Studio API key for Photo OCR and screenshot OCR fallback
- Google OAuth credentials for Google Sheets rules or payout sheets
- Google Drive for desktop
- company assignment rules and payout files configured inside the app

This guide treats the full workflow as required. Setup is not complete until every section below is done.

## What Each Requirement Is For

| Requirement | Needed for | Required for complete setup? |
| --- | --- | --- |
| Google Chrome | Card Ladder automation and extension | Yes |
| Python 3.11+ | running the desktop app | Yes, but installer tries to install it |
| `.venv` dependencies | app libraries like spreadsheet and image support | Yes, created by installer |
| Working folder | saving and finding card sheets | Yes |
| Card Ladder account | comping cards with Card Ladder | Yes |
| Card Ladder Chrome extension | automated comp runs | Yes |
| `GOOGLE_API_KEY` | Photo OCR and Card Ladder screenshot OCR fallback | Yes |
| Google OAuth Client ID/Secret | reading Google Sheets rule/payout files | Yes |
| Google Drive for desktop | synced Drive folders and Google Sheets shortcuts | Yes |
| assignment companies | best company and estimated payout | Yes |

## Step 1: Get The App Folder

Put the L.U.C.A.S project folder somewhere normal on the computer, for example:

```text
C:\Users\YourName\Documents\card_pipeline
```

The folder should contain files like:

```text
app.py
install_dependencies.bat
Run Card Pipeline.vbs
Run Card Pipeline.bat
README.md
cardladder-autocomp
```

If you are using Git, clone the repository. If not, download and unzip the project folder.

## Step 2: Install Google Chrome

Install Google Chrome if it is not already installed.

Chrome is needed for Card Ladder comping because the app talks to a local Chrome extension.

## Step 3: Run The Installer

Double-click:

```text
install_dependencies.bat
```

The installer will:

1. look for Python 3.11 or newer
2. try to install Python 3.11 with Windows Package Manager if Python is missing
3. create `.venv`
4. install app dependencies
5. verify Tkinter is available
6. create `.env` from `.env.example` if `.env` does not exist

If Windows asks for permission during Python install, approve it.

If automatic Python install fails, install Python manually from python.org. During manual install, make sure:

- `Add python.exe to PATH` is checked
- Tcl/Tk support is included

Then run `install_dependencies.bat` again.

## Step 4: Create The Sheet Folders

Create a main folder for your pipeline data inside Google Drive for desktop.

Example:

```text
G:\My Drive\CARD_PIPELINE
```

Inside it, create:

```text
G:\My Drive\CARD_PIPELINE\WORKING SHEETS
G:\My Drive\CARD_PIPELINE\INCOMING SHEETS
G:\My Drive\CARD_PIPELINE\RECEIVED SHEETS
```

The app can create some folders as it works, but starting with these three makes setup clearer.

L.U.C.A.S will also use or create:

```text
G:\My Drive\CARD_PIPELINE\COMPANY SHEETS
G:\My Drive\CARD_PIPELINE\ASSIGNMENT RULES
G:\My Drive\CARD_PIPELINE\sheet_markers.json
```

## Step 5: Launch The App

For normal use, double-click:

```text
Run Card Pipeline.vbs
```

If the app does not open or you want to see error messages, double-click:

```text
Run Card Pipeline.bat
```

## Step 6: Choose The Working Folder

When L.U.C.A.S opens:

1. click `Working Folder` in the top-right area
2. choose your `WORKING SHEETS` folder
3. confirm the app sees your working sheets

Choose the folder named `WORKING SHEETS`, not the parent `CARD_PIPELINE` folder.

The app remembers this in:

```text
lucas_settings.json
```

That file is local to the computer and should not be committed to Git.

## Step 7: Configure `.env`

Open the `.env` file in the L.U.C.A.S project folder.

It starts as a copy of `.env.example`.

A typical full setup looks like:

```env
GOOGLE_API_KEY=your_google_ai_studio_key
GOOGLE_SHEETS_OAUTH_CLIENT_ID=your_desktop_oauth_client_id
GOOGLE_SHEETS_OAUTH_CLIENT_SECRET=your_desktop_oauth_client_secret
LUCAS_WORKING_SHEETS_DIR=G:\My Drive\CARD_PIPELINE\WORKING SHEETS
```

For a complete setup, fill in every value shown above.

Do not commit `.env` to Git.

## Step 8: Set Up Photo OCR And OCR Fallback

Photo OCR needs:

```env
GOOGLE_API_KEY=...
```

To get this key:

1. go to Google AI Studio
2. create or copy an API key
3. paste it into `.env`
4. save `.env`
5. restart L.U.C.A.S

This key is used for:

- scanning photos into card rows
- Card Ladder screenshot OCR fallback

If this key is missing, setup is incomplete. Photo OCR and Card Ladder screenshot OCR fallback will not work.

## Step 9: Set Up Card Ladder

Card Ladder comping needs:

- Google Chrome
- a Card Ladder account
- a logged-in Card Ladder session in Chrome
- the L.U.C.A.S Chrome extension loaded

To load the extension:

1. open Chrome
2. go to:

```text
chrome://extensions
```

3. turn on `Developer mode`
4. click `Load unpacked`
5. select this folder inside the L.U.C.A.S project:

```text
cardladder-autocomp\extension
```

6. open Card Ladder in Chrome
7. log in to Card Ladder

The desktop app starts the local Card Ladder bridge automatically when it opens. The extension talks to that local bridge.

If comping does not start, check:

- Chrome is open
- the extension is enabled
- you are logged into Card Ladder
- L.U.C.A.S is running
- the Comp tab says the Card Ladder bridge is running

## Step 10: Set Up Google Sheets Access

Google Sheets access is part of the complete setup because company rules and payout files may live in Google Sheets.

1. go to Google Cloud Console
2. create or choose a project
3. enable the Google Sheets API
4. create an OAuth Client ID
5. choose application type:

```text
Desktop app
```

6. copy the client ID and client secret into `.env`:

```env
GOOGLE_SHEETS_OAUTH_CLIENT_ID=...
GOOGLE_SHEETS_OAUTH_CLIENT_SECRET=...
```

7. save `.env`
8. restart L.U.C.A.S
9. open Assignment Rules
10. click `Connect Google`
11. sign in with the Google account that can access the sheets

The app creates:

```text
lucas_google_sheets_token.json
```

That token file is local and should not be committed to Git.

## Step 11: Set Up Google Drive For Desktop

Google Drive for desktop is required for the standard team setup because the pipeline folders and source files can live in synced Drive folders.

Once installed, Google Drive usually creates a drive like:

```text
G:\My Drive
```

You can put `CARD_PIPELINE` there.

Native Google Sheets files may appear as `.gsheet` shortcuts. If L.U.C.A.S cannot read a `.gsheet` directly as a local workbook, it will use the saved Google Sheet URL and Google OAuth setup to read the live sheet.

For the easiest rule and payout setup, use synced `.xlsx` or `.csv` files when possible.

## Step 12: Set Up Assignment Companies

Assignment recommendations need company rules and payout rates.

In L.U.C.A.S:

1. open the `Assignment` tab
2. click `Assignment Rules`
3. create a company
4. choose whether the company is active
5. choose a rule source
6. choose a payout source
7. save the company

Each company can use:

- manual rules
- local rules file
- Google Keep export/text file
- local workbook or CSV
- Google Sheet through OAuth
- payout tiers inside the same workbook on a `Payouts` tab

The app saves company setup locally in:

```text
assignment_companies.json
```

That file is local and should not be committed unless you intentionally want to share it.

## Step 13: Check The Full Workflow

After setup, test the app in this order:

1. Create a small working sheet in the `Create` tab.
2. Save it to `WORKING SHEETS`.
3. Open the `Comp` tab and make sure the sheet appears.
4. Run one Card Ladder comp as a test.
5. Open Assignment Rules and make sure companies load.
6. Open the `Assignment` tab and confirm best company and estimated payout can populate.
7. Open the `Receive` tab and test marking a row received.
8. Open `Payouts/Tabs` and confirm assigned-person balances appear when relevant.

Do not start with a giant sheet until this small test works.

## Files That Stay Local

These files are expected to be different on every computer:

```text
.env
.venv
lucas_settings.json
lucas_google_sheets_token.json
assignment_companies.json
sheet_markers.json
```

Do not send these to Git unless you know exactly why you are doing it.

## Common Problems

### The app does not open

Run:

```text
Run Card Pipeline.bat
```

Read the console message. Most startup issues are missing Python, missing dependencies, or a bad `.env` value.

### The installer says Python is missing

Run `install_dependencies.bat` again. If it still cannot install Python automatically, install Python 3.11 or newer from python.org and check `Add python.exe to PATH`.

### Photo OCR says the Google key is missing

Add this to `.env`:

```env
GOOGLE_API_KEY=...
```

Then restart the app.

### Google Sheets cannot connect

Check:

- Google Sheets API is enabled
- OAuth client type is `Desktop app`
- `.env` has both client ID and client secret
- you clicked `Connect Google`
- the signed-in Google account has access to the sheet

### Card Ladder comping does not start

Check:

- Chrome is open
- Card Ladder is logged in
- the unpacked extension is enabled
- L.U.C.A.S is open
- the local bridge status is running

### Sheets are not showing up

Check that the app is pointed at the actual:

```text
WORKING SHEETS
```

folder, not the parent folder.

## Setup Checklist

Use this as the final handoff checklist:

- [ ] Project folder exists on the computer
- [ ] Google Chrome is installed
- [ ] `install_dependencies.bat` completed successfully
- [ ] `.env` exists
- [ ] `WORKING SHEETS`, `INCOMING SHEETS`, and `RECEIVED SHEETS` folders exist
- [ ] L.U.C.A.S opens
- [ ] `Working Folder` points to `WORKING SHEETS`
- [ ] `GOOGLE_API_KEY` is added
- [ ] Card Ladder extension is loaded
- [ ] user is logged into Card Ladder in Chrome
- [ ] Google OAuth credentials are added
- [ ] `Connect Google` has been completed
- [ ] Assignment companies are created and active
- [ ] one small test sheet works end to end
