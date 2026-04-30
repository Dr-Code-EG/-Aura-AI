package com.drcode.clock.settings

import android.content.Context
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map

private val Context.settingsDataStore by preferencesDataStore(name = "clock_settings")

data class ClockSettings(
    val extraQuestion: String = "Answer the question on the screen.",
)

class SettingsRepository(private val context: Context) {
    private val keyQuestion = stringPreferencesKey("extra_question")

    val settingsFlow: Flow<ClockSettings> = context.settingsDataStore.data.map { p -> toSettings(p) }

    suspend fun update(transform: (ClockSettings) -> ClockSettings) {
        context.settingsDataStore.edit { p ->
            val next = transform(toSettings(p))
            p[keyQuestion] = next.extraQuestion
        }
    }

    private fun toSettings(p: Preferences): ClockSettings = ClockSettings(
        extraQuestion = p[keyQuestion] ?: "Answer the question on the screen.",
    )
}
