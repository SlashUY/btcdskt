Dim shell
Set shell = CreateObject("WScript.Shell")
shell.Run "pythonw """ & CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName) & "\btc_widget.py""", 0, False
Set shell = Nothing
