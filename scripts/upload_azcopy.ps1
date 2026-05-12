<#
.SYNOPSIS
  Upload anonymized parquet from on-prem to Azure ADLS Gen2 over Private Link using AzCopy.

.PARAMETER SourceDir
  Local folder produced by onprem/anonymize.py.

.PARAMETER StorageAccount
  Target ADLS Gen2 account name (HNS enabled).

.PARAMETER Container
  Target container/filesystem name.

.PARAMETER SasToken
  Optional SAS token. If omitted, az login + AzCopy AAD auth is used.
#>
param(
  [Parameter(Mandatory=$true)] [string] $SourceDir,
  [Parameter(Mandatory=$true)] [string] $StorageAccount,
  [Parameter(Mandatory=$true)] [string] $Container,
  [string] $SasToken = ""
)

if (-not (Test-Path $SourceDir)) {
  throw "SourceDir not found: $SourceDir"
}

$dest = "https://$StorageAccount.dfs.core.windows.net/$Container/anonymized"
if ($SasToken) {
  $dest = "$dest`?$SasToken"
} else {
  Write-Host "Using AAD auth for AzCopy. Run 'azcopy login' first if not already authenticated."
}

azcopy copy "$SourceDir/*" $dest --recursive --put-md5 --check-length=true
if ($LASTEXITCODE -ne 0) { throw "azcopy failed with exit $LASTEXITCODE" }
Write-Host "Upload complete."
