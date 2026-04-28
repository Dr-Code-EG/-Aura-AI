package com.draura.aura.ui

import android.Manifest
import android.app.Activity
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.media.projection.MediaProjectionManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.rememberCoroutineScope
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.draura.aura.R
import com.draura.aura.bubble.AnswerBroadcast
import com.draura.aura.bubble.BubbleService
import com.draura.aura.capture.ScreenCaptureService
import com.draura.aura.chatgpt.ChatGptActivity
import com.draura.aura.settings.AuraSettings
import com.draura.aura.settings.SettingsRepository
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var settingsRepo: SettingsRepository
    private lateinit var projectionLauncher: androidx.activity.result.ActivityResultLauncher<Intent>
    private var pendingActionAfterProjection: (() -> Unit)? = null

    private val statusState = mutableStateOf<String?>(null)
    private val answerState = mutableStateOf<String>("")

    private val answerReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            val text = intent.getStringExtra(AnswerBroadcast.EXTRA_TEXT).orEmpty()
            when (intent.action) {
                AnswerBroadcast.ACTION_STATUS -> statusState.value = text
                AnswerBroadcast.ACTION_ANSWER -> {
                    statusState.value = getString(R.string.status_done)
                    answerState.value = text
                }
                AnswerBroadcast.ACTION_ERROR -> statusState.value = "Error: $text"
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settingsRepo = SettingsRepository(applicationContext)

        projectionLauncher = registerForActivityResult(
            ActivityResultContracts.StartActivityForResult(),
        ) { result ->
            if (result.resultCode == Activity.RESULT_OK && result.data != null) {
                ScreenCaptureService.start(this, result.resultCode, result.data!!)
                pendingActionAfterProjection?.invoke()
                pendingActionAfterProjection = null
            } else {
                statusState.value = getString(R.string.error_capture_denied)
            }
        }

        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    AuraScreen()
                }
            }
        }

        if (intent.getBooleanExtra(EXTRA_REQUEST_PROJECTION, false)) {
            requestProjection { /* nothing extra */ }
        }
    }

    override fun onStart() {
        super.onStart()
        val filter = IntentFilter().apply {
            addAction(AnswerBroadcast.ACTION_STATUS)
            addAction(AnswerBroadcast.ACTION_ANSWER)
            addAction(AnswerBroadcast.ACTION_ERROR)
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(answerReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
        } else {
            @Suppress("UnspecifiedRegisterReceiverFlag")
            registerReceiver(answerReceiver, filter)
        }
    }

    override fun onStop() {
        super.onStop()
        try { unregisterReceiver(answerReceiver) } catch (_: Throwable) {}
    }

    private fun requestProjection(thenRun: () -> Unit) {
        pendingActionAfterProjection = thenRun
        val mgr = getSystemService(MediaProjectionManager::class.java)
        if (mgr == null) {
            statusState.value = "Screen capture not available on this device."
            return
        }
        projectionLauncher.launch(mgr.createScreenCaptureIntent())
    }

    private fun ensureOverlayPermission(): Boolean {
        if (Settings.canDrawOverlays(this)) return true
        val intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:$packageName"),
        )
        startActivity(intent)
        return false
    }

    private fun ensureNotificationPermission(): Boolean {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return true
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIF)
        }
        return granted
    }

    private fun startBubble() {
        if (!ensureOverlayPermission()) {
            statusState.value = getString(R.string.overlay_permission_required)
            return
        }
        ensureNotificationPermission()
        // Bubble needs MediaProjection up first so taps don't bounce
        // back to the activity for permission every time.
        if (ScreenCaptureService.current() == null) {
            requestProjection {
                val intent = Intent(this, BubbleService::class.java)
                ContextCompat.startForegroundService(this, intent)
            }
        } else {
            val intent = Intent(this, BubbleService::class.java)
            ContextCompat.startForegroundService(this, intent)
        }
    }

    private fun stopBubble() {
        stopService(Intent(this, BubbleService::class.java))
    }

    private fun openChatGpt() {
        startActivity(Intent(this, ChatGptActivity::class.java))
    }

    @OptIn(ExperimentalMaterial3Api::class)
    @Composable
    private fun AuraScreen() {
        val settings by settingsRepo.settingsFlow.collectAsStateWithLifecycle(
            initialValue = AuraSettings(),
        )
        val scroll = rememberScrollState()
        val scope = rememberCoroutineScope()

        Scaffold(
            topBar = { TopAppBar(title = { Text(stringResource(R.string.app_name)) }) },
        ) { padding ->
            Column(
                modifier = Modifier
                    .padding(padding)
                    .padding(16.dp)
                    .verticalScroll(scroll),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                Text(
                    text = stringResource(R.string.settings_title),
                    style = MaterialTheme.typography.titleMedium,
                )

                ProviderDropdown(settings.provider) { newProvider ->
                    scope.launch { settingsRepo.update { it.copy(provider = newProvider) } }
                }

                OutlinedTextField(
                    value = settings.geminiApiKey,
                    onValueChange = { v ->
                        scope.launch { settingsRepo.update { it.copy(geminiApiKey = v) } }
                    },
                    label = { Text(stringResource(R.string.api_key_label)) },
                    placeholder = { Text(stringResource(R.string.api_key_hint)) },
                    visualTransformation = PasswordVisualTransformation(),
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                OutlinedTextField(
                    value = settings.geminiModel,
                    onValueChange = { v ->
                        scope.launch { settingsRepo.update { it.copy(geminiModel = v) } }
                    },
                    label = { Text(stringResource(R.string.model_label)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                )

                OutlinedTextField(
                    value = settings.extraQuestion,
                    onValueChange = { v ->
                        scope.launch { settingsRepo.update { it.copy(extraQuestion = v) } }
                    },
                    label = { Text(stringResource(R.string.extra_question_label)) },
                    placeholder = { Text(stringResource(R.string.extra_question_hint)) },
                    modifier = Modifier.fillMaxWidth(),
                )

                Spacer(Modifier.height(8.dp))

                Row(
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Button(
                        onClick = { startBubble() },
                        modifier = Modifier.weight(1f),
                    ) { Text(stringResource(R.string.start_bubble)) }
                    OutlinedButton(
                        onClick = { stopBubble() },
                        modifier = Modifier.weight(1f),
                    ) { Text(stringResource(R.string.stop_bubble)) }
                }

                OutlinedButton(
                    onClick = { openChatGpt() },
                    modifier = Modifier.fillMaxWidth(),
                ) { Text(stringResource(R.string.open_chatgpt_login)) }

                statusState.value?.let {
                    Text(
                        text = it,
                        style = MaterialTheme.typography.bodySmall,
                    )
                }

                Spacer(Modifier.height(8.dp))
                Text(
                    text = stringResource(R.string.response_label),
                    style = MaterialTheme.typography.titleMedium,
                )
                Card(modifier = Modifier.fillMaxWidth()) {
                    Box(modifier = Modifier.padding(12.dp)) {
                        if (answerState.value.isBlank()) {
                            Text(
                                text = stringResource(R.string.response_placeholder),
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        } else {
                            Text(
                                text = answerState.value,
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }
            }
        }
    }

    @Composable
    private fun ProviderDropdown(
        current: String,
        onChange: (String) -> Unit,
    ) {
        var expanded by remember { mutableStateOf(false) }
        val label = when (current) {
            AuraSettings.PROVIDER_CHATGPT -> stringResource(R.string.chatgpt_label)
            else -> stringResource(R.string.gemini_label)
        }
        Column(modifier = Modifier.fillMaxWidth()) {
            Text(
                text = stringResource(R.string.provider_label),
                style = MaterialTheme.typography.bodySmall,
            )
            OutlinedButton(
                onClick = { expanded = true },
                modifier = Modifier.fillMaxWidth(),
            ) { Text(label) }
            DropdownMenu(
                expanded = expanded,
                onDismissRequest = { expanded = false },
            ) {
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.gemini_label)) },
                    onClick = {
                        onChange(AuraSettings.PROVIDER_GEMINI)
                        expanded = false
                    },
                )
                DropdownMenuItem(
                    text = { Text(stringResource(R.string.chatgpt_label)) },
                    onClick = {
                        onChange(AuraSettings.PROVIDER_CHATGPT)
                        expanded = false
                    },
                )
            }
        }
    }

    companion object {
        const val EXTRA_REQUEST_PROJECTION = "request_projection"
        private const val REQ_NOTIF = 9421
    }
}
