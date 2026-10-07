package de.edgebird.lernsystem

import android.Manifest
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.ui.Modifier
import de.edgebird.lernsystem.ui.DocumentsScreen

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // Benachrichtigungen für den Vordergrunddienst der Indexierung (Android 13+)
        registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) { }
            .launch(Manifest.permission.POST_NOTIFICATIONS)
        setContent {
            MaterialTheme {
                Scaffold { inner -> androidx.compose.foundation.layout.Box(Modifier.padding(inner)) { DocumentsScreen() } }
            }
        }
    }
}
