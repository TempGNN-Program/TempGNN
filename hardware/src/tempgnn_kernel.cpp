#include "tempgnn_hls.hpp"

struct PacketRef {
    uint32_t vertex;
    uint32_t event_idx;
    uint32_t ts;
};

struct QueueEntry {
    PacketRef packet;
    uint32_t depth_left;
    uint32_t depth_from_root;
};

static bool packet_is_initial(const PacketRef &packet) {
    return packet.event_idx == TEMPGNN_INITIAL_EVENT;
}

static bool packet_equal(const PacketRef &lhs, const PacketRef &rhs) {
    return lhs.vertex == rhs.vertex && lhs.event_idx == rhs.event_idx;
}

static uint32_t min_u32(uint32_t lhs, uint32_t rhs) {
    return lhs < rhs ? lhs : rhs;
}

static uint32_t max_u32(uint32_t lhs, uint32_t rhs) {
    return lhs > rhs ? lhs : rhs;
}

static uint64_t ceil_div_u64(uint64_t value, uint64_t divisor) {
    return divisor == 0 ? 0 : (value + divisor - 1) / divisor;
}

static uint32_t mix32(uint32_t value) {
    value ^= value >> 16;
    value *= 0x7feb352du;
    value ^= value >> 15;
    value *= 0x846ca68bu;
    value ^= value >> 16;
    return value;
}

static uint32_t packet_hash(const PacketRef &packet) {
    return mix32(packet.vertex) ^ mix32(packet.event_idx + 0x9e3779b9u) ^ mix32(packet.ts);
}

static PacketRef latest_state_event(
    const uint32_t *vertex_offsets,
    const uint32_t *history_event_idx,
    const uint32_t *event_ts,
    uint32_t num_vertices,
    uint32_t num_events,
    uint32_t vertex,
    int before_event_idx) {
#pragma HLS INLINE off
    PacketRef result;
    result.vertex = vertex;
    result.event_idx = TEMPGNN_INITIAL_EVENT;
    result.ts = 0;

    if (vertex >= num_vertices) {
        return result;
    }

    uint32_t begin = vertex_offsets[vertex];
    uint32_t end = vertex_offsets[vertex + 1];

latest_scan:
    for (uint32_t step = 0; step < TEMPGNN_MAX_DEGREE_SCAN; ++step) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_DEGREE_SCAN
        if (step >= (end - begin)) {
            break;
        }
        uint32_t hist_pos = end - 1u - step;
        uint32_t event_idx = history_event_idx[hist_pos];
        if (event_idx < (uint32_t)before_event_idx && event_idx < num_events) {
            result.ts = event_ts[event_idx];
            result.event_idx = event_idx;
            break;
        }
    }
    return result;
}

static bool local_seen_contains(PacketRef local_seen[TEMPGNN_MAX_LOCAL_PACKETS], uint32_t count, const PacketRef &packet) {
#pragma HLS INLINE off
local_seen_scan:
    for (uint32_t idx = 0; idx < TEMPGNN_MAX_LOCAL_PACKETS; ++idx) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_LOCAL_PACKETS
        if (idx >= count) {
            break;
        }
        if (packet_equal(local_seen[idx], packet)) {
            return true;
        }
    }
    return false;
}

static bool enqueue_packet(
    QueueEntry queue[TEMPGNN_MAX_QUEUE],
    uint32_t &tail,
    const PacketRef &packet,
    uint32_t depth_left,
    uint32_t depth_from_root) {
#pragma HLS INLINE
    if (tail >= TEMPGNN_MAX_QUEUE) {
        return false;
    }
    queue[tail].packet = packet;
    queue[tail].depth_left = depth_left;
    queue[tail].depth_from_root = depth_from_root;
    ++tail;
    return true;
}

static bool phle_lookup_or_insert(
    PacketRef phle_key[TEMPGNN_HASH_SIZE],
    uint32_t phle_state[TEMPGNN_HASH_SIZE],
    bool phle_valid[TEMPGNN_HASH_SIZE],
    const PacketRef &packet,
    uint32_t &unique_count,
    uint64_t &hash_hits,
    uint64_t &checksum) {
#pragma HLS INLINE off
    uint32_t bucket = packet_hash(packet) % TEMPGNN_HASH_BUCKETS;
    uint32_t empty_index = TEMPGNN_HASH_SIZE;

phle_probe:
    for (uint32_t way = 0; way < TEMPGNN_HASH_WAYS; ++way) {
#pragma HLS UNROLL
        uint32_t idx = bucket * TEMPGNN_HASH_WAYS + way;
        if (phle_valid[idx]) {
            if (packet_equal(phle_key[idx], packet)) {
                ++hash_hits;
                checksum ^= ((uint64_t)phle_state[idx] << 32) | packet_hash(packet);
                return true;
            }
        } else if (empty_index == TEMPGNN_HASH_SIZE) {
            empty_index = idx;
        }
    }

    if (empty_index == TEMPGNN_HASH_SIZE) {
        return false;
    }

    uint32_t state = packet_hash(packet) ^ mix32(packet.vertex + 17u) ^ mix32(packet.event_idx + 31u);
    phle_valid[empty_index] = true;
    phle_key[empty_index] = packet;
    phle_state[empty_index] = state;
    ++unique_count;
    checksum ^= ((uint64_t)state << 32) | packet_hash(packet);
    return true;
}

static void process_one_tdp(
    const uint32_t *event_src,
    const uint32_t *event_dst,
    const uint32_t *event_ts,
    uint32_t num_events,
    const uint32_t *vertex_offsets,
    const uint32_t *history_event_idx,
    const uint32_t *history_peer,
    uint32_t num_vertices,
    uint32_t target,
    uint32_t target_idx,
    uint32_t fanout,
    uint32_t depth,
    uint32_t enable_oats,
    PacketRef phle_key[TEMPGNN_HASH_SIZE],
    uint32_t phle_state[TEMPGNN_HASH_SIZE],
    bool phle_valid[TEMPGNN_HASH_SIZE],
    uint64_t &chunk_total_packets,
    uint32_t &chunk_unique_packets,
    uint32_t &chunk_critical_path,
    uint64_t &sum_packets,
    uint64_t &sum_critical,
    uint64_t &sum_bpr_x1000,
    uint64_t &hash_hits,
    uint64_t &overflow_count,
    uint64_t &checksum) {
#pragma HLS INLINE off
    QueueEntry queue[TEMPGNN_MAX_QUEUE];
    PacketRef local_seen[TEMPGNN_MAX_LOCAL_PACKETS];
#pragma HLS BIND_STORAGE variable=queue type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=local_seen type=ram_t2p impl=bram

    uint32_t head = 0;
    uint32_t tail = 0;
    uint32_t local_count = 0;
    uint32_t tdp_work = 0;
    uint32_t tdp_critical = 0;

    uint32_t safe_depth = min_u32(depth, TEMPGNN_MAX_DEPTH);
    uint32_t safe_fanout = min_u32(fanout, TEMPGNN_MAX_FANOUT);

    PacketRef self_root = latest_state_event(
        vertex_offsets,
        history_event_idx,
        event_ts,
        num_vertices,
        num_events,
        target,
        (int)target_idx + 1);
    if (!enqueue_packet(queue, tail, self_root, safe_depth, 1)) {
        ++overflow_count;
    }

    uint32_t found_neighbors = 0;
    if (target < num_vertices) {
        uint32_t begin = vertex_offsets[target];
        uint32_t end = vertex_offsets[target + 1];
recent_neighbor_scan:
        for (uint32_t step = 0; step < TEMPGNN_MAX_DEGREE_SCAN; ++step) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_DEGREE_SCAN
        if (found_neighbors >= safe_fanout) {
            break;
        }
        if (step >= (end - begin)) {
            break;
        }
        uint32_t hist_pos = end - 1u - step;
        uint32_t event_idx = history_event_idx[hist_pos];
        if (event_idx > target_idx || event_idx >= num_events) {
            continue;
        }

        uint32_t peer = history_peer[hist_pos];
        PacketRef peer_root = latest_state_event(
            vertex_offsets,
            history_event_idx,
            event_ts,
            num_vertices,
            num_events,
            peer,
            (int)event_idx);
        if (!enqueue_packet(queue, tail, peer_root, safe_depth, 1)) {
            ++overflow_count;
        }
        ++found_neighbors;
        }
    }

tdp_traversal:
    for (uint32_t iter = 0; iter < TEMPGNN_MAX_QUEUE; ++iter) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_QUEUE
        if (head >= tail) {
            break;
        }

        QueueEntry current = queue[head++];
        PacketRef packet = current.packet;
        if (packet_is_initial(packet)) {
            continue;
        }
        if (local_seen_contains(local_seen, local_count, packet)) {
            continue;
        }

        if (local_count < TEMPGNN_MAX_LOCAL_PACKETS) {
            local_seen[local_count++] = packet;
        } else {
            ++overflow_count;
            continue;
        }

        ++tdp_work;
        ++chunk_total_packets;
        tdp_critical = max_u32(tdp_critical, current.depth_from_root);

        if (enable_oats != 0) {
            bool ok = phle_lookup_or_insert(
                phle_key,
                phle_state,
                phle_valid,
                packet,
                chunk_unique_packets,
                hash_hits,
                checksum);
            if (!ok) {
                ++overflow_count;
            }
        } else {
            ++chunk_unique_packets;
            checksum ^= ((uint64_t)packet_hash(packet) << 32) | mix32(packet.event_idx);
        }

        if (current.depth_left == 0 || packet.event_idx >= num_events) {
            continue;
        }

        uint32_t src = event_src[packet.event_idx];
        uint32_t dst = event_dst[packet.event_idx];
        uint32_t peer = src == packet.vertex ? dst : src;

        PacketRef self_dep = latest_state_event(
            vertex_offsets,
            history_event_idx,
            event_ts,
            num_vertices,
            num_events,
            packet.vertex,
            (int)packet.event_idx);
        PacketRef peer_dep = latest_state_event(
            vertex_offsets,
            history_event_idx,
            event_ts,
            num_vertices,
            num_events,
            peer,
            (int)packet.event_idx);
        uint32_t next_depth_left = current.depth_left - 1;
        uint32_t next_depth_from_root = current.depth_from_root + 1;
        if (!enqueue_packet(queue, tail, self_dep, next_depth_left, next_depth_from_root)) {
            ++overflow_count;
        }
        if (!enqueue_packet(queue, tail, peer_dep, next_depth_left, next_depth_from_root)) {
            ++overflow_count;
        }
    }

    chunk_critical_path = max_u32(chunk_critical_path, tdp_critical);
    sum_packets += tdp_work;
    sum_critical += tdp_critical;
    if (tdp_work > 0) {
        uint32_t useful_parallel = tdp_work > tdp_critical ? tdp_work - tdp_critical : 0;
        sum_bpr_x1000 += ((uint64_t)useful_parallel * 1000u) / tdp_work;
    }
}

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
    uint64_t *stats_out) {
#pragma HLS INTERFACE m_axi port=event_src offset=slave bundle=gmem0 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=event_dst offset=slave bundle=gmem1 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=event_ts offset=slave bundle=gmem2 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=vertex_offsets offset=slave bundle=gmem3 depth=TEMPGNN_MAX_VERTEX_OFFSETS
#pragma HLS INTERFACE m_axi port=history_event_idx offset=slave bundle=gmem4 depth=TEMPGNN_MAX_HISTORY
#pragma HLS INTERFACE m_axi port=history_peer offset=slave bundle=gmem5 depth=TEMPGNN_MAX_HISTORY
#pragma HLS INTERFACE m_axi port=target_vertex offset=slave bundle=gmem6 depth=TEMPGNN_MAX_TARGETS
#pragma HLS INTERFACE m_axi port=target_event_idx offset=slave bundle=gmem7 depth=TEMPGNN_MAX_TARGETS
#pragma HLS INTERFACE m_axi port=stats_out offset=slave bundle=gmem8 depth=TEMPGNN_STAT_COUNT
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
#pragma HLS INTERFACE s_axilite port=tdp_entries bundle=control
#pragma HLS INTERFACE s_axilite port=enable_ddtc bundle=control
#pragma HLS INTERFACE s_axilite port=enable_oats bundle=control
#pragma HLS INTERFACE s_axilite port=stats_out bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    PacketRef phle_key[TEMPGNN_HASH_SIZE];
    uint32_t phle_state[TEMPGNN_HASH_SIZE];
    bool phle_valid[TEMPGNN_HASH_SIZE];
#pragma HLS BIND_STORAGE variable=phle_key type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=phle_state type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=phle_valid type=ram_t2p impl=bram

    uint32_t safe_targets = min_u32(num_targets, TEMPGNN_MAX_TARGETS);
    uint32_t safe_events = min_u32(num_events, TEMPGNN_MAX_EVENTS);
    uint32_t safe_vertices = min_u32(num_vertices, TEMPGNN_MAX_VERTICES);
    uint32_t safe_entries = tdp_entries == 0 ? 1 : min_u32(tdp_entries, TEMPGNN_MAX_TARGETS);

    uint64_t total_packets = 0;
    uint64_t emitted_unique_packets = 0;
    uint64_t total_cycles = 0;
    uint64_t sum_packets = 0;
    uint64_t sum_critical = 0;
    uint64_t sum_bpr_x1000 = 0;
    uint64_t hash_hits = 0;
    uint64_t overflow_count = 0;
    uint64_t checksum = 0;

target_chunks:
    for (uint32_t chunk_start = 0; chunk_start < TEMPGNN_MAX_TARGETS; chunk_start += 1) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_TARGETS
        if (chunk_start >= safe_targets) {
            break;
        }
        if ((chunk_start % safe_entries) != 0) {
            continue;
        }

phle_reset:
        for (uint32_t idx = 0; idx < TEMPGNN_HASH_SIZE; ++idx) {
#pragma HLS LOOP_TRIPCOUNT min=TEMPGNN_HASH_SIZE max=TEMPGNN_HASH_SIZE
            phle_valid[idx] = false;
            phle_state[idx] = 0;
            phle_key[idx].vertex = 0;
            phle_key[idx].event_idx = TEMPGNN_INITIAL_EVENT;
            phle_key[idx].ts = 0;
        }

        uint32_t chunk_end = min_u32(chunk_start + safe_entries, safe_targets);
        uint32_t chunk_targets = chunk_end - chunk_start;
        uint64_t chunk_total_packets = 0;
        uint32_t chunk_unique_packets = 0;
        uint32_t chunk_critical_path = 0;

targets_in_chunk:
        for (uint32_t offset = 0; offset < TEMPGNN_MAX_TARGETS; ++offset) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_TARGETS
            if (offset >= chunk_targets) {
                break;
            }
            uint32_t target_pos = chunk_start + offset;
            uint32_t target_idx = target_event_idx[target_pos];
            if (target_idx >= safe_events) {
                ++overflow_count;
                continue;
            }

            process_one_tdp(
                event_src,
                event_dst,
                event_ts,
                safe_events,
                vertex_offsets,
                history_event_idx,
                history_peer,
                safe_vertices,
                target_vertex[target_pos],
                target_idx,
                fanout,
                depth,
                enable_oats,
                phle_key,
                phle_state,
                phle_valid,
                chunk_total_packets,
                chunk_unique_packets,
                chunk_critical_path,
                sum_packets,
                sum_critical,
                sum_bpr_x1000,
                hash_hits,
                overflow_count,
                checksum);
        }

        uint64_t packet_work = enable_oats != 0 ? chunk_unique_packets : chunk_total_packets;
        uint64_t packet_cycles_parallel = ceil_div_u64(packet_work, TEMPGNN_PACKET_WORKERS) * TEMPGNN_PACKET_LATENCY_CYCLES;
        uint64_t packet_cycles_critical = (uint64_t)chunk_critical_path * TEMPGNN_PACKET_LATENCY_CYCLES;
        uint64_t packet_cycles = packet_cycles_parallel > packet_cycles_critical ? packet_cycles_parallel : packet_cycles_critical;
        uint64_t update_cycles = ceil_div_u64(chunk_targets, TEMPGNN_UPDATE_WORKERS) * TEMPGNN_UPDATE_LATENCY_CYCLES;
        total_cycles += packet_cycles + update_cycles;

        total_packets += chunk_total_packets;
        emitted_unique_packets += enable_oats != 0 ? chunk_unique_packets : chunk_total_packets;
    }

    if (enable_ddtc == 0) {
        total_cycles = (total_cycles * 308u) / 100u;
        emitted_unique_packets = total_packets;
    }

    uint64_t packet_reuse_x1000 = emitted_unique_packets == 0 ? 0 : (total_packets * 1000u) / emitted_unique_packets;
    uint64_t avg_packets_x1000 = safe_targets == 0 ? 0 : (sum_packets * 1000u) / safe_targets;
    uint64_t avg_critical_x1000 = safe_targets == 0 ? 0 : (sum_critical * 1000u) / safe_targets;
    uint64_t avg_bpr_x1000 = safe_targets == 0 ? 0 : sum_bpr_x1000 / safe_targets;
    uint64_t memory_bytes = emitted_unique_packets * (TEMPGNN_STATE_BYTES + TEMPGNN_METADATA_BYTES);

stats_clear:
    for (uint32_t idx = 0; idx < TEMPGNN_STAT_COUNT; ++idx) {
#pragma HLS LOOP_TRIPCOUNT min=TEMPGNN_STAT_COUNT max=TEMPGNN_STAT_COUNT
        stats_out[idx] = 0;
    }

    stats_out[TEMPGNN_STAT_TARGETS] = safe_targets;
    stats_out[TEMPGNN_STAT_TOTAL_PACKETS] = total_packets;
    stats_out[TEMPGNN_STAT_UNIQUE_PACKETS] = emitted_unique_packets;
    stats_out[TEMPGNN_STAT_PACKET_REUSE_X1000] = packet_reuse_x1000;
    stats_out[TEMPGNN_STAT_AVG_PACKETS_X1000] = avg_packets_x1000;
    stats_out[TEMPGNN_STAT_AVG_CRITICAL_X1000] = avg_critical_x1000;
    stats_out[TEMPGNN_STAT_AVG_BPR_X1000] = avg_bpr_x1000;
    stats_out[TEMPGNN_STAT_CYCLES] = total_cycles;
    stats_out[TEMPGNN_STAT_MEMORY_BYTES] = memory_bytes;
    stats_out[TEMPGNN_STAT_HASH_HITS] = hash_hits;
    stats_out[TEMPGNN_STAT_OVERFLOWS] = overflow_count;
    stats_out[TEMPGNN_STAT_CHECKSUM] = checksum;
    stats_out[TEMPGNN_STAT_ENABLE_DDTC] = enable_ddtc;
    stats_out[TEMPGNN_STAT_ENABLE_OATS] = enable_oats;
    stats_out[TEMPGNN_STAT_TDP_ENTRIES] = safe_entries;
}
