package com.drcode.clock.capture

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat

/**
 * Transparent activity whose only job is to ask the user for the
 * MediaProjection consent dialog and hand the result off to
 * [ScreenCaptureService]. We finish immediately afterwards so the user
 * never sees a real Clock UI for the capture step — just the system
 * permission popup.
 */
class CaptureRequestActivity : ComponentActivity() {

    private val launcher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK && result.data != null) {
            val intent = Intent(this, ScreenCaptureService::class.java).apply {
                putExtra(ScreenCaptureService.EXTRA_RESULT_CODE, result.resultCode)
                putExtra(ScreenCaptureService.EXTRA_RESULT_DATA, result.data)
            }
            ContextCompat.startForegroundService(this, intent)
        }
        finish()
        // Skip the activity transition so the user perceives the
        // permission popup as a self-contained event.
        overridePendingTransition(0, 0)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        overridePendingTransition(0, 0)
        val mgr = getSystemService(MediaProjectionManager::class.java)
        if (mgr == null) {
            finish()
            return
        }
        launcher.launch(mgr.createScreenCaptureIntent())
    }
}
