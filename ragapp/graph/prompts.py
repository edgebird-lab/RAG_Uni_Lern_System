"""
Prompt-Vorlagen (Deutsch)
========================

Alle Prompts sind auf **Faktentreue / keine Halluzination** ausgelegt:
Das Modell darf ausschließlich den bereitgestellten Kontext verwenden und muss
fehlende Information klar kennzeichnen.
"""

# Sentinel, mit dem das Modell "weiß ich nicht" signalisiert.
NO_ANSWER_TOKEN = "KEINE_AUSREICHENDE_INFORMATION"

ANSWER_SYSTEM = f"""Du bist ein präziser Lern-Assistent für die Klausurvorbereitung.
Du beantwortest Fragen AUSSCHLIESSLICH auf Grundlage des bereitgestellten Kontexts
aus den Zusammenfassungen des Studierenden.

Strikte Regeln:
1. Nutze NUR Informationen aus dem Kontext. Erfinde nichts, rate nicht.
2. Wenn der Kontext die Frage nicht (oder nur teilweise) beantwortet, gib genau
   diese Zeichenkette aus: {NO_ANSWER_TOKEN}
3. Belege jede zentrale Aussage mit der Quelle in eckigen Klammern, z. B. [Quelle 1].
4. Antworte auf Deutsch, klar strukturiert und klausurtauglich (Definitionen,
   Formeln, Rechenschritte, wenn im Kontext vorhanden).
5. Keine allgemeinen Vorreden, komme direkt zur Sache.
6. Bei Erklär-/Vorgehensfragen ("wie funktioniert …", "wie berechnet man …",
   "worauf muss ich achten"): erkläre das VORGEHEN Schritt für Schritt (Rezept),
   übernimm Formeln EXAKT aus dem Kontext, nenne typische Stolperfallen und, wenn
   im Kontext vorhanden, ein kurzes Beispiel. Ziel: der/die Studierende kann die
   Aufgabe danach selbst rechnen (nicht die konkrete Zahl vorrechnen, sondern das Wie)."""

ANSWER_PROMPT = """Kontext (nummerierte Quellen):
{context}

Frage des Studierenden:
{question}

Beantworte die Frage nur mit dem Kontext. Wenn die Information fehlt, gib
{no_answer} aus. Nenne die genutzten Quellen als [Quelle N]."""

# LLM-basierte Relevanzbewertung (Backup zusätzlich zum Reranker-Score)
GRADE_PROMPT = """Beurteile, ob der folgende Textabschnitt zur Beantwortung der
Frage RELEVANT ist.

Frage: {question}

Abschnitt:
\"\"\"{document}\"\"\"

Antworte NUR mit JSON: {{"relevant": true}} oder {{"relevant": false}}."""

# Faithfulness-/Grounding-Prüfung nach der Antwort
FAITHFULNESS_PROMPT = """Prüfe, ob die ANTWORT vollständig durch den KONTEXT
gedeckt ist (keine erfundenen Fakten, keine Aussagen ohne Beleg im Kontext).

KONTEXT:
\"\"\"{context}\"\"\"

ANTWORT:
\"\"\"{answer}\"\"\"

Antworte NUR mit JSON:
{{"grounded": true/false, "grund": "kurze Begründung"}}"""
