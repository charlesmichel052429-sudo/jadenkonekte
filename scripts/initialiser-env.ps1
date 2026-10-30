# Crée .env à partir de .env.exemple en générant des secrets aléatoires.
#   powershell -ExecutionPolicy Bypass -File .\scripts\initialiser-env.ps1
# Ne remplace jamais un .env existant (la base garde le mot de passe de sa création).
$racine = Split-Path -Parent $PSScriptRoot
$cible = Join-Path $racine ".env"
if (Test-Path $cible) { Write-Host ".env existe déjà : rien à faire." -ForegroundColor Yellow; exit 0 }

function Secret([int]$octets = 24) {
    $b = New-Object byte[] $octets
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b)
    -join ($b | ForEach-Object { $_.ToString("x2") })
}

$lignes = Get-Content (Join-Path $racine ".env.exemple") -Encoding UTF8 | ForEach-Object {
    if ($_ -match '^JWT_SECRET=') { "JWT_SECRET=$(Secret 48)" }
    elseif ($_ -match '^([A-Z_]+)=a-remplacer$') { "$($Matches[1])=$(Secret)" }
    else { $_ }
}
[IO.File]::WriteAllLines($cible, $lignes, (New-Object Text.UTF8Encoding $false))
Write-Host ".env créé avec des secrets aléatoires. Mot de passe administrateur : voir ADMIN_MOT_DE_PASSE dans .env" -ForegroundColor Green
