package com.draura.aura.gemini

import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/**
 * Minimal Gemini REST client using the public Generative Language API.
 *
 * This deliberately avoids the official Google AI client SDK so the app
 * stays small and we don't pull in a transitive dep on Guava + Protobuf.
 */
class GeminiClient {
    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(60, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    /**
     * Sends [pngBytes] (the screenshot) plus [question] to Gemini and
     * returns the model's plain-text answer.
     *
     * @throws GeminiException on HTTP or API errors.
     */
    suspend fun answer(
        apiKey: String,
        model: String,
        pngBytes: ByteArray,
        question: String,
    ): String = withContext(Dispatchers.IO) {
        require(apiKey.isNotBlank()) { "Gemini API key is required" }

        val b64 = Base64.encodeToString(pngBytes, Base64.NO_WRAP)
        val payload = JSONObject().apply {
            put("contents", JSONArray().put(
                JSONObject().put("parts", JSONArray()
                    .put(JSONObject().put("text", question))
                    .put(JSONObject().put(
                        "inline_data",
                        JSONObject()
                            .put("mime_type", "image/png")
                            .put("data", b64)
                    ))
                )
            ))
            put("systemInstruction", JSONObject().put("parts", JSONArray().put(
                JSONObject().put(
                    "text",
                    "You are an expert tutor helping the user answer the question " +
                        "in the attached screenshot. Be precise. If multiple choice, " +
                        "give the answer letter and a 1-2 line justification."
                )
            )))
            put("generationConfig", JSONObject()
                .put("temperature", 0.2)
                .put("maxOutputTokens", 1024))
        }

        val url = "https://generativelanguage.googleapis.com/v1beta/models/" +
            "$model:generateContent?key=$apiKey"
        val req = Request.Builder()
            .url(url)
            .post(payload.toString().toRequestBody(JSON))
            .build()

        http.newCall(req).execute().use { resp ->
            val body = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) {
                throw GeminiException(
                    "Gemini HTTP ${resp.code}: ${truncate(body, 400)}"
                )
            }
            extractText(body)
        }
    }

    private fun extractText(body: String): String {
        val root = JSONObject(body)
        val candidates = root.optJSONArray("candidates")
            ?: throw GeminiException("Empty response from Gemini.")
        if (candidates.length() == 0) {
            val pf = root.optJSONObject("promptFeedback")
            throw GeminiException(
                "Gemini returned no candidates. ${pf?.toString()?.let { "Reason: $it" }.orEmpty()}"
            )
        }
        val parts = candidates.getJSONObject(0)
            .optJSONObject("content")
            ?.optJSONArray("parts")
            ?: throw GeminiException("Malformed Gemini response.")
        val sb = StringBuilder()
        for (i in 0 until parts.length()) {
            val t = parts.getJSONObject(i).optString("text", "")
            if (t.isNotEmpty()) sb.append(t)
        }
        return sb.toString().ifBlank { "(empty response)" }
    }

    private fun truncate(s: String, max: Int): String =
        if (s.length <= max) s else s.substring(0, max) + "…"

    companion object {
        private val JSON = "application/json; charset=utf-8".toMediaType()
    }
}

class GeminiException(msg: String) : RuntimeException(msg)
