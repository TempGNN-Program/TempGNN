#include "tempgnn_hls.hpp"

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

static bool check_stats(
    const std::string &name,
    const uint64_t actual[TEMPGNN_STAT_COUNT],
    const std::array<uint64_t, TEMPGNN_STAT_COUNT> &expected) {
    bool ok = true;
    for (int idx = 0; idx < TEMPGNN_STAT_COUNT; ++idx) {
        if (actual[idx] != expected[idx]) {
            std::cerr << name << " mismatch at stat[" << idx << "]: actual=" << actual[idx]
                      << " expected=" << expected[idx] << "\n";
            ok = false;
        }
    }
    return ok;
}

int main() {
    const uint32_t num_events = 24;
    const uint32_t num_vertices = 8;
    const uint32_t num_targets = 16;
    const uint32_t fanout = 4;
    const uint32_t depth = 2;
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

    uint64_t stats[TEMPGNN_STAT_COUNT] = {};
    bool ok = true;

    tempgnn_kernel(
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
        stats);
    print_stats("TempGNN", stats);
    ok &= check_stats(
        "TempGNN",
        stats,
        {16, 256, 69, 3710, 16000, 3000, 789, 232, 37536, 187, 0,
         10713527092011523068ull, 1, 1, 8, 0});

    tempgnn_kernel(
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
        stats);
    print_stats("TempGNN WO/OATS", stats);
    ok &= check_stats(
        "TempGNN WO/OATS",
        stats,
        {16, 256, 256, 1000, 16000, 3000, 789, 232, 139264, 0, 0,
         11736059554962654645ull, 1, 0, 8, 0});

    tempgnn_kernel(
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
        stats);
    print_stats("TempGNN WO/DDTC", stats);
    ok &= check_stats(
        "TempGNN WO/DDTC",
        stats,
        {16, 256, 256, 1000, 16000, 3000, 789, 714, 139264, 187, 0,
         10713527092011523068ull, 0, 1, 8, 0});

    if (!ok) {
        std::cerr << "TempGNN HLS C-sim test failed\n";
        return 1;
    }
    std::cout << "TempGNN HLS C-sim test passed\n";
    return 0;
}
