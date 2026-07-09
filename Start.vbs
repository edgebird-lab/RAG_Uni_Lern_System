' ============================================================
'  RAG-Lernsystem - unsichtbarer Starter
'  Startet Start.bat OHNE Konsolenfenster (nur im Hintergrund).
'  Der schoene Ladebildschirm erscheint direkt im App-Fenster.
'  Beim Beenden der App (Fenster schliessen / "Beenden"-Button)
'  endet auch dieser Hintergrundprozess automatisch.
' ============================================================
Option Explicit
Dim sh, fso, here
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
Set sh = CreateObject("WScript.Shell")
sh.CurrentDirectory = here
' 2. Parameter 0 = verstecktes Fenster, 3. Parameter False = nicht warten
sh.Run """" & here & "\Start.bat""", 0, False
