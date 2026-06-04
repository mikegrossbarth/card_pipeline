import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

export const DEFAULT_WORKBOOK = "C:/Users/User/Downloads/Blez x mikey MASTER SHEET.xlsx";
export const DEFAULT_SHEET = "612026";

export async function loadWorkbook(workbookPath) {
  const input = await FileBlob.load(workbookPath);
  const workbook = await SpreadsheetFile.importXlsx(input);
  return workbook;
}

export function findLookupRows(sheet, { force = false } = {}) {
  const usedRange = sheet.getUsedRange(true);
  const values = usedRange.values;
  if (!values?.length) throw new Error(`Sheet ${sheet.name} has no used rows.`);

  const header = values[0].map((value) => String(value || "").trim());
  const columns = header.reduce((acc, name, index) => {
    if (name) acc[normalizeHeader(name)] = index;
    return acc;
  }, {});

  const certCol = requiredColumn(columns, "certificationnumber");
  const cardCol = requiredColumn(columns, "card");
  const valueCol = requiredColumn(columns, "value");

  const rows = values
    .slice(1)
    .map((row, index) => {
      const excelRow = index + 2;
      const certNumber = normalizeCert(row[certCol]);
      const cardTitle = String(row[cardCol] || "").trim();
      const currentValue = row[valueCol];
      const grader = inferGrader(cardTitle);
      return {
        excelRow,
        rowIndex: index + 1,
        certNumber,
        cardTitle,
        currentValue,
        grader,
        reason: certNumber && cardTitle && grader ? "" : missingReason({ certNumber, cardTitle, grader }),
      };
    })
    .filter((row) => row.certNumber || row.cardTitle)
    .filter((row) => force || isBlank(row.currentValue));

  return {
    columns: { certCol, cardCol, valueCol },
    candidates: rows,
    runnable: rows.filter((row) => !row.reason),
    skipped: rows.filter((row) => row.reason),
  };
}

export function inferGrader(cardTitle) {
  const match = String(cardTitle || "").match(/\b(PSA|BGS|SGC|CGC)\b/i);
  return match ? match[1].toUpperCase() : "";
}

export function normalizeCert(value) {
  return String(value || "").replace(/[^0-9A-Z]/gi, "").trim();
}

export function normalizeHeader(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]/g, "");
}

export function isBlank(value) {
  return value == null || String(value).trim() === "";
}

export function parseArgs(rawArgs) {
  const parsed = {};
  for (let i = 0; i < rawArgs.length; i += 1) {
    const arg = rawArgs[i];
    if (!arg.startsWith("--")) continue;
    const [key, inlineValue] = arg.slice(2).split("=", 2);
    if (inlineValue != null) {
      parsed[key] = inlineValue;
    } else if (rawArgs[i + 1] && !rawArgs[i + 1].startsWith("--")) {
      parsed[key] = rawArgs[i + 1];
      i += 1;
    } else {
      parsed[key] = true;
    }
  }
  return parsed;
}

function requiredColumn(columns, key) {
  if (columns[key] == null) throw new Error(`Missing required column: ${key}`);
  return columns[key];
}

function missingReason(row) {
  const parts = [];
  if (!row.certNumber) parts.push("missing cert");
  if (!row.cardTitle) parts.push("missing card title");
  if (!row.grader) parts.push("missing grader in card title");
  return parts.join(", ");
}
