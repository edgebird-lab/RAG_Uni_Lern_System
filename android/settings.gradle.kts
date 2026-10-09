// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        // Tesseract4Android (Texterkennung, Apache-2.0) gibt es nur über JitPack; nur diese Gruppe wird von dort geladen
        maven("https://jitpack.io") { content { includeGroupByRegex("com\\.github\\.adaptech-cz.*") } }
    }
}

rootProject.name = "lernsystem-android"
include(":app", ":core", ":ai", ":data", ":ingest")
