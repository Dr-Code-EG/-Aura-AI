// Injected into chatgpt.com / chat.openai.com to programmatically
// attach a screenshot, type a question and read back the answer.
//
// The host application (PyQt) calls window.auraSendScreenshot(b64, question)
// from QWebChannel; this script wires up that bridge plus poll-and-read
// helpers that surface the latest assistant response back to the host.

(function () {
  if (window.__auraChatGPTBridgeInstalled) {
    return;
  }
  window.__auraChatGPTBridgeInstalled = true;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
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
      document.querySelector('button[aria-label*="Send" i]') ||
      document.querySelector('button[aria-label*="إرسال"]')
    );
  }

  async function attachFile(file) {
    const input = findFileInput();
    if (!input) {
      throw new Error("Could not find ChatGPT file input. Open a chat and try again.");
    }
    const dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dispatchEvent(new Event("change", { bubbles: true }));
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
    while (Date.now() - start < 8000) {
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
    const editor = findEditor();
    if (!editor) {
      throw new Error(
        "ChatGPT editor not found. Make sure you're logged in and a chat is open."
      );
    }
    const blob = base64ToBlob(b64, "image/png");
    const file = new File([blob], "screenshot.png", { type: "image/png" });

    await attachFile(file);
    await waitForUploadComplete(15000);
    await setEditorText(editor, question || "");
    await sleep(150);
    await clickSend();

    const final = await waitForResponse((partial) => {
      if (window.auraOnPartial) {
        try { window.auraOnPartial(partial); } catch (_) {}
      }
    }, 120000);
    return final;
  };

  window.auraIsReady = function () {
    return Boolean(findEditor() && findFileInput());
  };
})();
