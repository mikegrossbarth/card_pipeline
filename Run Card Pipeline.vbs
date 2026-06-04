Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = "C:\Users\User\Documents\Codex\2026-06-04\card_pipeline"
shell.Run """C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"" ""C:\Users\User\Documents\Codex\2026-06-04\card_pipeline\app.py""", 0, False
