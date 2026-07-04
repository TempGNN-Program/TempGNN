$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Kernel = if ($args.Count -ge 1) { $args[0] } else { "stats" }
$BuildDir = Join-Path $RootDir "build\hardware_csim"
New-Item -ItemType Directory -Force -Path $BuildDir | Out-Null

$Cxx = $env:CXX
if (-not $Cxx) {
  $Gxx = Get-Command g++ -ErrorAction SilentlyContinue
  if ($Gxx) {
    $Cxx = $Gxx.Source
  }
}
if (-not $Cxx) {
  $Clangxx = Get-Command clang++ -ErrorAction SilentlyContinue
  if ($Clangxx) {
    $Cxx = $Clangxx.Source
  }
}
if (-not $Cxx) {
  $BundledGxx = "D:\AMDDesignTools\2025.2\tps\mingw\10.0.0\win64.o\nt\bin\g++.exe"
  if (Test-Path $BundledGxx) {
    $Cxx = $BundledGxx
  }
}
if (-not $Cxx) {
  Write-Error "No C++ compiler found. Set CXX, add g++/clang++ to PATH, or install Vitis with bundled MinGW."
}
$Source = if ($Kernel -eq "forward") {
  "$RootDir\hardware\src\tempgnn_forward_kernel.cpp"
} else {
  "$RootDir\hardware\src\tempgnn_kernel.cpp"
}
$Testbench = if ($Kernel -eq "forward") {
  "$RootDir\hardware\tb\tempgnn_forward_tb.cpp"
} else {
  "$RootDir\hardware\tb\tempgnn_tb.cpp"
}
$Output = if ($Kernel -eq "forward") {
  "$BuildDir\tempgnn_forward_tb.exe"
} else {
  "$BuildDir\tempgnn_tb.exe"
}

& $Cxx -std=c++17 -O2 `
  -I"$RootDir\hardware\include" `
  $Source `
  $Testbench `
  -o $Output

& $Output
