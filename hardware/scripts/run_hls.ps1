$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Mode = if ($args.Count -ge 1) { $args[0] } else { "csynth" }
$Kernel = if ($args.Count -ge 2) { $args[1] } else { "stats" }

$Tcl = if ($Kernel -eq "forward") {
    "$RootDir\hardware\hls\tempgnn_forward_hls.tcl"
} else {
    "$RootDir\hardware\hls\tempgnn_hls.tcl"
}

$VitisRun = (Get-Command vitis-run -ErrorAction SilentlyContinue)
if ($VitisRun) {
    if ($Mode -eq "cosim") {
        $env:TEMPGNN_HLS_COSIM = "1"
    }
    & $VitisRun.Source --mode hls --tcl $Tcl
    exit $LASTEXITCODE
}

$HlsBin = (Get-Command vitis_hls -ErrorAction SilentlyContinue)
if (-not $HlsBin) {
    $HlsBin = (Get-Command vivado_hls -ErrorAction SilentlyContinue)
}
if (-not $HlsBin) {
    Write-Error "vitis-run/vitis_hls/vivado_hls not found in PATH. Source Xilinx/Vitis settings first."
}
if ($Mode -eq "cosim") {
    & $HlsBin.Source -f $Tcl cosim
} else {
    & $HlsBin.Source -f $Tcl
}
