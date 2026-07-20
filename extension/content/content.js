/**
 * HireAgent Fill — Content Script
 * Scans the current page for form fields and fills them on command.
 */

const HIREAGENT_PREFIX = "__hireagent__";

// ── Field Detection ──────────────────────────────────────────────────────────

function getLabel(el) {
  // 1. aria-label
  if (el.getAttribute("aria-label")) return el.getAttribute("aria-label").trim();

  // 2. <label for="id">
  if (el.id) {
    const lbl = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (lbl) return lbl.innerText.trim();
  }

  // 3. Wrapping label
  const wrap = el.closest("label");
  if (wrap) {
    const clone = wrap.cloneNode(true);
    clone.querySelectorAll("input,select,textarea").forEach(n => n.remove());
    const text = clone.innerText.trim();
    if (text) return text;
  }

  // 4. Preceding sibling / parent text
  const parent = el.parentElement;
  if (parent) {
    const prev = el.previousElementSibling;
    if (prev && prev.innerText) return prev.innerText.trim();
    // Look for a <p> or <span> labelling sibling
    const siblings = Array.from(parent.children);
    for (const sib of siblings) {
      if (sib === el) break;
      if (sib.innerText && !sib.querySelector("input,select,textarea")) {
        return sib.innerText.trim();
      }
    }
  }

  // 5. placeholder
  if (el.placeholder) return el.placeholder.trim();

  // 6. name attribute
  if (el.name) return el.name.replace(/[_\-]/g, " ").trim();

  return null;
}

function isVisible(el) {
  const style = window.getComputedStyle(el);
  return (
    style.display !== "none" &&
    style.visibility !== "hidden" &&
    style.opacity !== "0" &&
    el.offsetWidth > 0 &&
    el.offsetHeight > 0
  );
}

function isRequired(el) {
  return (
    el.required ||
    el.getAttribute("aria-required") === "true" ||
    (el.closest("[data-required]") !== null) ||
    (el.closest(".required") !== null)
  );
}

function scanFields() {
  const fields = [];
  const seen = new Set();

  const inputs = document.querySelectorAll(
    'input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="reset"]):not([type="file"]):not([type="image"]):not([type="checkbox"]):not([type="radio"]), textarea, select'
  );

  for (const el of inputs) {
    if (!isVisible(el)) continue;

    const label = getLabel(el);
    if (!label) continue;

    // Deduplicate by label
    const key = label.toLowerCase().replace(/\s+/g, " ");
    if (seen.has(key)) continue;
    seen.add(key);

    const field = {
      label,
      type: el.tagName.toLowerCase() === "select" ? "select" :
            el.tagName.toLowerCase() === "textarea" ? "textarea" :
            (el.type || "text"),
      required: isRequired(el),
      options: [],
      currentValue: el.value || "",
      xpathId: getXpathId(el),
    };

    if (el.tagName.toLowerCase() === "select") {
      field.options = Array.from(el.options)
        .filter(o => o.value)
        .map(o => o.text.trim());
    }

    fields.push(field);
  }

  return fields;
}

function getXpathId(el) {
  // Returns a stable enough identifier for the element
  if (el.id) return `#${el.id}`;
  if (el.name) return `[name="${el.name}"]`;
  // Fallback: index among siblings of same type
  const tag = el.tagName.toLowerCase();
  const all = Array.from(document.querySelectorAll(tag));
  const idx = all.indexOf(el);
  return `${tag}[${idx}]`;
}

// ── Field Filling ────────────────────────────────────────────────────────────

function findElement(xpathId) {
  if (xpathId.startsWith("#")) {
    return document.getElementById(xpathId.slice(1));
  }
  if (xpathId.startsWith("[name=")) {
    const name = xpathId.match(/\[name="(.+?)"\]/)?.[1];
    return name ? document.querySelector(`[name="${name}"]`) : null;
  }
  // tag[idx]
  const m = xpathId.match(/^(\w+)\[(\d+)\]$/);
  if (m) {
    const els = document.querySelectorAll(m[1]);
    return els[parseInt(m[2])] || null;
  }
  return null;
}

function nativeInputValueSet(el, value) {
  // React-compatible value injection
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype, "value"
  )?.set;
  const nativeTextareaSetter = Object.getOwnPropertyDescriptor(
    window.HTMLTextAreaElement.prototype, "value"
  )?.set;

  if (el.tagName === "INPUT" && nativeInputValueSetter) {
    nativeInputValueSetter.call(el, value);
  } else if (el.tagName === "TEXTAREA" && nativeTextareaSetter) {
    nativeTextareaSetter.call(el, value);
  } else {
    el.value = value;
  }

  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

function fillField(xpathId, value) {
  const el = findElement(xpathId);
  if (!el) return { ok: false, reason: "not found" };

  try {
    el.focus();

    if (el.tagName === "SELECT") {
      // Find best matching option
      const opts = Array.from(el.options);
      const val = value.toLowerCase();
      const match =
        opts.find(o => o.text.toLowerCase() === val) ||
        opts.find(o => o.text.toLowerCase().includes(val)) ||
        opts.find(o => o.value.toLowerCase() === val);

      if (match) {
        el.value = match.value;
        el.dispatchEvent(new Event("change", { bubbles: true }));
        return { ok: true };
      }
      return { ok: false, reason: `no option matching "${value}"` };
    }

    if (el.type === "checkbox" || el.type === "radio") {
      const shouldCheck = ["yes", "true", "1", "on"].includes(value.toLowerCase());
      el.checked = shouldCheck;
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return { ok: true };
    }

    // text / textarea
    nativeInputValueSet(el, value);
    el.blur();
    return { ok: true };
  } catch (e) {
    return { ok: false, reason: e.message };
  }
}

// ── Overlay UI ───────────────────────────────────────────────────────────────

function showFillBadge(count, total) {
  removeBadge();
  const badge = document.createElement("div");
  badge.id = `${HIREAGENT_PREFIX}badge`;
  badge.style.cssText = `
    position: fixed; bottom: 20px; right: 20px; z-index: 999999;
    background: #1a1a2e; color: #fff; border-radius: 12px;
    padding: 12px 18px; font-family: system-ui, sans-serif; font-size: 14px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4); display: flex; align-items: center; gap: 10px;
    border: 1px solid #4ade80;
  `;
  badge.innerHTML = `
    <span style="font-size:20px">✅</span>
    <div>
      <div style="font-weight:700;color:#4ade80">HireAgent Filled</div>
      <div style="opacity:0.8;font-size:12px">${count} of ${total} fields filled</div>
    </div>
    <button onclick="this.parentElement.remove()" style="
      background:none;border:none;color:#888;cursor:pointer;font-size:18px;padding:0;margin-left:8px
    ">×</button>
  `;
  document.body.appendChild(badge);
  setTimeout(removeBadge, 5000);
}

function showErrorBadge(msg) {
  removeBadge();
  const badge = document.createElement("div");
  badge.id = `${HIREAGENT_PREFIX}badge`;
  badge.style.cssText = `
    position: fixed; bottom: 20px; right: 20px; z-index: 999999;
    background: #1a1a2e; color: #fff; border-radius: 12px;
    padding: 12px 18px; font-family: system-ui, sans-serif; font-size: 14px;
    box-shadow: 0 4px 20px rgba(0,0,0,0.4); display: flex; align-items: center; gap: 10px;
    border: 1px solid #f87171;
  `;
  badge.innerHTML = `
    <span style="font-size:20px">⚠️</span>
    <div>
      <div style="font-weight:700;color:#f87171">HireAgent Error</div>
      <div style="opacity:0.8;font-size:12px">${msg}</div>
    </div>
    <button onclick="this.parentElement.remove()" style="
      background:none;border:none;color:#888;cursor:pointer;font-size:18px;padding:0;margin-left:8px
    ">×</button>
  `;
  document.body.appendChild(badge);
}

function removeBadge() {
  document.getElementById(`${HIREAGENT_PREFIX}badge`)?.remove();
}

// ── Message Handler ──────────────────────────────────────────────────────────

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "SCAN_FIELDS") {
    const fields = scanFields();
    sendResponse({ fields });
    return true;
  }

  if (msg.type === "FILL_FIELDS") {
    const { fieldMap } = msg; // { xpathId: value, ... }
    let filled = 0;
    const errors = [];

    for (const [xpathId, value] of Object.entries(fieldMap)) {
      if (!value) continue;
      const result = fillField(xpathId, value);
      if (result.ok) {
        filled++;
      } else {
        errors.push(`${xpathId}: ${result.reason}`);
      }
    }

    const total = Object.keys(fieldMap).length;
    showFillBadge(filled, total);
    sendResponse({ filled, total, errors });
    return true;
  }

  if (msg.type === "PING") {
    sendResponse({ alive: true, fieldCount: scanFields().length });
    return true;
  }
});

// Auto-scan on load and report field count to background
(function init() {
  const fields = scanFields();
  if (fields.length > 0) {
    chrome.runtime.sendMessage({
      type: "PAGE_FIELDS_DETECTED",
      url: window.location.href,
      fieldCount: fields.length,
    }).catch(() => {}); // background might not be listening yet
  }
})();
