package com.draura.aura.settings

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.settingsDataStore by preferencesDataStore(name = "aura_settings")

data class AuraSettings(
    val provider: String = PROVIDER_GEMINI,
    val geminiApiKey: String = "",
    val geminiModel: String = "gemini-2.0-flash",
    val extraQuestion: String = "Answer the question on the screen.",
) {
    companion object {
        const val PROVIDER_GEMINI = "gemini"
        const val PROVIDER_CHATGPT = "chatgpt"
    }
}

class SettingsRepository(private val context: Context) {
    private val keyProvider = stringPreferencesKey("provider")
    private val keyApiKey = stringPreferencesKey("gemini_api_key")
    private val keyModel = stringPreferencesKey("gemini_model")
    private val keyQuestion = stringPreferencesKey("extra_question")

    val settingsFlow: Flow<AuraSettings> = context.settingsDataStore.data.map { p ->
        toSettings(p)
    }

    suspend fun update(transform: (AuraSettings) -> AuraSettings) {
        context.settingsDataStore.edit { p ->
            val current = toSettings(p)
            val next = transform(current)
            p[keyProvider] = next.provider
            p[keyApiKey] = next.geminiApiKey
            p[keyModel] = next.geminiModel
            p[keyQuestion] = next.extraQuestion
        }
    }

    private fun toSettings(p: Preferences): AuraSettings = AuraSettings(
        provider = p[keyProvider] ?: AuraSettings.PROVIDER_GEMINI,
        geminiApiKey = p[keyApiKey] ?: "",
        geminiModel = p[keyModel] ?: "gemini-2.0-flash",
        extraQuestion = p[keyQuestion] ?: "Answer the question on the screen.",
    )
}
