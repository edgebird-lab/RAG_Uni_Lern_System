# Graphen durchlaufen

## Breitensuche

Die Breitensuche (BFS) durchläuft einen Graphen ebenenweise ausgehend von einem Startknoten. Sie benutzt eine Warteschlange: Zuerst kommt der Startknoten hinein; in jedem Schritt wird der vorderste Knoten entnommen, und alle seine noch nicht besuchten Nachbarn werden als besucht markiert und hinten angehängt. In einem ungewichteten Graphen findet die BFS kürzeste Wege, gemessen in der Anzahl der Kanten. Mit Adjazenzlisten beträgt die Laufzeit O(V + E), wobei V die Zahl der Knoten und E die Zahl der Kanten ist.

## Tiefensuche

Die Tiefensuche (DFS) folgt einem Pfad so tief wie möglich und kehrt erst dann zurück (Backtracking). Sie lässt sich rekursiv oder mit einem expliziten Stapel umsetzen und läuft ebenfalls in O(V + E). Die DFS ist die Grundlage für das Erkennen von Zyklen, das topologische Sortieren gerichteter azyklischer Graphen und das Finden starker Zusammenhangskomponenten. Führt eine Kante zu einem Knoten, der gerade auf dem Rekursionsstapel liegt, enthält der gerichtete Graph einen Zyklus.

## Der Algorithmus von Dijkstra

Der Algorithmus von Dijkstra berechnet kürzeste Wege von einem Startknoten zu allen anderen Knoten in einem Graphen mit nichtnegativen Kantengewichten. Er hält vorläufige Distanzen in einer Prioritätswarteschlange, entnimmt wiederholt den Knoten mit der kleinsten Distanz, legt seine Distanz fest und aktualisiert die Distanzen seiner Nachbarn (Relaxierung). Mit einem binären Heap beträgt die Laufzeit O((V + E) log V). Bei negativen Kantengewichten versagt der Algorithmus; dann nutzt man den Bellman-Ford-Algorithmus mit der Laufzeit O(V · E).
