const CARDLADDER_CONTENT_VERSION = "2026-06-01-cert-modal-tight-v3";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "CARDLADDER_CAPTURE_CURRENT") {
    sendResponse({
      ...(message.row || {}),
      value: null,
      status: "capture_requires_background_ocr",
      pageUrl: location.href,
      capturedAt: new Date().toISOString(),
    });
    return true;
  }
  if (message.type === "CARDLADDER_TEST_GRADER") {
    testGraderSelection(message.grader || "BGS")
      .then((result) => sendResponse(result))
      .catch((error) => sendResponse({ ok: false, error: error.message, version: CARDLADDER_CONTENT_VERSION }));
    return true;
  }
  if (message.type === "CARDLADDER_GET_GRADER_COORDS") {
    sendResponse(getGraderClickCoordinates(message.grader || "BGS"));
    return true;
  }
  if (message.type === "CARDLADDER_PREPARE_CERT_MODAL") {
    prepareCertModal()
      .then((result) => sendResponse(result))
      .catch((error) => sendResponse({ ok: false, error: error.message, version: CARDLADDER_CONTENT_VERSION }));
    return true;
  }
  if (message.type === "CARDLADDER_SUBMIT_CERT_MODAL") {
    submitPreparedCertModal(message.row)
      .then((result) => sendResponse(result))
      .catch((error) => sendResponse({ ...(message.row || {}), value: null, status: "error", error: error.message, capturedAt: new Date().toISOString() }));
    return true;
  }
  if (message.type !== "CARDLADDER_LOOKUP_ROW") return false;
  runLookup(message.row)
    .then((result) => sendResponse(result))
    .catch((error) => sendResponse({ results: [], error: error.message }));
  return true;
});

async function runLookup(row) {
  try {
    await clickLoginIfNeeded();
    await ensureSalesHistory();
    await clickCertMode();
    await chooseGrader(row.grader);
    await fillCert(row.certNumber);
    await submitSearch();
    await waitForResultsPage();
    return {
      ...row,
      value: null,
      status: "submitted",
      pageUrl: location.href,
      capturedAt: new Date().toISOString(),
    };
  } catch (error) {
    return {
      ...row,
      value: null,
      status: "error",
      error: error.message,
      capturedAt: new Date().toISOString(),
    };
  }
}

async function prepareCertModal() {
  await clickLoginIfNeeded();
  await ensureSalesHistory();
  await clickCertMode();
  if (!certSearchModal()) throw new Error("Could not open cert search modal.");
  return { ok: true, version: CARDLADDER_CONTENT_VERSION };
}

async function submitPreparedCertModal(row) {
  await fillCert(row.certNumber);
  await submitSearch();
  await waitForResultsPage();
  return {
    ...row,
    value: null,
    status: "submitted",
    pageUrl: location.href,
    capturedAt: new Date().toISOString(),
  };
}

async function waitForResultsPage() {
  for (let i = 0; i < 30; i += 1) {
    const text = document.body.innerText || "";
    if ((/Grade:\s*.+Grader:\s*.+Profile:/i.test(text) || /CL\s*Value/i.test(text)) && /\$\s*\d/i.test(text)) {
      await sleep(2500);
      window.scrollTo({ top: 0, behavior: "instant" });
      await sleep(700);
      return;
    }
    await sleep(500);
  }
  await sleep(2500);
}

async function clickLoginIfNeeded() {
  const login = findClickable(/^(log in|login|sign in)$/i);
  if (login) {
    login.click();
    await sleep(2500);
  }
}

async function ensureSalesHistory() {
  if (!location.pathname.includes("sales-history")) {
    location.href = "https://app.cardladder.com/sales-history";
    await sleep(3000);
  }
}

async function clickCertMode() {
  if (certSearchModal()) return;

  await resetSearchFocus();

  const searchInput = findSearchInput();
  if (searchInput) {
    const hashNode = findHashControlNearSearch(searchInput);
    if (hashNode) {
      clickLikeHuman(hashNode);
      await sleep(650);
      if (certSearchModal()) return;
      if (await clickCertMenuOptionIfShown()) return;
      if (certInputIsVisible()) return;
    }
  }

  const exactHash = [...document.querySelectorAll("button, [role='button'], a")]
    .find((el) => visibleText(el) === "#" || (el.getAttribute("aria-label") || "").match(/cert|number|#|hash/i));
  if (exactHash) {
    clickLikeHuman(exactHash);
    await sleep(500);
    await clickCertMenuOptionIfShown();
    return;
  }

  const nearSearch = [...document.querySelectorAll("button, [role='button']")]
    .find((el) => visibleText(el).includes("#"));
  if (nearSearch) {
    clickLikeHuman(nearSearch);
    await sleep(500);
    await clickCertMenuOptionIfShown();
    return;
  }

  if (searchInput) {
    const rect = searchInput.getBoundingClientRect();
    const clickPoints = [
      [rect.right - 22, rect.top + rect.height / 2],
      [rect.right - 34, rect.top + rect.height / 2],
      [rect.right - 12, rect.top + rect.height / 2],
    ];
    for (const [x, y] of clickPoints) {
      clickAtPoint(x, y);
      await sleep(500);
      if (document.activeElement === searchInput) {
        searchInput.blur();
        document.body.click();
        await sleep(300);
      }
      if (certSearchModal()) return;
      if (await clickCertMenuOptionIfShown()) return;
      if (certInputIsVisible()) return;
    }
  }

  const option = findClickable(/^(#|cert\s*#|certification\s*#|certification number|cert number)$/i);
  if (option) {
    clickLikeHuman(option);
    await sleep(500);
    return;
  }

  throw new Error("Could not find # cert search mode. Page clue: " + pageClue());
}

async function resetSearchFocus() {
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  document.activeElement?.blur?.();
  await closeGlobalSearchIfOpen();

  const heading = [...document.querySelectorAll("h1, h2, [role='heading'], div, main")]
    .filter((el) => isVisible(el))
    .find((el) => /^SALES$/i.test(visibleText(el)));
  if (heading) {
    clickLikeHuman(heading);
    await sleep(300);
    return;
  }

  const searchInput = findSearchInput();
  if (searchInput) {
    const rect = searchInput.getBoundingClientRect();
    clickAtPoint(Math.max(20, rect.left - 30), Math.max(20, rect.top - 35));
    await sleep(300);
    return;
  }

  clickAtPoint(Math.min(window.innerWidth - 20, 260), Math.min(window.innerHeight - 20, 180));
  await sleep(300);
}

async function chooseGrader(grader) {
  const normalized = String(grader || "").toUpperCase();
  const optionLabel = cardLadderGraderLabel(normalized);
  const modal = certSearchModal();
  if (modal) {
    const graderControl = findGraderControlInModal(modal) || findFieldControlInModal(modal, /grader/i);
    if (graderControl) {
      if (selectedControlText(graderControl).toUpperCase() === optionLabel) return;
      if (await clickDropdownThenOption(modal, graderControl, normalized, optionLabel)) return;
    }
  }

  const select = [...document.querySelectorAll("select")].find((el) =>
    [...el.options].some((option) => option.textContent.trim().toUpperCase() === optionLabel)
  );
  if (select) {
    select.value = [...select.options].find((option) => option.textContent.trim().toUpperCase() === optionLabel).value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(300);
    return;
  }

  const combobox = document.querySelector("[role='combobox'], input[placeholder*='Company' i], input[placeholder*='Grader' i]");
  if (combobox) {
    combobox.click();
    await sleep(300);
    const option = findClickable(new RegExp(`^${escapeRegExp(optionLabel)}$`, "i"));
    if (option) {
      option.click();
      await sleep(300);
      return;
    }
  }

  const textOption = findClickable(new RegExp(`^${escapeRegExp(optionLabel)}$`, "i"));
  if (textOption) {
    textOption.click();
    await sleep(300);
    return;
  }

  throw new Error(`Could not select grader ${normalized}. ${graderSelectionDebug(modal, optionLabel)}`);
}

async function testGraderSelection(grader) {
  const normalized = String(grader || "BGS").toUpperCase();
  const optionLabel = cardLadderGraderLabel(normalized);
  const modal = certSearchModal();
  if (!modal) {
    return { ok: false, version: CARDLADDER_CONTENT_VERSION, error: "Open the SEARCH SALES BY CERT # modal first." };
  }
  const control = findGraderControlInModal(modal) || findFieldControlInModal(modal, /grader/i);
  if (!control) {
    return { ok: false, version: CARDLADDER_CONTENT_VERSION, error: "Could not find Grader control.", modal: visibleText(modal).slice(0, 300) };
  }
  const ok = await clickDropdownThenOption(modal, control, normalized, optionLabel);
  return {
    ok,
    version: CARDLADDER_CONTENT_VERSION,
    wanted: optionLabel,
    selectedText: selectedControlText(control),
    debug: graderSelectionDebug(modal, optionLabel),
  };
}

function getGraderClickCoordinates(grader) {
  const normalized = String(grader || "BGS").toUpperCase();
  const modal = certSearchModal();
  if (!modal) {
    return { ok: false, version: CARDLADDER_CONTENT_VERSION, error: "Open the SEARCH SALES BY CERT # modal first." };
  }
  const control = findGraderControlInModal(modal) || findFieldControlInModal(modal, /grader/i);
  if (!control) {
    return { ok: false, version: CARDLADDER_CONTENT_VERSION, error: "Could not find Grader control.", modal: visibleText(modal).slice(0, 300) };
  }
  const indexByGrader = {
    PSA: 0,
    BGS: 1,
    BECKETT: 1,
    SGC: 2,
    CGC: 3,
  };
  const targetIndex = indexByGrader[normalized];
  if (targetIndex == null) {
    return { ok: false, version: CARDLADDER_CONTENT_VERSION, error: `Unsupported grader ${normalized}` };
  }
  const rect = graderFieldRect(modal, control);
  const optionHeight = Math.max(48, Math.min(58, rect.height));
  return {
    ok: true,
    version: CARDLADDER_CONTENT_VERSION,
    wanted: cardLadderGraderLabel(normalized),
    dropdown: {
      x: Math.max(rect.left + 20, rect.right - 32),
      y: rect.top + rect.height / 2,
    },
    option: {
      x: Math.min(rect.right - 24, rect.left + 38),
      y: rect.bottom + optionHeight * targetIndex + optionHeight / 2,
    },
    rect,
    selectedText: selectedControlText(control),
  };
}

async function clickDropdownThenOption(modal, control, grader, optionLabel) {
  await clickGraderDropdown(modal, control);
  const option = findGraderOption(optionLabel) || findGraderOptionByPosition(grader);
  if (option) {
    clickLikeHuman(option);
    await sleep(650);
    return true;
  }
  return clickGraderOptionByKnownPosition(modal, control, grader);
}

function cardLadderGraderLabel(grader) {
  const labels = {
    BGS: "BECKETT",
  };
  return labels[grader] || grader;
}

function findGraderControlInModal(modal) {
  const labels = [...modal.querySelectorAll("label, legend, span, div")]
    .filter((el) => isVisible(el) && /^grader$/i.test(visibleText(el).replace(/[:*]/g, "").trim()));

  for (const label of labels) {
    const labelRect = label.getBoundingClientRect();
    const controls = [...modal.querySelectorAll("select, [role='combobox'], button, input, div")]
      .filter((el) => isVisible(el) && el !== label && !label.contains(el))
      .map((el) => ({ el, rect: el.getBoundingClientRect(), text: selectedControlText(el) }))
      .filter(({ rect }) =>
        rect.top >= labelRect.bottom - 10 &&
        rect.top <= labelRect.bottom + 95 &&
        rect.left >= labelRect.left - 16 &&
        rect.left <= labelRect.left + 620
      )
      .filter(({ rect, text }) => rect.width >= 80 && rect.height >= 20 && !/^cert/i.test(text))
      .sort((a, b) => (a.rect.top - b.rect.top) || (b.rect.width - a.rect.width));
    if (controls[0]) return controls[0].el;
  }

  return [...modal.querySelectorAll("[role='combobox'], select, button")]
    .filter((el) => isVisible(el))
    .find((el) => /PSA|BECKETT|BGS|SGC|CGC|CSG|TAG|ISA|HGA/i.test(selectedControlText(el))) || null;
}

async function clickGraderDropdown(modal, control) {
  control.scrollIntoView({ block: "center", inline: "center" });
  await sleep(150);
  if (typeof control.focus === "function") control.focus();
  const rect = graderFieldRect(modal, control);
  clickLikeHuman(control, Math.max(rect.left + 20, rect.right - 32), rect.top + rect.height / 2);
  await sleep(700);
  if (!findAnyGraderOptions()) {
    clickAtPoint(Math.max(rect.left + 20, rect.right - 32), rect.top + rect.height / 2);
    await sleep(700);
  }
}

function graderFieldRect(modal, control) {
  const labels = [...modal.querySelectorAll("label, legend, span, div")]
    .filter((el) => isVisible(el) && /^grader$/i.test(visibleText(el).replace(/[:*]/g, "").trim()));
  const modalRect = modal.getBoundingClientRect();
  const controlRect = control.getBoundingClientRect();
  const label = labels
    .map((el) => ({ el, rect: el.getBoundingClientRect() }))
    .sort((a, b) => a.rect.top - b.rect.top)[0];

  if (!label) return controlRect;

  const top = Math.max(label.rect.bottom - 4, controlRect.top);
  const height = Math.max(42, Math.min(56, controlRect.height || 48));
  return {
    left: Math.max(modalRect.left + 18, controlRect.left || modalRect.left + 20),
    right: Math.min(modalRect.right - 18, controlRect.right || modalRect.right - 20),
    top,
    bottom: top + height,
    width: Math.min(modalRect.right - 36, controlRect.right || modalRect.right - 20) - Math.max(modalRect.left + 18, controlRect.left || modalRect.left + 20),
    height,
  };
}

function findAnyGraderOptions() {
  return [...document.querySelectorAll("[role='option'], [role='menuitem'], li, button, div, span")]
    .filter((el) => isVisible(el))
    .some((el) => /^(PSA|BECKETT|SGC|CGC)$/i.test(visibleText(el).replace(/\s+/g, " ").trim()));
}

function findGraderOption(grader) {
  const pattern = new RegExp(`(^|\\b)${escapeRegExp(grader)}($|\\b)`, "i");
  const candidates = [...document.querySelectorAll("[role='option'], [role='menuitem'], li, button, div, span")]
    .filter((el) => isVisible(el))
    .map((el) => ({ el, text: visibleText(el).replace(/\s+/g, " ").trim(), rect: el.getBoundingClientRect() }))
    .filter(({ text, rect }) => text && text.length <= 40 && pattern.test(text) && rect.top > 80)
    .filter(({ text }) => !/grader|cert|submit|search/i.test(text));

  candidates.sort((a, b) => {
    const exactA = a.text.toUpperCase() === grader ? 0 : 1;
    const exactB = b.text.toUpperCase() === grader ? 0 : 1;
    return exactA - exactB || a.text.length - b.text.length || a.rect.top - b.rect.top;
  });

  return candidates[0]?.el || null;
}

function findGraderOptionByPosition(grader) {
  const indexByGrader = {
    PSA: 0,
    BGS: 1,
    BECKETT: 1,
    SGC: 2,
    CGC: 3,
  };
  const targetIndex = indexByGrader[grader];
  if (targetIndex == null) return null;
  const options = [...document.querySelectorAll("[role='option'], [role='menuitem'], li, button, div")]
    .filter((el) => isVisible(el))
    .map((el) => ({ el, text: visibleText(el).replace(/\s+/g, " ").trim(), rect: el.getBoundingClientRect() }))
    .filter(({ text, rect }) => text && text.length <= 40 && /^(PSA|BECKETT|SGC|CGC)$/i.test(text) && rect.top > 80)
    .sort((a, b) => a.rect.top - b.rect.top);
  return options[targetIndex]?.el || null;
}

async function clickGraderOptionByKnownPosition(modal, control, grader) {
  const indexByGrader = {
    PSA: 0,
    BGS: 1,
    BECKETT: 1,
    SGC: 2,
    CGC: 3,
  };
  const targetIndex = indexByGrader[grader];
  if (targetIndex == null) return false;

  const rect = graderFieldRect(modal, control);
  const optionHeight = Math.max(48, Math.min(58, rect.height));
  const x = Math.min(rect.right - 24, rect.left + 38);
  const y = rect.bottom + optionHeight * targetIndex + optionHeight / 2;
  if (y >= window.innerHeight - 8) return false;
  clickAtPoint(x, y);
  await sleep(900);
  return true;
}

function selectedControlText(control) {
  if (!control) return "";
  if (control.matches?.("select")) return control.options[control.selectedIndex]?.textContent?.trim() || "";
  if (control.matches?.("input, textarea")) return control.value || control.getAttribute("placeholder") || "";
  return visibleText(control).replace(/\s+/g, " ").trim();
}

function graderSelectionDebug(modal, optionLabel) {
  const visibleOptions = [...document.querySelectorAll("[role='option'], [role='menuitem'], li, button, div, span")]
    .filter((el) => isVisible(el))
    .map((el) => visibleText(el).replace(/\s+/g, " ").trim())
    .filter((text) => text && /PSA|BECKETT|BGS|SGC|CGC|Grader/i.test(text))
    .slice(0, 12)
    .join(" | ");
  const modalText = modal ? visibleText(modal).replace(/\s+/g, " ").slice(0, 220) : "no modal";
  return `[${CARDLADDER_CONTENT_VERSION}; wanted ${optionLabel}; options ${visibleOptions || "none"}; modal ${modalText}]`;
}

async function fillCert(certNumber) {
  const modal = certSearchModal();
  if (modal) {
    const certInput = findFieldControlInModal(modal, /cert/i, "input");
    if (!certInput) throw new Error("Could not find cert input in cert search modal.");
    certInput.focus();
    setNativeValue(certInput, "");
    setNativeValue(certInput, certNumber);
    certInput.dispatchEvent(new Event("change", { bubbles: true }));
    await sleep(300);
    return;
  }

  const inputs = [...document.querySelectorAll("input:not([type='hidden']), textarea")];
  const certInput = inputs.find((el) =>
    `${el.placeholder || ""} ${el.getAttribute("aria-label") || ""} ${el.name || ""}`.match(/cert/i)
  ) || inputs[inputs.length - 1];

  if (!certInput) throw new Error("Could not find cert input.");
  certInput.focus();
  setNativeValue(certInput, "");
  setNativeValue(certInput, certNumber);
  certInput.dispatchEvent(new Event("change", { bubbles: true }));
  await sleep(300);
}

async function submitSearch() {
  const modal = certSearchModal();
  if (modal) {
    const submit = [...modal.querySelectorAll("button, [role='button']")]
      .find((el) => /^submit$/i.test(visibleText(el)));
    if (!submit) throw new Error("Could not find Submit button in cert search modal.");
    clickLikeHuman(submit);
    await sleep(3000);
    return;
  }

  const button = findClickable(/^(search|apply|submit)$/i) || document.querySelector("button[type='submit']");
  if (button) {
    button.click();
  } else {
    document.activeElement?.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  }
  await sleep(2500);
}

function readCardLadderValue() {
  const text = document.body.innerText;
  const normalized = text.replace(/\s+/g, " ");
  const labeled = normalized.match(/Card\s*Ladder\s*Value[\s\S]{0,80}?\$\s*([\d,]+(?:\.\d{1,2})?)/i)
    || normalized.match(/\bC\s*L\s*Value[\s\S]{0,80}?\$\s*([\d,]+(?:\.\d{1,2})?)/i);
  if (labeled) return Number(labeled[1].replace(/,/g, ""));

  const valueLabel = normalized.search(/\b(?:C\s*L|Card\s*Ladder)\s*Value\b/i);
  if (valueLabel >= 0) {
    const afterLabel = normalized.slice(valueLabel, valueLabel + 300);
    const nearbyMoney = afterLabel.match(/\$\s*([\d,]+(?:\.\d{1,2})?)/);
    if (nearbyMoney) return Number(nearbyMoney[1].replace(/,/g, ""));
  }

  const profileSummary = normalized.match(/\b\d+\s+results\s+Grade:\s*[^$]{0,260}?\$\s*([\d,]+(?:\.\d{1,2})?)/i);
  if (profileSummary) return Number(profileSummary[1].replace(/,/g, ""));

  const beforeFirstSale = normalized.split(/\bEBAY\s+-\s+/i)[0] || "";
  if (/Grade:\s*/i.test(beforeFirstSale) && /Profile:/i.test(beforeFirstSale)) {
    const summaryMoney = beforeFirstSale.match(/\$\s*([\d,]+(?:\.\d{1,2})?)/);
    if (summaryMoney) return Number(summaryMoney[1].replace(/,/g, ""));
  }

  const clNode = [...document.querySelectorAll("body *")]
    .filter((el) => isVisible(el))
    .map((el) => ({ el, text: visibleText(el), rect: el.getBoundingClientRect() }))
    .filter((item) => /\bC\s*L\s*Value\b|\bCard\s*Ladder\s*Value\b/i.test(item.text))
    .sort((a, b) => a.rect.top - b.rect.top || a.rect.left - b.rect.left)[0];

  if (clNode) {
    const localText = collectNearbyText(clNode.el);
    const localMatch = localText.replace(/\s+/g, " ").match(/\$?\s*([\d,]+(?:\.\d{1,2})?)/);
    if (localMatch) return Number(localMatch[1].replace(/,/g, ""));
  }

  const moneyValues = [...text.matchAll(/\$\s*([\d,]+(?:\.\d{1,2})?)/g)]
    .map((match) => Number(match[1].replace(/,/g, "")))
    .filter((value) => Number.isFinite(value) && value > 0);

  return moneyValues.length === 1 ? moneyValues[0] : null;
}

function collectNearbyText(node) {
  const parts = [];
  let current = node;
  for (let i = 0; i < 4 && current; i += 1) {
    parts.push(current.innerText || current.textContent || "");
    current = current.parentElement;
  }
  const rect = node.getBoundingClientRect();
  [...document.querySelectorAll("body *")]
    .filter((el) => isVisible(el))
    .map((el) => ({ el, rect: el.getBoundingClientRect(), text: visibleText(el) }))
    .filter((item) =>
      item.rect.top >= rect.top - 20 &&
      item.rect.top <= rect.bottom + 40 &&
      item.rect.left >= rect.left &&
      item.rect.left <= rect.right + 180
    )
    .forEach((item) => parts.push(item.text));
  return parts.join(" ");
}

async function waitForClValue() {
  for (let i = 0; i < 20; i += 1) {
    if (/\b(?:CL|Card\s*Ladder)\s*Value\b/i.test(document.body.innerText || "")) return;
    await sleep(500);
  }
}

function findClickable(pattern) {
  return [...document.querySelectorAll("button, [role='button'], a, [role='option'], li, div")]
    .find((el) => pattern.test(visibleText(el)));
}

function findSearchInput() {
  const inputs = [...document.querySelectorAll("input:not([type='hidden']), textarea")];
  return inputs.find((el) =>
    `${el.placeholder || ""} ${el.getAttribute("aria-label") || ""} ${el.name || ""}`.match(/search listing titles/i)
  );
}

async function closeGlobalSearchIfOpen() {
  const globalSearch = [...document.querySelectorAll("input:not([type='hidden']), textarea")]
    .find((el) =>
      isVisible(el) &&
      !`${el.placeholder || ""} ${el.getAttribute("aria-label") || ""} ${el.name || ""}`.match(/search listing titles/i) &&
      `${el.placeholder || ""} ${el.getAttribute("aria-label") || ""} ${el.name || ""}`.match(/^ ?search ?$/i)
    );
  if (!globalSearch) return;

  const rect = globalSearch.getBoundingClientRect();
  const overlayClose = [...document.querySelectorAll("button, [role='button'], span, div")]
    .filter((el) => isVisible(el))
    .map((el) => ({ el, rect: el.getBoundingClientRect(), text: visibleText(el) }))
    .filter(({ rect: r, text }) =>
      text === "×" &&
      r.top >= rect.top &&
      r.left >= rect.left &&
      r.left <= rect.right + 40
    )
    .sort((a, b) => a.rect.top - b.rect.top)[0]?.el;

  if (overlayClose) {
    clickLikeHuman(overlayClose);
    await sleep(250);
  }

  globalSearch.blur();
  document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  await sleep(250);
  clickAtPoint(Math.min(window.innerWidth - 80, rect.right + 160), Math.min(window.innerHeight - 80, rect.bottom + 160));
  await sleep(300);
}

function findHashControlNearSearch(searchInput) {
  const inputRect = searchInput.getBoundingClientRect();
  const candidates = [...document.querySelectorAll("button, [role='button'], span, div, svg, path")]
    .filter((el) => isVisible(el))
    .map((el) => ({ el, rect: el.getBoundingClientRect(), text: (el.innerText || el.textContent || "").trim() }))
    .filter(({ rect }) =>
      rect.top >= inputRect.top - 10 &&
      rect.bottom <= inputRect.bottom + 10 &&
      rect.left >= inputRect.right - 80 &&
      rect.right <= inputRect.right + 20
    )
    .filter(({ text, el }) => text === "#" || (el.getAttribute("aria-label") || "").match(/cert|number|hash|#/i));

  candidates.sort((a, b) => {
    const aExact = a.text === "#" ? 0 : 1;
    const bExact = b.text === "#" ? 0 : 1;
    return aExact - bExact || Math.abs(a.rect.right - inputRect.right) - Math.abs(b.rect.right - inputRect.right);
  });

  return candidates[0]?.el || null;
}

function certSearchModal() {
  const candidates = [...document.querySelectorAll("[role='dialog'], .modal, div")]
    .filter((el) => isVisible(el) && /SEARCH SALES BY CERT #/i.test(visibleText(el)))
    .map((el) => {
      const rect = el.getBoundingClientRect();
      const text = visibleText(el);
      return {
        el,
        rect,
        text,
        area: rect.width * rect.height,
        roleScore: el.getAttribute("role") === "dialog" ? 0 : 1,
      };
    })
    .filter(({ rect, text }) =>
      rect.width >= 300 &&
      rect.width <= Math.min(window.innerWidth, 900) &&
      rect.height >= 180 &&
      rect.height <= Math.min(window.innerHeight, 700) &&
      /Cert #/i.test(text) &&
      /Grader/i.test(text) &&
      /Submit/i.test(text)
    );

  candidates.sort((a, b) => a.roleScore - b.roleScore || a.area - b.area);
  return candidates[0]?.el || null;
}

function findFieldControlInModal(modal, labelPattern, preferredSelector = "input, textarea, [role='combobox'], select, button, div") {
  const controls = [...modal.querySelectorAll(preferredSelector)].filter((el) => isVisible(el));
  const direct = controls.find((el) =>
    `${el.placeholder || ""} ${el.getAttribute("aria-label") || ""} ${el.name || ""} ${visibleText(el)}`.match(labelPattern)
  );
  if (direct && direct.matches("input, textarea, select, [role='combobox'], button")) return direct;

  const labels = [...modal.querySelectorAll("label, legend, span, div")]
    .filter((el) => isVisible(el) && labelPattern.test(visibleText(el)));
  for (const label of labels) {
    const labelRect = label.getBoundingClientRect();
    const below = controls
      .map((el) => ({ el, rect: el.getBoundingClientRect() }))
      .filter(({ rect }) => rect.top >= labelRect.top - 4 && rect.top <= labelRect.bottom + 44)
      .filter(({ rect }) => rect.left >= labelRect.left - 20 && rect.left <= labelRect.right + 560)
      .sort((a, b) => (a.rect.top - b.rect.top) || (a.rect.left - b.rect.left))[0];
    if (below) return below.el;
  }

  if (labelPattern.test("cert")) return controls.find((el) => el.matches("input, textarea"));
  return controls[0] || null;
}

function certInputIsVisible() {
  return [...document.querySelectorAll("input:not([type='hidden']), textarea")]
    .some((el) => isVisible(el) && `${el.placeholder || ""} ${el.getAttribute("aria-label") || ""} ${el.name || ""}`.match(/cert/i));
}

async function clickCertMenuOptionIfShown() {
  await sleep(250);
  const option = [...document.querySelectorAll("button, [role='button'], [role='option'], li, div, span")]
    .filter((el) => isVisible(el))
    .find((el) => /^(#|cert\s*#|certification\s*#|certification number|cert number)$/i.test(visibleText(el)));
  if (!option) return false;
  clickLikeHuman(option);
  await sleep(400);
  return true;
}

function clickAtPoint(x, y) {
  const target = document.elementFromPoint(x, y);
  if (!target) return;
  const clickable = target.closest("button, [role='button'], span, div, label") || target;
  clickLikeHuman(clickable, x, y);
}

function clickLikeHuman(node, clientX = null, clientY = null) {
  const rect = node.getBoundingClientRect();
  const x = clientX ?? rect.left + rect.width / 2;
  const y = clientY ?? rect.top + rect.height / 2;
  ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach((type) => {
    node.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y }));
  });
  if (typeof node.click === "function") node.click();
}

function setNativeValue(input, value) {
  const descriptor = Object.getOwnPropertyDescriptor(input.constructor.prototype, "value");
  if (descriptor?.set) descriptor.set.call(input, value);
  else input.value = value;
  input.dispatchEvent(new Event("input", { bubbles: true }));
}

function visibleText(el) {
  const style = getComputedStyle(el);
  const box = el.getBoundingClientRect();
  if (style.display === "none" || style.visibility === "hidden" || box.width === 0 || box.height === 0) return "";
  return (el.innerText || el.textContent || el.getAttribute("aria-label") || el.title || "").trim();
}

function isVisible(node) {
  const rect = node.getBoundingClientRect();
  const style = getComputedStyle(node);
  return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
}

function pageClue() {
  return String(document.body?.innerText || "").replace(/\s+/g, " ").slice(0, 1500);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
