#include "tempgnn_hls.hpp"

#include <algorithm>
#include <array>
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <string>

static void print_stats(const std::string &name, const uint64_t stats[TEMPGNN_STAT_COUNT]) {
    std::cout << name << "\n";
    for (int idx = 0; idx < TEMPGNN_STAT_COUNT; ++idx) {
        std::cout << "  stat[" << std::setw(2) << idx << "] = " << stats[idx] << "\n";
    }
}

static void print_embedding_row(const std::string &name, const int16_t *embeddings, uint32_t row) {
    std::cout << name << "[" << row << "]";
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
        std::cout << " " << embeddings[row * TEMPGNN_FWD_DIM + dim];
    }
    std::cout << "\n";
}

static bool embeddings_equal(
    const int16_t *lhs,
    const int16_t *rhs,
    uint32_t rows) {
    for (uint32_t row = 0; row < rows; ++row) {
        for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
            uint32_t idx = row * TEMPGNN_FWD_DIM + dim;
            if (lhs[idx] != rhs[idx]) {
                std::cerr << "embedding mismatch at row=" << row << " dim=" << dim
                          << " lhs=" << lhs[idx] << " rhs=" << rhs[idx] << "\n";
                return false;
            }
        }
    }
    return true;
}

static bool check_forward_stats(
    const std::string &name,
    const uint64_t stats[TEMPGNN_STAT_COUNT],
    uint32_t expected_targets,
    bool oats_enabled) {
    bool ok = true;
    if (stats[TEMPGNN_STAT_TARGETS] != expected_targets) {
        std::cerr << name << " target count mismatch\n";
        ok = false;
    }
    if (stats[TEMPGNN_STAT_OVERFLOWS] != 0) {
        std::cerr << name << " overflow count is " << stats[TEMPGNN_STAT_OVERFLOWS] << "\n";
        ok = false;
    }
    if (stats[TEMPGNN_STAT_TOTAL_PACKETS] == 0 || stats[TEMPGNN_STAT_UNIQUE_PACKETS] == 0) {
        std::cerr << name << " did not materialize packets\n";
        ok = false;
    }
    if (oats_enabled && stats[TEMPGNN_STAT_UNIQUE_PACKETS] > stats[TEMPGNN_STAT_TOTAL_PACKETS]) {
        std::cerr << name << " unique packets exceeds total packets\n";
        ok = false;
    }
    if (!oats_enabled && stats[TEMPGNN_STAT_UNIQUE_PACKETS] != stats[TEMPGNN_STAT_TOTAL_PACKETS]) {
        std::cerr << name << " no-OATS unique packets should equal total packets\n";
        ok = false;
    }
    return ok;
}

int main() {
    const uint32_t num_events = 24;
    const uint32_t num_vertices = 8;
    const uint32_t num_targets = 16;
    const uint32_t fanout = 4;
    const uint32_t depth = TEMPGNN_FWD_MAX_DEPTH;
    const uint32_t tdp_entries = 8;

    static const uint32_t event_src[TEMPGNN_MAX_EVENTS] = {
        0, 1, 0, 2, 1, 3, 0, 4, 2, 1, 5, 0,
        6, 3, 2, 1, 4, 0, 5, 2, 6, 7, 3, 4,
    };
    static const uint32_t event_dst[TEMPGNN_MAX_EVENTS] = {
        1, 2, 2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
        7, 7, 7, 7, 7, 3, 7, 4, 1, 0, 5, 6,
    };
    static const uint32_t event_ts[TEMPGNN_MAX_EVENTS] = {
        0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11,
        12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
    };
    static const uint32_t vertex_offsets[TEMPGNN_MAX_VERTEX_OFFSETS] = {
        0, 6, 12, 18, 24, 30, 36, 41, 48,
    };
    static const uint32_t history_event_idx[TEMPGNN_MAX_HISTORY] = {
        0, 2, 6, 11, 17, 21, 0, 1, 4, 9, 15, 20,
        1, 2, 3, 8, 14, 19, 3, 4, 5, 13, 17, 22,
        5, 6, 7, 16, 19, 23, 7, 8, 9, 10, 18, 22,
        10, 11, 12, 20, 23, 12, 13, 14, 15, 16, 18, 21,
    };
    static const uint32_t history_peer[TEMPGNN_MAX_HISTORY] = {
        1, 2, 4, 6, 3, 7, 0, 2, 3, 5, 7, 6,
        1, 0, 3, 5, 7, 4, 2, 1, 4, 7, 0, 5,
        3, 0, 5, 7, 2, 6, 4, 2, 1, 6, 7, 3,
        5, 0, 7, 1, 4, 6, 3, 2, 1, 4, 5, 0,
    };
    static const uint32_t target_vertex[TEMPGNN_MAX_TARGETS] = {
        5, 5, 6, 6, 7, 7, 7, 7, 7, 3, 7, 4, 1, 0, 5, 6,
    };
    static const uint32_t target_event_idx[TEMPGNN_MAX_TARGETS] = {
        8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23,
    };

    static int16_t initial_memory[TEMPGNN_MAX_MEMORY_WORDS] = {};
    static int16_t event_features[TEMPGNN_MAX_EVENT_FEATURE_WORDS] = {};
    static int16_t weight_self[TEMPGNN_FWD_DIM] = {};
    static int16_t weight_peer[TEMPGNN_FWD_DIM] = {};
    static int16_t weight_event[TEMPGNN_FWD_DIM] = {};
    static int16_t bias[TEMPGNN_FWD_DIM] = {};
    static int16_t embeddings_oats[TEMPGNN_MAX_TARGET_EMBED_WORDS] = {};
    static int16_t embeddings_no_oats[TEMPGNN_MAX_TARGET_EMBED_WORDS] = {};
    static int16_t embeddings_no_ddtc[TEMPGNN_MAX_TARGET_EMBED_WORDS] = {};

    for (uint32_t vertex = 0; vertex < num_vertices; ++vertex) {
        for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
            initial_memory[vertex * TEMPGNN_FWD_DIM + dim] = (int16_t)(((vertex + 3u) * (dim + 5u) * 17u) % 257u - 128);
        }
    }
    for (uint32_t event_idx = 0; event_idx < num_events; ++event_idx) {
        for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
            event_features[event_idx * TEMPGNN_FWD_DIM + dim] = (int16_t)(((event_idx + 1u) * (dim + 7u) * 23u) % 1024u - 512);
        }
    }
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
        weight_self[dim] = 640;
        weight_peer[dim] = 320;
        weight_event[dim] = (int16_t)(96 + dim * 8);
        bias[dim] = (int16_t)((int32_t)dim * 3 - 9);
    }

    uint64_t stats_oats[TEMPGNN_STAT_COUNT] = {};
    uint64_t stats_no_oats[TEMPGNN_STAT_COUNT] = {};
    uint64_t stats_no_ddtc[TEMPGNN_STAT_COUNT] = {};

    tempgnn_forward_kernel(
        event_src,
        event_dst,
        event_ts,
        num_events,
        vertex_offsets,
        history_event_idx,
        history_peer,
        num_vertices,
        target_vertex,
        target_event_idx,
        num_targets,
        fanout,
        depth,
        tdp_entries,
        1,
        1,
        initial_memory,
        event_features,
        weight_self,
        weight_peer,
        weight_event,
        bias,
        embeddings_oats,
        stats_oats);

    tempgnn_forward_kernel(
        event_src,
        event_dst,
        event_ts,
        num_events,
        vertex_offsets,
        history_event_idx,
        history_peer,
        num_vertices,
        target_vertex,
        target_event_idx,
        num_targets,
        fanout,
        depth,
        tdp_entries,
        1,
        0,
        initial_memory,
        event_features,
        weight_self,
        weight_peer,
        weight_event,
        bias,
        embeddings_no_oats,
        stats_no_oats);

    tempgnn_forward_kernel(
        event_src,
        event_dst,
        event_ts,
        num_events,
        vertex_offsets,
        history_event_idx,
        history_peer,
        num_vertices,
        target_vertex,
        target_event_idx,
        num_targets,
        fanout,
        depth,
        tdp_entries,
        0,
        1,
        initial_memory,
        event_features,
        weight_self,
        weight_peer,
        weight_event,
        bias,
        embeddings_no_ddtc,
        stats_no_ddtc);

    print_stats("TempGNN forward", stats_oats);
    print_embedding_row("embedding", embeddings_oats, 0);
    print_stats("TempGNN forward WO/OATS", stats_no_oats);
    print_stats("TempGNN forward WO/DDTC", stats_no_ddtc);

    bool ok = true;
    ok &= check_forward_stats("TempGNN forward", stats_oats, num_targets, true);
    ok &= check_forward_stats("TempGNN forward WO/OATS", stats_no_oats, num_targets, false);
    ok &= check_forward_stats("TempGNN forward WO/DDTC", stats_no_ddtc, num_targets, true);
    if (stats_oats[TEMPGNN_STAT_MEMORY_BYTES] > stats_no_oats[TEMPGNN_STAT_MEMORY_BYTES]) {
        std::cerr << "OATS memory should not exceed no-OATS memory\n";
        ok = false;
    }
    ok &= embeddings_equal(embeddings_oats, embeddings_no_oats, num_targets);
    ok &= embeddings_equal(embeddings_oats, embeddings_no_ddtc, num_targets);

    if (!ok) {
        std::cerr << "TempGNN forward HLS C-sim test failed\n";
        return 1;
    }
    std::cout << "TempGNN forward HLS C-sim test passed\n";
    return 0;
}
