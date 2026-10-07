package de.edgebird.lernsystem

import android.app.Application

class LernsystemApp : Application() {
    val graph: AppGraph by lazy { AppGraph(this) }
}
