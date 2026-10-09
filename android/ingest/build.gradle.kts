// SPDX-FileCopyrightText: 2026 Robin Olbricht – Olbricht Digital (edgebird-lab)
// SPDX-License-Identifier: GPL-3.0-or-later

plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "de.edgebird.lernsystem.ingest"
    compileSdk = 37
    defaultConfig {
        minSdk = 31
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }
}

dependencies {
    api(project(":core"))
    api(project(":data"))
    implementation(libs.pdfium)
    implementation(libs.tesseract)

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.kotlinx.coroutines.test)
    testRuntimeOnly(libs.junit.platform.launcher)

    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.kotlinx.coroutines.test)
}

tasks.withType<Test>().configureEach { useJUnitPlatform() }

// Sprachdaten der Texterkennung bei Bedarf laden (siehe tools/fetch_tessdata.sh)
val fetchTessdata by tasks.registering(Exec::class) {
    val script = rootProject.file("tools/fetch_tessdata.sh")
    val marker = layout.projectDirectory.file("src/main/assets/tessdata/eng.traineddata").asFile
    onlyIf { !marker.exists() }
    commandLine("bash", script.absolutePath)
}
tasks.named("preBuild") { dependsOn(fetchTessdata) }
