package de.edgebird.lernsystem.core.scan

import kotlin.math.roundToInt

/** Punkt in Bildkoordinaten, normiert auf 0..1 (x nach rechts, y nach unten). */
data class Pt(val x: Float, val y: Float)

/**
 * Findet ein helles Blatt auf dunklerem Untergrund: Otsu-Schwelle, größte helle Fläche, Ecken als Extrempunkte.
 * Arbeitet auf einem kleinen Graustufenbild (z. B. 160 px breit); Reihenfolge der Ecken: oben links, oben rechts, unten rechts, unten links.
 */
object DocumentCorners {
    /** Ohne erkennbares Blatt (zu klein, fast das ganze Bild oder kein Kontrast) kommt `null` zurück. */
    fun detect(gray: IntArray, w: Int, h: Int): List<Pt>? {
        require(gray.size == w * h)
        val t = otsu(gray)
        val bright = BooleanArray(w * h) { gray[it] > t }
        val seen = BooleanArray(w * h)
        var best: IntArray? = null
        val stack = IntArray(w * h)
        for (start in bright.indices) {
            if (!bright[start] || seen[start]) continue
            var sp = 0
            stack[sp++] = start; seen[start] = true
            val members = ArrayList<Int>()
            while (sp > 0) {
                val p = stack[--sp]; members += p
                val x = p % w; val y = p / w
                if (x > 0 && bright[p - 1] && !seen[p - 1]) { seen[p - 1] = true; stack[sp++] = p - 1 }
                if (x < w - 1 && bright[p + 1] && !seen[p + 1]) { seen[p + 1] = true; stack[sp++] = p + 1 }
                if (y > 0 && bright[p - w] && !seen[p - w]) { seen[p - w] = true; stack[sp++] = p - w }
                if (y < h - 1 && bright[p + w] && !seen[p + w]) { seen[p + w] = true; stack[sp++] = p + w }
            }
            if (best == null || members.size > best.size) best = members.toIntArray()
        }
        val region = best ?: return null
        val share = region.size.toFloat() / (w * h)
        if (share < 0.15f || share > 0.9f) return null
        var tl = region[0]; var tr = region[0]; var br = region[0]; var bl = region[0]
        for (p in region) {
            val x = p % w; val y = p / w
            if (x + y < tl % w + tl / w) tl = p
            if (x - y > tr % w - tr / w) tr = p
            if (x + y > br % w + br / w) br = p
            if (y - x > bl / w - bl % w) bl = p
        }
        fun pt(p: Int) = Pt((p % w + 0.5f) / w, (p / w + 0.5f) / h)
        val out = listOf(pt(tl), pt(tr), pt(br), pt(bl))
        // Entartet (z. B. alle Punkte auf einer Linie): kein Viereck
        return if (area(out) < 0.05f) null else out
    }

    /** Fläche des Vierecks in normierten Koordinaten (Gauß). */
    fun area(q: List<Pt>): Float {
        var s = 0f
        for (i in q.indices) { val a = q[i]; val b = q[(i + 1) % q.size]; s += a.x * b.y - b.x * a.y }
        return kotlin.math.abs(s) / 2f
    }

    /** Sinnvolle Ausgabegröße (Pixel) für das entzerrte Blatt aus den Kantenlängen. */
    fun outputSize(q: List<Pt>, srcW: Int, srcH: Int): Pair<Int, Int> {
        fun d(a: Pt, b: Pt) = kotlin.math.hypot((a.x - b.x) * srcW, (a.y - b.y) * srcH)
        val w = maxOf(d(q[0], q[1]), d(q[3], q[2])).roundToInt().coerceAtLeast(1)
        val h = maxOf(d(q[0], q[3]), d(q[1], q[2])).roundToInt().coerceAtLeast(1)
        return w to h
    }

    /** Schwelle nach Otsu (maximale Varianz zwischen den Klassen). */
    fun otsu(gray: IntArray): Int {
        val hist = IntArray(256)
        for (g in gray) hist[g.coerceIn(0, 255)]++
        val total = gray.size.toDouble()
        var sum = 0.0; for (i in 0..255) sum += i * hist[i]
        var wB = 0.0; var sumB = 0.0; var best = 0.0; var thr = 127
        for (i in 0..255) {
            wB += hist[i]; if (wB == 0.0) continue
            val wF = total - wB; if (wF == 0.0) break
            sumB += i * hist[i]
            val mB = sumB / wB; val mF = (sum - sumB) / wF
            val v = wB * wF * (mB - mF) * (mB - mF)
            if (v > best) { best = v; thr = i }
        }
        return thr
    }
}
