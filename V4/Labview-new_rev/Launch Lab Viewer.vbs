Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir

launcher = scriptDir & "\Launch Lab Viewer.pyw"
pyw = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Launcher\pyw.exe"

If Not fso.FileExists(launcher) Then
    MsgBox "Could not find:" & vbCrLf & launcher, vbCritical, "Lab Viewer launch failed"
    WScript.Quit 1
End If

If Not fso.FileExists(pyw) Then
    pyw = "pyw.exe"
End If

command = Chr(34) & pyw & Chr(34) & " -3 " & Chr(34) & launcher & Chr(34)
shell.Run command, 0, False
