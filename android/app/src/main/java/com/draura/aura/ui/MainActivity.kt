package com.draura.aura.ui

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.draura.aura.R
import com.draura.aura.bubble.BubbleService
import com.draura.aura.chatgpt.ChatGptActivity
import com.draura.aura.settings.AuraSettings
import com.draura.aura.settings.SettingsRepository
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var settingsRepo: SettingsRepository
    private val statusState = mutableStateOf<String?>(null)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settingsRepo = SettingsRepository(applicationContext)

        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    AuraScreen()
                }
            }
        }
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

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.POST_NOTIFICATIONS,
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) {
            requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQ_NOTIF)
        }
    }

    private fun startBubble() {
        if (!ensureOverlayPermission()) {
            statusState.value = getString(R.string.overlay_permission_required)
            return
        }
        ensureNotificationPermission()
        val intent = Intent(this, BubbleService::class.java)
        ContextCompat.startForegroundService(this, intent)
        statusState.value = null
        // Hide the activity so the bubble is the user's main interaction surface.
        moveTaskToBack(true)
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
        val scope = rememberCoroutineScope()
        val scroll = rememberScrollState()

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
                    text = "How it works",
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(
                    text = "1. Tap \"Sign in to ChatGPT\" once to log in (cookies persist).\n" +
                        "2. Tap \"Start floating button\" — a small bubble appears over other apps.\n" +
                        "3. Open the question on screen and tap the bubble.\n" +
                        "4. Android asks for screen-capture permission. After capture the recording stops automatically.\n" +
                        "5. ChatGPT runs hidden in the background, then a dialog shows the answer.",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }

    companion object {
        private const val REQ_NOTIF = 9421
    }
}
