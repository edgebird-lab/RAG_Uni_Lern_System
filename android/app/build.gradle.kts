import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "de.edgebird.lernsystem"
    compileSdk = 37

    defaultConfig {
        applicationId = "de.edgebird.lernsystem"
        minSdk = 31
        targetSdk = 37
        versionCode = 1
        versionName = "0.1.0"
        // Das Sprachmodell (LiteRT-LM) braucht ein 64-Bit-ARM-Gerät; andere Architekturen würden die APK nur um rund 45 MB vergrößern
        ndk { abiFilters += "arm64-v8a" }
    }

    // Upload-Schlüssel für das App Bundle: Zugangsdaten stehen in keystore.properties (nicht im Repo); ohne die Datei entsteht ein unsigniertes Bundle
    val keystoreProps = Properties().apply { rootProject.file("keystore.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) } }
    signingConfigs {
        if (keystoreProps.isNotEmpty()) create("upload") {
            storeFile = file(keystoreProps.getProperty("storeFile")); storePassword = keystoreProps.getProperty("storePassword")
            keyAlias = keystoreProps.getProperty("keyAlias"); keyPassword = keystoreProps.getProperty("keyPassword")
        }
    }

    // Die Sprache (Deutsch/Englisch) wählt die App selbst; das Bundle darf die Ressourcen nicht nach Gerätesprache aufteilen
    bundle { language { enableSplit = false } }

    buildTypes {
        release {
            signingConfigs.findByName("upload")?.let { signingConfig = it }
            // Zum Prüfen des Release-Builds neben der Entwicklerversion: -PappIdSuffix=.rc (eigene App mit eigenen Daten)
            (project.findProperty("appIdSuffix") as String?)?.let { applicationIdSuffix = it }
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    buildFeatures { compose = true }
}

dependencies {
    implementation(project(":core"))
    implementation(project(":ai"))
    implementation(project(":data"))
    implementation(project(":ingest"))
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.icons)
    implementation(libs.androidx.compose.tooling.preview)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.work.runtime)
    debugImplementation(libs.androidx.compose.tooling)

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
}

tasks.withType<Test>().configureEach { useJUnitPlatform() }
