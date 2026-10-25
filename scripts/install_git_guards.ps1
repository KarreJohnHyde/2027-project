<#
.SYNOPSIS
  Installs a local pre-push hook that blocks any push while the Git history
  still contains patient-identifier findings (docs/security/PHI_RELEASE_BLOCKER.md).
.DESCRIPTION
  Hooks are local to this clone and not versioned. Remove .git/hooks/pre-push to
  uninstall. The hook runs scripts/privacy_scan.py --history, which never prints
  matched values.
#>
param([string]$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path)
$hook = Join-Path $Repo ".git\hooks\pre-push"
$content = @'
#!/bin/sh
# MedTwin release guard (installed by scripts/install_git_guards.ps1).
root="$(git rev-parse --show-toplevel)"
py="$root/.venv/Scripts/python.exe"
[ -x "$py" ] || py="$root/.venv/bin/python"
[ -x "$py" ] || py=python
if ! "$py" -I "$root/scripts/privacy_scan.py" --history --report "$root/logs/privacy/pre-push.json" >/dev/null 2>&1; then
  echo "MedTwin pre-push guard: Git history still contains patient-identifier or credential findings." >&2
  echo "Push blocked. See docs/security/PHI_RELEASE_BLOCKER.md and logs/privacy/pre-push.json." >&2
  exit 1
fi
exit 0
'@
[System.IO.File]::WriteAllText($hook, $content.Replace("`r`n", "`n"))
Write-Host "Installed $hook"
