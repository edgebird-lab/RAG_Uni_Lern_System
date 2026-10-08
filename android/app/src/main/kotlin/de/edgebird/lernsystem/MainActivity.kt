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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import de.edgebird.lernsystem.ui.ChatScreen
import de.edgebird.lernsystem.ui.DocumentsScreen
import de.edgebird.lernsystem.ui.LearnScreen
import de.edgebird.lernsystem.ui.PomodoroScreen

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
            MaterialTheme {
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
                    Box(Modifier.padding(inner)) { when (tab) { 0 -> ChatScreen(); 1 -> LearnScreen(); TAB_FOCUS -> PomodoroScreen(); else -> DocumentsScreen() } }
                }
            }
        }
    }

    companion object {
        const val EXTRA_TAB = "tab"
        const val TAB_FOCUS = 2
    }
}
