import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { DEFAULT_SHEET, DEFAULT_WORKBOOK, findLookupRows, loadWorkbook, parseArgs } from "./workbook-utils.mjs";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const args = parseArgs(process.argv.slice(2));
const workbookPath = args.workbook || DEFAULT_WORKBOOK;
const sheetName = args.sheet || DEFAULT_SHEET;
const outputPath = args.output || path.join(rootDir, "outputs", "cardladder-queue.json");
const force = Boolean(args.force);
const limit = args.limit ? Number(args.limit) : null;

const workbook = await loadWorkbook(workbookPath);
const sheet = workbook.worksheets.getItem(sheetName);
const { candidates, runnable, skipped } = findLookupRows(sheet, { force });
const selected = limit ? runnable.slice(0, limit) : runnable;

const queue = {
  createdAt: new Date().toISOString(),
  sourceWorkbook: workbookPath,
  sourceSheet: sheetName,
  targetValueColumn: "Value",
  totalBlankValueRows: candidates.length,
  totalRunnableRows: runnable.length,
  totalSkippedRows: skipped.length,
  rows: selected.map((row) => ({
    excelRow: row.excelRow,
    certNumber: row.certNumber,
    grader: row.grader,
    cardTitle: row.cardTitle,
  })),
  skipped: skipped.map((row) => ({
    excelRow: row.excelRow,
    certNumber: row.certNumber,
    grader: row.grader,
    cardTitle: row.cardTitle,
    reason: row.reason,
  })),
};

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, JSON.stringify(queue, null, 2));

console.log(JSON.stringify({
  output: outputPath,
  blankValueRows: queue.totalBlankValueRows,
  runnableRows: queue.totalRunnableRows,
  skippedRows: queue.totalSkippedRows,
  queuedRows: queue.rows.length,
}, null, 2));
