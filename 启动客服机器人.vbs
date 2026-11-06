Option Explicit
Dim shell, files, root, python, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
root = files.GetParentFolderName(WScript.ScriptFullName)
python = root & "\.venv\Scripts\pythonw.exe"
If Not files.FileExists(python) Then python = "pythonw.exe"
command = Chr(34) & python & Chr(34) & " " & Chr(34) & root & "\scripts\launch_local.py" & Chr(34)
shell.CurrentDirectory = root
shell.Run command, 0, False
