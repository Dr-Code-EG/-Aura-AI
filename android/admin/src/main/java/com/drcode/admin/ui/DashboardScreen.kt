package com.drcode.admin.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.drcode.admin.data.CodeRow
import com.drcode.admin.data.DeviceRow

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    state: AdminUiState,
    onRefresh: () -> Unit,
    onSignOut: () -> Unit,
    onGenerate: (Int) -> Unit,
    onRevoke: (String) -> Unit,
    onReset: (String) -> Unit,
    onBlock: (String) -> Unit,
    onUnblock: (String) -> Unit,
    onClearFresh: () -> Unit,
    onErrorDismissed: () -> Unit,
) {
    var tab by remember { mutableStateOf(0) }
    var search by remember { mutableStateOf("") }
    var showGenerate by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = {
                    Text(
                        text = state.email?.let { "Signed in: $it" }
                            ?: "Dr Code Admin",
                        style = MaterialTheme.typography.titleMedium,
                    )
                },
                actions = {
                    IconButton(onClick = onRefresh) {
                        Icon(Icons.Default.Refresh, contentDescription = "Refresh")
                    }
                    TextButton(onClick = onSignOut) { Text("Sign out") }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            TabRow(selectedTabIndex = tab) {
                Tab(selected = tab == 0, onClick = { tab = 0 },
                    text = { Text("Codes (${state.codes.size})") })
                Tab(selected = tab == 1, onClick = { tab = 1 },
                    text = { Text("Devices (${state.devices.size})") })
            }
            Row(
                modifier = Modifier.fillMaxWidth().padding(8.dp),
                verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                horizontalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                OutlinedTextField(
                    value = search,
                    onValueChange = { search = it },
                    placeholder = { Text("Search…") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                if (tab == 0) {
                    Button(onClick = { showGenerate = true }) {
                        Text("Generate")
                    }
                }
            }
            HorizontalDivider()

            if (tab == 0) {
                CodesList(
                    codes = state.codes.filter { matches(it, search) },
                    onRevoke = onRevoke,
                    onReset = onReset,
                )
            } else {
                DevicesList(
                    devices = state.devices.filter { matches(it, search) },
                    onBlock = onBlock,
                    onUnblock = onUnblock,
                )
            }
        }
    }

    if (showGenerate) {
        GenerateDialog(
            onDismiss = { showGenerate = false },
            onGenerate = {
                showGenerate = false
                onGenerate(it)
            },
        )
    }

    if (state.freshCodes.isNotEmpty()) {
        FreshCodesDialog(
            codes = state.freshCodes,
            onDismiss = onClearFresh,
        )
    }

    if (state.error != null) {
        AlertDialog(
            onDismissRequest = onErrorDismissed,
            confirmButton = {
                TextButton(onClick = onErrorDismissed) { Text("OK") }
            },
            title = { Text("Error") },
            text = { Text(state.error) },
        )
    }
}

@Composable
private fun CodesList(
    codes: List<CodeRow>,
    onRevoke: (String) -> Unit,
    onReset: (String) -> Unit,
) {
    LazyColumn(contentPadding = PaddingValues(8.dp)) {
        items(codes, key = { it.code }) { c ->
            Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(c.code, style = MaterialTheme.typography.titleMedium)
                    Text("Status: ${c.status}")
                    Text("Device: ${c.deviceLabel ?: c.device ?: "—"}")
                    Text("Last seen: ${c.lastSeenAt ?: "—"}")
                    Spacer(Modifier.height(4.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedButton(onClick = { onReset(c.code) }) {
                            Text("Reset")
                        }
                        OutlinedButton(onClick = { onRevoke(c.code) }) {
                            Text("Revoke")
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun DevicesList(
    devices: List<DeviceRow>,
    onBlock: (String) -> Unit,
    onUnblock: (String) -> Unit,
) {
    LazyColumn(contentPadding = PaddingValues(8.dp)) {
        items(devices, key = { it.fingerprint }) { d ->
            Card(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
                Column(modifier = Modifier.padding(12.dp)) {
                    Text(
                        text = d.label ?: d.fingerprint.take(16),
                        style = MaterialTheme.typography.titleMedium,
                    )
                    Text("Code: ${d.code ?: "—"}")
                    Text("Last seen: ${d.lastSeenAt ?: "—"}")
                    Text("Bad attempts: ${d.badAttempts}")
                    if (d.blocked) {
                        Text(
                            text = "BLOCKED: ${d.blockedReason ?: ""}",
                            color = Color(0xFFEF4444),
                        )
                    }
                    Spacer(Modifier.height(4.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        if (d.blocked) {
                            OutlinedButton(onClick = { onUnblock(d.fingerprint) }) {
                                Text("Unblock")
                            }
                        } else {
                            OutlinedButton(onClick = { onBlock(d.fingerprint) }) {
                                Text("Block")
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun GenerateDialog(
    onDismiss: () -> Unit,
    onGenerate: (Int) -> Unit,
) {
    var count by remember { mutableStateOf("10") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Generate codes") },
        text = {
            Column {
                Text("How many fresh DRCD codes to create?")
                Spacer(Modifier.height(8.dp))
                OutlinedTextField(
                    value = count,
                    onValueChange = { v -> count = v.filter { it.isDigit() } },
                    singleLine = true,
                    label = { Text("Count") },
                )
            }
        },
        confirmButton = {
            Button(onClick = {
                val n = count.toIntOrNull()?.coerceIn(1, 200) ?: 10
                onGenerate(n)
            }) { Text("Generate") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Cancel") }
        },
    )
}

@Composable
private fun FreshCodesDialog(
    codes: List<String>,
    onDismiss: () -> Unit,
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("New codes (${codes.size})") },
        text = {
            Column {
                codes.take(50).forEach { c ->
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 2.dp)
                            .clickable { /* selection handled by click anywhere */ }
                            .background(Color(0xFF111827))
                            .padding(8.dp),
                    ) {
                        Text(text = c, color = Color(0xFFA7F3D0))
                    }
                }
                if (codes.size > 50) {
                    Spacer(Modifier.height(8.dp))
                    Text("…and ${codes.size - 50} more.")
                }
            }
        },
        confirmButton = {
            Button(onClick = onDismiss) { Text("Done") }
        },
    )
}

private fun matches(c: CodeRow, query: String): Boolean {
    if (query.isBlank()) return true
    val q = query.trim().lowercase()
    return c.code.lowercase().contains(q) ||
        (c.deviceLabel ?: "").lowercase().contains(q) ||
        (c.device ?: "").lowercase().contains(q) ||
        c.status.lowercase().contains(q)
}

private fun matches(d: DeviceRow, query: String): Boolean {
    if (query.isBlank()) return true
    val q = query.trim().lowercase()
    return d.fingerprint.lowercase().contains(q) ||
        (d.label ?: "").lowercase().contains(q) ||
        (d.code ?: "").lowercase().contains(q)
}
