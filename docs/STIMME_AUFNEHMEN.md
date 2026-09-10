# Deine Stimme für das Audio-Overview aufnehmen

Diese Anleitung ist der erste (und wichtigste) Schritt für das Audio-Overview-
Feature: die App soll deine Dokumente später mit **deiner eigenen, geklonten
Stimme** vorlesen, nicht mit einer generischen KI-Stimme. Die Qualität der
Aufnahme entscheidet dabei mehr über das Endergebnis als jede Modell-Wahl -
deshalb lohnt es sich, sich hierfür 10 Minuten Zeit zu nehmen.

Die Aufnahme bleibt **komplett lokal auf deinem Rechner** - nichts davon wird
irgendwohin hochgeladen oder verlässt deinen PC.

## 1. Vorbereitung (2 Minuten)

- **Raum:** ruhig, möglichst ohne Hall. Ein normal möbliertes Zimmer (Teppich,
  Vorhänge, Regale) ist ideal - **kein** Bad, Treppenhaus oder leerer großer
  Raum (die harten Flächen erzeugen ein Echo, das sich später nicht mehr
  rausrechnen lässt). Fenster zu, Handy stumm, Lüftung/Ventilator/Klimaanlage
  aus.
- **Mikrofon:** Falls vorhanden ein USB-Mikrofon oder ein ordentliches Headset
  benutzen. Das eingebaute Laptop-Mikrofon geht zur Not auch, nimmt aber eher
  Raumhall und Lüftergeräusche mit auf - wenn du die Wahl hast, lieber ein
  externes Mikro nehmen.
- **Abstand:** ca. 15-20 cm zum Mikrofon, leicht seitlich statt direkt
  frontal ansprechen (vermeidet harte "P"/"B"-Plopplaute). Den Abstand
  während der ganzen Aufnahme möglichst gleich halten.

## 2. Aufnehmen (5-10 Minuten)

Irgendeine Aufnahme-App reicht völlig - das Standard-Diktiergerät des Handys,
Windows' "Sprachrekorder", Audacity, o. ä.

- **Format:** WAV, ersatzweise eine hochwertige MP3. 44.1 kHz. Mono reicht.
- **Sprechweise:** normales Tempo, normale Lautstärke - **nicht monoton**
  vorlesen, sondern so, als würdest du es jemandem erklären. Das Modell
  übernimmt Sprechmelodie und Betonung direkt aus der Aufnahme, ein
  lebendiger Vortrag klingt später auch lebendiger.
- Lies den Text unten **einmal komplett am Stück** vor (kleine Versprecher
  sind kein Problem, einfach den Satz nochmal sprechen und weiterlesen -
  nicht extra rausschneiden).
- Wenn dir das Ergebnis später nicht gefällt: einfach neu aufnehmen, das
  kannst du beliebig oft wiederholen.

## 3. Datei ablegen

Die fertige Aufnahme hier ablegen (Ordner ggf. neu anlegen):

```
data/voice/reference.wav
```

Die App sucht die Datei genau dort - liegt sie da, zeigt die kommende
Audio-Overview-Seite direkt den "Erstellen"-Knopf statt der Aufnahme-Anleitung.

---

## Der Vorlesetext

Bewusst abwechslungsreich (Aussagesätze, Fragen, Aufzählungen, Zahlen, ein paar
Fachbegriffe) - das deckt viele verschiedene Laute ab und ergibt eine deutlich
bessere Klonqualität als ein kurzer oder eintöniger Text. Insgesamt etwa 3-5
Minuten Sprechzeit.

> Hallo, ich nehme gerade meine Stimme auf, damit mein Lernsystem sie für
> Audio-Zusammenfassungen benutzen kann. Ich lese dafür einen kurzen Text vor,
> der möglichst viele verschiedene Laute und Satzformen enthält.
>
> Fangen wir mit etwas Einfachem an: Wie geht es dir heute? Ich hoffe, du hast
> einen angenehmen Tag. Das Wetter draußen wechselt gerade ständig zwischen
> Sonne und Wolken, aber das stört mich eigentlich nicht besonders.
>
> Beim Lernen für eine Klausur hilft es enorm, den Stoff in kleine Abschnitte
> zu unterteilen und regelmäßig zu wiederholen, statt alles auf den letzten
> Drücker in einer einzigen, langen Nacht durchzuackern. Wissenschaftliche
> Studien zur sogenannten "Spaced Repetition" zeigen das schon seit
> Jahrzehnten sehr deutlich.
>
> Zählen wir kurz ein paar Zahlen auf: eins, zwei, drei, vier, fünf, sechs,
> sieben, acht, neun, zehn - und weiter mit größeren Zahlen: dreiundzwanzig,
> einhundertsiebenundvierzig, zweitausendsechsundzwanzig. Auch Uhrzeiten und
> Daten kommen häufig vor, zum Beispiel: Die Vorlesung beginnt um Viertel
> nach neun, die Prüfung findet am zwölften Februar statt.
>
> Es gibt vier Jahreszeiten: Frühling, Sommer, Herbst und Winter. Jede davon
> hat ihren eigenen Charakter - der Frühling steht für Aufbruch, der Sommer
> für Wärme, der Herbst für Ruhe, und der Winter für Rückzug und Besinnung.
>
> Manchmal stelle ich mir auch Fragen wie: Was ist eigentlich der Unterschied
> zwischen Wissen und Verständnis? Kann man etwas auswendig lernen, ohne es
> wirklich zu begreifen? Und wie erkennt man den Unterschied bei sich selbst?
>
> Ein paar kniffligere Wörter zum Abschluss, damit auch schwierigere Laute
> vorkommen: Streichholzschächtelchen, Wirtschaftsprüfungsgesellschaft,
> Nachhaltigkeitsstrategie, Verantwortungsbewusstsein, Zusammenarbeit,
> Öffentlichkeitsarbeit, Empfängnisverhütung, Skepsis, Pfütze, Quarzuhr.
>
> Zum Schluss noch ein etwas längerer, ruhig gesprochener Absatz: Ich glaube,
> dass gute Erklärungen vor allem dann entstehen, wenn man sich Zeit nimmt,
> laut auszusprechen, was man verstanden hat - nicht nur stumm zu lesen. Genau
> deshalb finde ich die Idee, mir meine eigenen Zusammenfassungen vorlesen zu
> lassen, so spannend. Das war's von meiner Seite - vielen Dank fürs Zuhören,
> und bis zum nächsten Mal.

## Und danach?

Sobald `data/voice/reference.wav` existiert, teste ich zuerst **isoliert**
(nur ein Beispieltext, ohne die restliche Pipeline), ob die Klonqualität
überzeugt, und lasse dir eine Hörprobe zukommen, bevor die komplette
Audio-Overview-Seite gebaut wird.
