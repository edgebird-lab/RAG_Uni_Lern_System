package de.edgebird.lernsystem

import android.Manifest
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Scaffold
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import de.edgebird.lernsystem.ui.HomeScreen
import de.edgebird.lernsystem.ui.ModelScreen
import de.edgebird.lernsystem.ui.PomodoroScreen
import de.edgebird.lernsystem.ui.PrivacyScreen
import de.edgebird.lernsystem.ui.SubjectScreen
import de.edgebird.lernsystem.ui.SubjectTab
import de.edgebird.lernsystem.ui.theme.LernTheme

/** Ziele der Navigation; als Text gespeichert, damit sie Drehen und Prozessende überstehen: `home`, `subject:ID:TAB`, `focus`, `models`, `privacy`. */
private fun parse(route: String): List<String> = route.split(":")

class MainActivity : ComponentActivity() {
    private val requestedTab = mutableIntStateOf(-1)
    private val shared = mutableStateOf<de.edgebird.lernsystem.ui.SharedContent?>(null)

    override fun attachBaseContext(newBase: android.content.Context) {
        // Gebietsschema der App als Überschreibung der Konfiguration (statt den Kontext zu ersetzen: sonst ist er für Dienste wie das Drucken keine Activity mehr)
        applyOverrideConfiguration(android.content.res.Configuration().apply { setLocale(de.edgebird.lernsystem.core.i18n.Lang.current.locale) })
        super.attachBaseContext(newBase)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        requestedTab.intValue = intent.getIntExtra(EXTRA_TAB, -1)
        de.edgebird.lernsystem.ui.SharedContent.from(intent)?.let { shared.value = it }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedTab.intValue = intent.getIntExtra(EXTRA_TAB, -1)
        if (savedInstanceState == null) de.edgebird.lernsystem.ui.SharedContent.from(intent)?.let { shared.value = it }
        // Benachrichtigungen für Vordergrunddienste (Import, Download) und den Fokus-Timer (Android 13+)
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }.launch(Manifest.permission.POST_NOTIFICATIONS)
        setContent {
            LernTheme {
                val graph = (application as LernsystemApp).graph
                var modelsOk by rememberSaveable { mutableStateOf(graph.llmModelFile.exists() && graph.embeddingModelFile.exists()) }
                var route by rememberSaveable { mutableStateOf("home") }
                if (requestedTab.intValue >= 0) { route = "focus"; requestedTab.intValue = -1 }

                if (!modelsOk) {
                    Scaffold { inner -> Box(Modifier.padding(inner)) { ModelScreen(firstRun = true, onDone = { modelsOk = true }) } }
                    return@LernTheme
                }
                val share = shared.value
                if (share != null) {
                    de.edgebird.lernsystem.ui.ShareTargetDialog(
                        share, onDone = { msg -> shared.value = null; android.widget.Toast.makeText(this@MainActivity, msg, android.widget.Toast.LENGTH_LONG).show(); route = "home" },
                        onDismiss = { shared.value = null },
                    )
                }
                val parts = parse(route)
                androidx.compose.runtime.CompositionLocalProvider(de.edgebird.lernsystem.ui.LocalOpenModels provides { route = "models:$route" }) {
                when (parts[0]) {
                    "subject" -> {
                        val id = parts[1].toLong()
                        val tab = SubjectTab.entries[parts[2].toInt()]
                        BackHandler { route = "home" }
                        SubjectScreen(
                            subjectId = id, tab = tab, onTab = { route = "subject:$id:${it.ordinal}" }, onBack = { route = "home" },
                            onFocus = { route = "focus:subject:$id:${tab.ordinal}" }, onModels = { route = "models:subject:$id:${tab.ordinal}" },
                        )
                    }
                    "focus" -> Scaffold { inner ->
                        val back = parts.drop(1).joinToString(":").ifEmpty { "home" }
                        BackHandler { route = back }
                        Box(Modifier.padding(inner).fillMaxSize()) { PomodoroScreen(onBack = { route = back }) }
                    }
                    "models" -> Scaffold { inner ->
                        val back = parts.drop(1).joinToString(":").ifEmpty { "home" }
                        BackHandler { route = back }
                        Box(Modifier.padding(inner)) { ModelScreen(firstRun = false, onDone = {}, onBack = { route = back }) }
                    }
                    "privacy" -> Scaffold { inner ->
                        BackHandler { route = "home" }
                        Box(Modifier.padding(inner)) { PrivacyScreen(onBack = { route = "home" }) }
                    }
                    else -> Scaffold { inner ->
                        Box(Modifier.padding(inner)) {
                            HomeScreen(
                                onOpen = { route = "subject:$it:${SubjectTab.CHAT.ordinal}" }, onFocus = { route = "focus" },
                                onModels = { route = "models" }, onPrivacy = { route = "privacy" },
                            )
                        }
                    }
                }
                }
            }
        }
    }

    companion object {
        const val EXTRA_TAB = "tab"
        const val TAB_FOCUS = 2
    }
}
