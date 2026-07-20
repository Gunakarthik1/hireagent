/**
 * HireAgent Fill — Settings Script
 */

const FIELDS = [
  "apiKey", "firstName", "lastName", "email", "phone",
  "linkedin", "github", "website", "workAuth",
  "address", "city", "state", "zip", "country",
  "university", "degree", "major", "gradYear", "gpa",
  "currentCompany", "currentTitle", "yearsExp", "targetRole", "targetSalary",
  "skills", "gender", "race",
];

const PROFILE_FIELDS = FIELDS.filter(f => f !== "apiKey");

document.addEventListener("DOMContentLoaded", async () => {
  await loadSaved();

  document.getElementById("saveBtn").addEventListener("click", save);
  document.getElementById("clearBtn").addEventListener("click", clearAll);
  document.getElementById("testApiBtn").addEventListener("click", testApi);

  // Import from HireAgent export
  const importBtn = document.getElementById("importBtn");
  const importFile = document.getElementById("importFile");
  importBtn.addEventListener("click", () => importFile.click());
  importFile.addEventListener("change", importProfile);
});

async function loadSaved() {
  const data = await chrome.storage.local.get(["apiKey", "profile"]);

  if (data.apiKey) {
    document.getElementById("apiKey").value = data.apiKey;
  }

  if (data.profile) {
    for (const key of PROFILE_FIELDS) {
      const el = document.getElementById(key);
      if (el && data.profile[key] !== undefined) {
        el.value = Array.isArray(data.profile[key])
          ? data.profile[key].join(", ")
          : data.profile[key];
      }
    }
  }
}

async function save() {
  const apiKey = document.getElementById("apiKey").value.trim();

  const profile = {};
  for (const key of PROFILE_FIELDS) {
    const el = document.getElementById(key);
    if (!el) continue;
    const val = el.value.trim();
    if (key === "skills") {
      profile[key] = val ? val.split(",").map(s => s.trim()).filter(Boolean) : [];
    } else {
      profile[key] = val;
    }
  }

  await chrome.storage.local.set({ apiKey, profile });
  showToast("✅ Profile saved!", false);
}

async function clearAll() {
  if (!confirm("Clear all saved profile data?")) return;
  await chrome.storage.local.clear();
  for (const key of FIELDS) {
    const el = document.getElementById(key);
    if (el) el.value = "";
  }
  showToast("Cleared.", false);
}

async function testApi() {
  const apiKey = document.getElementById("apiKey").value.trim();
  if (!apiKey) {
    showToast("Enter an API key first.", true);
    return;
  }

  const btn = document.getElementById("testApiBtn");
  btn.textContent = "Testing...";
  btn.disabled = true;

  try {
    const res = await fetch("https://integrate.api.nvidia.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Authorization": `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "meta/llama-3.1-70b-instruct",
        messages: [{ role: "user", content: "Say OK" }],
        max_tokens: 5,
      }),
    });

    if (res.ok) {
      showToast("✅ API key works!", false);
    } else {
      const text = await res.text();
      showToast(`Error ${res.status}: ${text.slice(0, 80)}`, true);
    }
  } catch (e) {
    showToast(`Network error: ${e.message}`, true);
  } finally {
    btn.textContent = "Test";
    btn.disabled = false;
  }
}

async function importProfile(e) {
  const file = e.target.files[0];
  if (!file) return;
  const status = document.getElementById("importStatus");
  status.textContent = "Reading...";

  try {
    const text = await file.text();
    const data = JSON.parse(text);

    // Fill fields from imported data
    for (const key of PROFILE_FIELDS) {
      const el = document.getElementById(key);
      if (!el || data[key] === undefined) continue;
      el.value = Array.isArray(data[key]) ? data[key].join(", ") : data[key];
    }

    status.textContent = "✅ Imported! Click Save to apply.";
    status.style.color = "#4ade80";
    showToast("Profile imported — click Save to store it.", false);
  } catch (err) {
    status.textContent = "Error: " + err.message;
    status.style.color = "#f87171";
    showToast("Import failed: " + err.message, true);
  }

  // Reset so same file can be re-selected
  e.target.value = "";
}

function showToast(msg, isError) {
  const toast = document.getElementById("toast");
  toast.textContent = msg;
  toast.className = `toast${isError ? " error" : ""}`;
  toast.style.display = "block";
  setTimeout(() => { toast.style.display = "none"; }, 3000);
}
