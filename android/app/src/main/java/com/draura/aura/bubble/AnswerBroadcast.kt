package com.draura.aura.bubble

import android.content.Context
import android.content.Intent

/** Tiny in-process bus the bubble service uses to push text into the UI.
 *
 * We avoid androidx.localbroadcastmanager (deprecated, extra dep) in
 * favour of a straight broadcast scoped to our package via setPackage.
 */
object AnswerBroadcast {
    const val ACTION_STATUS = "com.draura.aura.STATUS"
    const val ACTION_ANSWER = "com.draura.aura.ANSWER"
    const val ACTION_ERROR = "com.draura.aura.ERROR"
    const val EXTRA_TEXT = "text"

    fun status(ctx: Context, text: String) = send(ctx, ACTION_STATUS, text)
    fun answer(ctx: Context, text: String) = send(ctx, ACTION_ANSWER, text)
    fun error(ctx: Context, text: String) = send(ctx, ACTION_ERROR, text)

    private fun send(ctx: Context, action: String, text: String) {
        val intent = Intent(action).apply {
            setPackage(ctx.packageName)
            putExtra(EXTRA_TEXT, text)
        }
        ctx.sendBroadcast(intent)
    }
}
