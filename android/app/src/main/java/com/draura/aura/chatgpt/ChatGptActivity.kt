package com.draura.aura.chatgpt

import android.annotation.SuppressLint
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.util.Base64
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.WebChromeClient
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import com.draura.aura.R
import com.draura.aura.settings.AuraSettings
import com.draura.aura.settings.SettingsRepository
import kotlinx.coroutines.flow.firstOrNull

/**
 * Hosts an embedded ChatGPT session.
 *
 * Has two modes driven by [EXTRA_AUTO_SEND]:
 *
 * 1. **Auto-send (silent) mode** — used when the bubble triggered a
 *    capture. The WebView is hidden behind a translucent overlay and a
 *    JS bridge:
 *      a) attaches the staged screenshot,
 *      b) types the user's default question,
 *      c) clicks Send,
 *      d) polls the DOM for the assistant reply,
 *      e) calls back into [JsBridge.onResponse] with the final text.
 *    The activity then shows the response in a Compose dialog with
 *    Copy / Open chat / Close actions.
 *
 * 2. **Manual mode** — the WebView is shown fullscreen so the user can
 *    sign in or browse their chats normally.
 *
 * If the JS bridge detects a /login or /auth URL during auto-send it
 * calls [JsBridge.onLoginRequired] and we transparently switch to
 * manual mode so the user can sign in.
 */
class ChatGptActivity : ComponentActivity() {

    private var webView: WebView? = null

    private val showWebView = mutableStateOf(false)
    private val state: MutableState<UiState> = mutableStateOf(UiState.Idle)

    sealed class UiState {
        data object Idle : UiState()
        data object Loading : UiState()
        data class Response(val text: String) : UiState()
        data class Error(val message: String) : UiState()
    }

    @SuppressLint("SetJavaScriptEnabled", "AddJavascriptInterface")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // Capture initial intent state.
        val autoSend = intent.getBooleanExtra(EXTRA_AUTO_SEND, false)
        val errorFromCapture = intent.getStringExtra(EXTRA_ERROR)

        if (errorFromCapture != null) {
            state.value = UiState.Error(errorFromCapture)
        } else if (autoSend) {
            state.value = UiState.Loading
        } else {
            showWebView.value = true
        }

        setContent {
            MaterialTheme {
                ChatGptScreen(
                    state = state.value,
                    showWebView = showWebView.value,
                    buildWebView = ::buildWebView,
                    onDismissResponse = { state.value = UiState.Idle; finish() },
                    onCopy = { text ->
                        val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                        cm.setPrimaryClip(ClipData.newPlainText("Aura answer", text))
                        Toast.makeText(this, R.string.copied_to_clipboard, Toast.LENGTH_SHORT).show()
                    },
                    onOpenChat = { showWebView.value = true; state.value = UiState.Idle },
                    onRetry = {
                        // Re-run the auto-send pipeline against whatever
                        // is staged. If nothing is staged this is a no-op.
                        state.value = UiState.Loading
                        runAutoSend()
                    },
                )
            }
        }

        if (autoSend && errorFromCapture == null) {
            // Wait for the WebView to come up + page to load — runAutoSend
            // gates on that internally via onPageFinished.
            // The PendingScreenshotHolder may already contain the bytes.
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        val err = intent.getStringExtra(EXTRA_ERROR)
        if (err != null) {
            state.value = UiState.Error(err)
            return
        }
        if (intent.getBooleanExtra(EXTRA_AUTO_SEND, false)) {
            state.value = UiState.Loading
            // If we already have a WebView, re-run the bridge against
            // the new staged screenshot. If page is still loading the
            // onPageFinished hook will pick it up.
            runAutoSend()
        }
    }

    @SuppressLint("SetJavaScriptEnabled", "AddJavascriptInterface")
    private fun buildWebView(ctx: Context): WebView {
        val wv = WebView(ctx).apply {
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
                javaScriptCanOpenWindowsAutomatically = true
                setSupportMultipleWindows(true)
            }
            webChromeClient = WebChromeClient()
            webViewClient = object : WebViewClient() {
                override fun onPageFinished(view: WebView?, url: String?) {
                    super.onPageFinished(view, url)
                    // Auto-send hook: as soon as the page is ready and we
                    // have a pending screenshot, run the bridge.
                    if (intent.getBooleanExtra(EXTRA_AUTO_SEND, false)
                        && PendingScreenshotHolder.peekBytes() != null
                    ) {
                        runAutoSend()
                    }
                }
            }
            addJavascriptInterface(JsBridge(), "AuraBridge")
        }
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setAcceptThirdPartyCookies(wv, true)
        wv.loadUrl(CHATGPT_URL)
        webView = wv
        return wv
    }

    private fun runAutoSend() {
        val wv = webView ?: return
        val bytes = PendingScreenshotHolder.consumeBytes() ?: return
        // Pull the user's default question off the settings store. We
        // do this synchronously off the cached value via runBlocking
        // semantics — but DataStore is a Flow, so use a background
        // coroutine and post the JS once we have the value.
        val question = settingsQuestionBlocking()
        val b64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
        val js = INJECT_JS
            .replace("__B64_PLACEHOLDER__", b64)
            .replace("__QUESTION_PLACEHOLDER__", jsString(question))
        wv.evaluateJavascript(js, null)
    }

    private fun settingsQuestionBlocking(): String {
        // First emission of the Flow is synchronous-ish but we still
        // need to hop threads. Use a simple wait with a default to
        // avoid blocking the UI thread.
        var result = "Answer the question on the screen."
        try {
            kotlinx.coroutines.runBlocking {
                val s = SettingsRepository(applicationContext).settingsFlow.firstOrNull()
                if (s != null && s.extraQuestion.isNotBlank()) result = s.extraQuestion
            }
        } catch (_: Throwable) {
            // Keep default.
        }
        return result
    }

    inner class JsBridge {
        @JavascriptInterface
        fun onProgress(stage: String) {
            // We could surface the stage in the loading dialog if we
            // wanted finer-grained UX. Currently we just keep showing
            // "Asking ChatGPT…".
        }

        @JavascriptInterface
        fun onResponse(text: String) {
            runOnUiThread { state.value = UiState.Response(text) }
        }

        @JavascriptInterface
        fun onError(message: String) {
            runOnUiThread { state.value = UiState.Error(message) }
        }

        @JavascriptInterface
        fun onLoginRequired() {
            runOnUiThread {
                state.value = UiState.Error(getString(R.string.error_chatgpt_not_signed_in))
                showWebView.value = true
            }
        }
    }

    override fun onDestroy() {
        try {
            webView?.let {
                (it.parent as? ViewGroup)?.removeView(it)
                it.removeAllViews()
                it.destroy()
            }
        } catch (_: Throwable) {}
        webView = null
        super.onDestroy()
    }

    companion object {
        const val EXTRA_AUTO_SEND = "auto_send"
        const val EXTRA_ERROR = "auto_send_error"
        private const val CHATGPT_URL = "https://chatgpt.com/"
        private const val MODERN_UA =
            "Mozilla/5.0 (Linux; Android 14; Pixel 8) " +
                "AppleWebKit/537.36 (KHTML, like Gecko) " +
                "Chrome/124.0.0.0 Mobile Safari/537.36"

        /** Quote a string for safe inclusion in JS source. */
        private fun jsString(s: String): String {
            val escaped = s
                .replace("\\", "\\\\")
                .replace("\"", "\\\"")
                .replace("\n", "\\n")
                .replace("\r", "")
                .replace("\u2028", "\\u2028")
                .replace("\u2029", "\\u2029")
            return "\"$escaped\""
        }

        // Injected JS. Keys to the resilience here:
        //   - retries to find the editor and Send button (DOM lazy-mounts)
        //   - polls assistant message text + "Stop" button to detect when
        //     streaming finishes, then waits 800ms of stability
        //   - on /login URL, calls onLoginRequired so the activity can
        //     swap to a visible WebView for the user to sign in.
        private val INJECT_JS = """
        (async function() {
          try {
            const url = location.href;
            if (/\/(auth\/)?login/.test(url) || /\/auth\//.test(url)) {
              AuraBridge.onLoginRequired();
              return;
            }
            AuraBridge.onProgress('attaching');
            const b64 = "__B64_PLACEHOLDER__";
            const question = __QUESTION_PLACEHOLDER__;
            const bin = atob(b64);
            const arr = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
            const file = new File([arr], "screenshot.png", { type: "image/png" });

            function findEditor() {
              return document.querySelector('div[contenteditable="true"]#prompt-textarea')
                || document.querySelector('#prompt-textarea')
                || document.querySelector('div[contenteditable="true"]')
                || document.querySelector('textarea');
            }
            function findSend() {
              return document.querySelector('button[data-testid="send-button"]')
                || document.querySelector('button[aria-label="Send prompt"]')
                || document.querySelector('button[aria-label*="Send"]')
                || document.querySelector('form button[type="submit"]');
            }
            function findStop() {
              return document.querySelector('button[data-testid="stop-button"]')
                || document.querySelector('button[aria-label*="Stop"]');
            }

            let editor = findEditor();
            for (let i = 0; i < 30 && !editor; i++) {
              await new Promise(r => setTimeout(r, 200));
              editor = findEditor();
            }
            if (!editor) { AuraBridge.onError('ChatGPT prompt not found.'); return; }
            editor.focus();

            const dt = new DataTransfer();
            dt.items.add(file);
            editor.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
            editor.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt }));

            AuraBridge.onProgress('typing');
            await new Promise(r => setTimeout(r, 1800));

            if (editor.tagName === 'TEXTAREA') {
              editor.value = question;
              editor.dispatchEvent(new Event('input', { bubbles: true }));
            } else {
              editor.innerText = question;
              editor.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertText', data: question }));
            }

            await new Promise(r => setTimeout(r, 350));

            let send = findSend();
            for (let i = 0; i < 25 && (!send || send.disabled); i++) {
              await new Promise(r => setTimeout(r, 250));
              send = findSend();
            }
            if (!send) { AuraBridge.onError('Send button not found.'); return; }
            send.click();
            AuraBridge.onProgress('sending');

            // Poll for response.
            let lastText = '';
            let lastChange = Date.now();
            const start = Date.now();
            while (Date.now() - start < 90000) {
              await new Promise(r => setTimeout(r, 500));
              const msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
              if (msgs.length === 0) continue;
              const last = msgs[msgs.length - 1];
              const text = (last.innerText || last.textContent || '').trim();
              if (!text) continue;
              const stillStreaming = !!findStop();
              if (text !== lastText) {
                lastText = text;
                lastChange = Date.now();
                continue;
              }
              if (!stillStreaming && Date.now() - lastChange > 800) {
                AuraBridge.onResponse(text);
                return;
              }
            }
            if (lastText) {
              AuraBridge.onResponse(lastText);
            } else {
              AuraBridge.onError('Timed out waiting for ChatGPT.');
            }
          } catch (e) {
            try { AuraBridge.onError('JS error: ' + (e && e.message ? e.message : e)); } catch (_) {}
          }
        })();
        """
    }
}

@Composable
private fun ChatGptScreen(
    state: ChatGptActivity.UiState,
    showWebView: Boolean,
    buildWebView: (Context) -> WebView,
    onDismissResponse: () -> Unit,
    onCopy: (String) -> Unit,
    onOpenChat: () -> Unit,
    onRetry: () -> Unit,
) {
    Surface(modifier = Modifier.fillMaxSize()) {
        Box(modifier = Modifier.fillMaxSize()) {
            // The WebView is always present (so cookies + JS bridge work)
            // but visually hidden behind the overlay during auto-send.
            AndroidView(
                factory = buildWebView,
                modifier = Modifier
                    .fillMaxSize()
                    .alpha(if (showWebView) 1f else 0f),
            )
            if (!showWebView) {
                Box(
                    modifier = Modifier
                        .fillMaxSize()
                        .background(Color(0xCC000000)),
                    contentAlignment = Alignment.Center,
                ) {
                    when (state) {
                        is ChatGptActivity.UiState.Loading,
                        is ChatGptActivity.UiState.Idle ->
                            LoadingCard()
                        is ChatGptActivity.UiState.Response ->
                            ResponseCard(
                                text = state.text,
                                onCopy = onCopy,
                                onOpenChat = onOpenChat,
                                onClose = onDismissResponse,
                            )
                        is ChatGptActivity.UiState.Error ->
                            ErrorCard(
                                message = state.message,
                                onClose = onDismissResponse,
                                onOpenChat = onOpenChat,
                                onRetry = onRetry,
                            )
                    }
                }
            }
        }
    }
    BackHandler(enabled = !showWebView) { onDismissResponse() }
}

@Composable
private fun LoadingCard() {
    Card(modifier = Modifier
        .fillMaxWidth()
        .padding(24.dp)) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(20.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            CircularProgressIndicator()
            Text(
                text = stringResource(R.string.dialog_loading),
                style = MaterialTheme.typography.bodyLarge,
            )
        }
    }
}

@Composable
private fun ResponseCard(
    text: String,
    onCopy: (String) -> Unit,
    onOpenChat: () -> Unit,
    onClose: () -> Unit,
) {
    Card(modifier = Modifier
        .fillMaxWidth()
        .padding(16.dp)) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = stringResource(R.string.response_label),
                style = MaterialTheme.typography.titleMedium,
            )
            val scroll = rememberScrollState()
            Text(
                text = text,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier
                    .fillMaxWidth()
                    .heightIn(min = 80.dp, max = 360.dp)
                    .verticalScroll(scroll),
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedButton(
                    onClick = { onCopy(text) },
                    modifier = Modifier.weight(1f),
                ) { Text(stringResource(R.string.dialog_copy)) }
                OutlinedButton(
                    onClick = onOpenChat,
                    modifier = Modifier.weight(1f),
                ) { Text(stringResource(R.string.dialog_open_chat)) }
                Button(
                    onClick = onClose,
                    modifier = Modifier.weight(1f),
                ) { Text(stringResource(R.string.dialog_close)) }
            }
        }
    }
}

@Composable
private fun ErrorCard(
    message: String,
    onClose: () -> Unit,
    onOpenChat: () -> Unit,
    onRetry: () -> Unit,
) {
    Card(modifier = Modifier
        .fillMaxWidth()
        .padding(16.dp)) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Text(
                text = "Error",
                style = MaterialTheme.typography.titleMedium,
            )
            Text(
                text = message,
                style = MaterialTheme.typography.bodyMedium,
            )
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedButton(
                    onClick = onOpenChat,
                    modifier = Modifier.weight(1f),
                ) { Text(stringResource(R.string.dialog_open_chat)) }
                Button(
                    onClick = onClose,
                    modifier = Modifier.weight(1f),
                ) { Text(stringResource(R.string.dialog_close)) }
            }
        }
    }
}

/**
 * Holder for the most recent screenshot or capture error. Lives in the
 * application process; not persisted across process death (which is fine
 * because the bubble flow always starts from a tap).
 */
object PendingScreenshotHolder {
    @Volatile private var bytes: ByteArray? = null
    @Volatile private var error: String? = null

    fun setBytes(b: ByteArray) {
        bytes = b
        error = null
    }

    fun setError(message: String) {
        error = message
        bytes = null
    }

    fun peekBytes(): ByteArray? = bytes

    fun consumeBytes(): ByteArray? {
        val b = bytes
        bytes = null
        return b
    }

    fun consumeError(): String? {
        val e = error
        error = null
        return e
    }
}
