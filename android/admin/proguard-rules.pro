# Keep only what Compose + Kotlin reflect need.
-keepclasseswithmembers class * {
    @androidx.compose.runtime.Composable <methods>;
}
