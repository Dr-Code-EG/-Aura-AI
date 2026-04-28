package com.draura.aura.chatgpt

import android.annotation.SuppressLint
import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.util.Base64
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.LinearLayout
import androidx.activity.ComponentActivity

/**
 * Activity hosting an embedded ChatGPT session in a WebView.
 *
 * - Cookies are persisted via the system CookieManager so the user only
 *   logs in once.
 * - When [EXTRA_AUTO_SEND] is true and a screenshot is staged in
 *   [PendingScreenshotHolder], we run a small JS snippet that pastes
 *   the image into the prompt and clicks Send — same idea as the
 *   desktop client.
 *
 * NOTE on JS bridge fragility: ChatGPT's DOM changes regularly. The
 * snippet here uses several fallback selectors and resilient lookups
 * but expect occasional breakage.
 */
class ChatGptActivity : ComponentActivity() {

    private lateinit var webView: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val container = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
        }
        webView = WebView(this).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            )
            settings.apply {
                javaScriptEnabled = true
                domStorageEnabled = true
                databaseEnabled = true
                @Suppress("DEPRECATION")
                allowFileAccess = false
                cacheMode = WebSettings.LOAD_DEFAULT
                userAgentString = MODERN_UA
                mediaPlaybackRequiresUserGesture = false
            }
            webChromeClient = WebChromeClient()
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    if (intent.getBooleanExtra(EXTRA_AUTO_SEND, false)) {
                        // Don't auto-send on the login screen; only after the
                        // user has navigated to /c or the chat home.
                        if (url != null && (url.contains("chatgpt.com") || url.contains("chat.openai.com"))) {
                            tryAutoSend()
                        }
                    }
                }
            }
        }
        container.addView(webView)
        setContentView(container)

        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView, true)

        if (savedInstanceState == null) {
            webView.loadUrl(CHATGPT_URL)
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        if (intent.getBooleanExtra(EXTRA_AUTO_SEND, false)) {
            tryAutoSend()
        }
    }

    private fun tryAutoSend() {
        val bytes = PendingScreenshotHolder.consume() ?: return
        val b64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
        // Build the JS as a string with a placeholder for the (already
        // base64-encoded) PNG so we don't have to escape it again.
        val js = INJECT_JS.replace("__B64_PLACEHOLDER__", b64)
        webView.evaluateJavascript(js, null)
    }

    override fun onDestroy() {
        try {
            (webView.parent as? ViewGroup)?.removeView(webView)
            webView.removeAllViews()
            webView.destroy()
        } catch (_: Throwable) {}
        super.onDestroy()
    }

    companion object {
        const val EXTRA_AUTO_SEND = "auto_send"
        private const val CHATGPT_URL = "https://chatgpt.com/"
        private const val MODERN_UA =
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) " +
                "AppleWebKit/537.36 (KHTML, like Gecko) " +
                "Chrome/124.0.0.0 Mobile Safari/537.36"

        // Best-effort JS that:
        //   1) Decodes the base64 PNG to a Blob/File.
        //   2) Tries to drop the file onto the prompt textarea via DataTransfer.
        //   3) Sets the prompt text and clicks the Send button.
        // Resilient to common DOM variations on chatgpt.com.
        private const val INJECT_JS = """
            (async function() {
              try {
                const b64 = "__B64_PLACEHOLDER__";
                const bin = atob(b64);
                const arr = new Uint8Array(bin.length);
                for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
                const file = new File([arr], "screenshot.png", { type: "image/png" });

                const editor = document.querySelector('textarea, [contenteditable="true"]');
                if (!editor) {
                  alert("ChatGPT prompt not found — make sure you're on a chat page.");
                  return;
                }

                // Drop the file via DataTransfer.
                const dt = new DataTransfer();
                dt.items.add(file);
                editor.focus();
                editor.dispatchEvent(new DragEvent("drop", { bubbles: true, dataTransfer: dt }));
                editor.dispatchEvent(new ClipboardEvent("paste", { bubbles: true, clipboardData: dt }));

                // Wait briefly for the upload preview to render.
                await new Promise(r => setTimeout(r, 1500));

                const question = "Answer the question on the screen.";
                if (editor.tagName === "TEXTAREA") {
                  editor.value = question;
                  editor.dispatchEvent(new Event("input", { bubbles: true }));
                } else {
                  editor.innerText = question;
                  editor.dispatchEvent(new InputEvent("input", { bubbles: true }));
                }

                await new Promise(r => setTimeout(r, 250));
                const sendBtn = document.querySelector(
                  '[data-testid="send-button"], button[aria-label*="Send"], button[type="submit"]'
                );
                if (sendBtn) sendBtn.click();
              } catch (e) {
                alert("Aura inject failed: " + (e && e.message ? e.message : e));
              }
            })();
        """
    }
}

/** Stash for a screenshot that's bigger than the Intent extras limit. */
object PendingScreenshotHolder {
    @Volatile private var bytes: ByteArray? = null

    fun set(b: ByteArray) { bytes = b }
    fun consume(): ByteArray? {
        val b = bytes
        bytes = null
        return b
    }
}
