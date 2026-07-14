#include "baseline_hls.hpp"

struct ViteNeighbor {
    uint32_t event_idx;
    uint32_t peer;
};

static bool vite_contains_peer(
    const ViteNeighbor neighbors[BASELINE_VITE_TOPK], uint32_t count, uint32_t peer) {
#pragma HLS INLINE
    bool found = false;
vite_duplicate_scan:
    for (uint32_t idx = 0; idx < BASELINE_VITE_TOPK; ++idx) {
#pragma HLS UNROLL
        if (idx < count && neighbors[idx].peer == peer) {
            found = true;
        }
    }
    return found;
}

static int16_t vite_model_update(
    uint32_t model_id,
    int16_t self,
    int16_t aggregate,
    int16_t event_value,
    int16_t ws,
    int16_t wp,
    int16_t we,
    int16_t b) {
#pragma HLS INLINE
    int32_t projection =
        (static_cast<int32_t>(self) * ws + static_cast<int32_t>(aggregate) * wp +
         static_cast<int32_t>(event_value) * we) /
            BASELINE_SCALE +
        b;
    if ((model_id & 3u) == 0u) {
        // JODIE: project the current memory along the interaction direction.
        return baseline_hard_tanh_q10(static_cast<int32_t>(self) + projection / 2);
    }
    if ((model_id & 3u) == 2u) {
        // TGAT: transformed temporal-neighbor aggregation.
        return baseline_hard_tanh_q10(projection + aggregate);
    }
    if ((model_id & 3u) == 3u) {
        // APAN: asynchronous propagation mailbox update.
        return baseline_hard_tanh_q10((static_cast<int32_t>(self) + aggregate * 2 + projection) / 3);
    }
    // TGN: compact fixed-point GRU update.
    int16_t reset = baseline_hard_sigmoid_q10(projection - aggregate / 2);
    int16_t update = baseline_hard_sigmoid_q10(projection + aggregate / 2);
    int32_t candidate_input = projection +
                              (static_cast<int32_t>(reset) * self) / BASELINE_SCALE;
    int16_t candidate = baseline_hard_tanh_q10(candidate_input);
    int32_t merged = (static_cast<int32_t>(BASELINE_SCALE - update) * self +
                      static_cast<int32_t>(update) * candidate) /
                     BASELINE_SCALE;
    return baseline_clamp_i16(merged);
}

extern "C" void vitegnn_kernel(BASELINE_KERNEL_ARGUMENTS) {
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
    uint64_t scanned_total = 0;
    uint64_t selected_total = 0;
    uint64_t duplicate_total = 0;
    uint64_t invalid_inputs = 0;
    uint64_t checksum = 0x56495445474e4e01ull;
    uint32_t scan_budget = baseline_min_u32(fanout, BASELINE_MAX_FANOUT);
    int16_t local_weight_self[BASELINE_DIM];
    int16_t local_weight_peer[BASELINE_DIM];
    int16_t local_weight_event[BASELINE_DIM];
    int16_t local_bias[BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=local_weight_self complete
#pragma HLS ARRAY_PARTITION variable=local_weight_peer complete
#pragma HLS ARRAY_PARTITION variable=local_weight_event complete
#pragma HLS ARRAY_PARTITION variable=local_bias complete
vite_load_weights:
    for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS PIPELINE II=1
        local_weight_self[dim] = weight_self[dim];
        local_weight_peer[dim] = weight_peer[dim];
        local_weight_event[dim] = weight_event[dim];
        local_bias[dim] = bias[dim];
    }

vite_targets:
    for (uint32_t target = 0; target < num_targets; ++target) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
        uint32_t vertex = target_vertex[target];
        uint32_t before_event = target_event_idx[target];
        if (vertex >= num_vertices || before_event > num_events) {
            ++invalid_inputs;
            continue;
        }

        // The bounded thpt-inspired selector serves the cached embedding. It
        // does not model ViTeGNN's separate maintenance data path.
        if ((inference_mode % 3u) == 2u) {
        vite_cached_embedding:
            for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
                int16_t output = initial_memory[vertex * BASELINE_DIM + dim];
                embedding_out[target * BASELINE_DIM + dim] = output;
                checksum = baseline_mix_checksum(checksum, output, target * BASELINE_DIM + dim);
            }
            selected_total += 1;
            continue;
        }

        uint32_t begin = vertex_offsets[vertex];
        uint32_t end = vertex_offsets[vertex + 1u];
        ViteNeighbor compacted[BASELINE_VITE_TOPK];
#pragma HLS ARRAY_PARTITION variable=compacted complete
        uint32_t recent_event_idx[BASELINE_MAX_DEGREE_SCAN];
        uint32_t recent_peer[BASELINE_MAX_DEGREE_SCAN];
#pragma HLS BIND_STORAGE variable=recent_event_idx type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=recent_peer type=ram_1p impl=bram
        uint32_t compact_count = 0;
        uint32_t valid_candidates = 0;
        uint32_t recent_count = baseline_min_u32(end - begin, BASELINE_MAX_DEGREE_SCAN);

        // Register the HBM reads before duplicate detection. This preserves
        // newest-first semantics while removing the AXI-read/comparator path
        // from a single HLS cycle.
    vite_load_recent:
        for (uint32_t step = 0; step < BASELINE_MAX_DEGREE_SCAN; ++step) {
#pragma HLS PIPELINE II=1
            if (step >= recent_count) {
                break;
            }
            uint32_t pos = end - 1u - step;
            recent_event_idx[step] = history_event_idx[pos];
            recent_peer[step] = history_peer[pos];
        }

        // Reproduces the shift/scan/compact behavior of the paper's NUU:
        // newest entries are kept, invalid and duplicate peers are removed.
    vite_neighbor_update_unit:
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
            if (vite_contains_peer(compacted, compact_count, peer)) {
                ++duplicate_total;
                continue;
            }
            if (compact_count < BASELINE_VITE_TOPK) {
                compacted[compact_count].event_idx = event_idx;
                compacted[compact_count].peer = peer;
                ++compact_count;
            }
        }
        selected_total += compact_count;

        int32_t aggregate[BASELINE_DIM];
        int32_t event_aggregate[BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=aggregate complete
#pragma HLS ARRAY_PARTITION variable=event_aggregate complete
    vite_clear_aggregate:
        for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
            aggregate[dim] = 0;
            event_aggregate[dim] = 0;
        }

    vite_attention_aggregate:
        for (uint32_t slot = 0; slot < BASELINE_VITE_TOPK; ++slot) {
#pragma HLS PIPELINE II=1
            if (slot >= compact_count) {
                break;
            }
            uint32_t event_idx = compacted[slot].event_idx;
            uint32_t delta = before_event < num_events ? event_ts[before_event] - event_ts[event_idx] : 0;
            int32_t attention = 256 + static_cast<int32_t>(127u - baseline_min_u32(delta, 127u));
        vite_attention_dims:
            for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
                aggregate[dim] +=
                    static_cast<int32_t>(initial_memory[compacted[slot].peer * BASELINE_DIM + dim]) * attention;
                event_aggregate[dim] +=
                    static_cast<int32_t>(event_features[event_idx * BASELINE_DIM + dim]) * attention;
            }
        }
        int32_t divisor = compact_count == 0 ? 1 : static_cast<int32_t>(compact_count) * 320;

    vite_compute_unit:
        for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
            int16_t self = initial_memory[vertex * BASELINE_DIM + dim];
            int16_t neighbor_value = baseline_clamp_i16(aggregate[dim] / divisor);
            int16_t event_value = baseline_clamp_i16(event_aggregate[dim] / divisor);
            int16_t output = vite_model_update(
                model_id,
                self,
                neighbor_value,
                event_value,
                local_weight_self[dim],
                local_weight_peer[dim],
                local_weight_event[dim],
                local_bias[dim]);
            embedding_out[target * BASELINE_DIM + dim] = output;
            checksum = baseline_mix_checksum(checksum, output, target * BASELINE_DIM + dim);
        }

        if (before_event < num_events) {
            checksum ^= static_cast<uint64_t>(event_src[before_event]) << 5;
            checksum ^= static_cast<uint64_t>(event_dst[before_event]) << 21;
        }
    }

    stats_out[BASELINE_STAT_TARGETS] = num_targets;
    stats_out[BASELINE_STAT_SCANNED] = scanned_total;
    stats_out[BASELINE_STAT_SELECTED] = selected_total;
    stats_out[BASELINE_STAT_REUSED] = duplicate_total;
    stats_out[BASELINE_STAT_MODEL] = model_id;
    stats_out[BASELINE_STAT_MODE] = inference_mode;
    stats_out[BASELINE_STAT_ARCH_PARAM0] = BASELINE_VITE_TOPK;
    stats_out[BASELINE_STAT_ARCH_PARAM1] = 1; // One packaged kernel compute unit.
    stats_out[BASELINE_STAT_OUTPUT_WORDS] = static_cast<uint64_t>(num_targets) * BASELINE_DIM;
    stats_out[BASELINE_STAT_CHECKSUM] = checksum;
    stats_out[BASELINE_STAT_INVALID_INPUTS] = invalid_inputs;
    stats_out[BASELINE_STAT_FLAGS] = reproduction_flags;
    stats_out[BASELINE_STAT_FANOUT] = fanout;
    stats_out[BASELINE_STAT_DEPTH] = depth;
    stats_out[BASELINE_STAT_VERSION] = 1;
}
