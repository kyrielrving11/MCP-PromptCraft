# Configure the current PowerShell session for UTF-8 Python development.
#
# Usage:
#   . .\scripts\windows_dev_env.ps1
#
# Dot-source the script so $OutputEncoding is updated in this session.

chcp 65001 > $null

$utf8NoBom = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $utf8NoBom
[Console]::OutputEncoding = $utf8NoBom
$global:OutputEncoding = $utf8NoBom

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "PowerShell and Python UTF-8 development settings are active for this session."
