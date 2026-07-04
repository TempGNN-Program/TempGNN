if {[info exists ::env(TEMPGNN_LAYOUT_OUTDIR)]} {
    set outdir $::env(TEMPGNN_LAYOUT_OUTDIR)
} else {
    set outdir "results/board_u280/layout_hook"
}

file mkdir $outdir
puts "TEMPGNN_LAYOUT_HOOK begin [clock format [clock seconds]]"

write_checkpoint -force "$outdir/tempgnn_u280_routed.dcp"
report_timing_summary -file "$outdir/tempgnn_u280_timing_summary_routed.rpt" -rpx "$outdir/tempgnn_u280_timing_summary_routed.rpx"
report_utilization -file "$outdir/tempgnn_u280_utilization_routed.rpt"
report_utilization -slr -file "$outdir/tempgnn_u280_slr_utilization_routed.rpt"

set fp [open "$outdir/tempgnn_u280_routed_cells.csv" w]
puts $fp "name,ref,loc,bel,is_kernel"
set placed [get_cells -hier -filter {IS_PRIMITIVE == 1 && LOC != ""}]
set n 0
set nk 0
foreach c $placed {
    set name [get_property NAME $c]
    set ref [get_property REF_NAME $c]
    set loc [get_property LOC $c]
    set bel [get_property BEL $c]
    set is_kernel [expr {[string match -nocase *tempgnn_forward_kernel* $name] || [string match -nocase *tempgnn* $name]}]
    if {$is_kernel} {incr nk}
    regsub -all {"} $name {""} name
    regsub -all {"} $ref {""} ref
    regsub -all {"} $loc {""} loc
    regsub -all {"} $bel {""} bel
    puts $fp "\"$name\",\"$ref\",\"$loc\",\"$bel\",$is_kernel"
    incr n
}
close $fp

set sfp [open "$outdir/tempgnn_u280_layout_hook_summary.txt" w]
puts $sfp "placed_primitives=$n"
puts $sfp "kernel_primitives=$nk"
puts $sfp "checkpoint=$outdir/tempgnn_u280_routed.dcp"
puts $sfp "cells_csv=$outdir/tempgnn_u280_routed_cells.csv"
close $sfp

puts "TEMPGNN_LAYOUT_HOOK placed_primitives=$n kernel_primitives=$nk"
puts "TEMPGNN_LAYOUT_HOOK end [clock format [clock seconds]]"
