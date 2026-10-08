package de.edgebird.lernsystem.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Chat
import androidx.compose.material.icons.automirrored.filled.LibraryBooks
import androidx.compose.material.icons.filled.AutoStories
import androidx.compose.material.icons.filled.School
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import de.edgebird.lernsystem.LernsystemApp
import de.edgebird.lernsystem.ui.theme.subjectColor

enum class SubjectTab(val label: String, val icon: ImageVector) {
    SOURCES("Quellen", Icons.AutoMirrored.Filled.LibraryBooks),
    CHAT("Chat", Icons.AutoMirrored.Filled.Chat),
    LEARN("Lernen", Icons.Default.School),
    STUDIO("Studio", Icons.Default.AutoStories),
}

/** Ein Fach mit seinen vier Bereichen (wie ein Notizbuch bei NotebookLM, plus Lernen). */
@Composable
fun SubjectScreen(subjectId: Long, tab: SubjectTab, onTab: (SubjectTab) -> Unit, onBack: () -> Unit, onFocus: () -> Unit, onModels: () -> Unit) {
    val ctx = androidx.compose.ui.platform.LocalContext.current
    val graph = (ctx.applicationContext as LernsystemApp).graph
    val subject by remember(subjectId) { graph.subjects.observe(subjectId) }.collectAsStateWithLifecycle(null)
    val all by remember { graph.subjects.observeSummaries() }.collectAsStateWithLifecycle(emptyList())
    val color = subject?.let { subjectColor(it.colorIndex) } ?: MaterialTheme.colorScheme.primary
    val focusVm: PomodoroViewModel = viewModel()

    Scaffold(
        containerColor = MaterialTheme.colorScheme.background,
        topBar = {
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(start = 4.dp, end = 12.dp, top = 8.dp, bottom = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Zurück zu den Fächern") }
                Box(Modifier.width(6.dp).height(28.dp).background(color, MaterialTheme.shapes.extraSmall))
                Text(subject?.name.orEmpty(), style = MaterialTheme.typography.titleLarge, modifier = Modifier.padding(start = 10.dp).weight(1f), maxLines = 1, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis)
                FocusChip(focusVm, onFocus)
            }
        },
        bottomBar = {
            NavigationBar(containerColor = MaterialTheme.colorScheme.surfaceContainer) {
                SubjectTab.entries.forEach { t ->
                    NavigationBarItem(
                        selected = t == tab, onClick = { onTab(t) }, icon = { Icon(t.icon, contentDescription = null) }, label = { Text(t.label) },
                        colors = NavigationBarItemDefaults.colors(indicatorColor = color.copy(alpha = 0.22f)),
                    )
                }
            }
        },
    ) { inner ->
        Box(Modifier.padding(inner).fillMaxSize()) {
            when (tab) {
                SubjectTab.SOURCES -> SourcesScreen(subjectId, otherSubjects = all.filter { it.subject.id != subjectId }.map { it.subject.id to it.subject.name })
                SubjectTab.CHAT -> ChatScreen(subjectId, onModels = onModels, onOpenSources = { onTab(SubjectTab.SOURCES) })
                SubjectTab.LEARN -> LearnScreen(subjectId)
                SubjectTab.STUDIO -> StudioScreen(subjectId)
            }
        }
    }
}
