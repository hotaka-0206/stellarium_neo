
param(
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$ruleName = "Astelock_Block_RemoteControl_8090"

# Find Stellarium installation
$candidates = @()

if ($env:ProgramFiles) {
    $candidates += Join-Path $env:ProgramFiles "Stellarium\stellarium.exe"
}

if (${env:ProgramFiles(x86)}) {
    $candidates += Join-Path ${env:ProgramFiles(x86)} "Stellarium\stellarium.exe"
}

$stellariumExe = $candidates |
    Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } |
    Select-Object -First 1

if (-not $stellariumExe) {
    throw "Stellarium executable not found. Firewall setup was not completed."
}

Write-Output "Stellarium: $stellariumExe"

# Check existing Astelock firewall rule
$existing = Get-NetFirewallRule -Name $ruleName -ErrorAction SilentlyContinue

if ($existing) {
    $appFilter = $existing | Get-NetFirewallApplicationFilter
    $portFilter = $existing | Get-NetFirewallPortFilter
    $addressFilter = $existing | Get-NetFirewallAddressFilter

    $valid = (
        $existing.Enabled.ToString() -eq "True" -and
        $existing.Direction.ToString() -eq "Inbound" -and
        $existing.Action.ToString() -eq "Block" -and
        $existing.Profile.ToString() -eq "Any" -and
        $appFilter.Program -eq $stellariumExe -and
        $portFilter.Protocol.ToString() -eq "TCP" -and
        $portFilter.LocalPort -eq "8090" -and
        $addressFilter.LocalAddress -eq "Any" -and
        $addressFilter.RemoteAddress -eq "Any"
    )

    if (-not $valid) {
        throw "Existing firewall rule does not match the required settings."
    }

    Write-Output "OK: Firewall rule already configured."
    exit 0
}

# Verification only: do not change firewall
if ($CheckOnly) {
    Write-Output "READY: Firewall rule can be created for this path."
    exit 0
}

# Create firewall rule
New-NetFirewallRule `
    -Name $ruleName `
    -DisplayName "Astelock - Block External Remote Control" `
    -Direction Inbound `
    -Program $stellariumExe `
    -Protocol TCP `
    -LocalPort 8090 `
    -LocalAddress Any `
    -RemoteAddress Any `
    -Action Block `
    -Profile Any `
    -Enabled True `
    -ErrorAction Stop | Out-Null

Write-Output "CREATED: Firewall rule configured successfully."
