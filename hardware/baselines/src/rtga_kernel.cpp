#include "baseline_hls.hpp"

#define RTGA_VISITED_SLOTS 1024

struct RtgaTreeEdge {
    uint32_t event_idx;
    uint32_t peer;
    uint32_t timestamp;
};

static bool rtga_contains_edge(
    const RtgaTreeEdge edges[BASELINE_MAX_FANOUT], uint32_t count, uint32_t event_idx) {
#pragma HLS INLINE
    bool found = false;
rtga_local_dedup:
    for (uint32_t idx = 0; idx < BASELINE_MAX_FANOUT; ++idx) {
#pragma HLS UNROLL
        if (idx < count && edges[idx].event_idx == event_idx) {
            found = true;
        }
    }
    return found;
}

static int16_t rtga_tau_message(
    uint32_t model_id,
    int16_t memory,
    int16_t feature,
    int16_t wp,
    int16_t we) {
#pragma HLS INLINE
    int32_t transformed =
        (static_cast<int32_t>(memory) * wp + static_cast<int32_t>(feature) * we) /
        BASELINE_SCALE;
    switch (model_id & 3u) {
    case 0: // JODIE trajectory message.
        return baseline_hard_tanh_q10(static_cast<int32_t>(memory) + transformed / 2);
    case 2: // TGAT temporal attention message.
        return baseline_hard_tanh_q10(transformed + feature / 2);
    case 3: // APAN asynchronous propagation message.
        return baseline_hard_tanh_q10((static_cast<int32_t>(memory) + feature + transformed) / 2);
    default: // TGN memory message.
        return baseline_hard_tanh_q10(transformed);
    }
}

extern "C" void rtga_kernel(BASELINE_KERNEL_ARGUMENTS) {
#pragma HLS INTERFACE m_axi port=event_src offset=slave bundle=gmem0
#pragma HLS INTERFACE m_axi port=event_dst offset=slave bundle=gmem1
#pragma HLS INTERFACE m_axi port=event_ts offset=slave bundle=gmem2
#pragma HLS INTERFACE m_axi port=vertex_offsets offset=slave bundle=gmem3
#pragma HLS INTERFACE m_axi port=history_event_idx offset=slave bundle=gmem4
#pragma HLS INTERFACE m_axi port=history_peer offset=slave bundle=gmem5
#pragma HLS INTERFACE m_axi port=target_vertex offset=slave bundle=gmem6
#pragma HLS INTERFACE m_axi port=target_event_idx offset=slave bundle=gmem7
#pragma HLS INTERFACE m_axi port=initial_memory offset=slave bundle=gmem8
#pragma HLS INTERFACE m_axi port=event_features offset=slave bundle=gmem9
#pragma HLS INTERFACE m_axi port=weight_self offset=slave bundle=gmem10
#pragma HLS INTERFACE m_axi port=weight_peer offset=slave bundle=gmem10
#pragma HLS INTERFACE m_axi port=weight_event offset=slave bundle=gmem10
#pragma HLS INTERFACE m_axi port=bias offset=slave bundle=gmem10
#pragma HLS INTERFACE m_axi port=embedding_out offset=slave bundle=gmem11
#pragma HLS INTERFACE m_axi port=stats_out offset=slave bundle=gmem12
#pragma HLS INTERFACE s_axilite port=event_src bundle=control
#pragma HLS INTERFACE s_axilite port=event_dst bundle=control
#pragma HLS INTERFACE s_axilite port=event_ts bundle=control
#pragma HLS INTERFACE s_axilite port=num_events bundle=control
#pragma HLS INTERFACE s_axilite port=vertex_offsets bundle=control
#pragma HLS INTERFACE s_axilite port=history_event_idx bundle=control
#pragma HLS INTERFACE s_axilite port=history_peer bundle=control
#pragma HLS INTERFACE s_axilite port=num_vertices bundle=control
#pragma HLS INTERFACE s_axilite port=target_vertex bundle=control
#pragma HLS INTERFACE s_axilite port=target_event_idx bundle=control
#pragma HLS INTERFACE s_axilite port=num_targets bundle=control
#pragma HLS INTERFACE s_axilite port=fanout bundle=control
#pragma HLS INTERFACE s_axilite port=depth bundle=control
#pragma HLS INTERFACE s_axilite port=model_id bundle=control
#pragma HLS INTERFACE s_axilite port=inference_mode bundle=control
#pragma HLS INTERFACE s_axilite port=reproduction_flags bundle=control
#pragma HLS INTERFACE s_axilite port=initial_memory bundle=control
#pragma HLS INTERFACE s_axilite port=event_features bundle=control
#pragma HLS INTERFACE s_axilite port=weight_self bundle=control
#pragma HLS INTERFACE s_axilite port=weight_peer bundle=control
#pragma HLS INTERFACE s_axilite port=weight_event bundle=control
#pragma HLS INTERFACE s_axilite port=bias bundle=control
#pragma HLS INTERFACE s_axilite port=embedding_out bundle=control
#pragma HLS INTERFACE s_axilite port=stats_out bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    baseline_clear_stats(stats_out);
    uint32_t visited_tag[RTGA_VISITED_SLOTS];
#pragma HLS BIND_STORAGE variable=visited_tag type=ram_t2p impl=bram
    bool cache_valid[BASELINE_RTGA_CACHE_LINES];
    uint32_t cache_vertex[BASELINE_RTGA_CACHE_LINES];
    uint32_t cache_priority[BASELINE_RTGA_CACHE_LINES];
    int16_t cache_memory[BASELINE_RTGA_CACHE_LINES][BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=cache_valid complete
#pragma HLS ARRAY_PARTITION variable=cache_vertex complete
#pragma HLS ARRAY_PARTITION variable=cache_priority complete
#pragma HLS ARRAY_PARTITION variable=cache_memory complete dim=2

rtga_clear_visited:
    for (uint32_t idx = 0; idx < RTGA_VISITED_SLOTS; ++idx) {
#pragma HLS PIPELINE II=1
        visited_tag[idx] = BASELINE_INITIAL_EVENT;
    }
rtga_clear_cache:
    for (uint32_t line = 0; line < BASELINE_RTGA_CACHE_LINES; ++line) {
#pragma HLS UNROLL
        cache_valid[line] = false;
        cache_vertex[line] = 0;
        cache_priority[line] = 0;
    rtga_clear_cache_dim:
        for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
            cache_memory[line][dim] = 0;
        }
    }

    uint64_t scanned_total = 0;
    uint64_t selected_total = 0;
    uint64_t reused_total = 0;
    uint64_t cache_hits = 0;
    uint64_t invalid_inputs = 0;
    uint64_t checksum = 0x5254474100000001ull;
    uint32_t scan_budget = baseline_min_u32(fanout, BASELINE_MAX_FANOUT);
    int16_t local_weight_self[BASELINE_DIM];
    int16_t local_weight_peer[BASELINE_DIM];
    int16_t local_weight_event[BASELINE_DIM];
    int16_t local_bias[BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=local_weight_self complete
#pragma HLS ARRAY_PARTITION variable=local_weight_peer complete
#pragma HLS ARRAY_PARTITION variable=local_weight_event complete
#pragma HLS ARRAY_PARTITION variable=local_bias complete
rtga_load_weights:
    for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS PIPELINE II=1
        local_weight_self[dim] = weight_self[dim];
        local_weight_peer[dim] = weight_peer[dim];
        local_weight_event[dim] = weight_event[dim];
        local_bias[dim] = bias[dim];
    }

rtga_targets:
    for (uint32_t target = 0; target < num_targets; ++target) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
        uint32_t vertex = target_vertex[target];
        uint32_t before_event = target_event_idx[target];
        if (vertex >= num_vertices || before_event > num_events) {
            ++invalid_inputs;
            continue;
        }
        uint32_t begin = vertex_offsets[vertex];
        uint32_t end = vertex_offsets[vertex + 1u];
        RtgaTreeEdge tree_edges[BASELINE_MAX_FANOUT];
#pragma HLS ARRAY_PARTITION variable=tree_edges complete
        uint32_t recent_event_idx[BASELINE_MAX_DEGREE_SCAN];
        uint32_t recent_peer[BASELINE_MAX_DEGREE_SCAN];
#pragma HLS BIND_STORAGE variable=recent_event_idx type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=recent_peer type=ram_1p impl=bram
        uint32_t tree_count = 0;
        uint32_t valid_candidates = 0;
        uint32_t recent_count = baseline_min_u32(end - begin, BASELINE_MAX_DEGREE_SCAN);

        // Register recent HBM entries before visited-tag and local-dedup
        // checks. This keeps the tree semantics intact while removing the
        // AXI-read/comparator/BRAM-write chain from one HLS cycle.
    rtga_load_recent:
        for (uint32_t step = 0; step < BASELINE_MAX_DEGREE_SCAN; ++step) {
#pragma HLS PIPELINE II=1
            if (step >= recent_count) {
                break;
            }
            uint32_t pos = end - 1u - step;
            recent_event_idx[step] = history_event_idx[pos];
            recent_peer[step] = history_peer[pos];
        }

        // TTCU + parallel sampler: construct triplets in descending temporal
        // order and suppress edges already visited by an earlier root.
    rtga_temporal_tree_construction:
        for (uint32_t step = 0; step < BASELINE_MAX_DEGREE_SCAN; ++step) {
            if (valid_candidates >= scan_budget || step >= recent_count) {
                break;
            }
            uint32_t event_idx = recent_event_idx[step];
            uint32_t peer = recent_peer[step];
            ++scanned_total;
            if (event_idx >= before_event || event_idx >= num_events || peer >= num_vertices) {
                continue;
            }
            ++valid_candidates;
            uint32_t visited_slot = event_idx & (RTGA_VISITED_SLOTS - 1u);
            if (visited_tag[visited_slot] == event_idx ||
                rtga_contains_edge(tree_edges, tree_count, event_idx)) {
                ++reused_total;
                continue;
            }
            visited_tag[visited_slot] = event_idx;
            tree_edges[tree_count].event_idx = event_idx;
            tree_edges[tree_count].peer = peer;
            tree_edges[tree_count].timestamp = event_ts[event_idx];
            ++tree_count;
        }
        selected_total += tree_count;

        int16_t selected_memory[BASELINE_MAX_FANOUT][BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=selected_memory complete dim=2
        int16_t selected_feature[BASELINE_MAX_FANOUT][BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=selected_feature complete dim=2

        // TADC: cache vertices with high degree / early timestamp priority.
    rtga_temporal_aware_cache:
        for (uint32_t edge = 0; edge < BASELINE_MAX_FANOUT; ++edge) {
            if (edge >= tree_count) {
                break;
            }
            uint32_t peer = tree_edges[edge].peer;
            uint32_t hit_line = BASELINE_RTGA_CACHE_LINES;
            uint32_t victim_line = 0;
            uint32_t victim_priority = 0xffffffffu;
        rtga_cache_lookup:
            for (uint32_t line = 0; line < BASELINE_RTGA_CACHE_LINES; ++line) {
#pragma HLS UNROLL
                if (cache_valid[line] && cache_vertex[line] == peer) {
                    hit_line = line;
                }
                if (!cache_valid[line] || cache_priority[line] < victim_priority) {
                    victim_priority = cache_valid[line] ? cache_priority[line] : 0;
                    victim_line = line;
                }
            }
            uint32_t use_line = hit_line;
            if (hit_line < BASELINE_RTGA_CACHE_LINES) {
                ++cache_hits;
            } else {
                uint32_t degree = vertex_offsets[peer + 1u] - vertex_offsets[peer];
                uint32_t priority =
                    (degree * 4096u) / (1u + baseline_min_u32(tree_edges[edge].timestamp, 4095u));
                use_line = victim_line;
                cache_valid[use_line] = true;
                cache_vertex[use_line] = peer;
                cache_priority[use_line] = priority;
            rtga_cache_fill:
                for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
                    cache_memory[use_line][dim] = initial_memory[peer * BASELINE_DIM + dim];
                }
            }
        rtga_stage_edge:
            for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
                selected_memory[edge][dim] = cache_memory[use_line][dim];
                selected_feature[edge][dim] =
                    event_features[tree_edges[edge].event_idx * BASELINE_DIM + dim];
            }
        }

        int32_t aggregate[BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=aggregate complete
    rtga_clear_aggregate:
        for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
            aggregate[dim] = 0;
        }

        // The processor is organized as eight parallel temporal arithmetic
        // units, matching the evaluated RTGA configuration.
    rtga_tau_groups:
        for (uint32_t base = 0; base < BASELINE_MAX_FANOUT; base += BASELINE_RTGA_TAUS) {
        rtga_tau_lanes:
            for (uint32_t lane = 0; lane < BASELINE_RTGA_TAUS; ++lane) {
#pragma HLS UNROLL
                uint32_t edge = base + lane;
                if (edge < tree_count) {
                rtga_tau_dims:
                    for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
                        aggregate[dim] += rtga_tau_message(
                            model_id,
                            selected_memory[edge][dim],
                            selected_feature[edge][dim],
                            local_weight_peer[dim],
                            local_weight_event[dim]);
                    }
                }
            }
        }

    rtga_temporal_aggregator:
        for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
            int16_t self = initial_memory[vertex * BASELINE_DIM + dim];
            int32_t message = tree_count == 0 ? 0 : aggregate[dim] / static_cast<int32_t>(tree_count);
            int32_t transformed =
                (static_cast<int32_t>(self) * local_weight_self[dim]) / BASELINE_SCALE + message +
                local_bias[dim];
            int16_t output = baseline_hard_tanh_q10(transformed);
            embedding_out[target * BASELINE_DIM + dim] = output;
            checksum = baseline_mix_checksum(checksum, output, target * BASELINE_DIM + dim);
        }

        if (before_event < num_events) {
            checksum ^= static_cast<uint64_t>(event_src[before_event]) << 9;
            checksum ^= static_cast<uint64_t>(event_dst[before_event]) << 25;
        }
    }

    stats_out[BASELINE_STAT_TARGETS] = num_targets;
    stats_out[BASELINE_STAT_SCANNED] = scanned_total;
    stats_out[BASELINE_STAT_SELECTED] = selected_total;
    stats_out[BASELINE_STAT_REUSED] = reused_total;
    stats_out[BASELINE_STAT_CACHE_HITS] = cache_hits;
    stats_out[BASELINE_STAT_MODEL] = model_id;
    stats_out[BASELINE_STAT_MODE] = inference_mode;
    stats_out[BASELINE_STAT_ARCH_PARAM0] = BASELINE_RTGA_TAUS;
    stats_out[BASELINE_STAT_ARCH_PARAM1] = BASELINE_RTGA_CACHE_LINES;
    stats_out[BASELINE_STAT_OUTPUT_WORDS] = static_cast<uint64_t>(num_targets) * BASELINE_DIM;
    stats_out[BASELINE_STAT_CHECKSUM] = checksum;
    stats_out[BASELINE_STAT_INVALID_INPUTS] = invalid_inputs;
    stats_out[BASELINE_STAT_FLAGS] = reproduction_flags;
    stats_out[BASELINE_STAT_FANOUT] = fanout;
    stats_out[BASELINE_STAT_DEPTH] = depth;
    stats_out[BASELINE_STAT_VERSION] = 1;
}
