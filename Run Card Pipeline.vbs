Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = appDir

pythonwPath = appDir & "\.venv\Scripts\pythonw.exe"
pythonPath = appDir & "\.venv\Scripts\python.exe"

If fso.FileExists(pythonwPath) Then
    shell.Run """" & pythonwPath & """ """ & appDir & "\app.py""", 0, False
ElseIf fso.FileExists(pythonPath) Then
    shell.Run """" & pythonPath & """ """ & appDir & "\app.py""", 1, False
Else
    pythonwPath = "pythonw.exe"
    result = shell.Run("cmd /c where pythonw.exe >nul 2>nul", 0, True)
    If result = 0 Then
        shell.Run """" & pythonwPath & """ """ & appDir & "\app.py""", 0, False
    Else
        MsgBox "L.U.C.A.S could not find Python." & vbCrLf & vbCrLf & _
               "Install Python 3.11 or newer from python.org, check Add python.exe to PATH, then run install_dependencies.bat.", _
               vbExclamation, "L.U.C.A.S"
    End If
End If
