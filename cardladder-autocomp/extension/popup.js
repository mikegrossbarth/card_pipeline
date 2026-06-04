const queueFile = document.getElementById("queueFile");
const loadQueue = document.getElementById("loadQueue");
const start = document.getElementById("start");
const testBgs = document.getElementById("testBgs");
const capture = document.getElementById("capture");
const download = document.getElementById("download");
const delayMs = document.getElementById("delayMs");
const status = document.getElementById("status");
const BRIDGE_URL = "http://127.0.0.1:8765";

let queue = null;
let results = [];

loadQueue.addEventListener("click", async () => {
  const file = queueFile.files?.[0];
  if (!file) return setStatus("Choose cardladder-queue.json first.");
  queue = JSON.parse(await file.text());
  results = [];
  await chrome.runtime.sendMessage({ type: "CARDLADDER_SAVE_QUEUE", queue });
  setStatus(`Loaded ${queue.rows.length} rows from ${queue.sourceSheet}.`);
});

start.addEventListener("click", async () => {
  const response = await chrome.runtime.sendMessage({ type: "CARDLADDER_SYNC_NOW" });
  if (!response?.ok) return setStatus(response?.error || "Run failed.");
  setStatus("Card Ladder window opened. Values will be captured, piped back, and the window will close automatically.");
});

testBgs.addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url?.startsWith("https://app.cardladder.com/")) {
    return setStatus("Open Card Ladder with the cert-search modal visible first.");
  }
  const response = await chrome.runtime.sendMessage({
    type: "CARDLADDER_TEST_BGS_NATIVE_CLICK",
  }).catch((error) => ({ ok: false, error: String(error?.message || error) }));
  setStatus(JSON.stringify(response, null, 2));
});

capture.addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.url?.startsWith("https://app.cardladder.com/")) {
    return setStatus("Open the Card Ladder results page first.");
  }

  const stored = await chrome.storage.local.get(["cardladderQueue", "cardladderResults"]);
  const row = stored.cardladderQueue?.rows?.[0] || {};
  const response = await chrome.runtime.sendMessage({
    type: "CARDLADDER_CAPTURE_ACTIVE_TAB",
    row,
  }).catch((error) => ({ value: null, status: "error", error: String(error?.message || error) }));
  results = [response];
  await chrome.storage.local.set({ cardladderResults: results });
  await postBridgeResult(response);
  await postBridgeFinish({
    ok: response.value != null,
    total: 1,
    found: response.value != null ? 1 : 0,
    source: "capture-page",
  });
  await closeCurrentTabOrWindow(tab);
  setStatus(`Captured current page: ${response.value ?? response.error ?? "no value found"}`);
});

download.addEventListener("click", async () => {
  const stored = await chrome.storage.local.get(["cardladderQueue", "cardladderResults"]);
  const payload = {
    createdAt: new Date().toISOString(),
    sourceWorkbook: stored.cardladderQueue?.sourceWorkbook,
    sourceSheet: stored.cardladderQueue?.sourceSheet,
    results: stored.cardladderResults || results,
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }));
  await chrome.downloads.download({
    url,
    filename: "cardladder-results.json",
    saveAs: true,
  });
});

setInterval(async () => {
  const stored = await chrome.runtime.sendMessage({ type: "CARDLADDER_GET_STATUS" }).catch(() => null);
  const currentStatus = stored?.cardladderStatus;
  if (!currentStatus) return;
  const lines = [
    `Stage: ${currentStatus.stage}`,
    `Done: ${currentStatus.completed || 0}/${currentStatus.total || 0}`,
  ];
  if (currentStatus.current) lines.push(`Current: ${currentStatus.current.grader} ${currentStatus.current.certNumber}`);
  if (currentStatus.lastResult) lines.push(`Last: ${currentStatus.lastResult.certNumber} -> ${currentStatus.lastResult.value ?? currentStatus.lastResult.status}`);
  if (currentStatus.error) lines.push(`Error: ${currentStatus.error}`);
  status.textContent = lines.join("\n");
}, 1000);

function setStatus(message) {
  status.textContent = message;
}

async function postBridgeResult(result) {
  await fetch(`${BRIDGE_URL}/result/cardladder`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(result),
  }).catch(() => {});
}

async function postBridgeFinish(payload) {
  await fetch(`${BRIDGE_URL}/finish/cardladder`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload),
  }).catch(() => {});
}

async function closeCurrentTabOrWindow(tab) {
  if (!tab?.id) return;
  const windowTabs = await chrome.tabs.query({ windowId: tab.windowId }).catch(() => []);
  if (windowTabs.length <= 1) {
    await chrome.windows.remove(tab.windowId).catch(() => {});
  } else {
    await chrome.tabs.remove(tab.id).catch(() => {});
  }
}
