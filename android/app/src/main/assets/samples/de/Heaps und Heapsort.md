# Heaps und Heapsort

## Heap-Eigenschaft

Ein binärer Heap ist ein vollständiger Binärbaum, in dem jeder Knoten die Heap-Eigenschaft erfüllt. In einem Max-Heap ist der Schlüssel jedes Knotens größer oder gleich den Schlüsseln seiner Kinder, daher steht der größte Schlüssel immer an der Wurzel. Im Min-Heap ist es umgekehrt: Die Wurzel enthält den kleinsten Schlüssel. Weil der Baum vollständig ist, lässt er sich platzsparend in einem Feld speichern: Die Kinder des Knotens an Index i stehen an den Indizes 2i+1 und 2i+2, sein Elternknoten steht an Index (i-1)/2 (abgerundet).

## Operationen

Beim Einfügen wird das neue Element zuerst am Ende des Feldes angehängt, damit der Baum vollständig bleibt. Danach wandert es durch Vertauschen mit seinem Elternknoten nach oben, solange es die Heap-Eigenschaft verletzt (Sift-up). Das sind höchstens O(log n) Vertauschungen, weil ein vollständiger Binärbaum mit n Knoten eine Höhe von etwa log2(n) hat.

Beim Entfernen des Maximums ersetzt man die Wurzel durch das letzte Element des Feldes, verkleinert den Heap um eins und lässt das neue Wurzelelement nach unten sinken (Sift-down): Es wird immer mit dem größeren seiner beiden Kinder getauscht, bis die Heap-Eigenschaft wieder gilt. Auch das kostet O(log n).

## Heap bauen und Heapsort

Einen Heap kann man aus einem unsortierten Feld in O(n) Zeit bauen, indem man Sift-down auf allen inneren Knoten aufruft, vom letzten inneren Knoten bis zur Wurzel. Heapsort baut zuerst einen Max-Heap und tauscht dann wiederholt die Wurzel mit dem letzten Element des Heap-Bereichs, verkleinert den Heap und stellt die Heap-Eigenschaft wieder her. Die Laufzeit beträgt im besten, mittleren und schlechtesten Fall O(n log n). Heapsort sortiert in place, ist aber nicht stabil.

## Prioritätswarteschlangen

Eine Prioritätswarteschlange ist ein abstrakter Datentyp, der das Einfügen von Elementen mit einer Priorität und das Entnehmen des Elements mit der höchsten Priorität unterstützt. Ein binärer Heap realisiert beide Operationen in O(log n). Anwendungen sind der Algorithmus von Dijkstra, ereignisgesteuerte Simulationen und Scheduler in Betriebssystemen.
