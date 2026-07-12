"""
Textqualität / Kauderwelsch-Erkennung
=====================================

Leichtgewichtige, rein lokale Heuristik (keine Modelle, keine Netz-Zugriffe),
die entscheidet, ob ein Textstück *sinnvoller* Fließtext oder Zeichenmüll ist
(typisch: OCR über Handschrift/Scans -> "Infs slen zu ridht8en 2at Q1 EBEHSOHFTEH").

Das Gate FILTERT nur, es schreibt NICHTS um: ein Chunk wird entweder unverändert
behalten oder verworfen. Native Dokumente bleiben dadurch wortgetreu.

Öffentliche API:
    meaningfulness(text)          -> float 0..1   (höher = eher echter Text)
    is_gibberish(text, ...)       -> (bool, grund)

Idee: Anteil "echt-wort-artiger" Tokens (Vokal vorhanden, plausible Länge 2–20,
keine Ziffern im Wort, keine wilden Konsonantencluster), gedämpft durch den
Anteil Ziffern-im-Wort-Müll. Formel-/Tabellen-/Code-Fragmente und sehr kurze
Texte werden bewusst NICHT als Kauderwelsch gewertet (im Zweifel behalten).
"""
from __future__ import annotations

import re

# Vokale inkl. Umlaute und gängiger Akzente (für den Vokal-Test).
VOWELS = set("aeiouyäöüAEIOUYÄÖÜáàâéèêíìóòúùÁÀÂÉÈÊ")

# Ein Buchstabe (kein Digit, kein Unterstrich) – unicode-bewusst.
_ALPHA_RE = re.compile(r"[^\W\d_]", re.UNICODE)

# Rand-Interpunktion, die von Tokens abgeschnitten wird.
_STRIP = " \t\n\r\f\v.,;:!?()[]{}\"'«»„“”‚‘’…/\\|<>#*=+~`^%&@·•–—-"

# Zeichen, die ein Token als Formel-/Code-Fragment ausweisen (kein Wortversuch):
# f(x), 3x^2, P(A|B), \sum_{i=1}, a=b; innerer Punkt -> Abkürzung (z.B., i.d.R.).
_FORMULA_CHARS = set("=^_+*|\\{}<>[]()/~°$€%.")

# Häufige deutsche/englische Funktions-/Allerweltswörter. Nur als POSITIVES
# Signal genutzt (Wörterbuch-Treffer); kein Blocker – Fachbegriffe fehlen hier
# absichtlich, sie werden strukturell als "wortartig" erkannt.
_COMMON = frozenset("""
der die das dem den des ein eine einen einem einer eines und oder aber sondern
denn weil dass ob wenn als wie so nur auch noch schon nicht kein keine ist sind
war waren wird werden wurde wurden sein hat haben hatte habe kann können muss
müssen soll sollen darf dürfen mag mögen will wollen für gegen ohne mit nach bei
seit von zu zur zum aus über unter vor hinter neben zwischen durch um an auf in
im am ans aufs ins vom beim zum dieser diese dieses jener jene jenes man sich
ihr ihre ihren sein seine seinen unser euer mein dein wir uns euch sie es er ihm
ihn ihnen mir mich dir dich hier dort da dann also somit daher deshalb deswegen
zum beispiel etwa bzw usw sowie sowohl entweder weder jedoch dennoch trotzdem
mehr weniger sehr viel viele wenig wenige alle alles jeder jede jedes beide
mehrere einige manche solche welche was wer wo wann warum wieder immer oft
the of and to in is are was were be been has have had will would can could
should may might must not no yes for with from this that these those which
who whom what when where why how all any some more most less than then thus
""".split())

# Bekannte deutsche Konsonanten-Cluster: vor dem Run-Zählen "aufgelöst",
# damit z. B. "Angstschweiß" nicht fälschlich als Cluster-Müll gilt.
_DIGRAPHS = ("tsch", "sch", "chs", "ck", "ch", "ph", "th", "sh", "qu",
             "ng", "nk", "pf", "tz", "dt", "ss", "st", "sp")


def _tokens(text: str) -> list[str]:
    return [t.strip(_STRIP) for t in (text or "").split()]


def _letters(tok: str) -> list[str]:
    return [c for c in tok if _ALPHA_RE.match(c)]


def _max_cons_run(core: str) -> int:
    """Längste Konsonantenfolge, nachdem bekannte dt. Digraphe kollabiert sind."""
    s = core.lower()
    for dg in _DIGRAPHS:
        s = s.replace(dg, "a")  # Platzhalter zählt als Vokal -> unterbricht den Run
    run = best = 0
    for c in s:
        if c in VOWELS or c == "a":
            run = 0
        elif c.isalpha():
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def _classify(tok: str) -> tuple[str, bool]:
    """Klassifiziert ein Token -> ('skip'|'alnum_ok'|'good'|'bad', ist_bekannt)."""
    if not tok:
        return "skip", False
    if not _letters(tok):
        return "skip", False                       # reine Symbole
    if any(c in _FORMULA_CHARS for c in tok):
        return "skip", False                       # f(x), 3x^2, P(A|B), z.B.
    low = tok.lower()
    if any(c.isdigit() for c in tok):
        # nach Trennern splitten; ein "gemischter" Teil hat Buchstabe UND Ziffer
        parts = re.split(r"[-/·]", tok)
        mixed = [p for p in parts
                 if any(ch.isdigit() for ch in p) and any(_ALPHA_RE.match(ch) for ch in p)]
        if not mixed:
            return "alnum_ok", False               # "20-jährige", "S-3"
        if all(p.upper() == p and len(p) <= 5 for p in mixed):
            return "alnum_ok", False               # H2O, CO2, MP3, 3D, B2B
        return "bad", False                        # ridht8en, 2at, d3r (Müll)
    core = "".join(_letters(tok))
    is_known = low.strip(_STRIP) in _COMMON
    if len(tok) > 25:
        return "bad", is_known                     # verklebte Extraktion
    if len(core) < 2:
        return "skip", is_known                    # Einzelbuchstabe
    vc = sum(1 for c in core if c in VOWELS)
    vr = vc / len(core)
    if vc == 0:
        return "bad", is_known                     # Konsonantenbrei (qwrtz, fhgk)
    if vr < 0.16 or vr > 0.85:
        return "bad", is_known                     # unplausibler Vokalanteil
    if _max_cons_run(core) > 4:
        return "bad", is_known                     # wilder Cluster
    return "good", is_known


def _stats(text: str) -> dict:
    ng = nb = na = 0
    n_garble = n_known = 0
    for tok in _tokens(text):
        if not tok:
            continue
        if re.fullmatch(r"\d+([.,]\d+)*", tok):    # reine Zahl -> neutral
            continue
        cls, known = _classify(tok)
        if cls == "good":
            ng += 1
        elif cls == "bad":
            nb += 1
            if any(c.isdigit() for c in tok):
                n_garble += 1
        elif cls == "alnum_ok":
            na += 1
        if known:
            n_known += 1
    return {"good": ng, "bad": nb, "alnum": na, "garble": n_garble,
            "known": n_known, "judged": ng + nb, "letterish": ng + nb + na}


# --------------------------------------------------------------------------- #
# Echtwort-Anteil ueber ein Woerterbuch (pyspellchecker, de+en). Das ist das
# ZUVERLAESSIGE Signal gegen "aussprechbaren Unsinn" (EBEHSOHFTEH,
# formolioequalitael), den die reine Struktur-Heuristik nicht faengt. Faellt
# sauber auf None zurueck, wenn pyspellchecker fehlt -> dann greift die
# Struktur-Heuristik als Ersatz (schwaecher). pyspellchecker steht in
# requirements.txt und wird vom Installer mitinstalliert.
# --------------------------------------------------------------------------- #
_SPELL = None                       # (de, en) SpellChecker | False (nicht verfuegbar)
_WORD_RE = re.compile(r"[A-Za-zÄÖÜäöüß]{2,}")


def _spell():
    global _SPELL
    if _SPELL is None:
        try:
            from spellchecker import SpellChecker
            _SPELL = (SpellChecker(language="de"), SpellChecker(language="en"))
        except Exception:  # noqa: BLE001
            _SPELL = False
    return _SPELL or None


# Deutsche Komposita (Deckungsbeitragsrechnung, Kostenartenrechnung,
# Halbwertszeit) stehen NICHT im Frequenzwoerterbuch. Bevor ein Wort als
# "unbekannt" zaehlt, versuchen wir daher, es an bekannten Fugen in >=2 bekannte
# Teilwoerter zu zerlegen. So bleibt der Echtwort-Anteil eines Fachabsatzes hoch,
# ohne dass 'aussprechbarer Unsinn' (der sich NICHT in echte Woerter zerlegt)
# durchrutscht.
_COMPOUND_MIN_PART = 4      # Mindestlaenge eines Teilworts (keine Mini-Fragmente)


def _in_lexicon(word: str, de, en) -> bool:
    w = word.lower()
    return (w in de) or (w in en)


def _splits_into_known(word: str, de, en, max_parts: int = 3) -> bool:
    """True, wenn ``word`` sich vollstaendig in >=2 bekannte Teilwoerter zerlegen
    laesst (optionales Fugen-s zwischen den Teilen). Rekursiv, aber durch
    ``max_parts`` und die Mindestteillaenge streng begrenzt (kein Backtracking-
    Blowup, wird ohnehin nur fuer bereits unbekannte Woerter aufgerufen)."""
    w = word.lower()
    n = len(w)
    if n < 2 * _COMPOUND_MIN_PART or max_parts <= 1:
        return False
    for i in range(_COMPOUND_MIN_PART, n - _COMPOUND_MIN_PART + 1):
        if not _in_lexicon(w[:i], de, en):
            continue
        rest = w[i:]
        # Rest direkt bekannt ODER selbst wieder ein Kompositum? Fugen-s optional.
        for cand in (rest, rest[1:] if rest[:1] == "s" else ""):
            if len(cand) < _COMPOUND_MIN_PART:
                continue
            if _in_lexicon(cand, de, en) or _splits_into_known(cand, de, en, max_parts - 1):
                return True
    return False


def _word_is_real(word: str, de, en) -> bool:
    return _in_lexicon(word, de, en) or _splits_into_known(word, de, en)


def real_word_ratio(text: str) -> "float | None":
    """Anteil der Woerter (>=2 Buchstaben), die im deutschen ODER englischen
    Woerterbuch stehen (dt. Komposita werden vor dem Urteil an bekannten Fugen
    zerlegt). None, wenn kein Woerterbuch verfuegbar oder <3 Woerter (zu wenig
    fuer ein Urteil)."""
    sp = _spell()
    if sp is None:
        return None
    de, en = sp
    toks = _WORD_RE.findall(text or "")
    if len(toks) < 3:
        return None
    known = sum(1 for t in toks if _word_is_real(t, de, en))
    return known / len(toks)


def _structural_score(st: dict) -> float:
    """Strukturelle Wortartigkeit 0..1 (Anteil wortartiger Tokens, gedaempft um
    Ziffern-im-Wort-Muell). Ohne beurteilbare Tokens -> 1.0 (im Zweifel
    behalten; die Guards in is_gibberish fangen 'nicht beurteilbar' ab)."""
    if st["judged"] == 0:
        return 1.0
    wg = st["good"] / st["judged"]
    gd = st["garble"] / max(1, st["letterish"])
    return max(0.0, min(1.0, wg * (1.0 - gd)))


_STRUCT_RESCUE_MIN = 0.9   # nur eine PRAKTISCH PERFEKTE Struktur darf niedriges rwr retten


def _combine(structural: float, rwr: "float | None") -> float:
    """Meaningfulness-Score. Primaersignal ist der KOMPOSITUM-bewusste Echtwort-
    Anteil ``rwr`` (``_splits_into_known`` zerlegt 'Deckungsbeitragsrechnung' etc.):
    echter Fachtext liegt hoch, OCR-Kauderwelsch niedrig. Ohne Woerterbuch/zu wenige
    Woerter (``rwr`` is None) zaehlt ersatzweise die Struktur.

    Die Struktur darf ``rwr`` NICHT generell ueberstimmen (kein max()): sonst rutscht
    'aussprechbares' Kauderwelsch wie 'EBEHSOHFTEH FTEH' (struc~0.25-0.5, rwr~0.3)
    durch. AUSNAHME: ist der Text strukturell PRAKTISCH PERFEKT (>=_STRUCT_RESCUE_MIN,
    keine Zeichenmuell-/Ziffern-Tokens), stammt ein niedriges rwr fast immer von
    woerterbuch-UNbekannten, aber ECHTEN Woertern (Eigennamen, Wirkstoffe, Bibliografie,
    Fachbegriffe) - solche Chunks wollen wir BEHALTEN. Realistisches Kauderwelsch hat
    fast immer struktur < 0.9 (gebrochene Tokens, Ziffernmuell, Konsonantenbrei)."""
    if rwr is None:
        return structural
    if structural >= _STRUCT_RESCUE_MIN:
        return max(rwr, structural)
    return rwr


def meaningfulness(text: str) -> float:
    """0..1: Wie sinnvoll der Text ist. Primaersignal ist der kompositum-bewusste
    Echtwort-Anteil laut Woerterbuch: er faengt 'aussprechbaren Unsinn' wie
    'EBEHSOHFTEH' UND rettet dichte Fachabsaetze mit dt. Komposita wie
    'Deckungsbeitragsrechnung' (die werden vor dem Urteil an Fugen zerlegt). Ohne
    Woerterbuch/zu wenige Woerter zaehlt ersatzweise die strukturelle
    Wortartigkeit; ohne beurteilbare Tokens -> 1.0 (im Zweifel behalten)."""
    st = _stats(text)
    return _combine(_structural_score(st), real_word_ratio(text))


def is_gibberish(text: str, *, min_chars: int = 25, min_alpha_ratio: float = 0.30,
                 min_tokens: int = 4, max_meaningfulness: float = 0.55
                 ) -> tuple[bool, str]:
    """Entscheidet, ob ``text`` Kauderwelsch ist. Gibt (True, grund) zurück, wenn
    ja. Im Zweifel (zu kurz / wenig Fließtext / zu wenige Tokens) -> (False, …),
    d. h. der Text wird BEHALTEN. Schwellen kommen aus der Config (s. pipeline)."""
    t = text or ""
    non_space = [c for c in t if not c.isspace()]
    if len(non_space) < min_chars:
        return False, "zu wenig Text zum Beurteilen"
    alpha = sum(1 for c in non_space if _ALPHA_RE.match(c))
    if alpha / len(non_space) < min_alpha_ratio:
        return False, "wenig Fließtext (Formel/Tabelle/Code) – nicht als Kauderwelsch gewertet"
    st = _stats(text)
    if st["judged"] < min_tokens:
        return False, "zu kurz zum sicheren Beurteilen"
    # Beide Signale je EINMAL berechnen (keine Doppelberechnung von _stats /
    # real_word_ratio wie zuvor ueber den meaningfulness()-Umweg).
    structural = _structural_score(st)
    rwr = real_word_ratio(text)
    m = _combine(structural, rwr)
    if m < max_meaningfulness:
        if rwr is not None:
            return True, (f"Kauderwelsch – nur {int(rwr * 100)}% echte Wörter laut "
                          f"Wörterbuch (Struktur {structural:.2f})")
        wg = st["good"] / st["judged"]
        gd = st["garble"] / max(1, st["letterish"])
        return True, (f"Kauderwelsch (Textqualität {m:.2f}: {int(wg * 100)}% wortartig, "
                      f"{int(gd * 100)}% Zeichenmüll-Tokens)")
    return False, ""
