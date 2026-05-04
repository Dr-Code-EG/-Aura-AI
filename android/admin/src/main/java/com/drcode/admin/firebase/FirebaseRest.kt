package com.drcode.admin.firebase

import com.drcode.admin.BuildConfig
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Tiny REST wrapper for Firebase Identity Toolkit + Firestore.
 *
 * The admin app deliberately does NOT use the Firebase Android SDK
 * (com.google.firebase:firebase-bom). The SDK requires the
 * google-services Gradle plugin and a per-package "Add app" entry in
 * the Firebase console — we want to ship the admin APK without
 * having to coordinate package names with the existing Firebase
 * project. REST works with just the project ID + public Web API key.
 */
class FirebaseRest(
    private val projectId: String = BuildConfig.FIREBASE_PROJECT_ID,
    private val apiKey: String = BuildConfig.FIREBASE_API_KEY,
) {
    private val http: OkHttpClient = OkHttpClient.Builder()
        .callTimeout(15, TimeUnit.SECONDS)
        .build()

    private val json = "application/json".toMediaType()
    private val firestoreBase =
        "https://firestore.googleapis.com/v1/projects/$projectId/databases/(default)/documents"

    // ----------------------------------------------------------- Auth
    data class AuthSession(
        val idToken: String,
        val refreshToken: String,
        val localId: String,
        val email: String,
    )

    @Throws(FirebaseException::class)
    fun signInWithPassword(email: String, password: String): AuthSession {
        val url =
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=$apiKey"
        val body = JSONObject().apply {
            put("email", email)
            put("password", password)
            put("returnSecureToken", true)
        }
        val resp = postJson(url, body, idToken = null)
        return AuthSession(
            idToken = resp.getString("idToken"),
            refreshToken = resp.getString("refreshToken"),
            localId = resp.getString("localId"),
            email = resp.optString("email", email),
        )
    }

    // ------------------------------------------------------- Firestore
    @Throws(FirebaseException::class)
    fun listCollection(path: String, idToken: String): List<JSONObject> {
        val url = "$firestoreBase/$path?pageSize=300"
        val raw = getJson(url, idToken)
        val docs = raw.optJSONArray("documents") ?: JSONArray()
        return (0 until docs.length()).map { docs.getJSONObject(it) }
    }

    @Throws(FirebaseException::class)
    fun getDocument(path: String, idToken: String): JSONObject? {
        val url = "$firestoreBase/$path"
        return try {
            getJson(url, idToken)
        } catch (e: FirebaseException) {
            if (e.statusCode == 404) null else throw e
        }
    }

    @Throws(FirebaseException::class)
    fun patchDocument(
        path: String,
        fields: Map<String, Any?>,
        idToken: String,
        updateMask: List<String>? = null,
    ): JSONObject {
        val mask = updateMask?.joinToString(separator = "&") {
            "updateMask.fieldPaths=$it"
        } ?: ""
        val url = if (mask.isEmpty()) {
            "$firestoreBase/$path"
        } else {
            "$firestoreBase/$path?$mask"
        }
        val body = JSONObject().put("fields", fieldsToJson(fields))
        val req = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $idToken")
            .header("Content-Type", "application/json")
            .patch(body.toString().toRequestBody(json))
            .build()
        return execute(req)
    }

    @Throws(FirebaseException::class)
    fun deleteDocument(path: String, idToken: String) {
        val url = "$firestoreBase/$path"
        val req = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $idToken")
            .delete()
            .build()
        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) {
                throw FirebaseException(resp.code, resp.body?.string() ?: "")
            }
        }
    }

    // ------------------------------------------------------- helpers
    private fun postJson(
        url: String,
        body: JSONObject,
        idToken: String?,
    ): JSONObject {
        val req = Request.Builder()
            .url(url)
            .header("Content-Type", "application/json")
            .apply {
                if (idToken != null) header("Authorization", "Bearer $idToken")
            }
            .post(body.toString().toRequestBody(json))
            .build()
        return execute(req)
    }

    private fun getJson(url: String, idToken: String): JSONObject {
        val req = Request.Builder()
            .url(url)
            .header("Authorization", "Bearer $idToken")
            .get()
            .build()
        return execute(req)
    }

    private fun execute(req: Request): JSONObject {
        http.newCall(req).execute().use { resp ->
            val text = resp.body?.string() ?: ""
            if (!resp.isSuccessful) {
                throw FirebaseException(resp.code, text)
            }
            return if (text.isNotEmpty()) JSONObject(text) else JSONObject()
        }
    }

    /** Convert plain Kotlin types into Firestore wire JSON. */
    private fun fieldsToJson(fields: Map<String, Any?>): JSONObject {
        val out = JSONObject()
        for ((k, v) in fields) {
            out.put(k, valueToJson(v))
        }
        return out
    }

    private fun valueToJson(v: Any?): JSONObject {
        val o = JSONObject()
        when (v) {
            null -> o.put("nullValue", JSONObject.NULL)
            is Boolean -> o.put("booleanValue", v)
            is Int -> o.put("integerValue", v.toString())
            is Long -> o.put("integerValue", v.toString())
            is Double -> o.put("doubleValue", v)
            is Float -> o.put("doubleValue", v.toDouble())
            is String -> o.put("stringValue", v)
            is Map<*, *> -> {
                val map = JSONObject()
                @Suppress("UNCHECKED_CAST")
                for ((mk, mv) in v as Map<String, Any?>) {
                    map.put(mk, valueToJson(mv))
                }
                o.put("mapValue", JSONObject().put("fields", map))
            }
            else -> o.put("stringValue", v.toString())
        }
        return o
    }
}

class FirebaseException(val statusCode: Int, val responseBody: String) :
    RuntimeException("Firebase REST error $statusCode: $responseBody")
