package de.edgebird.lernsystem

import android.Manifest
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import de.edgebird.lernsystem.ui.ChatScreen
import de.edgebird.lernsystem.ui.DocumentsScreen
import de.edgebird.lernsystem.ui.LearnScreen
import de.edgebird.lernsystem.ui.ModelScreen
import de.edgebird.lernsystem.ui.PomodoroScreen
import de.edgebird.lernsystem.ui.PrivacyScreen

class MainActivity : ComponentActivity() {
    private val requestedTab = mutableIntStateOf(-1)

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        requestedTab.intValue = intent.getIntExtra(EXTRA_TAB, -1)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestedTab.intValue = intent.getIntExtra(EXTRA_TAB, -1)
        // Benachrichtigungen für den Vordergrunddienst der Indexierung (Android 13+)
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }.launch(Manifest.permission.POST_NOTIFICATIONS)
        setContent {
            val dark = androidx.compose.foundation.isSystemInDarkTheme()
            val ctx = androidx.compose.ui.platform.LocalContext.current
            MaterialTheme(colorScheme = if (dark) androidx.compose.material3.dynamicDarkColorScheme(ctx) else androidx.compose.material3.dynamicLightColorScheme(ctx)) {
                val graph = (application as LernsystemApp).graph
                var modelsOk by rememberSaveable { mutableStateOf(graph.llmModelFile.exists() && graph.embeddingModelFile.exists()) }
                if (!modelsOk) {
                    Scaffold { inner -> Box(Modifier.padding(inner)) { ModelScreen(firstRun = true, onDone = { modelsOk = true }) } }
                    return@MaterialTheme
                }
                var showModels by rememberSaveable { mutableStateOf(false) }
                var showPrivacy by rememberSaveable { mutableStateOf(false) }
                if (showPrivacy) {
                    Scaffold { inner -> Box(Modifier.padding(inner)) { PrivacyScreen(onBack = { showPrivacy = false }) } }
                    return@MaterialTheme
                }
                if (showModels) {
                    Scaffold { inner -> Box(Modifier.padding(inner)) { ModelScreen(firstRun = false, onDone = {}, onBack = { showModels = false }) } }
                    return@MaterialTheme
                }
                var tab by rememberSaveable { mutableIntStateOf(0) }
                if (requestedTab.intValue >= 0) { tab = requestedTab.intValue; requestedTab.intValue = -1 }
                Scaffold(
                    bottomBar = {
                        NavigationBar {
                            NavigationBarItem(selected = tab == 0, onClick = { tab = 0 }, icon = {}, label = { Text("Chat") })
                            NavigationBarItem(selected = tab == 1, onClick = { tab = 1 }, icon = {}, label = { Text("Lernen") })
                            NavigationBarItem(selected = tab == TAB_FOCUS, onClick = { tab = TAB_FOCUS }, icon = {}, label = { Text("Fokus") })
                            NavigationBarItem(selected = tab == 3, onClick = { tab = 3 }, icon = {}, label = { Text("Dokumente") })
                        }
                    },
                ) { inner ->
                    Box(Modifier.padding(inner)) { when (tab) { 0 -> ChatScreen(onModels = { showModels = true }); 1 -> LearnScreen(); TAB_FOCUS -> PomodoroScreen(); else -> DocumentsScreen(onModels = { showModels = true }, onPrivacy = { showPrivacy = true }) } }
                }
            }
        }
    }

    companion object {
        const val EXTRA_TAB = "tab"
        const val TAB_FOCUS = 2
    }
}
