import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  DEFAULT_SHEET,
  DEFAULT_WORKBOOK,
  findLookupRows,
  getWorksheet,
  loadWorkbook,
  normalizeCert,
  parseArgs,
  saveWorkbook,
  setCellValue,
} from "./workbook-utils.mjs";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const args = parseArgs(process.argv.slice(2));
const workbookPath = args.workbook || DEFAULT_WORKBOOK;
const sheetName = args.sheet || DEFAULT_SHEET;
const resultsPath = args.results || path.join(rootDir, "outputs", "cardladder-results.json");
const outputPath = args.output || path.join(rootDir, "outputs", "cardladder-values.xlsx");
const force = Boolean(args.force);

if (!workbookPath) {
  throw new Error("Pass --workbook \"C:\\path\\to\\workbook.xlsx\".");
}

const workbook = await loadWorkbook(workbookPath);
const sheet = getWorksheet(workbook, sheetName);
const { columns, runnable } = findLookupRows(sheet, { force });

const resultsRaw = await fs.readFile(resultsPath, "utf8");
const resultsJson = JSON.parse(resultsRaw);
const results = Array.isArray(resultsJson) ? resultsJson : resultsJson.results || [];
const byCert = new Map(results.map((result) => [normalizeCert(result.certNumber), result]));

let filled = 0;
let missing = 0;
for (const row of runnable) {
  const result = byCert.get(row.certNumber);
  const value = parseValue(result?.value ?? result?.cardLadderValue);
  if (value == null) {
    missing += 1;
    continue;
  }
  setCellValue(sheet, row.excelRow, columns.valueCol, value);
  filled += 1;
}

await fs.mkdir(path.dirname(outputPath), { recursive: true });
saveWorkbook(workbook, outputPath);

console.log(JSON.stringify({
  resultsPath,
  output: outputPath,
  filled,
  missing,
}, null, 2));

function parseValue(value) {
  if (value == null || value === "") return null;
  const parsed = Number(String(value).replace(/[$,]/g, "").trim());
  return Number.isFinite(parsed) ? parsed : null;
}
