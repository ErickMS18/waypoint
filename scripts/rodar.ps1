# Waypoint: one-click run on Windows (called by RODAR_WAYPOINT.bat).
# Sets up the environment if needed, then: collect -> extract -> profile -> eval -> reports -> tests.
# Everything it prints also goes to data\logs\ultima_execucao.log.
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
Set-Location (Split-Path $PSScriptRoot -Parent)
New-Item -ItemType Directory -Force "data\logs" | Out-Null
$log = "data\logs\ultima_execucao.log"
Set-Content -Path $log -Value "Waypoint - $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding UTF8
Remove-Item "data\logs\FIM.txt" -ErrorAction SilentlyContinue

function Say([string]$msg) {
    Write-Host $msg -ForegroundColor Cyan
    Add-Content -Path $log -Value $msg -Encoding UTF8
}
function Run([string]$title, [string]$exe, [string[]]$argv) {
    Say "`n=== $title ==="
    & $exe @argv 2>&1 | ForEach-Object {
        $line = "$_"
        Write-Host $line
        Add-Content -Path $log -Value $line -Encoding UTF8
    }
    Say "(exit code: $LASTEXITCODE)"
}

# ---------- Python ----------
$exe = $null; $pre = @()
if (Get-Command py -ErrorAction SilentlyContinue) { $exe = "py"; $pre = @("-3") }
elseif (Get-Command python -ErrorAction SilentlyContinue) { $exe = "python" }
if (-not $exe) {
    Say "ERRO: Python nao encontrado. Instale o Python 3.11+ em https://www.python.org/downloads/ (marque 'Add to PATH')."
    Set-Content "data\logs\FIM.txt" "ERRO python" -Encoding UTF8
    Read-Host "Pressione Enter para fechar"; exit 1
}
$ver = & $exe @pre -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>&1
Say "Python encontrado: $exe $pre -> $ver"
if ([version]"$ver" -lt [version]"3.11") {
    Say "ERRO: o Waypoint precisa do Python 3.11 ou mais novo (achei $ver)."
    Set-Content "data\logs\FIM.txt" "ERRO versao python" -Encoding UTF8
    Read-Host "Pressione Enter para fechar"; exit 1
}

# ---------- environment ----------
if (-not (Test-Path ".venv\Scripts\python.exe")) { Run "Criando ambiente virtual" $exe ($pre + @("-m", "venv", ".venv")) }
$vpy = (Resolve-Path ".venv\Scripts\python.exe").Path
Run "Instalando dependencias" $vpy @("-m", "pip", "install", "-q", "--disable-pip-version-check", "-e", ".[dev]")
$wp = (Resolve-Path ".venv\Scripts\waypoint.exe").Path
Run "waypoint init" $wp @("init")

$hasKey = $false
if (Test-Path ".env") {
    $hasKey = @(Select-String -Path ".env" -Pattern '^\s*(GEMINI|ANTHROPIC|OPENAI|LLM)_API_KEY\s*=\s*\S+').Count -gt 0
}
Say "Chave de LLM no .env: $hasKey"
$noLlm = @(); if (-not $hasKey) { $noLlm = @("--no-llm") }

# ---------- pipeline ----------
Run "Empresas configuradas" $wp @("boards", "check")

$needProfile = -not (Test-Path "profile\profile.json")
if (-not $needProfile -and $hasKey) {
    $method = (Get-Content "profile\profile.json" -Raw | ConvertFrom-Json).method
    if ($method -eq "baseline") { $needProfile = $true }
}
if ($needProfile) {
    $cv = Get-ChildItem -Path "profile" -Include *.pdf, *.docx -File -Recurse | Select-Object -First 1
    if ($cv) { Run "Perfil a partir do curriculo" $wp (@("profile", $cv.FullName) + $noLlm) }
    else { Say "Sem curriculo em profile\ (coloque um .pdf ou .docx la, ou envie pela interface)." }
}

# coleta -> extracao (LLM + dicionario) -> plano -> relatorios (o mesmo que o botao 'Atualizar tudo')
Run "Atualizacao completa" $wp @("update")

if (-not (Test-Path "data\eval\texts.jsonl")) { Run "Amostra para avaliacao" $wp @("eval", "sample", "--n", "40") }
if (Test-Path "eval\gold.jsonl") {
    $evalArgs = @("eval", "run", "--update-readme"); if (-not $hasKey) { $evalArgs += @("--extractor", "baseline") }
    Run "Avaliacao" $wp $evalArgs
}
Run "Testes automaticos" $vpy @("-m", "pytest", "-q")

# ---------- atalho (Area de Trabalho + Menu Iniciar) ----------
Say "`n=== Atalho do Waypoint ==="
try {
    $root = (Get-Location).Path
    $pyw = Join-Path $root ".venv\Scripts\pythonw.exe"
    $shell = New-Object -ComObject WScript.Shell
    $places = @([Environment]::GetFolderPath("Desktop"), (Join-Path ([Environment]::GetFolderPath("Programs")) ""))
    foreach ($dir in $places) {
        $lnk = $shell.CreateShortcut((Join-Path $dir "Waypoint.lnk"))
        $lnk.TargetPath = $pyw
        $lnk.Arguments = '"' + (Join-Path $root "scripts\waypoint_launcher.pyw") + '"'
        $lnk.WorkingDirectory = $root
        $lnk.IconLocation = (Join-Path $root "assets\waypoint.ico") + ",0"
        $lnk.Description = "Waypoint - radar de carreira (abre a interface)"
        $lnk.Save()
        Say "Atalho criado: $(Join-Path $dir 'Waypoint.lnk')"
    }
} catch { Say "Nao consegui criar o atalho: $_" }

Set-Content "data\logs\FIM.txt" "OK $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Encoding UTF8
Say "`nPronto! Relatorios em reports\. Para abrir a interface: atalho Waypoint na Area de Trabalho."
Start-Process $pyw -ArgumentList ('"' + (Join-Path $root "scripts\waypoint_launcher.pyw") + '"') -WorkingDirectory $root
Read-Host "Pressione Enter para fechar"
