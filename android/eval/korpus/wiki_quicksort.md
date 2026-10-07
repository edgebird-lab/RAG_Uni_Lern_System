# Quicksort

> Quelle: Wikipedia (de), „Quicksort“, Revision 259794988, https://de.wikipedia.org/wiki/Quicksort, Lizenz CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/deed.de). Autorenliste in der Versionsgeschichte des Artikels. Text unverändert bis auf Überschriften-Format.

Quicksort (englisch quick  ‚schnell‘ und to sort ‚sortieren‘) ist ein schneller, rekursiver, nicht-stabiler Sortieralgorithmus, der nach dem Prinzip Teile und herrsche arbeitet. Er wurde ca. 1960 von C. Antony R. Hoare in seiner Grundform entwickelt und seitdem von vielen Forschern verbessert. Der Algorithmus hat den Vorteil, dass er über eine sehr kurze innere Schleife verfügt (was die Ausführungsgeschwindigkeit stark erhöht) und dass er, abgesehen von dem für die Rekursion zusätzlichen benötigten Platz auf dem Aufruf-Stack, ohne zusätzlichen Speicherplatz auskommt.
Im Durchschnitt führt der Quicksort-Algorithmus 
  
    
      
        
          
            O
          
        
        (
        n
        ⋅
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(n\cdot \log(n))}
  
 Vergleiche durch. Im schlechtesten Fall werden 
  
    
      
        
          
            O
          
        
        (
        
          n
          
            2
          
        
        )
      
    
    {\displaystyle {\mathcal {O}}(n^{2})}
  
 Vergleiche durchgeführt, was aber in der Praxis sehr selten vorkommt.


## Prinzip
Zunächst wird die zu sortierende Liste in zwei Teillisten („linke“ und „rechte“ Teilliste) getrennt. Dazu wählt Quicksort ein sogenanntes Pivotelement aus der Liste aus. Alle Elemente, die kleiner als das Pivotelement sind, kommen in die linke Teilliste, und alle, die größer sind, in die rechte Teilliste. Die Elemente, die gleich dem Pivotelement sind, können sich beliebig auf die Teillisten verteilen. Nach der Aufteilung sind die Elemente der linken Liste kleiner oder gleich den Elementen der rechten Liste.
Anschließend muss man also noch jede Teilliste in sich sortieren, um die Sortierung zu vollenden. Dazu wird der Quicksort-Algorithmus jeweils auf der linken und auf der rechten Teilliste ausgeführt. Jede Teilliste wird dann wieder in zwei Teillisten aufgeteilt und auf diese jeweils wieder der Quicksort-Algorithmus angewandt, und so weiter. Diese Selbstaufrufe werden als Rekursion bezeichnet. Wenn eine Teilliste der Länge eins oder null auftritt, so ist diese bereits sortiert und es erfolgt der Abbruch der Rekursion.
Die Positionen der Elemente, die gleich dem Pivotelement sind, hängen vom verwendeten Teilungsalgorithmus ab. Sie können sich beliebig auf die Teillisten verteilen. Da sich die Reihenfolge von gleichwertigen Elementen zueinander ändern kann, ist Quicksort im Allgemeinen nicht stabil.
Das Verfahren muss sicherstellen, dass jede der Teillisten mindestens um eins kürzer ist als die Gesamtliste. Dann endet die Rekursion garantiert nach endlich vielen Schritten. Das kann z. B. dadurch erreicht werden, dass das ursprünglich als Pivot gewählte Element auf einen Platz zwischen den Teillisten gesetzt wird und somit zu keiner Teilliste gehört.


## Pseudocode
Die Implementierung der Teilung erfolgt als In-place-Algorithmus: Die Elemente werden nicht in zusätzlichen Speicher kopiert, sondern nur innerhalb der Liste vertauscht. Dafür wird ein Verfahren verwendet, das als Teilen oder auch Partitionieren bezeichnet wird. Danach sind die beiden Teillisten gleich in der richtigen Position. Sobald die Teillisten in sich sortiert wurden, ist die Sortierung der Gesamtliste beendet.
Der folgende Pseudocode illustriert die Arbeitsweise des Algorithmus, wobei daten die zu sortierende Liste mit n Elementen ist. Bei jedem Aufruf von quicksort() gibt links den Index des ersten Elements in der Teilliste an und rechts den des letzten. Beim ersten Aufruf (oberste Rekursionsebene) ist links = 0 und rechts = n-1. Die übergebene Liste wird dabei rekursiv immer weiter geteilt, bis sie nur noch einen Wert enthält.

 funktion quicksort(links, rechts)
     falls links < rechts dann
         teiler:= teile(links, rechts)
         quicksort(links, teiler - 1)
         quicksort(teiler + 1, rechts)
     ende
 ende

Die folgende Implementierung der Funktion teile teilt das Feld so, dass sich das Pivotelement an seiner endgültigen Position befindet und alle kleineren Elemente davor stehen, während alle größeren danach kommen:

 funktion teile(links, rechts)
     i:= links
     // Starte mit j links vom Pivotelement
     j:= rechts - 1
     pivot:= daten[rechts]
     wiederhole solange i < j // solange i an j nicht vorbeigelaufen ist
         // Suche von links ein Element, welches größer als das Pivotelement ist
         wiederhole solange i < j und daten[i] <= pivot
             i:= i + 1
         ende
         // Suche von rechts ein Element, welches kleiner oder gleich dem Pivotelement ist
         wiederhole solange j > i und daten[j] > pivot
             j:= j - 1
         ende
         falls daten[i] > daten[j] dann
             tausche daten[i] mit daten[j]
         ende     ende
     // Tausche Pivotelement (daten[rechts]) mit neuer endgültiger Position (daten[i])
     // und gib die neue Position des Pivotelements zurück, beende Durchlauf
     falls daten[i] > pivot dann
         tausche daten[i] mit daten[rechts]
     sonst
         i:= rechts
     ende
     antworte i
 ende

Nach der Wahl des Pivotelementes wird zunächst ein Element vom Anfang der Liste beginnend gesucht (Index i), welches größer als das Pivotelement ist. Entsprechend wird vom Ende der Liste beginnend ein Element kleiner als das Pivotelement gesucht (Index j). Die beiden Elemente werden dann vertauscht und landen damit in der jeweils richtigen Teilliste. Dann werden die beiden Suchvorgänge von den erreichten Positionen fortgesetzt, bis sich die untere und obere Suche treffen; dort ist die Grenze zwischen den beiden Teillisten.


## Beispiel
teile(links, rechts)
Die Buchstabenfolge „einbeispiel“ soll alphabetisch sortiert werden.
Ausgangssituation nach Initialisierung von i und j, das Element rechts (l) ist das Pivotelement:

  e i n b e i s p i e l
  ^                 ^
  i                 j

Nach der ersten Suche in den inneren Schleifen hat i auf einem Element  > l  und j auf einem Element  <= l gehalten:

  e i n b e i s p i e l
      ^             ^
      i             j

Nach dem Tauschen der Elemente bei i und j:

  e i e b e i s p i n l
      ^             ^
      i             j

Nach der nächsten Suche und tauschen:

  e i e b e i i p s n l
              ^   ^
              i   j

Nach einer weiteren Suche sind die Indizes aneinander vorbeigelaufen:

  e i e b e i i p s n l
              ^ ^
              j i

Nach dem Tauschen von i und Pivot bezeichnet i die Trennstelle der Teillisten. Bei i steht das Pivot-Element, links davon sind nur Elemente ≤ Pivot und rechts nur solche > Pivot:

  e i e b e i i l s n p
                ^
                i


### Vollständiges Beispiel für alphabetische Sortierung
In diesem Beispiel soll der Quicksortalgorithmus die Buchstabenfolge „Quicksort“ sortieren. Zunächst wird das rechte Element P-> als Pivotelement definiert. Dann laufen die Zähler g für „größer“ von links nach rechts und k für „kleiner“ von rechts nach links los,

 Quicksort
^       ^^
g       kP

bis g auf ein Element trifft, welches größer als das Pivotelement ist und bis k auf ein Element trifft, welches kleiner oder gleich dem Pivotelement ist.

 Quicksort
  ^     ^^
  g     kP

Diese beiden gefundenen Elemente r und u werden dann im folgenden Schritt getauscht.

 Qricksout
  ^     ^^
  g     kP

Im folgenden Schritt laufen die Indizes k und g in der gleichen Richtung wie gehabt weiter und suchen Elemente, die bei k kleiner als oder gleich dem Pivotelement und bei g größer als das Pivotelement sind.

 Qricksout
       ^^^
       kgP

Jetzt sind k und g aneinander vorbeigelaufen. Dieses Ereignis ist eine Abbruchbedingung. Jetzt wird das Pivotelement mit dem durch g indizierten Element getauscht.

 Qricksotu
       ^^^
       kPg

Jetzt treffen folgende zwei Aussagen zu: „Links des Pivotelements sind alle Elemente kleiner oder gleich dem Pivotelement. Rechts des Pivotelements sind alle Elemente größer oder gleich dem Pivotelement.“

   links|:|rechts
 Qrickso|t|u
       ^|^|^
       k|P|g

Das Pivotelement „teilt“ nun die Datenmenge an der Stelle des Pivotelements in zwei Hälften Links und Rechts.
Nun muss der Algorithmus den linken und den rechten Teil auf die gleiche Weise wie im Vorangehenden schon geschehen weiterbehandeln. Hierdurch ergibt sich nun die Rekursion. Der rechte Teil (Der Buchstabe u) ist nur ein einzelnes Element und ist somit per Definition sortiert. Also wird nun der linke Teil behandelt. Das rechte Element ist wieder das Pivotelement, und die Zähler werden passend gesetzt.

 Qrickso|t|u
^     ^^
g     kP

Das Q ist größer als o und das k ist kleiner als das o.

 Qrickso|t|u
 ^   ^ ^
 g   k P

Also werden das Q und das k vertauscht.

 kricQso|t|u
 ^   ^ ^
 g   k P

Indizes g und k laufen weiter...

 kricQso|t|u
  ^ ^  ^
  g k  P

Das r und das c werden getauscht.

 kcirQso|t|u
  ^ ^  ^
  g k  P

Im folgenden Schritt sind die Indizes wieder aneinander vorbeigelaufen...

 kcirQso|t|u
   ^^  ^
   kg P

… und das Pivotelement (Buchstabe o) wird mit dem größeren Element (Buchstabe r) getauscht.

 kcioQsr|t|u
   ^^  ^
   kP  g

Nun ergibt sich erneut ein linker und ein rechter Teil.

links:rechts
 kci|o|Qsr  |t|u
   ^|^|  ^  | |
   k|P|  g  | |

Zunächst wird der linke Teil behandelt.

 kci|o| Qsr|t|u
^ ^^| |^ ^^| |
g kP| |g kP| |

 cki|o| Qsr|t|u
 ^^^| |^ ^^| |
 gkP| |g kP| |

Buchstabe c und k werden getauscht.

 cki|o| Qsr|t|u
 ^^^| |^ ^^| |
 kgP| |g kP| |

Indizes sind aneinander vorbeigelaufen, und das Element des Index g wird mit dem des Index P vertauscht.

 cik|o| Qsr|t|u
 ^^^| |^ ^^| |
 kPg| |g kP| |

Der jetzt entstandene neue linke und rechte Teil besteht nun nur noch aus einem einzelnen Element und gilt als sortiert.

 cik|o| Qsr|t|u
    | | ^^^| |
    | | kgP| |

Im ehemals rechten Teil (Buchstaben Qsr) laufen die Indizes direkt aneinander vorbei, und das Element bei g wird mit dem Pivotelement getauscht.

 cik|o| Qrs|t|u
    | | ^^^| |
    | | kPg| |

Damit sind alle Zeichen sortiert.

 cik|o| Qrs|t|u

Ergebnis:

 cikoQrstu


## Kenngrößen


### Laufzeit
Die Laufzeit des Algorithmus hängt im Wesentlichen von der Wahl des Pivotelementes ab.
Im Worst Case (schlechtesten Fall) wird das Pivotelement stets so gewählt, dass es das größte oder das kleinste Element der Liste ist. Dies ist etwa der Fall, wenn als Pivotelement stets das Element am Ende der Liste gewählt wird und die zu sortierende Liste bereits sortiert vorliegt. Die zu untersuchende Liste wird dann in jedem Rekursionsschritt nur um eins kleiner und die Zeitkomplexität wird beschrieben durch 
  
    
      
        
          
            O
          
        
        (
        
          n
          
            2
          
        
        )
      
    
    {\displaystyle {\mathcal {O}}(n^{2})}
  
. Die Anzahl der Vergleiche ist in diesem Fall

  
    
      
        
          
            
              n
              ⋅
              
                (
                
                  n
                  +
                  1
                
                )
              
            
            2
          
        
        −
        1
        =
        
          
            
              n
              
                2
              
            
            2
          
        
        +
        
          
            n
            2
          
        
        −
        1
      
    
    {\displaystyle {\frac {n\cdot \left(n+1\right)}{2}}-1={\frac {n^{2}}{2}}+{\frac {n}{2}}-1}
  
.
Im Best Case (besten Fall) wird das Pivotelement stets so gewählt, dass die beiden entstehenden Teillisten etwa gleich groß sind. In diesem Fall gilt für die asymptotische Laufzeit des Algorithmus 
  
    
      
        
          
            O
          
        
        (
        n
        ⋅
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(n\cdot \log(n))}
  
. Diese Zeitkomplexität gilt ebenso für den Average Case (durchschnittlichen Fall). Die Länge der jeweils längeren Teilliste beim rekursiven Aufruf ist nämlich im Schnitt

  
    
      
        
          
            2
            n
          
        
        
          ∑
          
            i
            =
            
              
                n
                2
              
            
          
          
            n
            −
            1
          
        
        i
        =
        
          
            3
            4
          
        
        n
        −
        
          
            2
            4
          
        
      
    
    {\displaystyle {\frac {2}{n}}\sum \limits _{i={\frac {n}{2}}}^{n-1}i={\frac {3}{4}}n-{\frac {2}{4}}}
  

und die Tiefe der Rekursion damit in 
  
    
      
        
          
            O
          
        
        (
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(\log(n))}
  
. Im Average Case ist die Anzahl der Vergleiche etwa

  
    
      
        2
        ⋅
        log
        ⁡
        (
        2
        )
        ⋅
        (
        n
        +
        1
        )
        ⋅
        
          log
          
            2
          
        
        ⁡
        (
        n
        )
        ≈
        1
        
          ,
        
        39
        ⋅
        (
        n
        +
        1
        )
        ⋅
        
          log
          
            2
          
        
        ⁡
        (
        n
        )
      
    
    {\displaystyle 2\cdot \log(2)\cdot (n+1)\cdot \log _{2}(n)\approx 1{,}39\cdot (n+1)\cdot \log _{2}(n)}
  
.
Für die Wahl des Pivotelementes sind in der Literatur verschiedene Ansätze beschrieben worden. Die Wahrscheinlichkeit des Eintreffens des Worst Case ist bei diesen unterschiedlich groß.
Ein möglicher Ansatz ist es, immer das erste, das letzte oder das mittlere Element der Liste zu wählen. Dieser naive Ansatz ist aber relativ ineffizient. Eine andere Möglichkeit ist es, den Median dieser drei Elemente zu bestimmen und als Pivotelement zu verwenden.
Ein anderer Ansatz ist, als Pivotelement ein zufälliges Element auszuwählen. Bei diesem randomisierten Quicksort ist die Wahrscheinlichkeit, dass das Pivotelement in jedem Teilungsschritt so gewählt wird, dass sich die Worst-Case-Laufzeit ergibt, extrem gering. Man kann davon ausgehen, dass er praktisch nie auftritt.
Es gibt Algorithmen, beispielsweise Heapsort, deren Laufzeiten auch im Worst Case durch 
  
    
      
        
          
            O
          
        
        (
        n
        ⋅
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(n\cdot \log(n))}
  
 beschränkt sind.
In der Praxis wird aber trotzdem Quicksort eingesetzt, da angenommen wird, dass bei Quicksort der Worst Case nur sehr selten auftritt und im mittleren Fall schneller als Heapsort ist, da die innerste Schleife von Quicksort nur einige wenige, sehr einfache Operationen enthält. Dies ist jedoch noch Forschungsgegenstand und einige Analysen und Simulationen sehen Heapsortvarianten vorne, sowohl aus informationstheoretischen Überlegungen wie Implementierungsbetrachtungen.
Heute ist Quicksort für ein breites Spektrum von praktischen Anwendungen der bevorzugte Sortieralgorithmus, weil er schnell ist und, sofern Rekursion zur Verfügung steht, einfach zu implementieren ist. In vielen Standardbibliotheken ist er bereits vorhanden. Mittlerweile steht jedoch mit Introsort auch eine Alternative zur Verfügung, die bei vergleichbarer mittlerer Laufzeit auch für den Worst Case eine obere Schranke von 
  
    
      
        
          
            O
          
        
        (
        n
        ⋅
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(n\cdot \log(n))}
  
 garantiert.
Verwendet man für die Wahl des Pivotelements den Median-of-medians-Algorithmus, welcher den Median eines Arrays in 
  
    
      
        
          
            O
          
        
        (
        n
        )
      
    
    {\displaystyle {\mathcal {O}}(n)}
  
 bestimmt, so kann insgesamt eine Laufzeit von 
  
    
      
        
          
            O
          
        
        (
        n
        ⋅
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(n\cdot \log(n))}
  
 für den schlechtesten Fall von Quicksort garantiert werden.


### Speicherplatz
Quicksort ist kein in-Place-Verfahren. Es vertauscht zwar die Elemente der zu sortierenden Liste nur innerhalb der Liste und kopiert sie nicht in zusätzlichen Speicherplatz, benötigt dafür jedoch für jede Rekursionsebene zusätzlichen Platz auf dem Stack.
Wie bei der Laufzeit hängt auch der Speicherverbrauch von der Wahl des Pivotelements und der Art der vorliegenden Daten ab. Im günstigsten und durchschnittlichen Fall, bei einer Rekursionstiefe in 
  
    
      
        
          
            O
          
        
        (
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(\log(n))}
  
, wird auch nur eine Stapelgröße von 
  
    
      
        
          
            O
          
        
        (
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(\log(n))}
  
 benötigt.
Im ungünstigsten Fall ist die Anzahl der Rekursionen nur durch die Listenlänge 
  
    
      
        n
      
    
    {\displaystyle n}
  
 beschränkt, was einen Stapel der Größe 
  
    
      
        
          
            O
          
        
        (
        n
        )
      
    
    {\displaystyle {\mathcal {O}}(n)}
  
 erfordert. Dies kann bei langen Listen zu einem Stapelüberlauf führen. Es gibt vielfältige Modifikationen des Algorithmus, um dieses Problem zu lösen oder zumindest die Wahrscheinlichkeit seines Auftretens zu vermindern:

Endrekursionsbeseitigung (siehe nachfolgender Pseudocode)
eine ausgewogenere Wahl des Pivotelements (z. B. Median von Drei)
Wahl eines zufälligen Pivotelements, wodurch systematische Probleme vermieden werden, die sich sonst durch bestimmte Vorsortierungen der Elemente im Zusammenspiel mit der Methode der Pivotwahl ergeben können
Vermeidung von Teillisten mit weniger als zwei Elementen (ergibt, wenn auch das Pivotelement aus den Teillisten genommen wird, die maximale Rekursionstiefe 
  
    
      
        n
        
          /
        
        3
      
    
    {\displaystyle n/3}
  
)
Der folgende Pseudocode ersetzt die Endrekursion (Sortierung der zweiten Teilliste) durch eine Iteration derart, dass die kürzere Teilliste rekursiv sortiert wird, die längere wird (iterativ) so lange erneut geteilt (und die jeweils kürzere Teilliste rekursiv sortiert), bis der verbleibende Rest leer ist. Die Rekursionstiefe ist dann nicht größer als 
  
    
      
        log
        ⁡
        (
        n
        )
      
    
    {\displaystyle \log(n)}
  
:

 funktion quicksort(links, rechts)
     solange rechts > links wiederhole
         teiler:= teile(links, rechts)
         falls rechts - teiler > teiler - links
            quicksort(links, teiler - 1) // kleinere Teilliste rekursiv ..
            links:= teiler + 1 // .. und größere iterativ sortieren
         sonst
            quicksort(teiler + 1, rechts)
            rechts:= teiler - 1
         ende
     ende
 ende

Eine weitere Möglichkeit, den in 
  
    
      
        n
      
    
    {\displaystyle n}
  
 linearen zusätzlichen Speicherplatz zu vermeiden, besteht darin, dass man zuerst die kleinere der beiden Teilfolgen rekursiv sortiert (die andere wird danach sortiert, aber ebenfalls rekursiv). Somit bleibt die Anzahl der noch nicht sortierten Teilfolgen durch 
  
    
      
        
          
            O
          
        
        (
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(\log(n))}
  
 beschränkt. Für jede noch nicht sortierte Teilfolge werden zwei Indexgrenzen gespeichert, die jeweils 
  
    
      
        
          
            O
          
        
        (
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(\log(n))}
  
 zusätzlichen Speicherplatz benötigen. Insgesamt benötigt Quicksort mit dieser Variante 
  
    
      
        
          
            O
          
        
        (
        
          log
          
            2
          
        
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(\log ^{2}(n))}
  
 zusätzlichen Speicherplatz.


## Varianten


### QuickSort für verkettete Listen
Bei nachfolgend dargestellter QuickSort-Variante für verkettete Listen wird als Pivotelement das jeweils erste der zu teilenden Folge gewählt. Ein Zeiger Zeiger2 wird soweit vorgeschoben, bis er auf ein Element trifft, das kleiner als das Pivot ist. Die Elemente, über die Zeiger2 hinweggegangen ist, sind demzufolge größer oder gleich dem Pivot. Ein Tausch des ersten dieser größeren Elemente mit dem bei Zeiger2 sorgt also dafür, dass die betreffenden Elemente im richtigen Teilabschnitt landen. Zeiger1 markiert das aktuelle Ende des Teilabschnitts der Elemente, die kleiner als das Pivot sind. Wenn Zeiger2 am rechten Rand der zu teilenden Folge angelangt ist, wird abschließend das Pivotelement an die richtige Position zwischen den Teilfolgen getauscht.

// Links, Rechts sind hier Zeiger
QuickSort(Links, Rechts):
  falls Links<>Rechts dann
    // Initialisierung der (lokalen) Zeiger
    // Zeiger0 wird nur als Vorgänger von Zeiger1 benötigt
    Zeiger0 := Links
    Zeiger1 := Links
    Zeiger2 := Links

    Pivot:= Links.Zahl

    wiederhole
      Zeiger2 := Zeiger2.Nachfolger;

      falls Zeiger2.Zahl<Pivot dann
        Zeiger0 := Zeiger1;
        Zeiger1 := Zeiger1.Nachfolger;
        tausche(Zeiger1, Zeiger2)
    solange bis Zeiger2 = Rechts;

    tausche(Links, Zeiger1);

    falls Zeiger1<>Rechts dann
      Zeiger1 := Zeiger1.Nachfolger;

    QuickSort(Links, Zeiger0);
    QuickSort(Zeiger1, Rechts);
ende

Der Nachteil dieses Verfahrens liegt darin, dass eine weitgehend sortierte Folge oder viele gleichartige Schlüsselwerte zu einem Worst-Case-ähnlichen Verhalten führen. Daher wählt man für verkettete Listen gern Sortieralgorithmen wie etwa Mergesort, die auch im Worst Case eine Zeitkomplexität von 
  
    
      
        
          
            O
          
        
        (
        n
        log
        ⁡
        (
        n
        )
        )
      
    
    {\displaystyle {\mathcal {O}}(n\log(n))}
  
 besitzen. Andere dynamische Datenstrukturen wie balancierte Bäume (z. B. B-Bäume, AVL-Bäume) verteilen die Kosten des Sortierens auf die Einfügeoperationen, so dass nachträgliches Sortieren nicht notwendig ist.


### Iteratives Quicksort
Quicksort kann auch nicht-rekursiv mit Hilfe eines kleinen Stack oder Array implementiert werden.
Hier eine einfache Variante mit zufälliger Auswahl des Pivotelements:

funktion quicksort_iterativ(links, rechts)
   zufall:= random() // zufälliger Startwert
   wiederhole // äußere Schleife
      solange links < rechts wiederhole
         pivot:= daten[random(links, rechts)] // Auswahl eines zufälligen Elements, das zwischen links und rechts liegt
         push(rechts) // rechten Teil später sortieren
         mitte:= links
         wiederhole // innere Schleife, teile Feld
            solange daten[mitte] < pivot wiederhole // suche falsch einsortiertes Element von links
               mitte:= mitte + 1
            ende
            solange daten[rechts] > pivot wiederhole // suche falsch einsortiertes Element von rechts
               rechts:= rechts - 1
            ende
            falls mitte >= rechts dann Abbruch innere Schleife
            tausche daten[mitte] mit daten[rechts]
         ende // Feld geteilt, linken Teil weitersortieren
      ende
      falls stapel leer dann Abbruch äußere Schleife // noch ein rechter Teil übrig?
      links:= rechts + 1
      pop(rechts) // jetzt rechten Teil sortieren
   ende
ende

Die Anweisung push legt dabei ein Element auf den Stack, wo es mit pop wieder geholt wird.
Die zufällige Wahl des Pivotelements sorgt dabei mit hoher Wahrscheinlichkeit für einen Average-Case.
Die Größe des nötigen Stapelspeichers ist dabei mit ausreichender Sicherheit kleiner als 2·log2(n). Falls ein begrenzter Stapel trotzdem überläuft, so kann zum Sortieren des noch verbleibenden Teils einfach von vorne begonnen werden.
Die Effizienz von Quicksort liegt darin, dass es Elemente aus großer Distanz miteinander vertauscht. Je kürzer die zu sortierende Liste wird, desto ineffizienter arbeitet Quicksort, da es sich einer Komplexität von 
  
    
      
        
          
            O
          
        
        (
        
          n
          
            2
          
        
        )
      
    
    {\displaystyle {\mathcal {O}}(n^{2})}
  
 nähert. Die von Quicksort in Teillisten zerlegte Liste hat jedoch die Eigenschaft, dass der Abstand zwischen einem Element und seiner sortierten Position nach oben beschränkt ist. Eine solche Liste sortiert Insertionsort in linearer Zeit, so dass häufig in der Implementierung unterhalb einer definierten Teillistenlänge der Quicksort abgebrochen wird, um mit Insertionsort weiter zu sortieren.


### Parallel Quicksort

Wenn mehrere Prozessoren/-kerne zur Verfügung stehen, ist es auch möglich Quicksort zu parallelisieren. Damit sind unter Umständen bessere Laufzeiten erreichbar.


## Literatur
Robert Sedgewick: Algorithmen. Pearson Studium, 2002, ISBN 3-8273-7032-9.
Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein: Introduction to Algorithms. 2. Auflage. MIT Press, Cambridge MA 2001, ISBN 0-262-03293-7 (englisch, Standardwerk zu Algorithmen). 
Thomas H. Cormen, Charles E. Leiserson, Ronald L. Rivest, Clifford Stein: Algorithmen. Eine Einführung. 2., korr. Auflage. Oldenbourg, München / Wien 2007, ISBN 978-3-486-58262-8 (englisch: Introduction to algorithms. Übersetzt von Karen Lippert, Micaela Krieger-Hauwede). 


## Weblinks
Kompakte Erklärung des Quicksort-Algorithmus
Vollständiger Quicksort-Artikel linux-related.de
JavaScript-Demonstration vieler Sortieralgorithmen, auch des Quicksort-Algorithmus (englisch)
Vorlesung zum Thema Quicksort. MIT (englisch)


## Einzelnachweise
