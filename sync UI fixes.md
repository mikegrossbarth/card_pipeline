# Sync UI Fixes

This platform-specific copy is superseded.

Use the universal note for all Mac and Windows LUCAS edit tracking:

`/Users/michaelgrossbarth/Documents/Codex/2026-08-07/we-are-working-on-lucas-mac/sync UI fixes.md`

Do not maintain separate Mac-only or Windows-only sync notes unless a future task explicitly changes the sync plan.

## 2026-08-26 - Inventory bulk edit toggle restored

- Windows Inventory bulk editing is opt-in again: the Bulk Edit toggle is visible in the Inventory toolbar, single-click cell navigation only runs while Bulk Edit is on, and normal mode returns to double-click-to-edit cells.
- Bulk Edit mode keeps the keyboard workflow for moving around the table with arrows and editing with Enter/F2.

## 2026-08-25 - Receive rematch safety and card typing UX

- Windows Receive rematch now clears stale fields when switching a row to a different incoming card, including blank fields from raw/no-cert matches. This prevents a previously selected graded cert/company/value from remaining attached after selecting a raw Curry Timeless-style card.
- Receive card-title editing is now single-click oriented: helper text says click, the autocomplete dropdown opens when editing starts, Down/Alt-Down posts the dropdown cleanly, and focus-out waits if the dropdown is open so arrow navigation does not prematurely commit.
- Regression coverage added for raw rematch stale-field clearing, Down opening the autocomplete dropdown, and focus-out not committing while the dropdown is visible.
