/* Toolbar popup: connection and memory summary only. */
const BACKEND = "http://127.0.0.1:8000";
const esc = s => String(s ?? "").replace(/[&<>\"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"}[c]));

document.getElementById("open").addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "kivi-toggle-from-popup" }, () => window.close());
});

(async function load() {
  const dot = document.getElementById("dot"), state = document.getElementById("state"), body = document.getElementById("body");
  try {
    const [statusRes, memoryRes] = await Promise.all([fetch(`${BACKEND}/api/status`), fetch(`${BACKEND}/api/memory`)]);
    if (!statusRes.ok || !memoryRes.ok) throw new Error("backend error");
    const status = await statusRes.json(), memory = await memoryRes.json();
    dot.className = "dot on";
    state.textContent = `connected · ${status.backend}`;
    const c = memory.counts || {}, prefs = memory.memory?.preference || [];
    const rules = prefs.filter(p => p.status === "active").slice(0, 3);
    const pending = prefs.filter(p => p.status === "observed");
    body.innerHTML = `<section><h3>What Kivi knows</h3><div class="nums"><div class="num">${c.facts || 0}<span>words</span></div><div class="num">${c.rules_active || 0}<span>rules</span></div><div class="num">${c.episodes || 0}<span>dictations</span></div></div></section><section><h3>Rules in force here</h3>${rules.length ? rules.map(r => `<div class="li">${esc(r.body)}</div>`).join("") : `<p>None yet. Say "remember that..." on any page.</p>`}</section>${pending.length ? `<section><h3>Noticed, not applied</h3><p>${pending.length} guess${pending.length > 1 ? "es" : ""} waiting for confirmation.</p></section>` : ""}<section><h3>Scope</h3><p>Selecting text tells Kivi <em>where</em>. Speaking tells it <em>what</em>. Nothing is written back until you press Apply.</p></section>`;
  } catch {
    dot.className = "dot off"; state.textContent = "not running";
    body.innerHTML = `<div class="err">Kivi's backend is not reachable at ${BACKEND}.<br><br>Start it with:<br><code>python run.py</code></div>`;
  }
})();
