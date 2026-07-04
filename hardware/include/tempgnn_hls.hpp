#ifndef TEMPGNN_HLS_HPP
#define TEMPGNN_HLS_HPP

#include <cstdint>

#ifndef TEMPGNN_MAX_EVENTS
#define TEMPGNN_MAX_EVENTS 8192
#endif

#ifndef TEMPGNN_MAX_VERTICES
#define TEMPGNN_MAX_VERTICES 16384
#endif

#define TEMPGNN_MAX_VERTEX_OFFSETS (TEMPGNN_MAX_VERTICES + 1)

#ifndef TEMPGNN_MAX_HISTORY
#define TEMPGNN_MAX_HISTORY (TEMPGNN_MAX_EVENTS * 2)
#endif

#ifndef TEMPGNN_MAX_DEGREE_SCAN
#define TEMPGNN_MAX_DEGREE_SCAN 4096
#endif

#ifndef TEMPGNN_MAX_TARGETS
#define TEMPGNN_MAX_TARGETS 1024
#endif

#ifndef TEMPGNN_MAX_FANOUT
#define TEMPGNN_MAX_FANOUT 20
#endif

#ifndef TEMPGNN_MAX_DEPTH
#define TEMPGNN_MAX_DEPTH 2
#endif

#ifndef TEMPGNN_MAX_QUEUE
#define TEMPGNN_MAX_QUEUE 4096
#endif

#ifndef TEMPGNN_MAX_LOCAL_PACKETS
#define TEMPGNN_MAX_LOCAL_PACKETS 4096
#endif

#ifndef TEMPGNN_HASH_BUCKETS
#define TEMPGNN_HASH_BUCKETS 2048
#endif

#ifndef TEMPGNN_HASH_WAYS
#define TEMPGNN_HASH_WAYS 4
#endif

#define TEMPGNN_HASH_SIZE (TEMPGNN_HASH_BUCKETS * TEMPGNN_HASH_WAYS)

#define TEMPGNN_PACKET_LATENCY_CYCLES 12
#define TEMPGNN_UPDATE_LATENCY_CYCLES 80
#define TEMPGNN_PACKET_WORKERS 64
#define TEMPGNN_UPDATE_WORKERS 8
#define TEMPGNN_STATE_BYTES 512
#define TEMPGNN_METADATA_BYTES 32
#define TEMPGNN_INITIAL_EVENT 0xffffffffu

#ifndef TEMPGNN_FWD_DIM
#define TEMPGNN_FWD_DIM 8
#endif

#ifndef TEMPGNN_FWD_MAX_DEPTH
#define TEMPGNN_FWD_MAX_DEPTH 8
#endif

#define TEMPGNN_FWD_SCALE 1024
#define TEMPGNN_MAX_MEMORY_WORDS (TEMPGNN_MAX_VERTICES * TEMPGNN_FWD_DIM)
#define TEMPGNN_MAX_EVENT_FEATURE_WORDS (TEMPGNN_MAX_EVENTS * TEMPGNN_FWD_DIM)
#define TEMPGNN_MAX_TARGET_EMBED_WORDS (TEMPGNN_MAX_TARGETS * TEMPGNN_FWD_DIM)

enum TempGNNStatIndex {
    TEMPGNN_STAT_TARGETS = 0,
    TEMPGNN_STAT_TOTAL_PACKETS = 1,
    TEMPGNN_STAT_UNIQUE_PACKETS = 2,
    TEMPGNN_STAT_PACKET_REUSE_X1000 = 3,
    TEMPGNN_STAT_AVG_PACKETS_X1000 = 4,
    TEMPGNN_STAT_AVG_CRITICAL_X1000 = 5,
    TEMPGNN_STAT_AVG_BPR_X1000 = 6,
    TEMPGNN_STAT_CYCLES = 7,
    TEMPGNN_STAT_MEMORY_BYTES = 8,
    TEMPGNN_STAT_HASH_HITS = 9,
    TEMPGNN_STAT_OVERFLOWS = 10,
    TEMPGNN_STAT_CHECKSUM = 11,
    TEMPGNN_STAT_ENABLE_DDTC = 12,
    TEMPGNN_STAT_ENABLE_OATS = 13,
    TEMPGNN_STAT_TDP_ENTRIES = 14,
    TEMPGNN_STAT_COUNT = 16
};

extern "C" void tempgnn_kernel(
    const uint32_t *event_src,
    const uint32_t *event_dst,
    const uint32_t *event_ts,
    uint32_t num_events,
    const uint32_t *vertex_offsets,
    const uint32_t *history_event_idx,
    const uint32_t *history_peer,
    uint32_t num_vertices,
    const uint32_t *target_vertex,
    const uint32_t *target_event_idx,
    uint32_t num_targets,
    uint32_t fanout,
    uint32_t depth,
    uint32_t tdp_entries,
    uint32_t enable_ddtc,
    uint32_t enable_oats,
    uint64_t *stats_out);

extern "C" void tempgnn_forward_kernel(
    const uint32_t *event_src,
    const uint32_t *event_dst,
    const uint32_t *event_ts,
    uint32_t num_events,
    const uint32_t *vertex_offsets,
    const uint32_t *history_event_idx,
    const uint32_t *history_peer,
    uint32_t num_vertices,
    const uint32_t *target_vertex,
    const uint32_t *target_event_idx,
    uint32_t num_targets,
    uint32_t fanout,
    uint32_t depth,
    uint32_t tdp_entries,
    uint32_t enable_ddtc,
    uint32_t enable_oats,
    const int16_t *initial_memory,
    const int16_t *event_features,
    const int16_t *weight_self,
    const int16_t *weight_peer,
    const int16_t *weight_event,
    const int16_t *bias,
    int16_t *embedding_out,
    uint64_t *stats_out);

#endif
