#include "baseline_hls.hpp"

struct MatgNeighbor {
    uint32_t event_idx;
    uint32_t peer;
    int32_t score;
};

static int32_t matg_time_score(uint32_t delta) {
#pragma HLS INLINE
    // Paper mechanism: a time-encoding LUT followed by a lightweight,
    // timestamp-only attention logit. These deterministic Q10 entries are
    // stand-ins for the paper's learned values.
    static const int16_t time_lut[128] = {
        2048, 2036, 2024, 2012, 2000, 1988, 1976, 1964,
        1952, 1940, 1928, 1916, 1904, 1892, 1880, 1868,
        1856, 1844, 1832, 1820, 1808, 1796, 1784, 1772,
        1760, 1748, 1736, 1724, 1712, 1700, 1688, 1676,
        1664, 1652, 1640, 1628, 1616, 1604, 1592, 1580,
        1568, 1556, 1544, 1532, 1520, 1508, 1496, 1484,
        1472, 1460, 1448, 1436, 1424, 1412, 1400, 1388,
        1376, 1364, 1352, 1340, 1328, 1316, 1304, 1292,
        1280, 1268, 1256, 1244, 1232, 1220, 1208, 1196,
        1184, 1172, 1160, 1148, 1136, 1124, 1112, 1100,
        1088, 1076, 1064, 1052, 1040, 1028, 1016, 1004,
        992, 980, 968, 956, 944, 932, 920, 908,
        896, 884, 872, 860, 848, 836, 824, 812,
        800, 788, 776, 764, 752, 740, 728, 716,
        704, 692, 680, 668, 656, 644, 632, 620,
        608, 596, 584, 572, 560, 548, 536, 524,
    };
#pragma HLS BIND_STORAGE variable=time_lut type=rom_1p impl=bram
    uint32_t bucket = delta < 128u ? delta : 127u;
    return time_lut[bucket];
}

static void matg_insert_topk(
    MatgNeighbor top[BASELINE_MATG_TOPK],
    uint32_t &count,
    uint32_t budget,
    const MatgNeighbor &candidate) {
#pragma HLS INLINE off
    if (count < budget) {
        top[count] = candidate;
        ++count;
        return;
    }
    uint32_t minimum = 0;
matg_find_minimum:
    for (uint32_t idx = 1; idx < BASELINE_MATG_TOPK; ++idx) {
#pragma HLS PIPELINE II=1
        if (idx < budget && top[idx].score < top[minimum].score) {
            minimum = idx;
        }
    }
    if (candidate.score > top[minimum].score) {
        top[minimum] = candidate;
    }
}

static int16_t matg_model_update(
    uint32_t model_id,
    int16_t self,
    int16_t message,
    int16_t event_value,
    int16_t ws,
    int16_t wp,
    int16_t we,
    int16_t b) {
#pragma HLS INLINE
    int32_t linear =
        (static_cast<int32_t>(self) * ws + static_cast<int32_t>(message) * wp +
         static_cast<int32_t>(event_value) * we) /
            BASELINE_SCALE +
        b;
    switch (model_id & 3u) {
    case 0: // JODIE-style projection.
        return baseline_hard_tanh_q10(static_cast<int32_t>(self) + linear / 2);
    case 2: // TGAT-style temporal attention transform.
        return baseline_hard_tanh_q10(linear + message / 2);
    case 3: // APAN-style asynchronous mailbox merge.
        return baseline_hard_tanh_q10((static_cast<int32_t>(self) * 3 + message + linear) / 4);
    default: { // TGN-style GRU merge.
        int16_t update = baseline_hard_sigmoid_q10(linear);
        int16_t candidate = baseline_hard_tanh_q10(linear + message / 2);
        int32_t merged = (static_cast<int32_t>(BASELINE_SCALE - update) * self +
                          static_cast<int32_t>(update) * candidate) /
                         BASELINE_SCALE;
        return baseline_clamp_i16(merged);
    }
    }
}

extern "C" void matg_kernel(BASELINE_KERNEL_ARGUMENTS) {
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
    uint64_t invalid_inputs = 0;
    uint64_t checksum = 0x4d41544700000001ull;
    int16_t local_weight_self[BASELINE_DIM];
    int16_t local_weight_peer[BASELINE_DIM];
    int16_t local_weight_event[BASELINE_DIM];
    int16_t local_bias[BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=local_weight_self complete
#pragma HLS ARRAY_PARTITION variable=local_weight_peer complete
#pragma HLS ARRAY_PARTITION variable=local_weight_event complete
#pragma HLS ARRAY_PARTITION variable=local_bias complete
matg_load_weights:
    for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS PIPELINE II=1
        local_weight_self[dim] = weight_self[dim];
        local_weight_peer[dim] = weight_peer[dim];
        local_weight_event[dim] = weight_event[dim];
        local_bias[dim] = bias[dim];
    }
    uint32_t scan_budget = baseline_min_u32(fanout, BASELINE_MAX_FANOUT);
    uint32_t prune_budget = 4;
    if ((model_id & 3u) == 0u) {
        prune_budget = 2;
    } else if ((model_id & 3u) == 2u) {
        prune_budget = 6;
    }
    prune_budget = baseline_min_u32(prune_budget, BASELINE_MATG_TOPK);

matg_targets:
    for (uint32_t target = 0; target < num_targets; ++target) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=1024
        uint32_t vertex = target_vertex[target];
        uint32_t before_event = target_event_idx[target];
        if (vertex >= num_vertices || before_event > num_events) {
            ++invalid_inputs;
            continue;
        }
        uint32_t target_time = before_event < num_events ? event_ts[before_event] : num_events;
        uint32_t begin = vertex_offsets[vertex];
        uint32_t end = vertex_offsets[vertex + 1u];
        MatgNeighbor top[BASELINE_MATG_TOPK];
#pragma HLS ARRAY_PARTITION variable=top complete
        uint32_t top_count = 0;
        uint32_t valid_candidates = 0;

    matg_scan_recent:
        for (uint32_t step = 0; step < BASELINE_MAX_DEGREE_SCAN; ++step) {
#pragma HLS PIPELINE II=1
            if (valid_candidates >= scan_budget || step >= end - begin) {
                break;
            }
            uint32_t pos = end - 1u - step;
            uint32_t event_idx = history_event_idx[pos];
            uint32_t peer = history_peer[pos];
            ++scanned_total;
            if (event_idx >= before_event || event_idx >= num_events || peer >= num_vertices) {
                continue;
            }
            ++valid_candidates;
            uint32_t timestamp = event_ts[event_idx];
            MatgNeighbor candidate;
            candidate.event_idx = event_idx;
            candidate.peer = peer;
            candidate.score = matg_time_score(target_time - timestamp);
            matg_insert_topk(top, top_count, prune_budget, candidate);
        }

        int32_t weighted_memory[BASELINE_DIM];
        int32_t weighted_event[BASELINE_DIM];
#pragma HLS ARRAY_PARTITION variable=weighted_memory complete
#pragma HLS ARRAY_PARTITION variable=weighted_event complete
    matg_clear_accumulators:
        for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
            weighted_memory[dim] = 0;
            weighted_event[dim] = 0;
        }
        int32_t score_sum = 0;
    matg_aggregate_neighbors:
        for (uint32_t slot = 0; slot < BASELINE_MATG_TOPK; ++slot) {
            if (slot >= top_count) {
                break;
            }
            int32_t weight = top[slot].score > 0 ? top[slot].score : 1;
            score_sum += weight;
        matg_aggregate_dims:
            for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
                weighted_memory[dim] +=
                    static_cast<int32_t>(initial_memory[top[slot].peer * BASELINE_DIM + dim]) * weight;
                weighted_event[dim] +=
                    static_cast<int32_t>(event_features[top[slot].event_idx * BASELINE_DIM + dim]) * weight;
            }
        }
        if (score_sum == 0) {
            score_sum = 1;
        }
        selected_total += top_count;

    matg_output_dims:
        for (uint32_t dim = 0; dim < BASELINE_DIM; ++dim) {
#pragma HLS UNROLL
            int16_t self = initial_memory[vertex * BASELINE_DIM + dim];
            int16_t message = baseline_clamp_i16(weighted_memory[dim] / score_sum);
            int16_t event_value = baseline_clamp_i16(weighted_event[dim] / score_sum);
            int16_t output = matg_model_update(
                model_id,
                self,
                message,
                event_value,
                local_weight_self[dim],
                local_weight_peer[dim],
                local_weight_event[dim],
                local_bias[dim]);
            embedding_out[target * BASELINE_DIM + dim] = output;
            checksum = baseline_mix_checksum(checksum, output, target * BASELINE_DIM + dim);
        }

        // Keep both endpoint streams observable, matching MATG's edge parser.
        if (before_event < num_events) {
            checksum ^= static_cast<uint64_t>(event_src[before_event]) << 1;
            checksum ^= static_cast<uint64_t>(event_dst[before_event]) << 17;
        }
    }

    stats_out[BASELINE_STAT_TARGETS] = num_targets;
    stats_out[BASELINE_STAT_SCANNED] = scanned_total;
    stats_out[BASELINE_STAT_SELECTED] = selected_total;
    stats_out[BASELINE_STAT_MODEL] = model_id;
    stats_out[BASELINE_STAT_MODE] = inference_mode;
    stats_out[BASELINE_STAT_ARCH_PARAM0] = 128; // Time LUT entries.
    stats_out[BASELINE_STAT_ARCH_PARAM1] = prune_budget;
    stats_out[BASELINE_STAT_OUTPUT_WORDS] = static_cast<uint64_t>(num_targets) * BASELINE_DIM;
    stats_out[BASELINE_STAT_CHECKSUM] = checksum;
    stats_out[BASELINE_STAT_INVALID_INPUTS] = invalid_inputs;
    stats_out[BASELINE_STAT_FLAGS] = reproduction_flags;
    stats_out[BASELINE_STAT_FANOUT] = fanout;
    stats_out[BASELINE_STAT_DEPTH] = depth;
    stats_out[BASELINE_STAT_VERSION] = 1;
}
