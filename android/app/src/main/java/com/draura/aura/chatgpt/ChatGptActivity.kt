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
import androidx.lifecycle.lifecycleScope
import com.draura.aura.R
import com.draura.aura.settings.AuraSettings
import com.draura.aura.settings.SettingsRepository
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.util.concurrent.atomic.AtomicBoolean

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

    /**
     * True from the moment we evaluate the auto-send JS until we hear
     * back from the bridge (success, error, or login-required). Prevents
     * a second [WebViewClient.onPageFinished] (e.g. ChatGPT redirecting
     * client-side from `/` to `/chat`) from kicking off a duplicate
     * injection while one is already running.
     */
    private val autoSendInProgress = AtomicBoolean(false)

    /**
     * The user's default question, eagerly loaded off the UI thread
     * during [onCreate] so [runAutoSend] never has to do blocking
     * DataStore I/O on the main thread (DataStore touches disk on
     * its first read — doing that synchronously from the WebView's
     * onPageFinished callback risks an ANR).
     *
     * Volatile so the read in [runAutoSend] sees the value written by
     * the lifecycleScope coroutine without needing a lock.
     */
    @Volatile
    private var cachedQuestion: String = "Answer the question on the screen."

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

        // Warm cachedQuestion off the main thread. DataStore's first
        // read touches disk; doing it synchronously from runAutoSend
        // (which is called from WebView callbacks on the UI thread)
        // would risk an ANR.
        lifecycleScope.launch {
            val q = withContext(Dispatchers.IO) {
                runCatching {
                    SettingsRepository(applicationContext).settingsFlow.firstOrNull()
                }.getOrNull()
            }
            if (q != null && q.extraQuestion.isNotBlank()) {
                cachedQuestion = q.extraQuestion
            }
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
            // Only consume the staged screenshot if the WebView is
            // fully loaded — otherwise the injected JS would be
            // discarded by the next page load and the bytes would be
            // gone for good. If the page is still loading, the
            // onPageFinished hook will fire runAutoSend itself once
            // it's ready (peekBytes is non-null until consumed).
            val wv = webView
            if (wv != null && wv.progress >= 100) {
                runAutoSend()
            }
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
                    // A page navigation (e.g. ChatGPT redirecting / -> /chat,
                    // a Cloudflare interstitial resolving, or the user
                    // logging in mid-flight) destroys any JS we previously
                    // injected, so any in-progress bridge call is now
                    // dead and its callbacks (onResponse / onError /
                    // onLoginRequired) can never fire to clear this flag.
                    // Reset it here so the new injection below isn't
                    // silently blocked by a permanently-stuck flag from
                    // the previous, now-invalidated, page.
                    autoSendInProgress.set(false)
                    // Auto-send hook: only fire if a screenshot is
                    // staged. The bridge itself handles waiting for
                    // ChatGPT's React app to finish booting and the
                    // editor to become visible — we don't gate on that
                    // here.
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
        // Peek (don't consume) so that if the JS bridge bails before
        // it has actually attached the file to the editor, the bytes
        // stay staged and the user can retry. The bridge calls
        // [JsBridge.onAttached] once the file is in the editor, and
        // that's when we drop the staged copy.
        val bytes = PendingScreenshotHolder.peekBytes() ?: return
        if (!autoSendInProgress.compareAndSet(false, true)) {
            // Another onPageFinished already kicked us off; don't
            // double-inject.
            return
        }
        // cachedQuestion was warmed off the UI thread in onCreate; if
        // the warmup hasn't finished yet we fall back to the default
        // baked into the field initializer rather than block.
        val question = cachedQuestion
        val b64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
        val js = INJECT_JS
            .replace("__B64_PLACEHOLDER__", b64)
            .replace("__QUESTION_PLACEHOLDER__", jsString(question))
        wv.evaluateJavascript(js, null)
    }

    inner class JsBridge {
        @JavascriptInterface
        fun onProgress(stage: String) {
            // We could surface the stage in the loading dialog if we
            // wanted finer-grained UX. Currently we just keep showing
            // "Asking ChatGPT…".
        }

        /**
         * Called by the JS bridge once it has successfully attached
         * the screenshot file to ChatGPT's editor. From this point on
         * the bytes are committed to the active conversation and we
         * drop the staged copy so subsequent taps don't re-send the
         * same screenshot.
         */
        @JavascriptInterface
        fun onAttached() {
            PendingScreenshotHolder.consumeBytes()
        }

        @JavascriptInterface
        fun onResponse(text: String) {
            runOnUiThread {
                autoSendInProgress.set(false)
                state.value = UiState.Response(text)
            }
        }

        @JavascriptInterface
        fun onError(message: String) {
            runOnUiThread {
                autoSendInProgress.set(false)
                // Bytes stay staged — the Retry button picks them up.
                state.value = UiState.Error(message)
            }
        }

        @JavascriptInterface
        fun onLoginRequired() {
            runOnUiThread {
                autoSendInProgress.set(false)
                // Don't consume bytes — the user will sign in, then
                // either tap Retry on the dialog (if it's still up) or
                // re-tap the bubble (which stages new bytes).
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
        //   - waits up to 30s for the editor to mount (slow cold loads,
        //     Cloudflare challenges, React app booting)
        //   - retries to find the editor and Send button
        //   - polls assistant message text + "Stop" button to detect when
        //     streaming finishes, then waits 800ms of stability
        //   - on a /login URL at any point, calls onLoginRequired so the
        //     activity can swap to a visible WebView for the user to sign
        //     in (bytes stay staged for retry)
        //   - calls AuraBridge.onAttached() only after the file is
        //     actually in the editor — host uses that as the commit
        //     point for dropping the staged screenshot copy.
        private val INJECT_JS = """
        (async function() {
          try {
            function isLoginUrl(u) {
              return /\/(auth\/)?login/.test(u)
                || /\/auth\//.test(u)
                || /accounts\.google\.com/.test(u)
                || /login\.live\.com/.test(u)
                || /\.openai\.com\/auth/.test(u);
            }
            if (isLoginUrl(location.href)) {
              AuraBridge.onLoginRequired();
              return;
            }
            AuraBridge.onProgress('waiting-for-page');

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

            // Wait up to 30s for the editor to mount.
            let editor = findEditor();
            for (let i = 0; i < 60 && !editor; i++) {
              await new Promise(r => setTimeout(r, 500));
              if (isLoginUrl(location.href)) {
                AuraBridge.onLoginRequired();
                return;
              }
              editor = findEditor();
            }
            if (!editor) {
              AuraBridge.onError('ChatGPT prompt not found. Open the chat tab and try again.');
              return;
            }
            // Tiny extra settle — ChatGPT sometimes mounts the editor
            // before its event handlers are attached.
            await new Promise(r => setTimeout(r, 400));
            editor.focus();

            AuraBridge.onProgress('attaching');
            const dt = new DataTransfer();
            dt.items.add(file);
            editor.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt }));
            editor.dispatchEvent(new ClipboardEvent('paste', { bubbles: true, cancelable: true, clipboardData: dt }));

            // The file is in the editor — commit: drop the staged copy
            // so retaps don't double-send. Past this point a failure
            // means the screenshot is already submitted to ChatGPT,
            // even if we can't read the answer back.
            try { AuraBridge.onAttached(); } catch (_) {}

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
                                canRetry = PendingScreenshotHolder.peekBytes() != null,
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
    canRetry: Boolean,
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
                if (canRetry) {
                    OutlinedButton(
                        onClick = onRetry,
                        modifier = Modifier.weight(1f),
                    ) { Text(stringResource(R.string.dialog_retry)) }
                }
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
