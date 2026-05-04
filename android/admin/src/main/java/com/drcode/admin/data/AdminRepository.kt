package com.drcode.admin.data

import com.drcode.admin.firebase.FirebaseRest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.security.SecureRandom
import java.time.Instant

/**
 * Glue between the UI and the Firestore REST layer. All network I/O
 * happens here on the IO dispatcher; the ViewModel never sees raw
 * JSON.
 */
class AdminRepository(
    private val firebase: FirebaseRest = FirebaseRest(),
) {
    @Volatile
    private var session: FirebaseRest.AuthSession? = null

    val isSignedIn: Boolean get() = session != null
    val signedInEmail: String? get() = session?.email

    suspend fun signIn(email: String, password: String) = withContext(Dispatchers.IO) {
        session = firebase.signInWithPassword(email, password)
    }

    fun signOut() {
        session = null
    }

    private fun token(): String =
        session?.idToken ?: error("Not signed in.")

    suspend fun listCodes(): List<CodeRow> = withContext(Dispatchers.IO) {
        firebase.listCollection("codes", token()).map(::parseCode)
            .sortedByDescending { it.createdAt ?: "" }
    }

    suspend fun listDevices(): List<DeviceRow> = withContext(Dispatchers.IO) {
        firebase.listCollection("devices", token()).map(::parseDevice)
            .sortedByDescending { it.lastSeenAt ?: "" }
    }

    suspend fun listBlockedDevices(): List<DeviceRow> =
        withContext(Dispatchers.IO) {
            firebase.listCollection("blocked_devices", token())
                .map(::parseDevice)
        }

    /** Generate `count` fresh DRCD-XXXX-XXXX-XXXX codes and store them. */
    suspend fun generateCodes(count: Int): List<String> =
        withContext(Dispatchers.IO) {
            val now = Instant.now().toString()
            val out = mutableListOf<String>()
            repeat(count) {
                val code = newCode()
                firebase.patchDocument(
                    path = "codes/$code",
                    fields = mapOf(
                        "status" to "unused",
                        "created_at" to now,
                        "created_by" to (session?.email ?: ""),
                    ),
                    idToken = token(),
                    updateMask = listOf("status", "created_at", "created_by"),
                )
                out += code
            }
            out
        }

    suspend fun revokeCode(code: String) = withContext(Dispatchers.IO) {
        firebase.patchDocument(
            path = "codes/$code",
            fields = mapOf("status" to "revoked"),
            idToken = token(),
            updateMask = listOf("status"),
        )
    }

    suspend fun resetCode(code: String) = withContext(Dispatchers.IO) {
        // Wipes the device binding so the same code can be reused on
        // a different machine — handy when a user replaces their PC.
        firebase.patchDocument(
            path = "codes/$code",
            fields = mapOf(
                "status" to "unused",
                "device" to "",
                "device_label" to "",
            ),
            idToken = token(),
            updateMask = listOf("status", "device", "device_label"),
        )
    }

    suspend fun blockDevice(fingerprint: String, reason: String) =
        withContext(Dispatchers.IO) {
            firebase.patchDocument(
                path = "blocked_devices/$fingerprint",
                fields = mapOf(
                    "blocked" to true,
                    "reason" to reason,
                    "blocked_at" to Instant.now().toString(),
                ),
                idToken = token(),
                updateMask = listOf("blocked", "reason", "blocked_at"),
            )
        }

    suspend fun unblockDevice(fingerprint: String) =
        withContext(Dispatchers.IO) {
            firebase.patchDocument(
                path = "blocked_devices/$fingerprint",
                fields = mapOf(
                    "blocked" to false,
                    "reason" to "",
                ),
                idToken = token(),
                updateMask = listOf("blocked", "reason"),
            )
            // Also reset the device's bad-attempts counter so the
            // user gets a clean slate on their next launch.
            firebase.patchDocument(
                path = "devices/$fingerprint",
                fields = mapOf(
                    "blocked" to false,
                    "bad_attempts" to 0,
                ),
                idToken = token(),
                updateMask = listOf("blocked", "bad_attempts"),
            )
        }

    private fun newCode(): String {
        val rng = SecureRandom()
        val alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  // no 0/O/1/I
        val sb = StringBuilder("DRCD")
        repeat(3) {
            sb.append('-')
            repeat(4) { sb.append(alphabet[rng.nextInt(alphabet.length)]) }
        }
        return sb.toString()
    }
}
