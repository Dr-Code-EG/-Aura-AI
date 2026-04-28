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
    val extraQuestion: String = "Answer the question on the screen.",
)

class SettingsRepository(private val context: Context) {
    private val keyQuestion = stringPreferencesKey("extra_question")

    val settingsFlow: Flow<AuraSettings> = context.settingsDataStore.data.map { p -> toSettings(p) }

    suspend fun update(transform: (AuraSettings) -> AuraSettings) {
        context.settingsDataStore.edit { p ->
            val next = transform(toSettings(p))
            p[keyQuestion] = next.extraQuestion
        }
    }

    private fun toSettings(p: Preferences): AuraSettings = AuraSettings(
        extraQuestion = p[keyQuestion] ?: "Answer the question on the screen.",
    )
}
