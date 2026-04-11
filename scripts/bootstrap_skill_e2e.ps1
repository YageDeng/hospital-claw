$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$bootstrapScript = Join-Path $scriptDir "bootstrap_skill_e2e.py"

$pythonCommand = $null
$pythonArgs = @()

if (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCommand = "py"
    $pythonArgs = @("-3", $bootstrapScript)
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCommand = "python"
    $pythonArgs = @($bootstrapScript)
}
else {
    Write-Error "Could not find 'py' or 'python' on PATH."
    exit 1
}

& $pythonCommand @pythonArgs @args
exit $LASTEXITCODE
