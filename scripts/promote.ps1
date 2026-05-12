<#
.SYNOPSIS
  Progressive A/B promotion of green deployment.
#>
param(
  [Parameter(Mandatory=$true)] [string] $Endpoint,
  [Parameter(Mandatory=$true)] [string] $Workspace,
  [Parameter(Mandatory=$true)] [string] $ResourceGroup,
  [ValidateSet("10","50","100")] [string] $GreenPct = "10"
)

$bluePct = 100 - [int]$GreenPct
$traffic = "blue=$bluePct green=$GreenPct"
Write-Host "Setting traffic on $Endpoint -> $traffic"

az ml online-endpoint update `
  --name $Endpoint `
  --workspace-name $Workspace `
  --resource-group $ResourceGroup `
  --traffic $traffic
if ($LASTEXITCODE -ne 0) { throw "Promotion failed." }
Write-Host "Done. Monitor App Insights and AML metrics before next step."
