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
