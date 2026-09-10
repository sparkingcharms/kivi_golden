/* Service worker: open or inject the page panel. No product logic lives here. */

async function toggle(tab) {
  if (!tab || !tab.id) return;
  try {
    await chrome.tabs.sendMessage(tab.id, { type: "kivi-open" });
  } catch {
    try {
      await chrome.scripting.insertCSS({ target: { tabId: tab.id }, files: ["content.css"] });
      await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
      await chrome.tabs.sendMessage(tab.id, { type: "kivi-open" });
    } catch (e) {
      console.warn("Kivi cannot run on this page:", e.message);
    }
  }
}

chrome.commands.onCommand.addListener((command) => {
  if (command === "open-kivi") {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => toggle(tab));
  }
});

chrome.runtime.onMessage.addListener((msg, _sender, reply) => {
  if (msg?.type === "kivi-toggle-from-popup") {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      toggle(tab);
      reply({ ok: true });
    });
    return true;
  }
});
