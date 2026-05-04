package com.drcode.admin.ui

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier

class AdminActivity : ComponentActivity() {

    private val vm: AdminViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            // Dark theme suits a dashboard.
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val state by vm.state.collectAsState()
                    if (!state.signedIn) {
                        LoginScreen(
                            state = state,
                            onSubmit = vm::signIn,
                            onErrorDismissed = vm::clearError,
                        )
                    } else {
                        DashboardScreen(
                            state = state,
                            onRefresh = vm::refresh,
                            onSignOut = vm::signOut,
                            onGenerate = vm::generateCodes,
                            onRevoke = vm::revokeCode,
                            onReset = vm::resetCode,
                            onBlock = vm::blockDevice,
                            onUnblock = vm::unblockDevice,
                            onClearFresh = vm::clearFreshCodes,
                            onErrorDismissed = vm::clearError,
                        )
                    }
                }
            }
        }
    }
}
