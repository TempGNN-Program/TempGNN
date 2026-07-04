set script_dir [file dirname [file normalize [info script]]]
set root_dir [file normalize [file join $script_dir .. ..]]
cd $root_dir
set project_dir tempgnn_forward_hls_prj
if {[info exists ::env(TEMPGNN_HLS_PROJECT_DIR)]} {
  set project_dir $::env(TEMPGNN_HLS_PROJECT_DIR)
}
set source_staging_dir [file join $project_dir hls_sources]

open_project -reset $project_dir
file mkdir $source_staging_dir
file copy -force [file join $root_dir hardware src tempgnn_forward_kernel.cpp] [file join $source_staging_dir tempgnn_forward_kernel.cpp]
set_top tempgnn_forward_kernel

set hls_cflags "-std=c++17 -I[file join $root_dir hardware include]"
if {[info exists ::env(TEMPGNN_HLS_CFLAGS)]} {
  append hls_cflags " " $::env(TEMPGNN_HLS_CFLAGS)
}

add_files -cflags $hls_cflags [file join $source_staging_dir tempgnn_forward_kernel.cpp]
add_files -tb -cflags $hls_cflags [file join $root_dir hardware tb tempgnn_forward_tb.cpp]

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
  set trace_level all
  if {[info exists ::env(TEMPGNN_HLS_TRACE_LEVEL)]} {
    set trace_level $::env(TEMPGNN_HLS_TRACE_LEVEL)
  }
  cosim_design -trace_level $trace_level
}

exit
