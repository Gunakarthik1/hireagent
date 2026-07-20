/**
 * HireAgent Fill — Popup Script
 */

let currentTabId = null;
let scannedFields = [];

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  currentTabId = tab?.id;

  // Wire buttons
  document.getElementById("fillBtn").addEventListener("click", onFillClick);
  document.getElementById("rescanBtn").addEventListener("click", () => scanPage(tab));
  document.getElementById("settingsBtn").addEventListener("click", openSettings);
  document.getElementById("editProfileBtn").addEventListener("click", openSettings);

  // Check profile exists
  const { profile, apiKey } = await chrome.storage.local.get(["profile", "apiKey"]);

  if (!profile || !apiKey) {
    setStatus("⚙️", "Setup needed", "Add your profile & API key in Settings", true);
    document.getElementById("fillBtn").disabled = true;
    return;
  }

  // Scan the page
  await scanPage(tab);
});

async function scanPage(tab) {
  resetResult();
  setStatus("🔍", "Scanning...", "Detecting form fields", true);
  setFieldCount(0);

  try {
    // Inject content script if not already present
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      files: ["content/content.js"],
    }).catch(() => {}); // Already injected = no-op

    const response = await chrome.tabs.sendMessage(tab.id, { type: "SCAN_FIELDS" });
    scannedFields = response?.fields || [];

    if (scannedFields.length === 0) {
      setStatus("🤷", "No fields found", "This page may not be a job application form", false);
      document.getElementById("fillBtn").disabled = true;
    } else {
      setStatus("✅", "Form detected", `${scannedFields.length} fillable fields found`, false);
      setFieldCount(scannedFields.length);
      document.getElementById("fillBtn").disabled = false;
    }
  } catch (err) {
    setStatus("⚠️", "Cannot scan", "Try refreshing the page", false);
    document.getElementById("fillBtn").disabled = true;
  }
}

// ── Fill ─────────────────────────────────────────────────────────────────────

async function onFillClick() {
  const { profile, apiKey } = await chrome.storage.local.get(["profile", "apiKey"]);

  if (!apiKey) {
    showResult("error", "No API Key", "Add your NVIDIA NIM API key in Settings.");
    return;
  }
  if (!profile) {
    showResult("error", "No Profile", "Add your profile in Settings.");
    return;
  }
  if (scannedFields.length === 0) {
    showResult("error", "No Fields", "Rescan the page first.");
    return;
  }

  setFillBtnLoading(true);
  showProgress(0, "Asking AI to fill fields...");

  try {
    showProgress(20, "Sending fields to AI...");

    // Ask background to call AI
    const response = await chrome.runtime.sendMessage({
      type: "FILL_WITH_AI",
      fields: scannedFields,
      profile,
    });

    if (!response?.ok) {
      throw new Error(response?.error || "Unknown error from background");
    }

    showProgress(70, "Filling form...");

    // Send fill instructions to content script
    const fillResponse = await chrome.tabs.sendMessage(currentTabId, {
      type: "FILL_FIELDS",
      fieldMap: response.fieldMap,
    });

    showProgress(100, "Done!");
    await sleep(400);
    hideProgress();

    const filled = fillResponse?.filled ?? Object.keys(response.fieldMap).length;
    const total = scannedFields.length;
    showResult(
      "success",
      `Filled ${filled} / ${total} fields`,
      `Review the form and make any corrections before submitting.`
    );
  } catch (err) {
    hideProgress();
    showResult("error", "Fill Failed", err.message);
  } finally {
    setFillBtnLoading(false);
  }
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function setStatus(icon, title, subtitle, dim) {
  document.getElementById("statusIcon").textContent = icon;
  document.getElementById("statusTitle").textContent = title;
  document.getElementById("statusSubtitle").textContent = subtitle;
  document.getElementById("statusCard").style.opacity = dim ? "0.6" : "1";
}

function setFieldCount(n) {
  const el = document.getElementById("fieldCount");
  el.textContent = n;
  el.classList.toggle("zero", n === 0);
}

function setFillBtnLoading(loading) {
  const btn = document.getElementById("fillBtn");
  const icon = document.getElementById("fillBtnIcon");
  const text = document.getElementById("fillBtnText");
  btn.disabled = loading;
  btn.classList.toggle("loading", loading);
  if (loading) {
    icon.className = "spinner";
    icon.textContent = "";
    text.textContent = "Filling...";
  } else {
    icon.className = "";
    icon.textContent = "✨";
    text.textContent = "Auto-Fill Form";
  }
}

function showProgress(pct, label) {
  const section = document.getElementById("progressSection");
  section.style.display = "block";
  document.getElementById("progressBar").style.width = `${pct}%`;
  document.getElementById("progressLabel").textContent = label;
}

function hideProgress() {
  document.getElementById("progressSection").style.display = "none";
}

function showResult(type, title, body) {
  const card = document.getElementById("resultCard");
  card.style.display = "block";
  card.className = `result ${type}`;
  document.getElementById("resultTitle").textContent = title;
  document.getElementById("resultBody").textContent = body;
}

function resetResult() {
  document.getElementById("resultCard").style.display = "none";
  hideProgress();
}

function openSettings() {
  chrome.runtime.openOptionsPage();
}

function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}
