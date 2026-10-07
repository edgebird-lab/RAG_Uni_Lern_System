package de.edgebird.lernsystem

import android.Manifest
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

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Benachrichtigungen für den Vordergrunddienst der Indexierung (Android 13+)
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { }.launch(Manifest.permission.POST_NOTIFICATIONS)
        setContent {
            MaterialTheme {
                var tab by rememberSaveable { mutableIntStateOf(0) }
                Scaffold(
                    bottomBar = {
                        NavigationBar {
                            NavigationBarItem(selected = tab == 0, onClick = { tab = 0 }, icon = {}, label = { Text("Chat") })
                            NavigationBarItem(selected = tab == 1, onClick = { tab = 1 }, icon = {}, label = { Text("Lernen") })
                            NavigationBarItem(selected = tab == 2, onClick = { tab = 2 }, icon = {}, label = { Text("Dokumente") })
                        }
                    },
                ) { inner ->
                    Box(Modifier.padding(inner)) { when (tab) { 0 -> ChatScreen(); 1 -> LearnScreen(); else -> DocumentsScreen() } }
                }
            }
        }
    }
}
