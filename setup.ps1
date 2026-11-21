# One-time setup on Windows. Run from the project folder:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.11+ not found. Install it from https://www.python.org/downloads/ and try again."
}

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& .\.venv\Scripts\python.exe -m pip install -e ".[dev]"
& .\.venv\Scripts\waypoint.exe init

Write-Host ""
Write-Host "Pronto. Proximos passos:" -ForegroundColor Green
Write-Host "  1. Ative o ambiente:   .\.venv\Scripts\Activate.ps1"
Write-Host "  2. Coloque sua chave de LLM no arquivo .env (notepad .env)"
Write-Host "  3. waypoint collect   ->   waypoint extract   ->   waypoint profile <seu_cv.pdf>   ->   waypoint ui"
