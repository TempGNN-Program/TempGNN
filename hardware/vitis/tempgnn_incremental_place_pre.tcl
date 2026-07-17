if {![info exists ::env(TEMPGNN_INCREMENTAL_DCP)] ||
    $::env(TEMPGNN_INCREMENTAL_DCP) eq ""} {
    error "TEMPGNN_INCREMENTAL_DCP must name a routed checkpoint"
}

set incremental_dcp [file normalize $::env(TEMPGNN_INCREMENTAL_DCP)]
if {![file exists $incremental_dcp]} {
    error "incremental checkpoint does not exist: $incremental_dcp"
}

puts "TempGNN incremental checkpoint: $incremental_dcp"
read_checkpoint -incremental $incremental_dcp
