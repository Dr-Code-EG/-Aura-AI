// Injected into chatgpt.com / chat.openai.com to programmatically
// attach a screenshot, type a question and read back the answer.
//
// The host application (PyQt) calls window.auraSendScreenshot(b64, question)
// from QWebChannel; this script wires up that bridge plus poll-and-read
// helpers that surface the latest assistant response back to the host.
//
// Resilience features:
//   * waits up to 30 s for ChatGPT's React app to mount (covers slow
//     cold loads, Cloudflare interstitials, redirect to /chat)
//   * detects login / OAuth URLs and surfaces them to the host so the
//     user can be prompted to sign in instead of getting a cryptic
//     "editor not found" error
//   * uses both DataTransfer drop *and* native file-input set so the
//     screenshot lands regardless of which entry point ChatGPT
//     happens to expose this week
//   * polls the assistant message + the "Stop" button to detect when
//     streaming actually finishes, then waits for ~1 s of stability

(function () {
  if (window.__auraChatGPTBridgeInstalled) {
    return;
  }
  window.__auraChatGPTBridgeInstalled = true;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function isLoginUrl(u) {
    if (!u) return false;
    return /\/(auth\/)?login/.test(u)
      || /\/auth\//.test(u)
      || /accounts\.google\.com/.test(u)
      || /login\.live\.com/.test(u)
      || /\.openai\.com\/auth/.test(u)
      || /appleid\.apple\.com/.test(u);
  }

  function base64ToBlob(b64, mime) {
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return new Blob([bytes], { type: mime || "image/png" });
  }

  function findEditor() {
    return (
      document.querySelector('div[contenteditable="true"]#prompt-textarea') ||
      document.querySelector('#prompt-textarea') ||
      document.querySelector('div[contenteditable="true"][data-virtualkeyboard]') ||
      document.querySelector('div[contenteditable="true"]') ||
      document.querySelector('textarea')
    );
  }

  function findFileInput() {
    return document.querySelector('input[type="file"]');
  }

  function findSendButton() {
    return (
      document.querySelector('button[data-testid="send-button"]') ||
      document.querySelector('button[aria-label="Send prompt"]') ||
      document.querySelector('button[aria-label*="Send" i]') ||
      document.querySelector('button[aria-label*="إرسال"]') ||
      document.querySelector('form button[type="submit"]')
    );
  }

  function isLoggedOut() {
    // ChatGPT renders prominent "Log in" / "Sign up" buttons in the top-right
    // when the visitor is anonymous. When signed in those are replaced by an
    // avatar / "New chat" controls.
    const buttons = document.querySelectorAll(
      'button, a[role="button"], a[href*="/auth/login"]'
    );
    for (const b of buttons) {
      const text = (b.innerText || b.textContent || "").trim().toLowerCase();
      if (text === "log in" || text === "sign up" || text === "sign up for free") {
        return true;
      }
    }
    return false;
  }

  // Wait up to `timeoutMs` for the ChatGPT React app to mount its
  // editor. Returns the editor element on success, `false` on timeout
  // (the editor genuinely never appeared — likely a DOM change on
  // ChatGPT's side or a stuck page), and `null` if the page navigated
  // to a login URL during the wait. The caller distinguishes those
  // two failure modes so the user gets the right error message.
  async function waitForEditor(timeoutMs) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (isLoginUrl(location.href)) return null;
      const editor = findEditor();
      if (editor) {
        // Tiny extra settle — sometimes the editor is in the DOM
        // before its event handlers have attached.
        await sleep(400);
        return editor;
      }
      await sleep(500);
    }
    return false;
  }

  // Try the native file-input route first (most reliable when the
  // input is already in the DOM). Fall back to a synthetic drop on
  // the editor for the cases where ChatGPT lazy-mounts the input.
  async function attachFile(editor, file) {
    const dt = new DataTransfer();
    dt.items.add(file);

    const input = findFileInput();
    if (input) {
      try {
        input.files = dt.files;
        input.dispatchEvent(new Event("change", { bubbles: true }));
        return;
      } catch (_) {
        // Some browsers reject programmatic file-input mutation;
        // fall through to the drop path.
      }
    }

    editor.focus();
    editor.dispatchEvent(
      new DragEvent("drop", {
        bubbles: true,
        cancelable: true,
        dataTransfer: dt,
      })
    );
    editor.dispatchEvent(
      new ClipboardEvent("paste", {
        bubbles: true,
        cancelable: true,
        clipboardData: dt,
      })
    );
  }

  async function setEditorText(editor, text) {
    if (editor instanceof HTMLTextAreaElement) {
      const setter = Object.getOwnPropertyDescriptor(
        window.HTMLTextAreaElement.prototype,
        "value"
      ).set;
      setter.call(editor, text);
      editor.dispatchEvent(new Event("input", { bubbles: true }));
      return;
    }
    // ProseMirror / contenteditable
    editor.focus();
    editor.innerHTML = "";
    document.execCommand("insertText", false, text);
    editor.dispatchEvent(new InputEvent("input", { bubbles: true }));
  }

  async function waitForUploadComplete(timeoutMs) {
    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      // ChatGPT shows a spinner / progress while the file uploads.
      const spinner = document.querySelector('[role="progressbar"]');
      if (!spinner) {
        return true;
      }
      await sleep(200);
    }
    return false;
  }

  async function clickSend() {
    const start = Date.now();
    while (Date.now() - start < 15000) {
      const btn = findSendButton();
      if (btn && !btn.disabled) {
        btn.click();
        return;
      }
      await sleep(200);
    }
    throw new Error("Send button never became clickable.");
  }

  function getLatestAssistantMessage() {
    const nodes = document.querySelectorAll(
      '[data-message-author-role="assistant"]'
    );
    if (nodes.length === 0) {
      return null;
    }
    const last = nodes[nodes.length - 1];
    return last.innerText || last.textContent || "";
  }

  function isAssistantStillStreaming() {
    // ChatGPT renders a stop button while the model is still generating.
    return Boolean(
      document.querySelector('button[data-testid="stop-button"]') ||
        document.querySelector('button[aria-label*="Stop" i]')
    );
  }

  async function waitForResponse(onUpdate, timeoutMs) {
    const start = Date.now();
    let lastText = "";
    let stable = 0;
    // Poll until streaming stops AND text settles for ~1s.
    while (Date.now() - start < timeoutMs) {
      const current = getLatestAssistantMessage() || "";
      if (current && current !== lastText) {
        lastText = current;
        stable = 0;
        if (onUpdate) {
          try { onUpdate(current); } catch (_) {}
        }
      } else if (current) {
        stable += 1;
      }
      if (current && !isAssistantStillStreaming() && stable >= 4) {
        return current;
      }
      await sleep(250);
    }
    return lastText || "";
  }

  window.auraSendScreenshot = async function (b64, question) {
    if (isLoginUrl(location.href)) {
      throw new Error("AURA_LOGIN_REQUIRED");
    }
    if (isLoggedOut()) {
      throw new Error("AURA_LOGIN_REQUIRED");
    }

    // Wait up to 30 s for the editor to mount. Slow first-load,
    // Cloudflare interstitials, and React app hydration all happen
    // here. Earlier versions failed within ~1 s with "editor not
    // found".
    const editor = await waitForEditor(30000);
    if (editor === null) {
      // navigated to a login URL during the wait
      throw new Error("AURA_LOGIN_REQUIRED");
    }
    if (!editor) {
      throw new Error(
        "ChatGPT editor never appeared. Open the chat tab and try again."
      );
    }

    const blob = base64ToBlob(b64, "image/png");
    const file = new File([blob], "screenshot.png", { type: "image/png" });

    await attachFile(editor, file);
    await waitForUploadComplete(15000);
    await setEditorText(editor, question || "");
    await sleep(300);
    await clickSend();

    const final = await waitForResponse((partial) => {
      if (window.auraOnPartial) {
        try { window.auraOnPartial(partial); } catch (_) {}
      }
    }, 120000);
    return final;
  };

  window.auraIsReady = function () {
    if (isLoginUrl(location.href)) return false;
    return Boolean(findEditor() && !isLoggedOut());
  };
})();
