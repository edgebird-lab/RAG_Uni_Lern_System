# Gson liest diese Klassen über Feldnamen (Manifest des Modell-Repos, JSON-Antworten der KI): nicht umbenennen.
-keep class de.edgebird.lernsystem.core.models.** { *; }
-keepattributes Signature, *Annotation*
-keep class com.google.gson.reflect.TypeToken { *; }
-keep class * extends com.google.gson.reflect.TypeToken

# Die Sprachausgabe (sherpa-onnx) wird aus nativem Code über Klassen- und Feldnamen angesprochen: nicht umbenennen
-keep class com.k2fsa.sherpa.onnx.** { *; }

# Natives rufen Java-Klassen dieser Bibliotheken über ihre Namen auf (JNI); die Bibliotheken bringen keine eigenen Regeln mit.
# Ohne diese Zeilen stürzt die App im Release-Build beim ersten Chat ab (NoSuchMethodError in LiteRtLmJni$JniMessageCallback).
-keep class com.google.ai.edge.litertlm.** { *; }
-keep class io.legere.pdfiumandroid.** { *; }
