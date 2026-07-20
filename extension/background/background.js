/**
 * HireAgent Fill — Background Service Worker
 * Handles LLM API calls to NVIDIA NIM and stores field count per tab.
 */

const NIM_BASE_URL = "https://integrate.api.nvidia.com/v1";
const FILL_MODEL = "meta/llama-3.1-70b-instruct"; // fast, reliable for form filling

// Track field counts per tab so the popup badge shows them
const tabFieldCounts = {};

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "PAGE_FIELDS_DETECTED") {
    if (sender.tab?.id) {
      tabFieldCounts[sender.tab.id] = msg.fieldCount;
      // Update badge
      chrome.action.setBadgeText({
        text: msg.fieldCount > 0 ? String(msg.fieldCount) : "",
        tabId: sender.tab.id,
      });
      chrome.action.setBadgeBackgroundColor({ color: "#4ade80", tabId: sender.tab.id });
    }
    return false;
  }

  if (msg.type === "FILL_WITH_AI") {
    handleFillWithAI(msg.fields, msg.profile, sender.tab?.id)
      .then(result => sendResponse({ ok: true, ...result }))
      .catch(err => sendResponse({ ok: false, error: err.message }));
    return true; // keep channel open for async response
  }

  if (msg.type === "GET_TAB_FIELD_COUNT") {
    sendResponse({ count: tabFieldCounts[msg.tabId] || 0 });
    return false;
  }
});

// Clear badge when tab navigates
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    delete tabFieldCounts[tabId];
    chrome.action.setBadgeText({ text: "", tabId }).catch(() => {});
  }
});

async function handleFillWithAI(fields, profile, tabId) {
  const { apiKey } = await chrome.storage.local.get("apiKey");
  if (!apiKey) throw new Error("No API key set. Go to extension Settings.");

  const prompt = buildFillPrompt(fields, profile);

  const res = await fetch(`${NIM_BASE_URL}/chat/completions`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: FILL_MODEL,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        { role: "user", content: prompt },
      ],
      max_tokens: 2048,
      temperature: 0.1,
    }),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`NIM API error ${res.status}: ${text.slice(0, 200)}`);
  }

  const data = await res.json();
  const content = data.choices?.[0]?.message?.content || "";

  // Parse JSON from response
  const fieldMap = parseFieldMap(content, fields);
  return { fieldMap, rawResponse: content };
}

const SYSTEM_PROMPT = `You are an expert at filling job application forms.
Given a list of form fields and a candidate profile, return a JSON object mapping each field's xpathId to the correct value to fill.

Rules:
- Return ONLY valid JSON. No markdown, no explanation.
- For select fields, use one of the provided options exactly.
- For checkbox/radio: use "yes" or "no".
- For phone: format as +1-XXX-XXX-XXXX or (XXX) XXX-XXXX.
- For salary: use a specific number (e.g. "95000") or range from the profile's target.
- For "How did you hear about us?": use "LinkedIn" or "Indeed" or "Online Job Board".
- For "authorized to work in US": "yes".
- For "require sponsorship now or in the future": "no" (OPT counts as no sponsorship needed).
- For disability status: "No, I Don't Have a Disability" or equivalent "No" option.
- For veteran status: "I am not a protected veteran" or equivalent.
- For gender: "Prefer not to say" unless profile specifies.
- For race/ethnicity: "Prefer not to say" unless profile specifies.
- Leave fields empty (empty string) if no answer can be confidently determined.
- Do NOT invent information not in the profile.`;

function buildFillPrompt(fields, profile) {
  const fieldList = fields.map(f => {
    let desc = `- xpathId: ${f.xpathId}\n  label: "${f.label}"\n  type: ${f.type}`;
    if (f.required) desc += " (REQUIRED)";
    if (f.options?.length) desc += `\n  options: [${f.options.slice(0, 20).join(", ")}]`;
    if (f.currentValue) desc += `\n  currentValue: "${f.currentValue}"`;
    return desc;
  }).join("\n\n");

  const profileText = `
Name: ${profile.firstName} ${profile.lastName}
Email: ${profile.email}
Phone: ${profile.phone}
Address: ${profile.city}, ${profile.state} ${profile.zip}, ${profile.country || "United States"}
LinkedIn: ${profile.linkedin || ""}
GitHub: ${profile.github || ""}
Website/Portfolio: ${profile.website || ""}
University: ${profile.university}
Degree: ${profile.degree}
Major: ${profile.major}
Graduation: ${profile.gradYear}
GPA: ${profile.gpa || ""}
Current/Last Company: ${profile.currentCompany || ""}
Current/Last Title: ${profile.currentTitle || ""}
Years of Experience: ${profile.yearsExp || "0-1"}
Target Role: ${profile.targetRole || "Software Engineer"}
Target Salary: ${profile.targetSalary || "95000"}
Skills: ${(profile.skills || []).join(", ")}
Work Authorization: ${profile.workAuth || "OPT - no sponsorship needed"}
Eligible to work in US: Yes
Requires sponsorship: No
`.trim();

  return `CANDIDATE PROFILE:\n${profileText}\n\nFORM FIELDS:\n${fieldList}\n\nReturn JSON object: { "<xpathId>": "<value>", ... }`;
}

function parseFieldMap(content, fields) {
  // Strip markdown fences
  let cleaned = content.trim();
  if (cleaned.startsWith("```")) {
    cleaned = cleaned.replace(/^```[a-z]*\n?/, "").replace(/\n?```$/, "").trim();
  }

  // Extract JSON object
  const match = cleaned.match(/\{[\s\S]*\}/);
  if (!match) return {};

  try {
    return JSON.parse(match[0]);
  } catch {
    return {};
  }
}
