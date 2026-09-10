# Kivi - Chrome extension

This is a secondary surface for Kivi. The primary review surface remains the local app in `RUN.md`. The extension adds the real-world layer: Kivi can sit over an actual Gmail, Slack, WhatsApp Web, Notion, Docs, Teams or other browser page and use the current page selection as context.

## Install

1. Start the backend from the project root with `python run.py`.
2. Open `chrome://extensions`.
3. Enable **Developer mode**.
4. Click **Load unpacked** and select this `extension/` folder.
5. Open a supported web app and use **Ctrl+Shift+K**. `Alt+Shift+K` is the page-level fallback.

The extension is a local development build and talks only to `http://127.0.0.1:8000`.

## Interaction

**Where:** select the text on the page.

**What:** speak or type what you want done.

**Understand:** Kivi interprets the request using the current app and selected text.

**Preview:** the proposed result is shown before the page changes.

**Apply:** only the explicit Apply action writes back to an editable field. If Kivi cannot safely edit the target, it copies the result instead.

Nothing is silently submitted, sent, posted or clicked on the user's behalf.

## Supported surfaces

| Host | App context |
| --- | --- |
| `mail.google.com` | Gmail |
| `outlook.live.com`, `outlook.office.com` | Mail |
| `app.slack.com` | Slack |
| `web.whatsapp.com` | WhatsApp |
| `notion.so`, `notion.site` | Notion |
| `github.dev`, `vscode.dev` | Cursor |
| `docs.google.com` | Docs |
| `teams.microsoft.com`, `teams.live.com` | Teams |
| anything else | Chrome |

## Backend contract

`POST http://127.0.0.1:8000/api/ask` receives `text`, `app` and `selection`. The toolbar popup reads `/api/status` and `/api/memory` for connection and memory summaries.

The backend emits CORS headers only for extension origins. The extension does not expose the memory API to the host page.

## Review notes

- Typed input always works even when browser speech recognition is unavailable.
- Browser speech recognition is only a development ASR surface. It is not Sarvam ASR and should not be treated as representative of final multilingual speech quality.
- Language chips describe how the user speaks. They do not force an output language.
- Google Docs is limited because much of its editing surface is canvas-based rather than normal editable DOM.
- The build is single-user and localhost-only. There is no authentication or remote backend.

## Validation

The extension JavaScript is syntax-checked with Node. The Python application is syntax-checked with `python -m compileall`. Full `verify.py` requires the project's Python dependencies to be installed first.
