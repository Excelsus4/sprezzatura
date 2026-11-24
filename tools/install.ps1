<#
.SYNOPSIS
  Sprezzatura installer for Windows (Windows PowerShell 5.1+ / PowerShell 7).

.DESCRIPTION
  Installs skill\sprezzatura from a LOCAL checkout into supported agents:
    claude -> ~\.claude\skills\sprezzatura  (+ ~\.claude\commands\*.md)
    codex  -> ~\.codex\skills\sprezzatura
    agy    -> plugin mode (default): ~\.gemini\config\plugins\sprezzatura\skills\sprezzatura
                                     + generated ~\.gemini\config\plugins\sprezzatura\plugin.json
              skill mode:            ~\.gemini\config\skills\sprezzatura
  -Target auto (default) installs for every agent whose config dir exists,
  falling back to claude.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\install.ps1 -Target all
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File tools\install.ps1 -Target all -DryRun
#>
[CmdletBinding()]
param(
    [ValidateSet('claude', 'agy', 'codex', 'all', 'auto')]
    [string]$Target = 'auto',
    [switch]$DryRun,
    [string]$HomeDir = '',
    [string]$Source = '',
    [ValidateSet('skill', 'plugin')]
    [string]$AgyMode = 'plugin'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

# --- product metadata ---
$SkillName = 'sprezzatura'
$DisplayName = 'Sprezzatura'
$PluginVersion = '0.1.0'
$PluginDescription = 'Read-only diff audit for locale, clock, path, crash, and concurrency bugs that pass local tests. Isolated checks, blind verifier.'
$SuggestedPrompts = @(
    'Audit my current changes for edge-case bugs with Sprezzatura',
    'Run a Sprezzatura deep audit on this branch before release',
    'Check this folder for locale, clock, and filesystem edge-case bugs with Sprezzatura'
)

if (-not $HomeDir) {
    $HomeDir = $env:USERPROFILE
    if (-not $HomeDir) { $HomeDir = $HOME }
}
if (-not $HomeDir) { throw 'Cannot determine home directory; pass -HomeDir.' }

function Write-Step([string]$Message) { Write-Host $Message }

function Test-SkillRoot([string]$Dir) {
    if (-not $Dir) { return $false }
    return (Test-Path -LiteralPath (Join-Path $Dir "skill\$SkillName\SKILL.md") -PathType Leaf)
}

function Remove-Dest([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        # Junction/symlink: remove the link only, never the link target's contents.
        [IO.Directory]::Delete($Path)
    }
    else {
        Remove-Item -LiteralPath $Path -Recurse -Force
    }
}

function Install-SkillDir([string]$Label, [string]$Dest) {
    Write-Step "[$Label] skill -> $Dest"
    if ($DryRun) {
        if (Test-Path -LiteralPath $Dest) { Write-Step "[dry-run] would replace existing $Dest" }
        Write-Step "[dry-run] would copy $Source\skill\$SkillName\* -> $Dest"
        return
    }
    Remove-Dest $Dest
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    Copy-Item -Path (Join-Path $Source "skill\$SkillName\*") -Destination $Dest -Recurse -Force
    # Never ship bytecode caches.
    Get-ChildItem -LiteralPath $Dest -Recurse -Directory -Filter '__pycache__' -Force -ErrorAction SilentlyContinue |
        ForEach-Object { Remove-Item -LiteralPath $_.FullName -Recurse -Force }
}

function Get-PluginJson {
    $manifest = [ordered]@{
        name             = $SkillName
        displayName      = $DisplayName
        version          = $PluginVersion
        description      = $PluginDescription
        suggestedPrompts = @($SuggestedPrompts)
    }
    return (ConvertTo-Json -InputObject $manifest -Depth 4)
}

# --- locate source (local checkout only) -----------------------------------
if (-not $Source) {
    $scriptDir = $null
    if ($PSCommandPath) { $scriptDir = Split-Path -Parent $PSCommandPath }
    elseif ($MyInvocation.MyCommand.Path) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
    if ($scriptDir) {
        foreach ($cand in @($scriptDir, (Split-Path -Parent $scriptDir))) {
            if ($cand -and (Test-SkillRoot $cand)) { $Source = (Resolve-Path -LiteralPath $cand).Path; break }
        }
    }
    if (-not $Source) {
        Write-Error ("Local $DisplayName checkout not found (expected skill\$SkillName\SKILL.md next to or above this script). " +
            'Clone https://github.com/Excelsus4/sprezzatura and run tools\install.ps1 from the checkout, or pass -Source <repo root>.') -ErrorAction Continue
        exit 1
    }
}
elseif (-not (Test-SkillRoot $Source)) {
    Write-Error "skill\$SkillName\SKILL.md not found under '$Source'. Pass -Source <repo root> of a $DisplayName checkout." -ErrorAction Continue
    exit 1
}
else {
    $Source = (Resolve-Path -LiteralPath $Source).Path
}
Write-Step "Source: $Source"

# --- resolve targets -------------------------------------------------------
$targets = @()
switch ($Target) {
    'all' { $targets = @('claude', 'agy', 'codex') }
    'auto' {
        if (Test-Path -LiteralPath (Join-Path $HomeDir '.claude') -PathType Container) { $targets += 'claude' }
        if (Test-Path -LiteralPath (Join-Path $HomeDir '.gemini') -PathType Container) { $targets += 'agy' }
        if (Test-Path -LiteralPath (Join-Path $HomeDir '.codex') -PathType Container) { $targets += 'codex' }
        if ($targets.Count -eq 0) {
            Write-Step 'No agent config dirs detected; defaulting to claude'
            $targets = @('claude')
        }
    }
    default { $targets = @($Target) }
}

foreach ($t in $targets) {
    switch ($t) {
        'claude' {
            Install-SkillDir 'claude' (Join-Path $HomeDir ".claude\skills\$SkillName")
            $cmdDir = Join-Path $HomeDir '.claude\commands'
            $cmdSrcDir = Join-Path $Source 'commands'
            $cmdFiles = @()
            if (Test-Path -LiteralPath $cmdSrcDir -PathType Container) {
                $cmdFiles = @(Get-ChildItem -LiteralPath $cmdSrcDir -Filter '*.md' -File | Sort-Object Name)
            }
            if ($cmdFiles.Count -eq 0) {
                Write-Step "[claude] warning: no $cmdSrcDir\*.md found; skipping slash commands"
            }
            else {
                if (-not $DryRun) { New-Item -ItemType Directory -Path $cmdDir -Force | Out-Null }
                foreach ($f in $cmdFiles) {
                    $cmdDest = Join-Path $cmdDir $f.Name
                    Write-Step "[claude] command -> $cmdDest"
                    if ($DryRun) { Write-Step "[dry-run] would copy $($f.FullName) -> $cmdDest" }
                    else { Copy-Item -LiteralPath $f.FullName -Destination $cmdDest -Force }
                }
            }
        }
        'codex' {
            Install-SkillDir 'codex' (Join-Path $HomeDir ".codex\skills\$SkillName")
        }
        'agy' {
            if ($AgyMode -eq 'skill') {
                Install-SkillDir 'agy' (Join-Path $HomeDir ".gemini\config\skills\$SkillName")
            }
            else {
                $pluginRoot = Join-Path $HomeDir ".gemini\config\plugins\$SkillName"
                $legacy = Join-Path $HomeDir ".gemini\config\skills\$SkillName"
                if (Test-Path -LiteralPath $legacy) {
                    Write-Step "[agy] warning: skill-mode install also exists at $legacy (remove it to avoid a duplicate skill)"
                }
                Write-Step "[agy] plugin -> $pluginRoot"
                if (-not $DryRun) { Remove-Dest $pluginRoot }
                Install-SkillDir 'agy' (Join-Path $pluginRoot "skills\$SkillName")
                $manifestPath = Join-Path $pluginRoot 'plugin.json'
                $json = Get-PluginJson
                Write-Step "[agy] manifest -> $manifestPath"
                if ($DryRun) {
                    Write-Step "[dry-run] would write $manifestPath :"
                    Write-Step $json
                }
                else {
                    # UTF-8 without BOM on both Windows PowerShell 5.1 and PowerShell 7.
                    [IO.File]::WriteAllText($manifestPath, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
                }
            }
        }
    }
}

if ($DryRun) { Write-Step 'Dry run complete. No files were changed.' }
else { Write-Step ("$DisplayName installed for: " + ($targets -join ', ')) }
