# Vérification de l'environnement de développement Jaden Konekté (Windows / PowerShell 5.1+)
#   powershell -ExecutionPolicy Bypass -File .\scripts\verifier-environnement.ps1
# Lecture seule : ne démarre, n'arrête et ne supprime aucun conteneur ni volume.

$racine = Split-Path -Parent $PSScriptRoot
$ok = $true

function Verifier($nom, [scriptblock]$test) {
    try {
        $r = & $test
        Write-Host ("[OK]  {0,-28} {1}" -f $nom, $r) -ForegroundColor Green
    } catch {
        Write-Host ("[KO]  {0,-28} {1}" -f $nom, $_.Exception.Message) -ForegroundColor Red
        $script:ok = $false
    }
}

Verifier "Docker (client/serveur)" {
    $v = docker version --format '{{.Client.Version}} / {{.Server.Version}} {{.Server.Os}}' 2>$null
    if (-not $v) { throw "moteur Docker injoignable : lancez Docker Desktop" }
    if ($v -notmatch 'linux') { throw "moteur Windows actif : basculez sur les conteneurs Linux" }
    $v
}
Verifier "Docker Compose" { (docker compose version --short) }
Verifier "WSL 2" {
    $s = (wsl --status 2>$null | Out-String) -replace "`0", ""
    if ($s -notmatch '2') { throw "WSL 2 non détecté" }
    "version par défaut 2"
}
Verifier "Python 3.13 (py launcher)" {
    $v = py -3.13 --version 2>$null
    if (-not $v) { throw "Python 3.13 absent (3.14 est trop récent pour certaines roues : torch, onnxruntime)" }
    $v
}
Verifier "Environnement virtuel .venv" {
    $py = Join-Path $racine ".venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { throw "absent : py -3.13 -m venv .venv" }
    & $py --version
}
Verifier "Contrat openapi.yaml" {
    $val = Join-Path $racine ".venv\Scripts\openapi-spec-validator.exe"
    if (-not (Test-Path $val)) { throw "installer : .\.venv\Scripts\pip install openapi-spec-validator" }
    $r = & $val (Join-Path $racine "openapi.yaml") 2>&1 | Out-String
    if ($r -notmatch ': OK') { throw $r.Trim() }
    "valide (OpenAPI 3.1)"
}
foreach ($port in 1883, 8080) {
    Verifier "Port $port libre" {
        $c = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        if ($c) {
            $p = (Get-Process -Id $c[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
            throw "déjà utilisé par $p (un autre docker compose ?)"
        }
        "libre"
    }
}
Verifier "Fichier .env" {
    if (-not (Test-Path (Join-Path $racine ".env"))) { throw "absent : lancer scripts\initialiser-env.ps1" }
    "présent"
}

if ($ok) { Write-Host "`nEnvironnement prêt." -ForegroundColor Green }
else { Write-Host "`nCorrigez les points [KO] ci-dessus." -ForegroundColor Yellow }
