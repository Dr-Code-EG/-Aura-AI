package com.drcode.admin.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.drcode.admin.data.AdminRepository
import com.drcode.admin.data.CodeRow
import com.drcode.admin.data.DeviceRow
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class AdminUiState(
    val signedIn: Boolean = false,
    val email: String? = null,
    val loading: Boolean = false,
    val error: String? = null,
    val codes: List<CodeRow> = emptyList(),
    val devices: List<DeviceRow> = emptyList(),
    val freshCodes: List<String> = emptyList(),
)

class AdminViewModel(
    private val repo: AdminRepository = AdminRepository(),
) : ViewModel() {

    private val _state = MutableStateFlow(AdminUiState())
    val state: StateFlow<AdminUiState> = _state.asStateFlow()

    fun signIn(email: String, password: String) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                repo.signIn(email, password)
                _state.value = _state.value.copy(
                    signedIn = true,
                    email = repo.signedInEmail,
                    loading = false,
                )
                refresh()
            } catch (t: Throwable) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = humanize(t),
                )
            }
        }
    }

    fun signOut() {
        repo.signOut()
        _state.value = AdminUiState()
    }

    fun refresh() {
        if (!_state.value.signedIn) return
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val codes = repo.listCodes()
                val devices = repo.listDevices()
                _state.value = _state.value.copy(
                    codes = codes,
                    devices = devices,
                    loading = false,
                )
            } catch (t: Throwable) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = humanize(t),
                )
            }
        }
    }

    fun generateCodes(count: Int) {
        viewModelScope.launch {
            _state.value = _state.value.copy(loading = true, error = null)
            try {
                val fresh = repo.generateCodes(count)
                _state.value = _state.value.copy(
                    freshCodes = fresh,
                    loading = false,
                )
                refresh()
            } catch (t: Throwable) {
                _state.value = _state.value.copy(
                    loading = false,
                    error = humanize(t),
                )
            }
        }
    }

    fun revokeCode(code: String) = launchSafe {
        repo.revokeCode(code); refresh()
    }

    fun resetCode(code: String) = launchSafe {
        repo.resetCode(code); refresh()
    }

    fun blockDevice(fingerprint: String) = launchSafe {
        repo.blockDevice(fingerprint, "Blocked by admin")
        refresh()
    }

    fun unblockDevice(fingerprint: String) = launchSafe {
        repo.unblockDevice(fingerprint)
        refresh()
    }

    fun clearFreshCodes() {
        _state.value = _state.value.copy(freshCodes = emptyList())
    }

    fun clearError() {
        _state.value = _state.value.copy(error = null)
    }

    private fun launchSafe(block: suspend () -> Unit) {
        viewModelScope.launch {
            try { block() } catch (t: Throwable) {
                _state.value = _state.value.copy(error = humanize(t))
            }
        }
    }

    private fun humanize(t: Throwable): String {
        val msg = t.message.orEmpty()
        return when {
            msg.contains("INVALID_PASSWORD") ||
                msg.contains("EMAIL_NOT_FOUND") ->
                "Wrong email or password."
            msg.contains("INVALID_EMAIL") ->
                "Email address looks invalid."
            msg.contains("USER_DISABLED") ->
                "This admin account is disabled."
            msg.contains("PERMISSION_DENIED") ->
                "Your account isn't authorised as an admin."
            msg.contains("Network error", ignoreCase = true) ->
                "Network error. Check your connection."
            else -> msg.ifBlank { t.javaClass.simpleName }
        }
    }
}
