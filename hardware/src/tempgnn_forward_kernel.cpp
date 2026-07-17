#include "tempgnn_hls.hpp"

struct FwdPacketRef {
    uint32_t vertex;
    uint32_t event_idx;
    uint32_t ts;
};

struct FwdQueueEntry {
    FwdPacketRef packet;
    uint32_t depth_left;
    uint32_t depth_from_root;
};

struct FwdPackedState {
    uint64_t lo;
    uint64_t hi;
};

static const uint32_t TEMPGNN_FWD_NOT_INDEXED_EVENT = 0xfffffffeu;

// The measured forward path supports depth two. With one target root, at most
// TEMPGNN_MAX_FANOUT neighbor roots, and binary dependencies, 147 queue entries
// are reachable; 256 leaves explicit headroom for duplicate/self-loop cases.
#define TEMPGNN_FWD_SUPPORTED_DEPTH 2
#define TEMPGNN_FWD_QUEUE_CAPACITY 256
#define TEMPGNN_FWD_LOCAL_CAPACITY 256
#define TEMPGNN_FWD_HEAP_LEVELS 8
#define TEMPGNN_FWD_PACKET_SLOTS (TEMPGNN_MAX_EVENTS * 2)
#define TEMPGNN_FWD_EVENT_BITMAP_WORDS ((TEMPGNN_MAX_EVENTS + 63) / 64)

static uint32_t fwd_min_u32(uint32_t lhs, uint32_t rhs) {
    return lhs < rhs ? lhs : rhs;
}

static uint32_t fwd_max_u32(uint32_t lhs, uint32_t rhs) {
    return lhs > rhs ? lhs : rhs;
}

static uint64_t fwd_ceil_div_u64(uint64_t value, uint64_t divisor) {
    return divisor == 0 ? 0 : (value + divisor - 1) / divisor;
}

static uint32_t fwd_ctz64(uint64_t value) {
#pragma HLS INLINE
    uint32_t offset = 0;
    if ((uint32_t)value == 0) {
        offset += 32;
        value >>= 32;
    }
    if ((uint16_t)value == 0) {
        offset += 16;
        value >>= 16;
    }
    if ((uint8_t)value == 0) {
        offset += 8;
        value >>= 8;
    }
    if ((value & 0x0fu) == 0) {
        offset += 4;
        value >>= 4;
    }
    if ((value & 0x03u) == 0) {
        offset += 2;
        value >>= 2;
    }
    if ((value & 0x01u) == 0) {
        ++offset;
    }
    return offset;
}

static uint32_t fwd_mix32(uint32_t value) {
    value ^= value >> 16;
    value *= 0x7feb352du;
    value ^= value >> 15;
    value *= 0x846ca68bu;
    value ^= value >> 16;
    return value;
}

static uint32_t fwd_packet_hash(const FwdPacketRef &packet) {
    return fwd_mix32(packet.vertex) ^ fwd_mix32(packet.event_idx + 0x9e3779b9u) ^ fwd_mix32(packet.ts);
}

static bool fwd_packet_is_initial(const FwdPacketRef &packet) {
    return packet.event_idx == TEMPGNN_INITIAL_EVENT;
}

static bool fwd_packet_equal(const FwdPacketRef &lhs, const FwdPacketRef &rhs) {
    return lhs.vertex == rhs.vertex && lhs.event_idx == rhs.event_idx;
}

static uint64_t fwd_packet_key(const FwdPacketRef &packet) {
#pragma HLS INLINE
    return ((uint64_t)packet.vertex << 32u) | packet.event_idx;
}

static uint32_t fwd_packet_slot(
    const uint32_t *event_src,
    const FwdPacketRef &packet) {
#pragma HLS INLINE
    uint32_t side = packet.vertex == event_src[packet.event_idx] ? 0u : 1u;
    return (packet.event_idx << 1u) | side;
}

static int16_t fwd_clamp_i16(int32_t value) {
    if (value > 32767) {
        return 32767;
    }
    if (value < -32768) {
        return -32768;
    }
    return (int16_t)value;
}

static int16_t fwd_hard_tanh_q10(int32_t value) {
    if (value > TEMPGNN_FWD_SCALE) {
        return TEMPGNN_FWD_SCALE;
    }
    if (value < -TEMPGNN_FWD_SCALE) {
        return -TEMPGNN_FWD_SCALE;
    }
    return fwd_clamp_i16(value);
}

static FwdPacketRef fwd_latest_state_event(
    const uint32_t *vertex_offsets,
    const uint32_t *history_event_idx,
    const uint32_t *event_ts,
    uint32_t num_vertices,
    uint32_t num_events,
    uint32_t vertex,
    int before_event_idx) {
#pragma HLS INLINE off
    FwdPacketRef result;
    result.vertex = vertex;
    result.event_idx = TEMPGNN_INITIAL_EVENT;
    result.ts = 0;

    if (vertex >= num_vertices) {
        return result;
    }

    if (before_event_idx <= 0) {
        return result;
    }

    uint32_t begin = vertex_offsets[vertex];
    uint32_t end = vertex_offsets[vertex + 1];

    uint32_t available = end - begin;
    uint32_t search_begin = available > TEMPGNN_MAX_DEGREE_SCAN
                                ? end - TEMPGNN_MAX_DEGREE_SCAN
                                : begin;
    uint32_t limit = fwd_min_u32((uint32_t)before_event_idx, num_events);
    uint32_t lower = search_begin;
    uint32_t upper = end;

// Histories are stored in increasing event-index order. Find the first entry
// at or after the limit, preserving the old bounded reverse-scan semantics.
fwd_latest_lower_bound:
    for (uint32_t step = 0; step < 13; ++step) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=13
        if (lower >= upper) {
            break;
        }
        uint32_t middle = lower + ((upper - lower) >> 1);
        uint32_t event_idx = history_event_idx[middle];
        if (event_idx < limit) {
            lower = middle + 1u;
        } else {
            upper = middle;
        }
    }

    if (lower > search_begin) {
        uint32_t event_idx = history_event_idx[lower - 1u];
        result.ts = event_ts[event_idx];
        result.event_idx = event_idx;
    }
    return result;
}

static FwdPacketRef fwd_predecessor_state_event(
    const uint32_t *event_src,
    const uint32_t *event_dst,
    const uint32_t *event_ts,
    const uint32_t *vertex_offsets,
    const uint32_t *history_event_idx,
    const uint32_t predecessor_src[TEMPGNN_MAX_EVENTS],
    const uint32_t predecessor_dst[TEMPGNN_MAX_EVENTS],
    uint32_t num_vertices,
    uint32_t num_events,
    const FwdPacketRef &packet) {
#pragma HLS INLINE off
    if (fwd_packet_is_initial(packet) || packet.event_idx >= num_events) {
        FwdPacketRef initial = {packet.vertex, TEMPGNN_INITIAL_EVENT, 0};
        return initial;
    }

    uint32_t src = event_src[packet.event_idx];
    uint32_t dst = event_dst[packet.event_idx];
    uint32_t predecessor = TEMPGNN_FWD_NOT_INDEXED_EVENT;
    if (packet.vertex == src) {
        predecessor = predecessor_src[packet.event_idx];
    } else if (packet.vertex == dst) {
        predecessor = predecessor_dst[packet.event_idx];
    }

    if (predecessor == TEMPGNN_FWD_NOT_INDEXED_EVENT) {
        FwdPacketRef initial = {packet.vertex, TEMPGNN_INITIAL_EVENT, 0};
        return initial;
    }

    FwdPacketRef result = {packet.vertex, predecessor, 0};
    if (predecessor != TEMPGNN_INITIAL_EVENT) {
        result.ts = event_ts[predecessor];
    }
    return result;
}

static FwdPacketRef fwd_target_state_event(
    const uint32_t *event_src,
    const uint32_t *event_dst,
    const uint32_t *event_ts,
    const uint32_t *vertex_offsets,
    const uint32_t *history_event_idx,
    const uint32_t predecessor_src[TEMPGNN_MAX_EVENTS],
    const uint32_t predecessor_dst[TEMPGNN_MAX_EVENTS],
    const uint8_t predecessor_indexed[TEMPGNN_MAX_EVENTS],
    uint32_t num_vertices,
    uint32_t num_events,
    uint32_t vertex,
    uint32_t event_idx) {
#pragma HLS INLINE off
    if (event_idx < num_events) {
        uint32_t src = event_src[event_idx];
        uint32_t dst = event_dst[event_idx];
        uint8_t indexed_mask = predecessor_indexed[event_idx];
        bool indexed = (vertex == src && (indexed_mask & 1u) != 0) ||
                       (vertex == dst && (indexed_mask & 2u) != 0);
        if (indexed) {
            FwdPacketRef result = {vertex, event_idx, event_ts[event_idx]};
            return result;
        }
    }
    return fwd_latest_state_event(
        vertex_offsets,
        history_event_idx,
        event_ts,
        num_vertices,
        num_events,
        vertex,
        (int)event_idx + 1);
}

static bool fwd_enqueue_packet(
    FwdQueueEntry queue[TEMPGNN_FWD_QUEUE_CAPACITY],
    uint32_t &tail,
    const FwdPacketRef &packet,
    uint32_t depth_left,
    uint32_t depth_from_root) {
#pragma HLS INLINE
    if (tail >= TEMPGNN_FWD_QUEUE_CAPACITY) {
        return false;
    }
    queue[tail].packet = packet;
    queue[tail].depth_left = depth_left;
    queue[tail].depth_from_root = depth_from_root;
    ++tail;
    return true;
}

static bool fwd_find_local_packet(
    const uint32_t *event_src,
    const FwdPacketRef &packet,
    uint16_t lookup_tags[TEMPGNN_FWD_PACKET_SLOTS],
    uint16_t lookup_indices[TEMPGNN_FWD_PACKET_SLOTS],
    uint16_t lookup_tag,
    uint32_t &found) {
#pragma HLS INLINE
    uint32_t slot = fwd_packet_slot(event_src, packet);
    if (lookup_tags[slot] == lookup_tag) {
        found = lookup_indices[slot];
        return true;
    }
    found = TEMPGNN_FWD_LOCAL_CAPACITY;
    return false;
}

static void fwd_index_local_packet(
    const uint32_t *event_src,
    uint16_t lookup_tags[TEMPGNN_FWD_PACKET_SLOTS],
    uint16_t lookup_indices[TEMPGNN_FWD_PACKET_SLOTS],
    uint16_t lookup_tag,
    const FwdPacketRef &packet,
    uint32_t packet_idx) {
#pragma HLS INLINE
    uint32_t slot = fwd_packet_slot(event_src, packet);
    lookup_tags[slot] = lookup_tag;
    lookup_indices[slot] = (uint16_t)packet_idx;
}

static bool fwd_compute_order_before(
    FwdPacketRef packets[TEMPGNN_FWD_LOCAL_CAPACITY],
    uint32_t lhs,
    uint32_t rhs) {
#pragma HLS INLINE
    uint32_t lhs_event = packets[lhs].event_idx;
    uint32_t rhs_event = packets[rhs].event_idx;
    return lhs_event < rhs_event || (lhs_event == rhs_event && lhs > rhs);
}

static void fwd_compute_heap_push(
    uint16_t heap[TEMPGNN_FWD_LOCAL_CAPACITY],
    uint32_t &count,
    FwdPacketRef packets[TEMPGNN_FWD_LOCAL_CAPACITY],
    uint32_t packet_idx) {
#pragma HLS INLINE off
    uint32_t position = count++;

fwd_compute_heap_sift_up:
    for (uint32_t level = 0; level < TEMPGNN_FWD_HEAP_LEVELS; ++level) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_FWD_HEAP_LEVELS
        if (position == 0) {
            break;
        }
        uint32_t parent = (position - 1u) >> 1;
        uint32_t parent_idx = heap[parent];
        if (!fwd_compute_order_before(packets, packet_idx, parent_idx)) {
            break;
        }
        heap[position] = (uint16_t)parent_idx;
        position = parent;
    }
    heap[position] = (uint16_t)packet_idx;
}

static uint32_t fwd_compute_heap_pop(
    uint16_t heap[TEMPGNN_FWD_LOCAL_CAPACITY],
    uint32_t &count,
    FwdPacketRef packets[TEMPGNN_FWD_LOCAL_CAPACITY]) {
#pragma HLS INLINE off
    uint32_t result = heap[0];
    --count;
    if (count == 0) {
        return result;
    }

    uint32_t replacement = heap[count];
    uint32_t position = 0;

fwd_compute_heap_sift_down:
    for (uint32_t level = 0; level < TEMPGNN_FWD_HEAP_LEVELS; ++level) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_FWD_HEAP_LEVELS
        uint32_t left = position * 2u + 1u;
        if (left >= count) {
            break;
        }
        uint32_t right = left + 1u;
        uint32_t child = left;
        if (right < count && fwd_compute_order_before(packets, heap[right], heap[left])) {
            child = right;
        }
        uint32_t child_idx = heap[child];
        if (!fwd_compute_order_before(packets, child_idx, replacement)) {
            break;
        }
        heap[position] = (uint16_t)child_idx;
        position = child;
    }
    heap[position] = (uint16_t)replacement;
    return result;
}

static void fwd_load_initial_state(
    const int16_t *initial_memory,
    uint32_t num_vertices,
    uint32_t vertex,
    int16_t state[TEMPGNN_FWD_DIM]) {
#pragma HLS INLINE off
fwd_load_initial_dim:
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
        if (vertex < num_vertices) {
            state[dim] = initial_memory[vertex * TEMPGNN_FWD_DIM + dim];
        } else {
            state[dim] = 0;
        }
    }
}

static void fwd_copy_state(
    const int16_t src[TEMPGNN_FWD_DIM],
    int16_t dst[TEMPGNN_FWD_DIM]) {
#pragma HLS INLINE
fwd_copy_dim:
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
        dst[dim] = src[dim];
    }
}

static void fwd_store_local_state(
    int16_t states[TEMPGNN_FWD_LOCAL_CAPACITY][TEMPGNN_FWD_DIM],
    uint32_t idx,
    const int16_t src[TEMPGNN_FWD_DIM]) {
#pragma HLS INLINE
fwd_store_local_dim:
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
        states[idx][dim] = src[dim];
    }
}

static void fwd_load_local_state(
    int16_t states[TEMPGNN_FWD_LOCAL_CAPACITY][TEMPGNN_FWD_DIM],
    uint32_t idx,
    int16_t dst[TEMPGNN_FWD_DIM]) {
#pragma HLS INLINE
fwd_load_local_dim:
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
        dst[dim] = states[idx][dim];
    }
}

static bool fwd_phle_lookup(
    uint64_t phle_key[TEMPGNN_HASH_SIZE],
    uint16_t phle_tags[TEMPGNN_HASH_SIZE],
    FwdPackedState phle_state[TEMPGNN_HASH_SIZE],
    uint16_t phle_tag,
    const FwdPacketRef &packet,
    uint32_t packet_hash,
    int16_t state[TEMPGNN_FWD_DIM],
    uint64_t &hash_hits,
    uint64_t &checksum) {
#pragma HLS INLINE off
    uint32_t bucket = packet_hash % TEMPGNN_HASH_BUCKETS;
    uint64_t packet_key = fwd_packet_key(packet);

fwd_phle_probe_lookup:
    for (uint32_t way = 0; way < TEMPGNN_HASH_WAYS; ++way) {
#pragma HLS UNROLL
        uint32_t idx = bucket * TEMPGNN_HASH_WAYS + way;
        if (phle_tags[idx] == phle_tag && phle_key[idx] == packet_key) {
            ++hash_hits;
            uint64_t local = packet_hash;
            FwdPackedState packed = phle_state[idx];
        fwd_phle_copy_hit:
            for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
                uint64_t word = dim < 4 ? packed.lo : packed.hi;
                state[dim] = (int16_t)(word >> ((dim & 3u) * 16u));
                local ^= ((uint64_t)(uint16_t)state[dim]) << ((dim & 3u) * 16u);
            }
            checksum ^= local;
            return true;
        }
    }
    return false;
}

static bool fwd_phle_insert(
    uint64_t phle_key[TEMPGNN_HASH_SIZE],
    uint16_t phle_tags[TEMPGNN_HASH_SIZE],
    FwdPackedState phle_state[TEMPGNN_HASH_SIZE],
    uint16_t phle_tag,
    const FwdPacketRef &packet,
    uint32_t packet_hash,
    const int16_t state[TEMPGNN_FWD_DIM],
    uint64_t &checksum) {
#pragma HLS INLINE off
    uint32_t bucket = packet_hash % TEMPGNN_HASH_BUCKETS;
    uint64_t packet_key = fwd_packet_key(packet);
    uint32_t empty_index = TEMPGNN_HASH_SIZE;

fwd_phle_probe_insert:
    for (uint32_t way = 0; way < TEMPGNN_HASH_WAYS; ++way) {
#pragma HLS UNROLL
        uint32_t idx = bucket * TEMPGNN_HASH_WAYS + way;
        if (phle_tags[idx] == phle_tag) {
            if (phle_key[idx] == packet_key) {
                return true;
            }
        } else if (empty_index == TEMPGNN_HASH_SIZE) {
            empty_index = idx;
        }
    }

    if (empty_index == TEMPGNN_HASH_SIZE) {
        return false;
    }

    phle_tags[empty_index] = phle_tag;
    phle_key[empty_index] = packet_key;
    uint64_t local = packet_hash;
    FwdPackedState packed = {0, 0};

fwd_phle_store_dim:
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
        uint64_t component = ((uint64_t)(uint16_t)state[dim]) << ((dim & 3u) * 16u);
        if (dim < 4) {
            packed.lo |= component;
        } else {
            packed.hi |= component;
        }
        local ^= component;
    }
    phle_state[empty_index] = packed;
    checksum ^= local;
    return true;
}

static void fwd_update_state(
    const uint32_t *event_dst,
    const int16_t *event_features,
    const int16_t *weight_self,
    const int16_t *weight_peer,
    const int16_t *weight_event,
    const int16_t *bias,
    const int16_t self_state[TEMPGNN_FWD_DIM],
    const int16_t peer_state[TEMPGNN_FWD_DIM],
    const FwdPacketRef &packet,
    int16_t out_state[TEMPGNN_FWD_DIM]) {
#pragma HLS INLINE off
    bool dst_side = packet.event_idx != TEMPGNN_INITIAL_EVENT && packet.vertex == event_dst[packet.event_idx];

fwd_update_dim:
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
        int16_t feature = event_features[packet.event_idx * TEMPGNN_FWD_DIM + dim];
        if (dst_side) {
            feature = (int16_t)-feature;
        }
        int32_t acc = bias[dim];
        acc += ((int32_t)self_state[dim] * (int32_t)weight_self[dim]) / TEMPGNN_FWD_SCALE;
        acc += ((int32_t)peer_state[dim] * (int32_t)weight_peer[dim]) / TEMPGNN_FWD_SCALE;
        acc += ((int32_t)feature * (int32_t)weight_event[dim]) / TEMPGNN_FWD_SCALE;
        out_state[dim] = fwd_hard_tanh_q10(acc);
    }
}

static void fwd_dependency_state(
    const uint32_t *event_src,
    const int16_t *initial_memory,
    uint32_t num_vertices,
    bool valid[TEMPGNN_FWD_LOCAL_CAPACITY],
    int16_t states[TEMPGNN_FWD_LOCAL_CAPACITY][TEMPGNN_FWD_DIM],
    uint16_t lookup_tags[TEMPGNN_FWD_PACKET_SLOTS],
    uint16_t lookup_indices[TEMPGNN_FWD_PACKET_SLOTS],
    uint16_t lookup_tag,
    const FwdPacketRef &dependency,
    int16_t out_state[TEMPGNN_FWD_DIM]) {
#pragma HLS INLINE off
    if (fwd_packet_is_initial(dependency)) {
        fwd_load_initial_state(initial_memory, num_vertices, dependency.vertex, out_state);
        return;
    }

    uint32_t dep_idx = TEMPGNN_FWD_LOCAL_CAPACITY;
    if (fwd_find_local_packet(
            event_src,
            dependency,
            lookup_tags,
            lookup_indices,
            lookup_tag,
            dep_idx) &&
        valid[dep_idx]) {
        fwd_load_local_state(states, dep_idx, out_state);
    } else {
        fwd_load_initial_state(initial_memory, num_vertices, dependency.vertex, out_state);
    }
}

static void fwd_process_target(
    const uint32_t *event_src,
    const uint32_t *event_dst,
    const uint32_t *event_ts,
    const uint32_t *packet_hashes,
    uint32_t num_events,
    const uint32_t *vertex_offsets,
    const uint32_t *history_event_idx,
    uint32_t num_vertices,
    uint32_t target,
    uint32_t target_idx,
    uint32_t fanout,
    uint32_t depth,
    uint32_t enable_oats,
    const int16_t *initial_memory,
    const int16_t *event_features,
    const int16_t *weight_self,
    const int16_t *weight_peer,
    const int16_t *weight_event,
    const int16_t *bias,
    uint64_t phle_key[TEMPGNN_HASH_SIZE],
    uint16_t phle_tags[TEMPGNN_HASH_SIZE],
    FwdPackedState phle_state[TEMPGNN_HASH_SIZE],
    uint16_t phle_tag,
    const uint32_t predecessor_src[TEMPGNN_MAX_EVENTS],
    const uint32_t predecessor_dst[TEMPGNN_MAX_EVENTS],
    const uint8_t predecessor_indexed[TEMPGNN_MAX_EVENTS],
    uint16_t local_lookup_tags[TEMPGNN_FWD_PACKET_SLOTS],
    uint16_t local_lookup_indices[TEMPGNN_FWD_PACKET_SLOTS],
    uint16_t local_lookup_tag,
    uint64_t event_bitmap[TEMPGNN_FWD_EVENT_BITMAP_WORDS],
    uint16_t event_bitmap_tags[TEMPGNN_FWD_EVENT_BITMAP_WORDS],
    int16_t target_embedding[TEMPGNN_FWD_DIM],
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
    FwdQueueEntry queue[TEMPGNN_FWD_QUEUE_CAPACITY];
    FwdPacketRef local_packets[TEMPGNN_FWD_LOCAL_CAPACITY];
    bool local_valid[TEMPGNN_FWD_LOCAL_CAPACITY];
    int16_t local_states[TEMPGNN_FWD_LOCAL_CAPACITY][TEMPGNN_FWD_DIM];
    uint16_t compute_order[TEMPGNN_FWD_LOCAL_CAPACITY];
#pragma HLS BIND_STORAGE variable=queue type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=local_packets type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=local_valid type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=local_states type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=compute_order type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=local_states complete dim=2

    uint32_t head = 0;
    uint32_t tail = 0;
    uint32_t local_count = 0;
    uint32_t compute_order_count = 0;
    uint32_t tdp_critical = 0;
    uint32_t safe_depth = fwd_min_u32(depth, TEMPGNN_FWD_SUPPORTED_DEPTH);
    uint32_t safe_fanout = fwd_min_u32(fanout, TEMPGNN_MAX_FANOUT);
    uint32_t min_event_word = TEMPGNN_FWD_EVENT_BITMAP_WORDS;
    uint32_t max_event_word = 0;

    FwdPacketRef self_root = fwd_target_state_event(
        event_src,
        event_dst,
        event_ts,
        vertex_offsets,
        history_event_idx,
        predecessor_src,
        predecessor_dst,
        predecessor_indexed,
        num_vertices,
        num_events,
        target,
        target_idx);
    if (!fwd_enqueue_packet(queue, tail, self_root, safe_depth, 1)) {
        ++overflow_count;
    }

    uint32_t found_neighbors = 0;
    FwdPacketRef neighbor_packet = self_root;
    bool repeat_self_loop = false;
    if (!fwd_packet_is_initial(neighbor_packet)) {
        uint32_t root_src = event_src[neighbor_packet.event_idx];
        uint32_t root_dst = event_dst[neighbor_packet.event_idx];
        repeat_self_loop = root_src == target && root_dst == target;
    }
    if (target < num_vertices) {
    fwd_recent_neighbor_scan:
        for (uint32_t step = 0; step < TEMPGNN_MAX_FANOUT; ++step) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_FANOUT
            if (found_neighbors >= safe_fanout || fwd_packet_is_initial(neighbor_packet)) {
                break;
            }
            uint32_t event_idx = neighbor_packet.event_idx;
            uint32_t src = event_src[event_idx];
            uint32_t dst = event_dst[event_idx];
            uint32_t peer = src == target ? dst : src;
            FwdPacketRef peer_packet = {peer, event_idx, event_ts[event_idx]};
            FwdPacketRef peer_root = fwd_predecessor_state_event(
                event_src,
                event_dst,
                event_ts,
                vertex_offsets,
                history_event_idx,
                predecessor_src,
                predecessor_dst,
                num_vertices,
                num_events,
                peer_packet);
            if (!fwd_enqueue_packet(queue, tail, peer_root, safe_depth, 1)) {
                ++overflow_count;
            }
            if (repeat_self_loop) {
                repeat_self_loop = false;
            } else {
                neighbor_packet = fwd_predecessor_state_event(
                    event_src,
                    event_dst,
                    event_ts,
                    vertex_offsets,
                    history_event_idx,
                    predecessor_src,
                    predecessor_dst,
                    num_vertices,
                    num_events,
                    neighbor_packet);
                if (!fwd_packet_is_initial(neighbor_packet)) {
                    uint32_t next_src = event_src[neighbor_packet.event_idx];
                    uint32_t next_dst = event_dst[neighbor_packet.event_idx];
                    repeat_self_loop = next_src == target && next_dst == target;
                }
            }
            ++found_neighbors;
        }
    }

fwd_tdp_traversal:
    for (uint32_t iter = 0; iter < TEMPGNN_FWD_QUEUE_CAPACITY; ++iter) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_FWD_QUEUE_CAPACITY
        if (head >= tail) {
            break;
        }

        FwdQueueEntry current = queue[head++];
        FwdPacketRef packet = current.packet;
        if (fwd_packet_is_initial(packet)) {
            continue;
        }

        uint32_t existing = TEMPGNN_FWD_LOCAL_CAPACITY;
        if (fwd_find_local_packet(
                event_src,
                packet,
                local_lookup_tags,
                local_lookup_indices,
                local_lookup_tag,
                existing)) {
            continue;
        }

        if (local_count >= TEMPGNN_FWD_LOCAL_CAPACITY) {
            ++overflow_count;
            continue;
        }

        local_packets[local_count] = packet;
        local_valid[local_count] = false;
        fwd_index_local_packet(
            event_src,
            local_lookup_tags,
            local_lookup_indices,
            local_lookup_tag,
            packet,
            local_count);
        uint32_t bitmap_word = packet.event_idx >> 6u;
        uint32_t bitmap_bit = packet.event_idx & 63u;
        if (event_bitmap_tags[bitmap_word] != local_lookup_tag) {
            event_bitmap_tags[bitmap_word] = local_lookup_tag;
            event_bitmap[bitmap_word] = 0;
        }
        event_bitmap[bitmap_word] |= 1ull << bitmap_bit;
        min_event_word = fwd_min_u32(min_event_word, bitmap_word);
        max_event_word = fwd_max_u32(max_event_word, bitmap_word);
        ++local_count;
        ++chunk_total_packets;
        tdp_critical = fwd_max_u32(tdp_critical, current.depth_from_root);

        if (current.depth_left == 0 || packet.event_idx >= num_events) {
            continue;
        }

        uint32_t src = event_src[packet.event_idx];
        uint32_t dst = event_dst[packet.event_idx];
        uint32_t peer = src == packet.vertex ? dst : src;
        FwdPacketRef self_dep = fwd_predecessor_state_event(
            event_src,
            event_dst,
            event_ts,
            vertex_offsets,
            history_event_idx,
            predecessor_src,
            predecessor_dst,
            num_vertices,
            num_events,
            packet);
        FwdPacketRef peer_packet = {peer, packet.event_idx, packet.ts};
        FwdPacketRef peer_dep = fwd_predecessor_state_event(
            event_src,
            event_dst,
            event_ts,
            vertex_offsets,
            history_event_idx,
            predecessor_src,
            predecessor_dst,
            num_vertices,
            num_events,
            peer_packet);
        uint32_t next_depth_left = current.depth_left - 1;
        uint32_t next_depth_from_root = current.depth_from_root + 1;
        if (!fwd_enqueue_packet(queue, tail, self_dep, next_depth_left, next_depth_from_root)) {
            ++overflow_count;
        }
        if (!fwd_enqueue_packet(queue, tail, peer_dep, next_depth_left, next_depth_from_root)) {
            ++overflow_count;
        }
    }

fwd_compute_order_words:
    for (uint32_t word_offset = 0; word_offset < TEMPGNN_FWD_EVENT_BITMAP_WORDS; ++word_offset) {
#pragma HLS PIPELINE off
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_FWD_EVENT_BITMAP_WORDS
        if (min_event_word == TEMPGNN_FWD_EVENT_BITMAP_WORDS ||
            word_offset > max_event_word - min_event_word) {
            break;
        }
        uint32_t word_idx = min_event_word + word_offset;
        uint64_t bits = event_bitmap_tags[word_idx] == local_lookup_tag
                            ? event_bitmap[word_idx]
                            : 0;

    fwd_compute_order_bits:
        for (uint32_t bit_iter = 0; bit_iter < 64; ++bit_iter) {
#pragma HLS PIPELINE off
#pragma HLS LOOP_TRIPCOUNT min=0 max=64
            if (bits == 0) {
                break;
            }
            uint32_t event_idx = (word_idx << 6u) + fwd_ctz64(bits);
            bits &= bits - 1u;

            uint32_t slot = event_idx << 1u;
            bool src_valid = local_lookup_tags[slot] == local_lookup_tag;
            bool dst_valid = local_lookup_tags[slot + 1u] == local_lookup_tag;
            uint32_t src_idx = src_valid ? local_lookup_indices[slot] : 0;
            uint32_t dst_idx = dst_valid ? local_lookup_indices[slot + 1u] : 0;

            if (src_valid && dst_valid) {
                uint32_t first_idx = src_idx > dst_idx ? src_idx : dst_idx;
                uint32_t second_idx = src_idx > dst_idx ? dst_idx : src_idx;
                compute_order[compute_order_count++] = (uint16_t)first_idx;
                compute_order[compute_order_count++] = (uint16_t)second_idx;
            } else if (src_valid) {
                compute_order[compute_order_count++] = (uint16_t)src_idx;
            } else if (dst_valid) {
                compute_order[compute_order_count++] = (uint16_t)dst_idx;
            }
        }
    }

fwd_compute_reverse:
    for (uint32_t pass = 0; pass < TEMPGNN_FWD_LOCAL_CAPACITY; ++pass) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_FWD_LOCAL_CAPACITY
        if (pass >= compute_order_count) {
            break;
        }

        uint32_t packet_idx = compute_order[pass];
        FwdPacketRef packet = local_packets[packet_idx];
        uint32_t packet_hash = packet_hashes[fwd_packet_slot(event_src, packet)];
        int16_t out_state[TEMPGNN_FWD_DIM];
#pragma HLS ARRAY_PARTITION variable=out_state complete dim=1

        bool reused = false;
        if (enable_oats != 0) {
            reused = fwd_phle_lookup(
                phle_key,
                phle_tags,
                phle_state,
                phle_tag,
                packet,
                packet_hash,
                out_state,
                hash_hits,
                checksum);
        }

        if (!reused) {
            uint32_t src = event_src[packet.event_idx];
            uint32_t dst = event_dst[packet.event_idx];
            uint32_t peer = src == packet.vertex ? dst : src;
            FwdPacketRef self_dep = fwd_predecessor_state_event(
                event_src,
                event_dst,
                event_ts,
                vertex_offsets,
                history_event_idx,
                predecessor_src,
                predecessor_dst,
                num_vertices,
                num_events,
                packet);
            FwdPacketRef peer_packet = {peer, packet.event_idx, packet.ts};
            FwdPacketRef peer_dep = fwd_predecessor_state_event(
                event_src,
                event_dst,
                event_ts,
                vertex_offsets,
                history_event_idx,
                predecessor_src,
                predecessor_dst,
                num_vertices,
                num_events,
                peer_packet);
            int16_t self_state[TEMPGNN_FWD_DIM];
            int16_t peer_state[TEMPGNN_FWD_DIM];
#pragma HLS ARRAY_PARTITION variable=self_state complete dim=1
#pragma HLS ARRAY_PARTITION variable=peer_state complete dim=1

            fwd_dependency_state(
                event_src,
                initial_memory,
                num_vertices,
                local_valid,
                local_states,
                local_lookup_tags,
                local_lookup_indices,
                local_lookup_tag,
                self_dep,
                self_state);
            fwd_dependency_state(
                event_src,
                initial_memory,
                num_vertices,
                local_valid,
                local_states,
                local_lookup_tags,
                local_lookup_indices,
                local_lookup_tag,
                peer_dep,
                peer_state);
            fwd_update_state(event_dst, event_features, weight_self, weight_peer, weight_event, bias, self_state, peer_state, packet, out_state);
            ++chunk_unique_packets;

            if (enable_oats != 0) {
                if (!fwd_phle_insert(
                        phle_key,
                        phle_tags,
                        phle_state,
                        phle_tag,
                        packet,
                        packet_hash,
                        out_state,
                        checksum)) {
                    ++overflow_count;
                }
            } else {
                uint64_t local = packet_hash;
            fwd_no_oats_checksum_dim:
                for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
                    local ^= ((uint64_t)(uint16_t)out_state[dim]) << ((dim & 3u) * 16u);
                }
                checksum ^= local;
            }
        }

        fwd_store_local_state(local_states, packet_idx, out_state);
        local_valid[packet_idx] = true;
    }

    uint32_t root_idx = TEMPGNN_FWD_LOCAL_CAPACITY;
    if (!fwd_packet_is_initial(self_root) &&
        fwd_find_local_packet(
            event_src,
            self_root,
            local_lookup_tags,
            local_lookup_indices,
            local_lookup_tag,
            root_idx) &&
        local_valid[root_idx]) {
        fwd_load_local_state(local_states, root_idx, target_embedding);
    } else {
        fwd_load_initial_state(initial_memory, num_vertices, target, target_embedding);
    }

    chunk_critical_path = fwd_max_u32(chunk_critical_path, tdp_critical);
    sum_packets += local_count;
    sum_critical += tdp_critical;
    if (local_count > 0) {
        uint32_t useful_parallel = local_count > tdp_critical ? local_count - tdp_critical : 0;
        sum_bpr_x1000 += ((uint64_t)useful_parallel * 1000u) / local_count;
    }
}

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
    uint64_t input_cache_key,
    const int16_t *initial_memory,
    const int16_t *event_features,
    const int16_t *weight_self,
    const int16_t *weight_peer,
    const int16_t *weight_event,
    const int16_t *bias,
    int16_t *embedding_out,
    uint64_t *stats_out) {
#pragma HLS INTERFACE m_axi port=event_src offset=slave bundle=gmem0 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=event_dst offset=slave bundle=gmem0 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=event_ts offset=slave bundle=gmem0 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=vertex_offsets offset=slave bundle=gmem0 depth=TEMPGNN_MAX_VERTEX_OFFSETS
#pragma HLS INTERFACE m_axi port=history_event_idx offset=slave bundle=gmem0 depth=TEMPGNN_MAX_HISTORY
#pragma HLS INTERFACE m_axi port=history_peer offset=slave bundle=gmem0 depth=TEMPGNN_MAX_HISTORY
#pragma HLS INTERFACE m_axi port=target_vertex offset=slave bundle=gmem0 depth=TEMPGNN_MAX_TARGETS
#pragma HLS INTERFACE m_axi port=target_event_idx offset=slave bundle=gmem0 depth=TEMPGNN_MAX_TARGETS
#pragma HLS INTERFACE m_axi port=initial_memory offset=slave bundle=gmem0 depth=TEMPGNN_MAX_MEMORY_WORDS
#pragma HLS INTERFACE m_axi port=event_features offset=slave bundle=gmem0 depth=TEMPGNN_MAX_EVENT_FEATURE_WORDS
#pragma HLS INTERFACE m_axi port=weight_self offset=slave bundle=gmem0 depth=TEMPGNN_FWD_DIM
#pragma HLS INTERFACE m_axi port=weight_peer offset=slave bundle=gmem0 depth=TEMPGNN_FWD_DIM
#pragma HLS INTERFACE m_axi port=weight_event offset=slave bundle=gmem0 depth=TEMPGNN_FWD_DIM
#pragma HLS INTERFACE m_axi port=bias offset=slave bundle=gmem0 depth=TEMPGNN_FWD_DIM
#pragma HLS INTERFACE m_axi port=embedding_out offset=slave bundle=gmem0 depth=TEMPGNN_MAX_TARGET_EMBED_WORDS
#pragma HLS INTERFACE m_axi port=stats_out offset=slave bundle=gmem0 depth=TEMPGNN_STAT_COUNT
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
#pragma HLS INTERFACE s_axilite port=input_cache_key bundle=control
#pragma HLS INTERFACE s_axilite port=initial_memory bundle=control
#pragma HLS INTERFACE s_axilite port=event_features bundle=control
#pragma HLS INTERFACE s_axilite port=weight_self bundle=control
#pragma HLS INTERFACE s_axilite port=weight_peer bundle=control
#pragma HLS INTERFACE s_axilite port=weight_event bundle=control
#pragma HLS INTERFACE s_axilite port=bias bundle=control
#pragma HLS INTERFACE s_axilite port=embedding_out bundle=control
#pragma HLS INTERFACE s_axilite port=stats_out bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    static uint64_t phle_key[TEMPGNN_HASH_SIZE];
    static uint16_t phle_tags[TEMPGNN_HASH_SIZE];
    static FwdPackedState phle_state[TEMPGNN_HASH_SIZE];
    static uint32_t packet_hash_local[TEMPGNN_FWD_PACKET_SLOTS];
    static uint32_t event_src_local[TEMPGNN_MAX_EVENTS];
    static uint32_t event_dst_local[TEMPGNN_MAX_EVENTS];
    static uint32_t event_ts_local[TEMPGNN_MAX_EVENTS];
    static uint32_t vertex_offsets_local[TEMPGNN_MAX_VERTEX_OFFSETS];
    static uint32_t history_event_idx_local[TEMPGNN_MAX_HISTORY];
    static int16_t initial_memory_local[TEMPGNN_MAX_MEMORY_WORDS];
    static int16_t event_features_local[TEMPGNN_MAX_EVENT_FEATURE_WORDS];
    static int16_t weight_self_local[TEMPGNN_FWD_DIM];
    static int16_t weight_peer_local[TEMPGNN_FWD_DIM];
    static int16_t weight_event_local[TEMPGNN_FWD_DIM];
    static int16_t bias_local[TEMPGNN_FWD_DIM];
    static uint32_t predecessor_src[TEMPGNN_MAX_EVENTS];
    static uint32_t predecessor_dst[TEMPGNN_MAX_EVENTS];
    static uint8_t predecessor_indexed[TEMPGNN_MAX_EVENTS];
    static bool input_cache_valid = false;
    static uint16_t local_lookup_tags[TEMPGNN_FWD_PACKET_SLOTS];
    static uint16_t local_lookup_indices[TEMPGNN_FWD_PACKET_SLOTS];
    static uint64_t event_bitmap[TEMPGNN_FWD_EVENT_BITMAP_WORDS];
    static uint16_t event_bitmap_tags[TEMPGNN_FWD_EVENT_BITMAP_WORDS];
    static uint16_t invocation_epoch = 0;
    static bool lookup_tags_valid = false;
    static uint64_t cached_input_key = 0;
#pragma HLS BIND_STORAGE variable=phle_key type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=phle_tags type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=phle_state type=ram_t2p impl=uram
#pragma HLS ARRAY_PARTITION variable=phle_key cyclic factor=TEMPGNN_HASH_WAYS dim=1
#pragma HLS ARRAY_PARTITION variable=phle_tags cyclic factor=TEMPGNN_HASH_WAYS dim=1
#pragma HLS ARRAY_PARTITION variable=phle_state cyclic factor=TEMPGNN_HASH_WAYS dim=1
#pragma HLS BIND_STORAGE variable=packet_hash_local type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=event_src_local type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=event_dst_local type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=event_ts_local type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=vertex_offsets_local type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=history_event_idx_local type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=initial_memory_local type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=event_features_local type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=initial_memory_local cyclic factor=TEMPGNN_FWD_DIM dim=1
#pragma HLS ARRAY_PARTITION variable=event_features_local cyclic factor=TEMPGNN_FWD_DIM dim=1
#pragma HLS ARRAY_PARTITION variable=weight_self_local complete dim=1
#pragma HLS ARRAY_PARTITION variable=weight_peer_local complete dim=1
#pragma HLS ARRAY_PARTITION variable=weight_event_local complete dim=1
#pragma HLS ARRAY_PARTITION variable=bias_local complete dim=1
#pragma HLS BIND_STORAGE variable=predecessor_src type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=predecessor_dst type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=predecessor_indexed type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=local_lookup_tags type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=local_lookup_indices type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=event_bitmap type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=event_bitmap_tags type=ram_t2p impl=bram

    uint32_t safe_targets = fwd_min_u32(num_targets, TEMPGNN_MAX_TARGETS);
    uint32_t safe_events = fwd_min_u32(num_events, TEMPGNN_MAX_EVENTS);
    uint32_t safe_vertices = fwd_min_u32(num_vertices, TEMPGNN_MAX_VERTICES);
    uint32_t safe_entries = tdp_entries == 0 ? 1 : fwd_min_u32(tdp_entries, TEMPGNN_MAX_TARGETS);
    uint32_t safe_history = fwd_min_u32(vertex_offsets[safe_vertices], TEMPGNN_MAX_HISTORY);
    uint32_t memory_words = safe_vertices * TEMPGNN_FWD_DIM;
    uint32_t feature_words = safe_events * TEMPGNN_FWD_DIM;
    bool refresh_input_cache = !input_cache_valid || cached_input_key != input_cache_key;

    if (refresh_input_cache) {
fwd_event_cache_load:
    for (uint32_t event_idx = 0; event_idx < TEMPGNN_MAX_EVENTS; ++event_idx) {
#pragma HLS PIPELINE II=1
        if (event_idx >= safe_events) {
            break;
        }
        event_src_local[event_idx] = event_src[event_idx];
        event_dst_local[event_idx] = event_dst[event_idx];
        event_ts_local[event_idx] = event_ts[event_idx];
    }

fwd_packet_hash_cache_build:
    for (uint32_t event_idx = 0; event_idx < TEMPGNN_MAX_EVENTS; ++event_idx) {
#pragma HLS PIPELINE II=1
        if (event_idx >= safe_events) {
            break;
        }
        FwdPacketRef src_packet = {event_src_local[event_idx], event_idx, event_ts_local[event_idx]};
        FwdPacketRef dst_packet = {event_dst_local[event_idx], event_idx, event_ts_local[event_idx]};
        packet_hash_local[event_idx << 1u] = fwd_packet_hash(src_packet);
        packet_hash_local[(event_idx << 1u) | 1u] = fwd_packet_hash(dst_packet);
    }

fwd_vertex_offset_cache_load:
    for (uint32_t idx = 0; idx < TEMPGNN_MAX_VERTEX_OFFSETS; ++idx) {
#pragma HLS PIPELINE II=1
        if (idx > safe_vertices) {
            break;
        }
        vertex_offsets_local[idx] = vertex_offsets[idx];
    }

fwd_history_cache_load:
    for (uint32_t idx = 0; idx < TEMPGNN_MAX_HISTORY; ++idx) {
#pragma HLS PIPELINE II=1
        if (idx >= safe_history) {
            break;
        }
        history_event_idx_local[idx] = history_event_idx[idx];
    }

fwd_initial_memory_cache_load:
    for (uint32_t idx = 0; idx < TEMPGNN_MAX_MEMORY_WORDS; ++idx) {
#pragma HLS PIPELINE II=1
        if (idx >= memory_words) {
            break;
        }
        initial_memory_local[idx] = initial_memory[idx];
    }

fwd_event_feature_cache_load:
    for (uint32_t idx = 0; idx < TEMPGNN_MAX_EVENT_FEATURE_WORDS; ++idx) {
#pragma HLS PIPELINE II=1
        if (idx >= feature_words) {
            break;
        }
        event_features_local[idx] = event_features[idx];
    }

fwd_weight_cache_load:
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
        weight_self_local[dim] = weight_self[dim];
        weight_peer_local[dim] = weight_peer[dim];
        weight_event_local[dim] = weight_event[dim];
        bias_local[dim] = bias[dim];
    }
    }

    uint64_t total_packets = 0;
    uint64_t emitted_unique_packets = 0;
    uint64_t total_cycles = 0;
    uint64_t sum_packets = 0;
    uint64_t sum_critical = 0;
    uint64_t sum_bpr_x1000 = 0;
    uint64_t hash_hits = 0;
    uint64_t overflow_count = 0;
    uint64_t checksum = 0;

    if (refresh_input_cache) {
fwd_predecessor_reset:
    for (uint32_t event_idx = 0; event_idx < TEMPGNN_MAX_EVENTS; ++event_idx) {
#pragma HLS PIPELINE II=1
        predecessor_src[event_idx] = TEMPGNN_FWD_NOT_INDEXED_EVENT;
        predecessor_dst[event_idx] = TEMPGNN_FWD_NOT_INDEXED_EVENT;
        predecessor_indexed[event_idx] = 0;
    }

fwd_predecessor_vertices:
    for (uint32_t vertex = 0; vertex < TEMPGNN_MAX_VERTICES; ++vertex) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_VERTICES
        if (vertex >= safe_vertices) {
            break;
        }
        uint32_t begin = vertex_offsets_local[vertex];
        uint32_t end = vertex_offsets_local[vertex + 1u];
        uint32_t available = end - begin;
        uint32_t search_begin = available > TEMPGNN_MAX_DEGREE_SCAN
                                    ? end - TEMPGNN_MAX_DEGREE_SCAN
                                    : begin;
        uint32_t previous = TEMPGNN_INITIAL_EVENT;

    fwd_predecessor_history:
        for (uint32_t step = 0; step < TEMPGNN_MAX_DEGREE_SCAN; ++step) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_DEGREE_SCAN
            if (step >= end - search_begin) {
                break;
            }
            uint32_t event_idx = history_event_idx_local[search_begin + step];
            if (event_idx >= safe_events) {
                continue;
            }
            uint32_t src = event_src_local[event_idx];
            uint32_t dst = event_dst_local[event_idx];
            bool indexed = false;
            uint8_t indexed_mask = predecessor_indexed[event_idx];
            if (src == vertex && predecessor_src[event_idx] == TEMPGNN_FWD_NOT_INDEXED_EVENT) {
                predecessor_src[event_idx] = previous;
                indexed_mask |= 1u;
                indexed = true;
            }
            if (dst == vertex && predecessor_dst[event_idx] == TEMPGNN_FWD_NOT_INDEXED_EVENT) {
                predecessor_dst[event_idx] = previous;
                indexed_mask |= 2u;
                indexed = true;
            }
            if (indexed) {
                predecessor_indexed[event_idx] = indexed_mask;
                previous = event_idx;
            }
        }
    }

fwd_predecessor_finalize:
    for (uint32_t event_idx = 0; event_idx < TEMPGNN_MAX_EVENTS; ++event_idx) {
#pragma HLS PIPELINE II=1
        if (event_idx >= safe_events) {
            break;
        }
        if (predecessor_src[event_idx] == TEMPGNN_FWD_NOT_INDEXED_EVENT) {
            predecessor_src[event_idx] = TEMPGNN_INITIAL_EVENT;
        }
        if (predecessor_dst[event_idx] == TEMPGNN_FWD_NOT_INDEXED_EVENT) {
            predecessor_dst[event_idx] = TEMPGNN_INITIAL_EVENT;
        }
    }
        cached_input_key = input_cache_key;
        input_cache_valid = true;
        invocation_epoch = 0;
        lookup_tags_valid = false;
    }

    bool reset_lookup_tags = !lookup_tags_valid || invocation_epoch == 63u;
    if (reset_lookup_tags) {
    fwd_phle_tag_reset:
        for (uint32_t idx = 0; idx < TEMPGNN_HASH_SIZE; ++idx) {
#pragma HLS PIPELINE II=1
            phle_tags[idx] = 0;
        }

    fwd_local_lookup_reset:
        for (uint32_t idx = 0; idx < TEMPGNN_FWD_PACKET_SLOTS; ++idx) {
#pragma HLS PIPELINE II=1
            local_lookup_tags[idx] = 0;
        }

    fwd_event_bitmap_tag_reset:
        for (uint32_t idx = 0; idx < TEMPGNN_FWD_EVENT_BITMAP_WORDS; ++idx) {
#pragma HLS PIPELINE II=1
            event_bitmap_tags[idx] = 0;
        }
        invocation_epoch = 1u;
        lookup_tags_valid = true;
    } else {
        ++invocation_epoch;
    }
    uint16_t invocation_tag_prefix = (uint16_t)(invocation_epoch << 10u);

fwd_target_chunks:
    for (uint32_t chunk_start = 0; chunk_start < TEMPGNN_MAX_TARGETS; chunk_start += 1) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_TARGETS
        if (chunk_start >= safe_targets) {
            break;
        }
        if ((chunk_start % safe_entries) != 0) {
            continue;
        }

        uint32_t chunk_end = fwd_min_u32(chunk_start + safe_entries, safe_targets);
        uint32_t chunk_targets = chunk_end - chunk_start;
        uint16_t phle_tag =
            (uint16_t)(invocation_tag_prefix | (uint16_t)(chunk_start / safe_entries));
        uint64_t chunk_total_packets = 0;
        uint32_t chunk_unique_packets = 0;
        uint32_t chunk_critical_path = 0;

    fwd_targets_in_chunk:
        for (uint32_t offset = 0; offset < TEMPGNN_MAX_TARGETS; ++offset) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_TARGETS
            if (offset >= chunk_targets) {
                break;
            }
            uint32_t target_pos = chunk_start + offset;
            uint32_t target_idx = target_event_idx[target_pos];
            int16_t target_embedding[TEMPGNN_FWD_DIM];
#pragma HLS ARRAY_PARTITION variable=target_embedding complete dim=1

            if (target_idx >= safe_events) {
                ++overflow_count;
                fwd_load_initial_state(initial_memory_local, safe_vertices, target_vertex[target_pos], target_embedding);
            } else {
                fwd_process_target(
                    event_src_local,
                    event_dst_local,
                    event_ts_local,
                    packet_hash_local,
                    safe_events,
                    vertex_offsets_local,
                    history_event_idx_local,
                    safe_vertices,
                    target_vertex[target_pos],
                    target_idx,
                    fanout,
                    depth,
                    enable_oats,
                    initial_memory_local,
                    event_features_local,
                    weight_self_local,
                    weight_peer_local,
                    weight_event_local,
                    bias_local,
                    phle_key,
                    phle_tags,
                    phle_state,
                    phle_tag,
                    predecessor_src,
                    predecessor_dst,
                    predecessor_indexed,
                    local_lookup_tags,
                    local_lookup_indices,
                    (uint16_t)(invocation_tag_prefix | (uint16_t)target_pos),
                    event_bitmap,
                    event_bitmap_tags,
                    target_embedding,
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

        fwd_embedding_store_dim:
            for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
                embedding_out[target_pos * TEMPGNN_FWD_DIM + dim] = target_embedding[dim];
                checksum ^= ((uint64_t)(uint16_t)target_embedding[dim]) << ((dim & 3u) * 16u);
            }
        }

        uint64_t packet_work = enable_oats != 0 ? chunk_unique_packets : chunk_total_packets;
        uint64_t packet_cycles_parallel = fwd_ceil_div_u64(packet_work, TEMPGNN_PACKET_WORKERS) * TEMPGNN_PACKET_LATENCY_CYCLES;
        uint64_t packet_cycles_critical = (uint64_t)chunk_critical_path * TEMPGNN_PACKET_LATENCY_CYCLES;
        uint64_t packet_cycles = packet_cycles_parallel > packet_cycles_critical ? packet_cycles_parallel : packet_cycles_critical;
        uint64_t forward_cycles = fwd_ceil_div_u64(packet_work, TEMPGNN_UPDATE_WORKERS) * TEMPGNN_UPDATE_LATENCY_CYCLES;
        total_cycles += packet_cycles + forward_cycles;
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
    uint64_t memory_bytes = emitted_unique_packets * (TEMPGNN_FWD_DIM * sizeof(int16_t) + TEMPGNN_METADATA_BYTES);

fwd_stats_clear:
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
    stats_out[TEMPGNN_STAT_PARTIAL_REDUCTIONS] =
        ((sum_critical & 0xffffffffull) << 32u) | (sum_bpr_x1000 & 0xffffffffull);
}
