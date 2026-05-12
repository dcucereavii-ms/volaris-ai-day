<#
.SYNOPSIS
  Instant rollback: route 100% traffic back to blue.
#>
param(
  [Parameter(Mandatory=$true)] [string] $Endpoint,
  [Parameter(Mandatory=$true)] [string] $Workspace,
  [Parameter(Mandatory=$true)] [string] $ResourceGroup
)

Write-Host "ROLLING BACK $Endpoint -> blue=100 green=0"
az ml online-endpoint update `
  --name $Endpoint `
  --workspace-name $Workspace `
  --resource-group $ResourceGroup `
  --traffic "blue=100 green=0"
if ($LASTEXITCODE -ne 0) { throw "Rollback failed." }

Write-Host "Rollback complete. Investigate green deployment offline."
