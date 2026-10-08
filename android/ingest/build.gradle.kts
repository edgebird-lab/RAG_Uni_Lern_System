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
    implementation(libs.mlkit.text)
    implementation("com.google.android.gms:play-services-tasks:18.2.0")

    testImplementation(libs.junit.jupiter)
    testImplementation(libs.kotlinx.coroutines.test)
    testRuntimeOnly(libs.junit.platform.launcher)

    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.kotlinx.coroutines.test)
}

tasks.withType<Test>().configureEach { useJUnitPlatform() }
