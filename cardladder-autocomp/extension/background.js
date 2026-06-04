const SALES_HISTORY_URL = "https://app.cardladder.com/sales-history";
const BRIDGE_URL = "http://127.0.0.1:8765";
const MAX_RUN_MS = 20 * 60 * 1000;

let runInProgress = false;
let activeWindowId = null;
let lastCommandId = 0;

chrome.runtime.onInstalled.addListener(() => {
  chrome.runtime.openOptionsPage?.();
  chrome.alarms.create("cardladder-bridge-poll", { periodInMinutes: 0.05 });
});

chrome.action.onClicked.addListener(() => startCardLadderRun(true));
setInterval(pollDesktopBridge, 2500);
chrome.runtime.onStartup?.addListener(() => {
  chrome.alarms.create("cardladder-bridge-poll", { periodInMinutes: 0.05 });
});
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "cardladder-bridge-poll") pollDesktopBridge();
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "CARDLADDER_SAVE_QUEUE") {
    chrome.storage.local.set({ cardladderQueue: message.queue, cardladderResults: [] })
      .then(() => sendResponse({ ok: true }));
    return true;
  }

  if (message.type === "CARDLADDER_SYNC_NOW") {
    startCardLadderRun(true).then(sendResponse);
    return true;
  }

  if (message.type === "CARDLADDER_GET_STATUS") {
    pollDesktopBridge();
    chrome.storage.local.get(["cardladderStatus", "cardladderResults", "cardladderQueue"]).then(sendResponse);
    return true;
  }

  if (message.type === "CARDLADDER_CAPTURE_ACTIVE_TAB") {
    captureActiveTabWithOcr(message.row || {}).then(sendResponse);
    return true;
  }

  if (message.type === "CARDLADDER_TEST_BGS_NATIVE_CLICK") {
    testBgsNativeClick().then(sendResponse);
    return true;
  }
});

async function startCardLadderRun(focusWindow) {
  if (runInProgress) return { ok: false, error: "Card Ladder run already in progress" };
  runInProgress = true;

  try {
    const { cardladderQueue } = await chrome.storage.local.get(["cardladderQueue"]);
    const rows = cardladderQueue?.rows || [];
    if (!rows.length) throw new Error("No Card Ladder queue loaded.");

    await chrome.storage.local.set({
      cardladderStatus: {
        ok: true,
        stage: "opening Card Ladder",
        total: rows.length,
        completed: 0,
        startedAt: new Date().toISOString(),
      },
      cardladderResults: [],
    });

    const tab = await createSalesHistoryWindow(focusWindow);
    await runRows(tab.id, rows);
    return { ok: true };
  } catch (error) {
    await chrome.storage.local.set({
      cardladderStatus: {
        ok: false,
        stage: "failed",
        error: String(error?.message || error),
        finishedAt: new Date().toISOString(),
      },
    });
    return { ok: false, error: String(error?.message || error) };
  } finally {
    runInProgress = false;
  }
}

async function pollDesktopBridge() {
  if (runInProgress) return;
  const response = await fetch(`${BRIDGE_URL}/command`).then((r) => r.json()).catch(() => null);
  const command = response?.command;
  if (!command || command.id === lastCommandId) return;
  lastCommandId = command.id;
  if (command.type !== "RUN_ALL_COMPS") return;
  await fetch(`${BRIDGE_URL}/ack`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ id: command.id }),
  }).catch(() => {});
  await startBridgeRun(command.queue || []);
}

async function startBridgeRun(rows) {
  if (runInProgress) return;
  runInProgress = true;
  try {
    if (!rows.length) throw new Error("Desktop bridge sent no Card Ladder rows.");
    await chrome.storage.local.set({
      cardladderStatus: {
        ok: true,
        stage: "opening Card Ladder",
        total: rows.length,
        completed: 0,
        startedAt: new Date().toISOString(),
      },
      cardladderResults: [],
    });
    const tab = await createSalesHistoryWindow(true);
    await runRows(tab.id, rows, { postToBridge: true });
  } catch (error) {
    await postBridgeFinish({ ok: false, error: String(error?.message || error) });
  } finally {
    runInProgress = false;
  }
}

async function createSalesHistoryWindow(focusWindow) {
  if (activeWindowId !== null) {
    await chrome.windows.remove(activeWindowId).catch(() => {});
    activeWindowId = null;
  }
  const win = await chrome.windows.create({
    url: SALES_HISTORY_URL,
    focused: focusWindow,
    type: "normal",
    width: 1320,
    height: 920,
  });
  activeWindowId = win.id;
  const tab = win.tabs && win.tabs[0];
  if (!tab?.id) throw new Error("Could not create Card Ladder window.");
  return tab;
}

async function runRows(tabId, rows, options = {}) {
  const started = Date.now();
  const results = [];

  for (let index = 0; index < rows.length; index += 1) {
    if (Date.now() - started > MAX_RUN_MS) throw new Error("Card Ladder run timed out.");
    const row = rows[index];
    await waitForTabNotLoading(tabId);
    await injectContent(tabId);

    await chrome.storage.local.set({
      cardladderStatus: {
        ok: true,
        stage: "looking up",
        total: rows.length,
        completed: index,
        current: row,
        updatedAt: new Date().toISOString(),
      },
    });

    const result = await lookupRowWithRetries(tabId, row);

    results.push(result);
    if (options.postToBridge) await postBridgeResult(result);
    await chrome.storage.local.set({
      cardladderResults: results,
      cardladderStatus: {
        ok: true,
        stage: "looking up",
        total: rows.length,
        completed: index + 1,
        lastResult: result,
        updatedAt: new Date().toISOString(),
      },
    });

    await delay(1800);
  }

  await chrome.storage.local.set({
    cardladderResults: results,
    cardladderStatus: {
      ok: true,
      stage: "finished",
      total: rows.length,
      completed: rows.length,
      found: results.filter((result) => result.value != null).length,
      finishedAt: new Date().toISOString(),
    },
  });
  if (options.postToBridge) {
    await postBridgeFinish({
      ok: true,
      total: rows.length,
      found: results.filter((result) => result.value != null).length,
    });
  }
  await closeActiveWindow();
}

async function lookupRowWithRetries(tabId, row) {
  const pageResult = await submitRowWithNativeGrader(tabId, row);

  if (pageResult?.status === "error") return pageResult;

  let lastResult = null;
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    lastResult = await captureValueWithOcr(tabId, row, { ...pageResult, ocrAttempt: attempt });
    if (lastResult?.value != null) return lastResult;
    await delay(3000);
  }
  return lastResult;
}

async function submitRowWithNativeGrader(tabId, row) {
  const prepared = await chrome.tabs.sendMessage(tabId, {
    type: "CARDLADDER_PREPARE_CERT_MODAL",
    row,
  }).catch((error) => ({
    ok: false,
    error: String(error?.message || error),
  }));

  if (!prepared?.ok) {
    return {
      ...row,
      value: null,
      status: "error",
      error: prepared?.error || "Could not prepare Card Ladder cert modal",
      capturedAt: new Date().toISOString(),
    };
  }

  const grader = String(row.grader || "").toUpperCase();
  if (grader) {
    const selected = await nativeSelectGrader(tabId, grader);
    if (!selected?.ok) {
      return {
        ...row,
        value: null,
        status: "error",
        error: selected?.error || `Could not select grader ${grader}`,
        capturedAt: new Date().toISOString(),
      };
    }
  }

  return chrome.tabs.sendMessage(tabId, {
    type: "CARDLADDER_SUBMIT_CERT_MODAL",
    row,
  }).catch((error) => ({
    ...row,
    value: null,
    status: "error",
    error: String(error?.message || error),
    capturedAt: new Date().toISOString(),
  }));
}

async function nativeSelectGrader(tabId, grader) {
  const coords = await chrome.tabs.sendMessage(tabId, {
    type: "CARDLADDER_GET_GRADER_COORDS",
    grader,
  }).catch((error) => ({ ok: false, error: String(error?.message || error) }));
  if (!coords?.ok) return coords;
  await debuggerClick(tabId, coords.dropdown.x, coords.dropdown.y);
  await delay(700);
  await debuggerClick(tabId, coords.option.x, coords.option.y);
  await delay(900);
  return { ok: true, grader, selectedLabel: coords.wanted, before: coords };
}

async function captureValueWithOcr(tabId, row, pageResult = {}) {
  await delay(3500);
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  let captureError = "";
  let image = tabId ? await debuggerCaptureScreenshot(tabId).catch((error) => {
    captureError = String(error?.message || error);
    return "";
  }) : "";
  if (!image) {
    image = await chrome.tabs.captureVisibleTab(tab?.windowId, { format: "png" }).catch((error) => {
      captureError = String(error?.message || error);
      return "";
    });
  }
  if (!image) {
    return {
      ...row,
      value: null,
      status: "ocr_error",
      error: "Could not capture Card Ladder screenshot" + (captureError ? `: ${captureError}` : ""),
      pageUrl: pageResult.pageUrl || tab?.url || "",
      capturedAt: new Date().toISOString(),
    };
  }
  const ocr = await fetch(`${BRIDGE_URL}/ocr/cardladder`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ image, row }),
  }).then((r) => r.json()).catch((error) => ({ ok: false, error: String(error?.message || error) }));

  return {
    ...row,
    value: ocr.value ?? null,
    status: ocr.ok ? "ok" : "ocr_not_found",
    ocr,
    pageUrl: pageResult.pageUrl || tab?.url || "",
    capturedAt: new Date().toISOString(),
  };
}

async function captureActiveTabWithOcr(row) {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url?.startsWith("https://app.cardladder.com/")) {
    return { ...row, value: null, status: "error", error: "Open a Card Ladder results page first" };
  }
  return captureValueWithOcr(tab.id, row, { pageUrl: tab.url });
}

async function debuggerCaptureScreenshot(tabId) {
  const target = { tabId };
  await chrome.debugger.attach(target, "1.3").catch((error) => {
    const message = String(error?.message || error);
    if (!/Another debugger|already attached/i.test(message)) throw error;
  });
  try {
    const metrics = await chrome.debugger.sendCommand(target, "Page.getLayoutMetrics").catch(() => null);
    const viewport = metrics?.cssVisualViewport || metrics?.visualViewport;
    const content = metrics?.cssContentSize || metrics?.contentSize;
    const width = Math.max(900, Math.ceil(viewport?.clientWidth || content?.width || 1280));
    const height = Math.min(1900, Math.max(1200, Math.ceil(content?.height || viewport?.clientHeight || 1200)));
    const result = await chrome.debugger.sendCommand(target, "Page.captureScreenshot", {
      format: "png",
      fromSurface: true,
      captureBeyondViewport: true,
      clip: {
        x: 0,
        y: 0,
        width,
        height,
        scale: 1,
      },
    });
    if (!result?.data) throw new Error("Debugger screenshot returned no data");
    return `data:image/png;base64,${result.data}`;
  } finally {
    await chrome.debugger.detach(target).catch(() => {});
  }
}

async function testBgsNativeClick() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab?.id || !tab.url?.startsWith("https://app.cardladder.com/")) {
    return { ok: false, error: "Open Card Ladder with the cert-search modal visible first." };
  }
  await injectContent(tab.id);
  const coords = await chrome.tabs.sendMessage(tab.id, {
    type: "CARDLADDER_GET_GRADER_COORDS",
    grader: "BGS",
  }).catch((error) => ({ ok: false, error: String(error?.message || error) }));
  if (!coords?.ok) return coords;

  await debuggerClick(tab.id, coords.dropdown.x, coords.dropdown.y);
  await delay(700);
  await debuggerClick(tab.id, coords.option.x, coords.option.y);
  await delay(700);

  const after = await chrome.tabs.sendMessage(tab.id, {
    type: "CARDLADDER_GET_GRADER_COORDS",
    grader: "BGS",
  }).catch((error) => ({ ok: false, error: String(error?.message || error) }));

  return {
    ok: true,
    method: "debugger-native-click",
    before: coords,
    after,
  };
}

async function debuggerClick(tabId, x, y) {
  const target = { tabId };
  await chrome.debugger.attach(target, "1.3").catch((error) => {
    const message = String(error?.message || error);
    if (!/Another debugger|already attached/i.test(message)) throw error;
  });
  try {
    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      type: "mouseMoved",
      x,
      y,
      button: "none",
    });
    await delay(80);
    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      type: "mousePressed",
      x,
      y,
      button: "left",
      clickCount: 1,
    });
    await delay(80);
    await chrome.debugger.sendCommand(target, "Input.dispatchMouseEvent", {
      type: "mouseReleased",
      x,
      y,
      button: "left",
      clickCount: 1,
    });
  } finally {
    await chrome.debugger.detach(target).catch(() => {});
  }
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

async function closeActiveWindow() {
  if (activeWindowId !== null) {
    const windowId = activeWindowId;
    activeWindowId = null;
    await chrome.windows.remove(windowId).catch(() => {});
  }
}

async function injectContent(tabId) {
  await chrome.scripting.executeScript({
    target: { tabId },
    files: ["content.js"],
  }).catch(() => {});
}

async function waitForTabNotLoading(tabId) {
  for (let i = 0; i < 60; i += 1) {
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab) throw new Error("Card Ladder tab closed.");
    if (tab.status === "complete") {
      await delay(700);
      return;
    }
    await delay(1000);
  }
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
