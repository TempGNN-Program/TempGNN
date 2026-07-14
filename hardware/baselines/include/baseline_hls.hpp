#ifndef TEMPGNN_BASELINE_HLS_HPP
#define TEMPGNN_BASELINE_HLS_HPP

#include <cstdint>

#define BASELINE_DIM 8
#define BASELINE_SCALE 1024
#define BASELINE_MAX_FANOUT 20
#define BASELINE_MAX_DEGREE_SCAN 64
#define BASELINE_MATG_TOPK 6
#define BASELINE_VITE_TOPK 4
#define BASELINE_RTGA_TAUS 8
#define BASELINE_RTGA_CACHE_LINES 16
#define BASELINE_STAT_COUNT 16
#define BASELINE_INITIAL_EVENT 0xffffffffu

enum BaselineStatIndex {
    BASELINE_STAT_TARGETS = 0,
    BASELINE_STAT_SCANNED = 1,
    BASELINE_STAT_SELECTED = 2,
    BASELINE_STAT_REUSED = 3,
    BASELINE_STAT_CACHE_HITS = 4,
    BASELINE_STAT_MODEL = 5,
    BASELINE_STAT_MODE = 6,
    BASELINE_STAT_ARCH_PARAM0 = 7,
    BASELINE_STAT_ARCH_PARAM1 = 8,
    BASELINE_STAT_OUTPUT_WORDS = 9,
    BASELINE_STAT_CHECKSUM = 10,
    BASELINE_STAT_INVALID_INPUTS = 11,
    BASELINE_STAT_FLAGS = 12,
    BASELINE_STAT_FANOUT = 13,
    BASELINE_STAT_DEPTH = 14,
    BASELINE_STAT_VERSION = 15
};

// The three paper-based kernels deliberately use the same argument layout as
// tempgnn_forward_kernel.  Arguments 13--15 carry model, mode, and reproduction
// flags for the baseline kernels.  A shared host can therefore hold the graph,
// launch, and timing conditions constant without sharing implementation logic.
#define BASELINE_KERNEL_ARGUMENTS                                                        \
    const uint32_t *event_src,                                                          \
    const uint32_t *event_dst,                                                          \
    const uint32_t *event_ts,                                                           \
    uint32_t num_events,                                                                \
    const uint32_t *vertex_offsets,                                                     \
    const uint32_t *history_event_idx,                                                  \
    const uint32_t *history_peer,                                                       \
    uint32_t num_vertices,                                                              \
    const uint32_t *target_vertex,                                                      \
    const uint32_t *target_event_idx,                                                   \
    uint32_t num_targets,                                                               \
    uint32_t fanout,                                                                    \
    uint32_t depth,                                                                     \
    uint32_t model_id,                                                                  \
    uint32_t inference_mode,                                                            \
    uint32_t reproduction_flags,                                                        \
    const int16_t *initial_memory,                                                      \
    const int16_t *event_features,                                                      \
    const int16_t *weight_self,                                                         \
    const int16_t *weight_peer,                                                         \
    const int16_t *weight_event,                                                        \
    const int16_t *bias,                                                                \
    int16_t *embedding_out,                                                             \
    uint64_t *stats_out

extern "C" void matg_kernel(BASELINE_KERNEL_ARGUMENTS);
extern "C" void vitegnn_kernel(BASELINE_KERNEL_ARGUMENTS);
extern "C" void rtga_kernel(BASELINE_KERNEL_ARGUMENTS);

static int16_t baseline_clamp_i16(int32_t value) {
#pragma HLS INLINE
    if (value > 32767) {
        return 32767;
    }
    if (value < -32768) {
        return -32768;
    }
    return static_cast<int16_t>(value);
}

static int16_t baseline_hard_tanh_q10(int32_t value) {
#pragma HLS INLINE
    if (value > BASELINE_SCALE) {
        return BASELINE_SCALE;
    }
    if (value < -BASELINE_SCALE) {
        return -BASELINE_SCALE;
    }
    return static_cast<int16_t>(value);
}

static int16_t baseline_hard_sigmoid_q10(int32_t value) {
#pragma HLS INLINE
    int32_t result = (BASELINE_SCALE / 2) + value / 4;
    if (result < 0) {
        result = 0;
    }
    if (result > BASELINE_SCALE) {
        result = BASELINE_SCALE;
    }
    return static_cast<int16_t>(result);
}

static uint32_t baseline_min_u32(uint32_t lhs, uint32_t rhs) {
#pragma HLS INLINE
    return lhs < rhs ? lhs : rhs;
}

static uint64_t baseline_mix_checksum(uint64_t checksum, int32_t value, uint32_t index) {
#pragma HLS INLINE
    uint64_t word = static_cast<uint32_t>(value) ^ (static_cast<uint64_t>(index) << 32);
    checksum ^= word + 0x9e3779b97f4a7c15ull + (checksum << 6) + (checksum >> 2);
    return checksum;
}

static void baseline_clear_stats(uint64_t *stats_out) {
baseline_clear_stats_loop:
    for (uint32_t idx = 0; idx < BASELINE_STAT_COUNT; ++idx) {
#pragma HLS PIPELINE II=1
        stats_out[idx] = 0;
    }
}

#endif
