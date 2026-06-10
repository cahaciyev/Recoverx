"""Native Windows file/folder dialogs via PowerShell Windows.Forms.

tkinter's filedialog is unreliable when the process is elevated (UAC admin).
These helpers spawn a PowerShell child process that shows the native
Windows dialog and returns the selected path via stdout.
"""
from __future__ import annotations

import os
import subprocess
from datetime import datetime
from typing import Optional

_CREATE_NO_WINDOW = 0x08000000


def _powershell_exe() -> str:
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    p = os.path.join(root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return p if os.path.isfile(p) else "powershell"


def _ps(script: str) -> str:
    """Run a PowerShell snippet (no console flash) and return its trimmed stdout.

    The native .NET dialog it shows is unaffected by CREATE_NO_WINDOW - only the
    PowerShell console is suppressed.
    """
    try:
        r = subprocess.run(
            [_powershell_exe(), "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=120,
            creationflags=_CREATE_NO_WINDOW,
        )
        return (r.stdout or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def ask_directory(title: str = "Select folder") -> Optional[str]:
    """Show a native Browse-For-Folder dialog. Returns path or None."""
    script = f"""
Add-Type -AssemblyName System.Windows.Forms | Out-Null
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = '{title}'
$d.ShowNewFolderButton = $true
$d.RootFolder = 'MyComputer'
if ($d.ShowDialog() -eq 'OK') {{ $d.SelectedPath }} else {{ '' }}
"""
    path = _ps(script)
    return path if path else None


def ask_open_file(title: str = "Open file", filter_str: str = "All files (*.*)|*.*") -> Optional[str]:
    """Show a native Open-File dialog. filter_str uses Windows.Forms pipe format."""
    script = f"""
Add-Type -AssemblyName System.Windows.Forms | Out-Null
$f = New-Object System.Windows.Forms.OpenFileDialog
$f.Title = '{title}'
$f.Filter = '{filter_str}'
$f.CheckFileExists = $true
if ($f.ShowDialog() -eq 'OK') {{ $f.FileName }} else {{ '' }}
"""
    path = _ps(script)
    return path if path else None


def ask_save_file(
    title: str = "Save file",
    filter_str: str = "All files (*.*)|*.*",
    default_ext: str = "",
    initial_file: str = "",
) -> Optional[str]:
    """Show a native Save-File dialog. Returns path or None."""
    safe_name = initial_file.replace("'", "")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms | Out-Null
$f = New-Object System.Windows.Forms.SaveFileDialog
$f.Title = '{title}'
$f.Filter = '{filter_str}'
$f.DefaultExt = '{default_ext}'
$f.FileName = '{safe_name}'
$f.OverwritePrompt = $true
if ($f.ShowDialog() -eq 'OK') {{ $f.FileName }} else {{ '' }}
"""
    path = _ps(script)
    return path if path else None
