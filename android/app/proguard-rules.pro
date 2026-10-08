# Gson liest diese Klassen über Feldnamen (Manifest des Modell-Repos, JSON-Antworten der KI): nicht umbenennen.
-keep class de.edgebird.lernsystem.core.models.** { *; }
-keepattributes Signature, *Annotation*
-keep class com.google.gson.reflect.TypeToken { *; }
-keep class * extends com.google.gson.reflect.TypeToken
