package com.drcode.admin.data

import org.json.JSONObject

/** A single activation code as it lives in Firestore. */
data class CodeRow(
    val code: String,
    val status: String,           // unused | active | revoked
    val device: String?,
    val deviceLabel: String?,
    val activatedAt: String?,
    val lastSeenAt: String?,
    val createdAt: String?,
)

/** A device that has either claimed a code or accumulated bad attempts. */
data class DeviceRow(
    val fingerprint: String,
    val code: String?,
    val label: String?,
    val lastSeenAt: String?,
    val badAttempts: Int,
    val blocked: Boolean,
    val blockedReason: String?,
)

/** Decode a Firestore document into a [CodeRow]. */
fun parseCode(doc: JSONObject): CodeRow {
    val name = doc.optString("name")
    val codeId = name.substringAfterLast("/")
    val fields = doc.optJSONObject("fields") ?: JSONObject()
    return CodeRow(
        code = codeId,
        status = fields.stringValue("status") ?: "unused",
        device = fields.stringValue("device"),
        deviceLabel = fields.stringValue("device_label"),
        activatedAt = fields.stringValue("activated_at"),
        lastSeenAt = fields.stringValue("last_seen_at"),
        createdAt = fields.stringValue("created_at"),
    )
}

fun parseDevice(doc: JSONObject): DeviceRow {
    val name = doc.optString("name")
    val fp = name.substringAfterLast("/")
    val fields = doc.optJSONObject("fields") ?: JSONObject()
    return DeviceRow(
        fingerprint = fp,
        code = fields.stringValue("code"),
        label = fields.stringValue("label"),
        lastSeenAt = fields.stringValue("last_seen_at"),
        badAttempts = fields.intValue("bad_attempts") ?: 0,
        blocked = fields.boolValue("blocked") ?: false,
        blockedReason = fields.stringValue("reason"),
    )
}

private fun JSONObject.stringValue(key: String): String? {
    val obj = optJSONObject(key) ?: return null
    return if (obj.has("stringValue")) obj.optString("stringValue") else null
}

private fun JSONObject.intValue(key: String): Int? {
    val obj = optJSONObject(key) ?: return null
    return obj.optString("integerValue").takeIf { it.isNotEmpty() }?.toIntOrNull()
}

private fun JSONObject.boolValue(key: String): Boolean? {
    val obj = optJSONObject(key) ?: return null
    return if (obj.has("booleanValue")) obj.optBoolean("booleanValue") else null
}
