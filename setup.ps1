# One-time setup for kore-agent-kit.
# Run once from this folder:  .\setup.ps1
# Safe to run twice: every step checks before acting.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host ""
Write-Host "kore-agent-kit setup" -ForegroundColor Cyan
Write-Host "--------------------"

# 1. VS Code config. Remote tools cannot write to a .vscode folder, so the
#    files shipped as vscode-config and get moved into place here.
if (Test-Path "vscode-config") {
    if (-not (Test-Path ".vscode")) { New-Item -ItemType Directory -Path ".vscode" | Out-Null }
    Copy-Item "vscode-config\*" ".vscode\" -Force
    Remove-Item "vscode-config" -Recurse -Force
    Write-Host "[ok] VS Code config installed (F5 runs the server)"
} else {
    Write-Host "[--] VS Code config already in place"
}

# 2. Git.
if (-not (Test-Path ".git")) {
    git init -b main | Out-Null

    $email = git config user.email
    if (-not $email) {
        git config user.name  "Nandita Menon"
        git config user.email "nanditam1010@gmail.com"
        Write-Host "[ok] git identity set for this repo"
    }

    git add -A
    git commit -q -m "Add kore-agent-kit: grounded agent over a document corpus" -m @"
Stdlib-only Python. Runs with no pip install and no API key: the mock
provider keeps retrieval real when no key is set, so a dead network cannot
take a demo down.

Includes an OpenAI-compatible client, heading-aware TF-IDF retrieval, a tool
registry, a tool-calling loop with a visible trace, a stdlib HTTP server, a
chat UI, and an eval harness.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
"@
    Write-Host "[ok] git repo initialised, first commit made"
} else {
    Write-Host "[--] git repo already exists"
}

# 3. Prove it runs.
Write-Host ""
Write-Host "Running smoke test..." -ForegroundColor Cyan
$py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" } else { "python3" }
& $py -m tests.smoke
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Smoke test failed. Check that Python 3.9+ is on PATH." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "Done. Next:" -ForegroundColor Green
Write-Host "  $py -m app.server        then open http://localhost:8000"
Write-Host ""
Write-Host "To push to GitHub (create the empty repo first, no README):"
Write-Host "  git remote add origin https://github.com/<you>/kore-agent-kit.git"
Write-Host "  git push -u origin main"
Write-Host ""
