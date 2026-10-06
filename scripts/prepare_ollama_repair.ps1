$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$repairRoot = Join-Path $projectRoot 'data/ollama-repair-20260925'
$archive = Join-Path $repairRoot 'ollama-windows-amd64-v0.34.4.zip'
$stage = Join-Path $repairRoot 'v0.34.4'
$url = 'https://github.com/ollama/ollama/releases/download/v0.34.4/ollama-windows-amd64.zip'
$expectedHash = '535193f38f3344e5b08f5d1c171c31ce11aa17f0124ff69ae26d8ec7fe06fa62'
$expectedSize = 1461155106
New-Item -ItemType Directory -Path $repairRoot -Force | Out-Null
Write-Output 'Downloading official Ollama v0.34.4 Windows amd64 package (1.46 GB); existing model files are reused.'
if (-not (Test-Path -LiteralPath $archive) -or (Get-Item -LiteralPath $archive).Length -ne $expectedSize) {
    & curl.exe --fail --location --retry 3 --connect-timeout 25 --silent --show-error --continue-at - --output $archive $url
    if ($LASTEXITCODE -ne 0) { throw "Official package download failed: curl exit $LASTEXITCODE" }
}
if ((Get-Item -LiteralPath $archive).Length -ne $expectedSize) { throw 'Package size mismatch' }
$hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
if ($hash -ne $expectedHash) { throw 'Official SHA256 mismatch; package will not be executed' }
Write-Output 'Official SHA256 verified. Extracting the complete NVIDIA package.'
if (Test-Path -LiteralPath $stage) { throw 'Staging directory already exists; inspect it before continuing' }
Add-Type -AssemblyName System.IO.Compression.FileSystem
[IO.Compression.ZipFile]::ExtractToDirectory($archive, $stage)
$manifest = [ordered]@{
    version = '0.34.4'; source = $url; sha256 = $hash; size = $expectedSize
    prepared_at = (Get-Date).ToUniversalTime().ToString('o')
    stage = $stage; model_directory = $env:OLLAMA_MODELS
    files = @(Get-ChildItem -LiteralPath $stage -Recurse -File | Select-Object FullName,Length)
}
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $repairRoot 'package-manifest.json') -Encoding UTF8
Get-AuthenticodeSignature -LiteralPath (Join-Path $stage 'ollama.exe') | Select-Object Status,StatusMessage,@{Name='Signer';Expression={$_.SignerCertificate.Subject}} | ConvertTo-Json
Write-Output ('Prepared: ' + $stage)
