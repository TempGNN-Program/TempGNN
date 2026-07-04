set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir .. ..]]
cd $root_dir
set project_dir tempgnn_hls_prj
set source_staging_dir [file join $project_dir hls_sources]

open_project -reset $project_dir
file mkdir $source_staging_dir
file copy -force [file join $root_dir hardware src tempgnn_kernel.cpp] [file join $source_staging_dir tempgnn_kernel.cpp]
set_top tempgnn_kernel

add_files -cflags "-std=c++17 -I[file join $root_dir hardware include]" [file join $source_staging_dir tempgnn_kernel.cpp]
add_files -tb -cflags "-std=c++17 -I[file join $root_dir hardware include]" [file join $root_dir hardware tb tempgnn_tb.cpp]

open_solution -reset "u280_225mhz"
if {[info exists ::env(TEMPGNN_HLS_PART)]} {
  set_part $::env(TEMPGNN_HLS_PART)
} else {
  set_part {xcu280-fsvh2892-2L-e}
}
create_clock -period 4.444 -name default

catch {config_compile -name_max_length 256}

csim_design
csynth_design

set run_cosim 0
if {[llength $argv] > 0 && [string equal [string tolower [lindex $argv 0]] "cosim"]} {
  set run_cosim 1
}
if {[info exists ::env(TEMPGNN_HLS_COSIM)] && [string equal $::env(TEMPGNN_HLS_COSIM) "1"]} {
  set run_cosim 1
}
if {$run_cosim} {
  cosim_design -trace_level all
}

exit
