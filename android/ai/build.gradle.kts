plugins {
    alias(libs.plugins.android.library)
}

android {
    namespace = "de.edgebird.lernsystem.ai"
    compileSdk = 37
    defaultConfig { minSdk = 31 }
}

dependencies {
    api(project(":core"))
    implementation(libs.litertlm.android)
}

// Native Bibliotheken der Offline-Sprachausgabe (sherpa-onnx) bei Bedarf laden (siehe tools/fetch_sherpa.sh)
val fetchSherpa by tasks.registering(Exec::class) {
    val script = rootProject.file("tools/fetch_sherpa.sh")
    val marker = layout.projectDirectory.file("src/main/jniLibs/arm64-v8a/libsherpa-onnx-jni.so").asFile
    onlyIf { !marker.exists() }
    commandLine("bash", script.absolutePath)
}
tasks.named("preBuild") { dependsOn(fetchSherpa) }
