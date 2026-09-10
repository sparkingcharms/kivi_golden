/* Kivi page layer.
 *
 * Reads the current page selection, captures typed/voice intent, asks the
 * local backend, shows a preview, and waits for explicit Apply.
 */

const BACKEND = "http://127.0.0.1:8000";
const APP_BY_HOST = [
  [/mail\.google\./, "Gmail"],
  [/outlook\.(live|office)\./, "Mail"],
  [/(app|.*\.)slack\.com/, "Slack"],
  [/web\.whatsapp\.com/, "WhatsApp"],
  [/(notion\.so|notion\.site)/, "Notion"],
  [/(github\.dev|vscode\.dev|cursor\.)/, "Cursor"],
  [/docs\.google\./, "Docs"],
  [/teams\.(microsoft|live)\./, "Teams"]
];

function currentApp() {
  const host = location.hostname;
  for (const [re, name] of APP_BY_HOST) if (re.test(host)) return name;
  return "Chrome";
}

let anchor = null;

function readSelection() {
  const el = document.activeElement;
  if (el && (el.tagName === "TEXTAREA" ||
      (el.tagName === "INPUT" && /^(text|search|email|url)$/i.test(el.type)))) {
    const { selectionStart: s, selectionEnd: e, value } = el;
    if (s !== e) return { text: value.slice(s, e), kind: "field", el, start: s, end: e };
  }

  const sel = window.getSelection();
  const text = sel ? sel.toString().trim() : "";
  if (text) return {
    text,
    kind: "document",
    range: sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null
  };
  return null;
}

async function applyText(replacement) {
  if (!anchor) return "no-target";

  if (anchor.kind === "field" && document.body.contains(anchor.el)) {
    const el = anchor.el;
    const before = el.value.slice(0, anchor.start);
    const after = el.value.slice(anchor.end);
    el.focus();
    el.value = before + replacement + after;
    const caret = before.length + replacement.length;
    el.setSelectionRange(caret, caret);
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return "applied";
  }

  if (anchor.kind === "document" && anchor.range) {
    const host = anchor.range.commonAncestorContainer;
    const editable = host.nodeType === 1
      ? host.closest("[contenteditable='true']")
      : host.parentElement?.closest("[contenteditable='true']");
    if (editable) {
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(anchor.range);
      editable.focus();
      document.execCommand("insertText", false, replacement);
      return "applied";
    }
  }

  try {
    await navigator.clipboard.writeText(replacement);
    return "copied";
  } catch {
    return "no-target";
  }
}

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
let recogniser = null;
let listening = false;
const LANGS = [["en-IN", "English"], ["ta-IN", "தமிழ்"], ["hi-IN", "हिन्दी"], ["te-IN", "తెలుగు"]];

function getLang() { return localStorage.getItem("kivi-lang") || "en-IN"; }

function startListening(onPartial, onFinal, onError) {
  if (!SR) { onError("Speech recognition is unavailable. Type instead."); return; }
  stopListening();
  recogniser = new SR();
  recogniser.lang = getLang();
  recogniser.interimResults = true;
  recogniser.continuous = false;
  recogniser.maxAlternatives = 1;
  let finalText = "";
  recogniser.onresult = (ev) => {
    let interim = "";
    for (let i = ev.resultIndex; i < ev.results.length; i++) {
      const r = ev.results[i];
      if (r.isFinal) finalText += r[0].transcript;
      else interim += r[0].transcript;
    }
    onPartial((finalText + interim).trim());
  };
  recogniser.onerror = (ev) => {
    listening = false;
    onError(ev.error === "not-allowed" ? "Microphone blocked. Allow it for this site, or type instead." : `Speech error: ${ev.error}. Type instead.`);
  };
  recogniser.onend = () => {
    listening = false;
    if (finalText.trim()) onFinal(finalText.trim());
  };
  listening = true;
  try { recogniser.start(); } catch (e) { listening = false; onError(e.message); }
}

function stopListening() {
  if (recogniser) { try { recogniser.stop(); } catch {} recogniser = null; }
  listening = false;
}

let root = null, shadow = null, lastResult = null, lastBody = "";
const esc = (s) => String(s ?? "").replace(/[&<>\"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;" }[c]));

function ensurePanel() {
  if (root) return;
  root = document.createElement("div");
  root.id = "kivi-root";
  shadow = root.attachShadow({ mode: "open" });
  const style = document.createElement("style");
  style.textContent = PANEL_CSS;
  shadow.append(style);
  const box = document.createElement("div");
  box.className = "wrap";
  shadow.append(box);
  document.documentElement.append(root);
  shadow.addEventListener("click", onClick);
  shadow.addEventListener("keydown", e => {
    if (e.key === "Escape") { e.stopPropagation(); close(); }
    if (e.key === "Enter" && e.target.id === "kivi-input") send();
  });
}

function close() { stopListening(); root?.remove(); root = null; shadow = null; }

function resultBody(r) {
  const tag = t => `<span class="t">${esc(t)}</span>`;
  if (r.status === "unclear" || r.status === "ambiguous") {
    const opts = (r.options || []).map(o => {
      const text = typeof o === "string" ? o : o.body || "";
      return `<button class="opt" data-fill="${esc(text)}">${esc(text.slice(0, 70))}</button>`;
    }).join("");
    return `<div class="out ask">${esc(r.say || "Which did you mean?")}</div>${r.reason ? `<div class="tags">${tag(r.reason)}</div>` : ""}${opts ? `<div class="opts">${opts}</div>` : ""}`;
  }
  if (r.status === "declined") return `<div class="out no">${esc(r.say || "I can't do that.")}</div>`;
  if (r.status === "answered") {
    const rows = [...(r.active || []), ...(r.observed || [])].map(m => `<div class="li">${esc(m.body)}</div>`).join("");
    return `<div class="out">${esc(r.say || "")}</div>${rows}`;
  }
  const text = r.after || r.draft || r.reshaped?.after || r.episode?.body || r.say || "";
  const applied = r.applied || r.reshaped?.applied || [];
  const found = r.episode ? `<div class="tags">${tag(r.episode.scope_app || "")}${tag(new Date(r.episode.created_ts * 1000).toLocaleString(undefined, { weekday: "short", hour: "2-digit", minute: "2-digit" }))}</div>` : "";
  const canApply = !!(r.after || r.draft || r.reshaped?.after);
  return `<div class="out">${esc(text)}</div>${found}${applied.length ? `<div class="tags">${applied.map(tag).join("")}</div>` : ""}<div class="foot"><span class="note">${esc(r.note || "Nothing has changed on the page yet.")}</span>${canApply ? `<button class="apply" data-act="apply">Apply</button>` : ""}</div>`;
}

function render(state = {}) {
  ensurePanel();
  const box = shadow.querySelector(".wrap");
  const sel = anchor?.text || "";
  const langs = LANGS.map(([code, label]) => `<button class="chip ${getLang() === code ? "on" : ""}" data-lang="${code}">${label}</button>`).join("");
  box.innerHTML = `<header><span class="dot ${listening ? "live" : ""}"></span><b>Kivi</b><span class="meta">${esc(currentApp())}${sel ? ` · ${sel.split(/\s+/).length} words selected` : " · nothing selected"}</span><button class="x" data-act="close">×</button></header>${sel ? `<div class="sel">${esc(sel.slice(0, 260))}${sel.length > 260 ? "…" : ""}</div>` : ""}<div class="row"><input id="kivi-input" placeholder="${listening ? "Listening…" : "Say what to do, or type it"}" value="${esc(state.said || "")}" autocomplete="off" spellcheck="false"><button class="mic ${listening ? "live" : ""}" data-act="mic">${listening ? "Stop" : "Speak"}</button><button class="go" data-act="send">Ask</button></div><div class="langs">${langs}</div>${state.busy ? `<div class="note">Thinking…</div>` : ""}${state.error ? `<div class="err">${esc(state.error)}</div>` : ""}${state.body || ""}`;
  const input = shadow.getElementById("kivi-input");
  if (input && !listening) input.focus();
}

async function onClick(e) {
  const t = e.target.closest("[data-act], [data-lang], [data-fill]");
  if (!t) return;
  e.stopPropagation();
  if (t.dataset.lang) { localStorage.setItem("kivi-lang", t.dataset.lang); render({ said: shadow.getElementById("kivi-input")?.value, body: lastBody }); return; }
  if (t.dataset.fill) { shadow.getElementById("kivi-input").value = t.dataset.fill; return; }
  if (t.dataset.act === "close") return close();
  if (t.dataset.act === "mic") return listening ? (stopListening(), render({ body: lastBody })) : mic();
  if (t.dataset.act === "send") return send();
  if (t.dataset.act === "apply") {
    const text = lastResult?.after || lastResult?.draft || lastResult?.reshaped?.after;
    const how = await applyText(text);
    t.textContent = how === "applied" ? "Applied" : how === "copied" ? "Copied - paste it in" : "Nowhere to apply";
    t.disabled = true;
  }
}

function mic() {
  render({});
  startListening(partial => { const i = shadow.getElementById("kivi-input"); if (i) i.value = partial; }, final => { render({ said: final, body: lastBody }); send(final); }, msg => render({ error: msg || undefined, body: lastBody }));
}

async function send(override) {
  const said = (override || shadow.getElementById("kivi-input")?.value || "").trim();
  if (!said) return;
  stopListening();
  lastBody = "";
  render({ said, busy: true });
  try {
    const res = await fetch(`${BACKEND}/api/ask`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: said, app: currentApp(), selection: anchor?.text || null }) });
    if (!res.ok) throw new Error(`backend returned ${res.status}`);
    lastResult = await res.json();
    lastBody = resultBody(lastResult);
    render({ said, body: lastBody });
  } catch {
    render({ said, error: `Cannot reach Kivi at ${BACKEND}. Start it with: python run.py` });
  }
}

function open() { anchor = readSelection(); lastResult = null; lastBody = ""; render({}); }

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "kivi-open") { root ? close() : open(); reply({ ok: true }); }
  return true;
});

window.addEventListener("keydown", e => {
  if (e.altKey && e.shiftKey && (e.key === "K" || e.key === "k")) { e.preventDefault(); root ? close() : open(); }
}, true);

const PANEL_CSS = `
:host { all: initial; }
.wrap { position: fixed; right: 20px; bottom: 20px; width: 380px; z-index: 2147483647; background: #161a15; color: #dfe4d8; border-radius: 10px; box-shadow: 0 16px 44px rgba(0,0,0,.42); overflow: hidden; font-family: -apple-system,system-ui,sans-serif; font-size: 14px; line-height: 1.5; }
header { display:flex; align-items:center; gap:8px; padding:11px 13px; border-bottom:1px solid rgba(223,228,216,.1); } header b { font-size:15px; color:#e7ebe2; } .meta { margin-left:auto; font-size:11px; color:#a9b19d; text-transform:uppercase; } .x { background:none; border:0; color:#6a7161; font-size:19px; cursor:pointer; } .dot { width:13px; height:13px; border-radius:50%; background:#8fc46e; flex:0 0 auto; } .dot.live { animation:pulse 1.1s ease-in-out infinite; } @keyframes pulse { 50% { box-shadow:0 0 0 6px rgba(143,196,110,0); } }
.sel { margin:11px 13px 0; padding:9px 10px; border-radius:6px; font-size:13px; background:rgba(143,196,110,.09); border:1px solid rgba(143,196,110,.22); color:#c9e5b3; } .row { display:flex; gap:6px; padding:11px 13px 0; } .row input { flex:1; min-width:0; background:#1b1f19; border:1px solid rgba(223,228,216,.16); border-radius:6px; padding:9px 10px; color:#dfe4d8; font:inherit; } .mic,.go { border:0; border-radius:6px; padding:9px 11px; font-weight:600; cursor:pointer; font:inherit; } .mic { background:rgba(223,228,216,.1); color:#dfe4d8; } .mic.live { background:#e2d3a8; color:#2a2410; } .go,.apply { background:#8fc46e; color:#12200a; } .langs { display:flex; gap:5px; padding:8px 13px 0; } .chip,.opt { background:none; border:1px solid rgba(223,228,216,.18); color:#a9b19d; border-radius:13px; padding:4px 9px; cursor:pointer; font:inherit; font-size:11.5px; } .chip.on { border-color:#8fc46e; color:#c9e5b3; } .out,.li { margin:11px 13px 0; padding:10px 11px; border-radius:6px; background:#1b1f19; white-space:pre-wrap; } .out.ask { background:rgba(226,211,168,.1); color:#e2d3a8; } .out.no { background:rgba(226,168,168,.1); color:#e6b8b8; } .li { margin-top:6px; font-size:13.5px; } .tags,.opts { display:flex; flex-wrap:wrap; gap:5px; padding:8px 13px 0; } .t { font-size:11.5px; padding:3px 8px; border-radius:10px; background:rgba(143,196,110,.16); color:#c9e5b3; } .foot { display:flex; align-items:center; gap:8px; padding:11px 13px; margin-top:10px; border-top:1px solid rgba(223,228,216,.1); } .note { font-size:11.5px; color:#a9b19d; flex:1; padding:8px 13px; } .apply { border:0; border-radius:13px; padding:6px 13px; font-size:12.5px; font-weight:600; cursor:pointer; } .err { margin:11px 13px; padding:9px 10px; border-radius:6px; background:rgba(226,168,168,.1); color:#e6b8b8; }`;
