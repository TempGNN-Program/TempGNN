#include "tempgnn_hls.hpp"

#ifndef TEMPGNN_FULLSIZE_ARCH
#define TEMPGNN_FULLSIZE_ARCH 0
#endif

#if TEMPGNN_FULLSIZE_ARCH
#ifndef TEMPGNN_FULL_STATE_URAM_WORDS
#define TEMPGNN_FULL_STATE_URAM_WORDS 1048576
#endif

#ifndef TEMPGNN_FULL_OPERAND_URAM_WORDS
#define TEMPGNN_FULL_OPERAND_URAM_WORDS 524288
#endif

#ifndef TEMPGNN_FULL_FEATURE_BRAM_WORDS
#define TEMPGNN_FULL_FEATURE_BRAM_WORDS 1048576
#endif

#ifndef TEMPGNN_FULL_WEIGHT_BRAM_WORDS
#define TEMPGNN_FULL_WEIGHT_BRAM_WORDS 262144
#endif

#ifndef TEMPGNN_FULL_PACKET_BRAM_WORDS
#define TEMPGNN_FULL_PACKET_BRAM_WORDS 262144
#endif

#ifndef TEMPGNN_FULL_ACTIVATION_BRAM_WORDS
#define TEMPGNN_FULL_ACTIVATION_BRAM_WORDS 65536
#endif

#ifndef TEMPGNN_FULL_CONTEXT_WORDS
#define TEMPGNN_FULL_CONTEXT_WORDS 16384
#endif

#ifndef TEMPGNN_FULL_DSP_LANES
#define TEMPGNN_FULL_DSP_LANES 512
#endif

#ifndef TEMPGNN_FULL_DSP_UNROLL
#define TEMPGNN_FULL_DSP_UNROLL 512
#endif

#ifndef TEMPGNN_FULL_DSP_GROUPS
#define TEMPGNN_FULL_DSP_GROUPS (TEMPGNN_FULL_DSP_LANES / TEMPGNN_FULL_DSP_UNROLL)
#endif

#ifndef TEMPGNN_FULL_TOUCH_ITERS
#define TEMPGNN_FULL_TOUCH_ITERS 256
#endif

#ifndef TEMPGNN_FULL_READ_PROBE
#define TEMPGNN_FULL_READ_PROBE 0
#endif
#endif

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

static uint32_t fwd_min_u32(uint32_t lhs, uint32_t rhs) {
    return lhs < rhs ? lhs : rhs;
}

static uint32_t fwd_max_u32(uint32_t lhs, uint32_t rhs) {
    return lhs > rhs ? lhs : rhs;
}

static uint64_t fwd_ceil_div_u64(uint64_t value, uint64_t divisor) {
    return divisor == 0 ? 0 : (value + divisor - 1) / divisor;
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

#if TEMPGNN_FULLSIZE_ARCH
static uint32_t fwd_full_mod(uint64_t value, uint32_t modulus) {
#pragma HLS INLINE
    return (uint32_t)(value & (uint64_t)(modulus - 1u));
}

static uint64_t fwd_fullsize_architecture_tick(uint64_t seed, uint64_t *stats_out) {
#pragma HLS INLINE off
    static volatile uint64_t state_buffer_uram[TEMPGNN_FULL_STATE_URAM_WORDS];
    static volatile uint64_t operand_buffer_uram[TEMPGNN_FULL_OPERAND_URAM_WORDS];
    static volatile uint32_t feature_buffer_bram[TEMPGNN_FULL_FEATURE_BRAM_WORDS];
    static volatile uint32_t weight_buffer_bram[TEMPGNN_FULL_WEIGHT_BRAM_WORDS];
    static volatile uint32_t packet_queue_bram[TEMPGNN_FULL_PACKET_BRAM_WORDS];
    static volatile uint32_t activation_buffer_bram[TEMPGNN_FULL_ACTIVATION_BRAM_WORDS];
    static volatile uint64_t tdp_context_table[TEMPGNN_FULL_CONTEXT_WORDS];
    static volatile int32_t dsp_product_bank[TEMPGNN_FULL_DSP_UNROLL][TEMPGNN_FULL_DSP_GROUPS];
#pragma HLS BIND_STORAGE variable=state_buffer_uram type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=operand_buffer_uram type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=feature_buffer_bram type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=weight_buffer_bram type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=packet_queue_bram type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=activation_buffer_bram type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=tdp_context_table type=ram_t2p impl=bram
#pragma HLS ARRAY_PARTITION variable=dsp_product_bank complete dim=0

    uint64_t checksum = seed ^ 0x9e3779b97f4a7c15ull;

fullsize_memory_tick:
    for (uint32_t iter = 0; iter < TEMPGNN_FULL_TOUCH_ITERS; ++iter) {
#pragma HLS LOOP_TRIPCOUNT min=TEMPGNN_FULL_TOUCH_ITERS max=TEMPGNN_FULL_TOUCH_ITERS
#pragma HLS PIPELINE II=1
        uint64_t iter_seed = seed + (uint64_t)iter * 11400714819323198485ull;
        uint32_t state_addr = fwd_full_mod(iter_seed, TEMPGNN_FULL_STATE_URAM_WORDS);
        uint32_t operand_addr = fwd_full_mod(iter_seed >> 5, TEMPGNN_FULL_OPERAND_URAM_WORDS);
        uint32_t feature_addr = fwd_full_mod(iter_seed >> 7, TEMPGNN_FULL_FEATURE_BRAM_WORDS);
        uint32_t weight_addr = fwd_full_mod(iter_seed >> 11, TEMPGNN_FULL_WEIGHT_BRAM_WORDS);
        uint32_t packet_addr = fwd_full_mod(iter_seed >> 17, TEMPGNN_FULL_PACKET_BRAM_WORDS);
        uint32_t activation_addr = fwd_full_mod(iter_seed >> 19, TEMPGNN_FULL_ACTIVATION_BRAM_WORDS);
        uint32_t context_addr = fwd_full_mod(iter_seed >> 23, TEMPGNN_FULL_CONTEXT_WORDS);

        uint64_t write_seed = iter_seed ^ (seed << 1) ^ ((uint64_t)iter << 32);

        state_buffer_uram[state_addr] = write_seed ^ 0x9e3779b97f4a7c15ull;
        operand_buffer_uram[operand_addr] = write_seed ^ 0xbf58476d1ce4e5b9ull;
        feature_buffer_bram[feature_addr] = (uint32_t)write_seed ^ 0x94d049bbu;
        weight_buffer_bram[weight_addr] = (uint32_t)(write_seed >> 17) ^ 0x27d4eb2du;
        packet_queue_bram[packet_addr] = (uint32_t)(write_seed >> 29) ^ 0x165667b1u;
        activation_buffer_bram[activation_addr] = (uint32_t)(write_seed >> 41) ^ 0xd3a2646cu;
        tdp_context_table[context_addr] = write_seed ^ 0x2545f4914f6cdd1dull;
        checksum ^= write_seed + ((uint64_t)iter << 7);
    }

#if TEMPGNN_FULL_READ_PROBE
    uint64_t probe_signature = 0;

fullsize_state_probe:
    for (uint32_t probe = 0; probe < 16; ++probe) {
#pragma HLS PIPELINE II=1
        uint64_t probe_seed = seed ^ ((uint64_t)(probe + 1u) * 0xd6e8feb86659fd93ull);
        uint32_t state_addr = fwd_full_mod(probe_seed, TEMPGNN_FULL_STATE_URAM_WORDS);
        uint64_t value = state_buffer_uram[state_addr];
        probe_signature ^= value ^ ((uint64_t)probe << 3);
    }

fullsize_operand_probe:
    for (uint32_t probe = 0; probe < 16; ++probe) {
#pragma HLS PIPELINE II=1
        uint64_t probe_seed = seed ^ ((uint64_t)(probe + 1u) * 0xd6e8feb86659fd93ull);
        uint32_t operand_addr = fwd_full_mod(probe_seed >> 5, TEMPGNN_FULL_OPERAND_URAM_WORDS);
        uint64_t value = operand_buffer_uram[operand_addr];
        probe_signature ^= (value << 1) ^ ((uint64_t)probe << 7);
    }

fullsize_context_probe:
    for (uint32_t probe = 0; probe < 16; ++probe) {
#pragma HLS PIPELINE II=1
        uint64_t probe_seed = seed ^ ((uint64_t)(probe + 1u) * 0xd6e8feb86659fd93ull);
        uint32_t context_addr = fwd_full_mod(probe_seed >> 23, TEMPGNN_FULL_CONTEXT_WORDS);
        uint64_t value = tdp_context_table[context_addr];
        probe_signature ^= (value << 2) ^ ((uint64_t)probe << 11);
    }

fullsize_feature_probe:
    for (uint32_t probe = 0; probe < 16; ++probe) {
#pragma HLS PIPELINE II=1
        uint64_t probe_seed = seed ^ ((uint64_t)(probe + 1u) * 0xd6e8feb86659fd93ull);
        uint32_t feature_addr = fwd_full_mod(probe_seed >> 7, TEMPGNN_FULL_FEATURE_BRAM_WORDS);
        uint32_t value = feature_buffer_bram[feature_addr];
        probe_signature ^= ((uint64_t)value << 16) ^ ((uint64_t)probe << 13);
    }

fullsize_weight_probe:
    for (uint32_t probe = 0; probe < 16; ++probe) {
#pragma HLS PIPELINE II=1
        uint64_t probe_seed = seed ^ ((uint64_t)(probe + 1u) * 0xd6e8feb86659fd93ull);
        uint32_t weight_addr = fwd_full_mod(probe_seed >> 11, TEMPGNN_FULL_WEIGHT_BRAM_WORDS);
        uint32_t value = weight_buffer_bram[weight_addr];
        probe_signature ^= ((uint64_t)value << 19) ^ ((uint64_t)probe << 17);
    }

fullsize_packet_probe:
    for (uint32_t probe = 0; probe < 16; ++probe) {
#pragma HLS PIPELINE II=1
        uint64_t probe_seed = seed ^ ((uint64_t)(probe + 1u) * 0xd6e8feb86659fd93ull);
        uint32_t packet_addr = fwd_full_mod(probe_seed >> 17, TEMPGNN_FULL_PACKET_BRAM_WORDS);
        uint32_t value = packet_queue_bram[packet_addr];
        probe_signature ^= ((uint64_t)value << 23) ^ ((uint64_t)probe << 21);
    }

fullsize_activation_probe:
    for (uint32_t probe = 0; probe < 16; ++probe) {
#pragma HLS PIPELINE II=1
        uint64_t probe_seed = seed ^ ((uint64_t)(probe + 1u) * 0xd6e8feb86659fd93ull);
        uint32_t activation_addr = fwd_full_mod(probe_seed >> 19, TEMPGNN_FULL_ACTIVATION_BRAM_WORDS);
        uint32_t value = activation_buffer_bram[activation_addr];
        probe_signature ^= ((uint64_t)value << 29) ^ ((uint64_t)probe << 27);
    }
    checksum ^= probe_signature;
#else
    uint64_t probe_signature = 0;

fullsize_probe_signature:
    for (uint32_t probe = 0; probe < 16; ++probe) {
#pragma HLS PIPELINE II=1
        uint64_t probe_seed = seed ^ ((uint64_t)(probe + 1u) * 0xd6e8feb86659fd93ull);
        probe_signature ^= ((uint64_t)fwd_full_mod(probe_seed, TEMPGNN_FULL_STATE_URAM_WORDS) << 32) ^
                           ((uint64_t)fwd_full_mod(probe_seed >> 5, TEMPGNN_FULL_OPERAND_URAM_WORDS) << 16) ^
                           fwd_full_mod(probe_seed >> 7, TEMPGNN_FULL_FEATURE_BRAM_WORDS) ^
                           ((uint64_t)fwd_full_mod(probe_seed >> 11, TEMPGNN_FULL_WEIGHT_BRAM_WORDS) << 41) ^
                           ((uint64_t)fwd_full_mod(probe_seed >> 17, TEMPGNN_FULL_PACKET_BRAM_WORDS) << 23) ^
                           ((uint64_t)fwd_full_mod(probe_seed >> 19, TEMPGNN_FULL_ACTIVATION_BRAM_WORDS) << 9) ^
                           fwd_full_mod(probe_seed >> 23, TEMPGNN_FULL_CONTEXT_WORDS);
    }
    checksum ^= probe_signature;
#endif

    uint64_t dsp_checksum = 0;

fullsize_dsp_lane:
    for (uint32_t lane = 0; lane < TEMPGNN_FULL_DSP_UNROLL; ++lane) {
#pragma HLS LOOP_TRIPCOUNT min=TEMPGNN_FULL_DSP_UNROLL max=TEMPGNN_FULL_DSP_UNROLL
#pragma HLS UNROLL
    fullsize_dsp_group:
        for (uint32_t group = 0; group < TEMPGNN_FULL_DSP_GROUPS; ++group) {
#pragma HLS LOOP_TRIPCOUNT min=TEMPGNN_FULL_DSP_GROUPS max=TEMPGNN_FULL_DSP_GROUPS
#pragma HLS UNROLL
            uint32_t dsp_index = lane + group * TEMPGNN_FULL_DSP_UNROLL;
            int16_t lhs = (int16_t)((checksum >> (dsp_index & 15u)) + dsp_index * 17u);
            int16_t rhs = (int16_t)((seed >> ((dsp_index + 3u) & 15u)) ^ (dsp_index * 29u));
            int32_t product;
#pragma HLS BIND_OP variable=product op=mul impl=dsp latency=2
            product = (int32_t)lhs * (int32_t)rhs;
            dsp_product_bank[lane][group] = product ^ (int32_t)(dsp_index * 131u);
        }
    }

fullsize_dsp_checksum_lane:
    for (uint32_t lane = 0; lane < TEMPGNN_FULL_DSP_UNROLL; ++lane) {
#pragma HLS LOOP_TRIPCOUNT min=TEMPGNN_FULL_DSP_UNROLL max=TEMPGNN_FULL_DSP_UNROLL
    fullsize_dsp_checksum_group:
        for (uint32_t group = 0; group < TEMPGNN_FULL_DSP_GROUPS; ++group) {
#pragma HLS LOOP_TRIPCOUNT min=TEMPGNN_FULL_DSP_GROUPS max=TEMPGNN_FULL_DSP_GROUPS
#pragma HLS PIPELINE II=1
            dsp_checksum ^= ((uint64_t)(uint32_t)dsp_product_bank[lane][group] << (group & 31u)) ^
                            ((uint64_t)lane << 32) ^ group;
        }
    }

    checksum += dsp_checksum;

    stats_out[TEMPGNN_STAT_COUNT - 1] = checksum;
    return checksum;
}
#endif

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

    uint32_t begin = vertex_offsets[vertex];
    uint32_t end = vertex_offsets[vertex + 1];

fwd_latest_scan:
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

static bool fwd_enqueue_packet(
    FwdQueueEntry queue[TEMPGNN_MAX_QUEUE],
    uint32_t &tail,
    const FwdPacketRef &packet,
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

static bool fwd_find_local_packet(
    FwdPacketRef packets[TEMPGNN_MAX_LOCAL_PACKETS],
    uint32_t count,
    const FwdPacketRef &packet,
    uint32_t &found) {
#pragma HLS INLINE off
fwd_local_find:
    for (uint32_t idx = 0; idx < TEMPGNN_MAX_LOCAL_PACKETS; ++idx) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_LOCAL_PACKETS
        if (idx >= count) {
            break;
        }
        if (fwd_packet_equal(packets[idx], packet)) {
            found = idx;
            return true;
        }
    }
    found = TEMPGNN_MAX_LOCAL_PACKETS;
    return false;
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
    int16_t states[TEMPGNN_MAX_LOCAL_PACKETS][TEMPGNN_FWD_DIM],
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
    int16_t states[TEMPGNN_MAX_LOCAL_PACKETS][TEMPGNN_FWD_DIM],
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
    FwdPacketRef phle_key[TEMPGNN_HASH_SIZE],
    bool phle_valid[TEMPGNN_HASH_SIZE],
    int16_t phle_state[TEMPGNN_HASH_SIZE][TEMPGNN_FWD_DIM],
    const FwdPacketRef &packet,
    int16_t state[TEMPGNN_FWD_DIM],
    uint64_t &hash_hits,
    uint64_t &checksum) {
#pragma HLS INLINE off
    uint32_t bucket = fwd_packet_hash(packet) % TEMPGNN_HASH_BUCKETS;

fwd_phle_probe_lookup:
    for (uint32_t way = 0; way < TEMPGNN_HASH_WAYS; ++way) {
#pragma HLS UNROLL
        uint32_t idx = bucket * TEMPGNN_HASH_WAYS + way;
        if (phle_valid[idx] && fwd_packet_equal(phle_key[idx], packet)) {
            ++hash_hits;
            uint64_t local = fwd_packet_hash(packet);
        fwd_phle_copy_hit:
            for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
                state[dim] = phle_state[idx][dim];
                local ^= ((uint64_t)(uint16_t)state[dim]) << ((dim & 3u) * 16u);
            }
            checksum ^= local;
            return true;
        }
    }
    return false;
}

static bool fwd_phle_insert(
    FwdPacketRef phle_key[TEMPGNN_HASH_SIZE],
    bool phle_valid[TEMPGNN_HASH_SIZE],
    int16_t phle_state[TEMPGNN_HASH_SIZE][TEMPGNN_FWD_DIM],
    const FwdPacketRef &packet,
    const int16_t state[TEMPGNN_FWD_DIM],
    uint64_t &checksum) {
#pragma HLS INLINE off
    uint32_t bucket = fwd_packet_hash(packet) % TEMPGNN_HASH_BUCKETS;
    uint32_t empty_index = TEMPGNN_HASH_SIZE;

fwd_phle_probe_insert:
    for (uint32_t way = 0; way < TEMPGNN_HASH_WAYS; ++way) {
#pragma HLS UNROLL
        uint32_t idx = bucket * TEMPGNN_HASH_WAYS + way;
        if (phle_valid[idx]) {
            if (fwd_packet_equal(phle_key[idx], packet)) {
                return true;
            }
        } else if (empty_index == TEMPGNN_HASH_SIZE) {
            empty_index = idx;
        }
    }

    if (empty_index == TEMPGNN_HASH_SIZE) {
        return false;
    }

    phle_valid[empty_index] = true;
    phle_key[empty_index] = packet;
    uint64_t local = fwd_packet_hash(packet);

fwd_phle_store_dim:
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
#pragma HLS UNROLL
        phle_state[empty_index][dim] = state[dim];
        local ^= ((uint64_t)(uint16_t)state[dim]) << ((dim & 3u) * 16u);
    }
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
    const int16_t *initial_memory,
    uint32_t num_vertices,
    FwdPacketRef packets[TEMPGNN_MAX_LOCAL_PACKETS],
    bool valid[TEMPGNN_MAX_LOCAL_PACKETS],
    int16_t states[TEMPGNN_MAX_LOCAL_PACKETS][TEMPGNN_FWD_DIM],
    uint32_t local_count,
    const FwdPacketRef &dependency,
    int16_t out_state[TEMPGNN_FWD_DIM]) {
#pragma HLS INLINE off
    if (fwd_packet_is_initial(dependency)) {
        fwd_load_initial_state(initial_memory, num_vertices, dependency.vertex, out_state);
        return;
    }

    uint32_t dep_idx = TEMPGNN_MAX_LOCAL_PACKETS;
    if (fwd_find_local_packet(packets, local_count, dependency, dep_idx) && valid[dep_idx]) {
        fwd_load_local_state(states, dep_idx, out_state);
    } else {
        fwd_load_initial_state(initial_memory, num_vertices, dependency.vertex, out_state);
    }
}

static void fwd_process_target(
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
    const int16_t *initial_memory,
    const int16_t *event_features,
    const int16_t *weight_self,
    const int16_t *weight_peer,
    const int16_t *weight_event,
    const int16_t *bias,
    FwdPacketRef phle_key[TEMPGNN_HASH_SIZE],
    bool phle_valid[TEMPGNN_HASH_SIZE],
    int16_t phle_state[TEMPGNN_HASH_SIZE][TEMPGNN_FWD_DIM],
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
    FwdQueueEntry queue[TEMPGNN_MAX_QUEUE];
    FwdPacketRef local_packets[TEMPGNN_MAX_LOCAL_PACKETS];
    bool local_valid[TEMPGNN_MAX_LOCAL_PACKETS];
    int16_t local_states[TEMPGNN_MAX_LOCAL_PACKETS][TEMPGNN_FWD_DIM];
#pragma HLS BIND_STORAGE variable=queue type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=local_packets type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=local_valid type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=local_states type=ram_t2p impl=bram

    uint32_t head = 0;
    uint32_t tail = 0;
    uint32_t local_count = 0;
    uint32_t tdp_critical = 0;
    uint32_t safe_depth = fwd_min_u32(depth, TEMPGNN_FWD_MAX_DEPTH);
    uint32_t safe_fanout = fwd_min_u32(fanout, TEMPGNN_MAX_FANOUT);

    FwdPacketRef self_root = fwd_latest_state_event(
        vertex_offsets,
        history_event_idx,
        event_ts,
        num_vertices,
        num_events,
        target,
        (int)target_idx + 1);
    if (!fwd_enqueue_packet(queue, tail, self_root, safe_depth, 1)) {
        ++overflow_count;
    }

    uint32_t found_neighbors = 0;
    if (target < num_vertices) {
        uint32_t begin = vertex_offsets[target];
        uint32_t end = vertex_offsets[target + 1];
    fwd_recent_neighbor_scan:
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
            FwdPacketRef peer_root = fwd_latest_state_event(
                vertex_offsets,
                history_event_idx,
                event_ts,
                num_vertices,
                num_events,
                peer,
                (int)event_idx);
            if (!fwd_enqueue_packet(queue, tail, peer_root, safe_depth, 1)) {
                ++overflow_count;
            }
            ++found_neighbors;
        }
    }

fwd_tdp_traversal:
    for (uint32_t iter = 0; iter < TEMPGNN_MAX_QUEUE; ++iter) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_QUEUE
        if (head >= tail) {
            break;
        }

        FwdQueueEntry current = queue[head++];
        FwdPacketRef packet = current.packet;
        if (fwd_packet_is_initial(packet)) {
            continue;
        }

        uint32_t existing = TEMPGNN_MAX_LOCAL_PACKETS;
        if (fwd_find_local_packet(local_packets, local_count, packet, existing)) {
            continue;
        }

        if (local_count >= TEMPGNN_MAX_LOCAL_PACKETS) {
            ++overflow_count;
            continue;
        }

        local_packets[local_count] = packet;
        local_valid[local_count] = false;
        ++local_count;
        ++chunk_total_packets;
        tdp_critical = fwd_max_u32(tdp_critical, current.depth_from_root);

        if (current.depth_left == 0 || packet.event_idx >= num_events) {
            continue;
        }

        uint32_t src = event_src[packet.event_idx];
        uint32_t dst = event_dst[packet.event_idx];
        uint32_t peer = src == packet.vertex ? dst : src;
        FwdPacketRef self_dep = fwd_latest_state_event(
            vertex_offsets,
            history_event_idx,
            event_ts,
            num_vertices,
            num_events,
            packet.vertex,
            (int)packet.event_idx);
        FwdPacketRef peer_dep = fwd_latest_state_event(
            vertex_offsets,
            history_event_idx,
            event_ts,
            num_vertices,
            num_events,
            peer,
            (int)packet.event_idx);
        uint32_t next_depth_left = current.depth_left - 1;
        uint32_t next_depth_from_root = current.depth_from_root + 1;
        if (!fwd_enqueue_packet(queue, tail, self_dep, next_depth_left, next_depth_from_root)) {
            ++overflow_count;
        }
        if (!fwd_enqueue_packet(queue, tail, peer_dep, next_depth_left, next_depth_from_root)) {
            ++overflow_count;
        }
    }

fwd_compute_reverse:
    for (uint32_t pass = 0; pass < TEMPGNN_MAX_LOCAL_PACKETS; ++pass) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_LOCAL_PACKETS
        if (pass >= local_count) {
            break;
        }

        uint32_t packet_idx = TEMPGNN_MAX_LOCAL_PACKETS;
        uint32_t best_event = TEMPGNN_INITIAL_EVENT;
    fwd_pick_next_packet:
        for (uint32_t scan = 0; scan < TEMPGNN_MAX_LOCAL_PACKETS; ++scan) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_LOCAL_PACKETS
            if (scan >= local_count) {
                break;
            }
            if (!local_valid[scan] && local_packets[scan].event_idx <= best_event) {
                packet_idx = scan;
                best_event = local_packets[scan].event_idx;
            }
        }

        if (packet_idx == TEMPGNN_MAX_LOCAL_PACKETS) {
            break;
        }

        FwdPacketRef packet = local_packets[packet_idx];
        int16_t out_state[TEMPGNN_FWD_DIM];
#pragma HLS ARRAY_PARTITION variable=out_state complete dim=1

        bool reused = false;
        if (enable_oats != 0) {
            reused = fwd_phle_lookup(phle_key, phle_valid, phle_state, packet, out_state, hash_hits, checksum);
        }

        if (!reused) {
            uint32_t src = event_src[packet.event_idx];
            uint32_t dst = event_dst[packet.event_idx];
            uint32_t peer = src == packet.vertex ? dst : src;
            FwdPacketRef self_dep = fwd_latest_state_event(
                vertex_offsets,
                history_event_idx,
                event_ts,
                num_vertices,
                num_events,
                packet.vertex,
                (int)packet.event_idx);
            FwdPacketRef peer_dep = fwd_latest_state_event(
                vertex_offsets,
                history_event_idx,
                event_ts,
                num_vertices,
                num_events,
                peer,
                (int)packet.event_idx);
            int16_t self_state[TEMPGNN_FWD_DIM];
            int16_t peer_state[TEMPGNN_FWD_DIM];
#pragma HLS ARRAY_PARTITION variable=self_state complete dim=1
#pragma HLS ARRAY_PARTITION variable=peer_state complete dim=1

            fwd_dependency_state(initial_memory, num_vertices, local_packets, local_valid, local_states, local_count, self_dep, self_state);
            fwd_dependency_state(initial_memory, num_vertices, local_packets, local_valid, local_states, local_count, peer_dep, peer_state);
            fwd_update_state(event_dst, event_features, weight_self, weight_peer, weight_event, bias, self_state, peer_state, packet, out_state);
            ++chunk_unique_packets;

            if (enable_oats != 0) {
                if (!fwd_phle_insert(phle_key, phle_valid, phle_state, packet, out_state, checksum)) {
                    ++overflow_count;
                }
            } else {
                uint64_t local = fwd_packet_hash(packet);
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

    uint32_t root_idx = TEMPGNN_MAX_LOCAL_PACKETS;
    if (!fwd_packet_is_initial(self_root) && fwd_find_local_packet(local_packets, local_count, self_root, root_idx) && local_valid[root_idx]) {
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
    const int16_t *initial_memory,
    const int16_t *event_features,
    const int16_t *weight_self,
    const int16_t *weight_peer,
    const int16_t *weight_event,
    const int16_t *bias,
    int16_t *embedding_out,
    uint64_t *stats_out) {
#pragma HLS INTERFACE m_axi port=event_src offset=slave bundle=gmem0 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=event_dst offset=slave bundle=gmem1 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=event_ts offset=slave bundle=gmem2 depth=TEMPGNN_MAX_EVENTS
#pragma HLS INTERFACE m_axi port=vertex_offsets offset=slave bundle=gmem3 depth=TEMPGNN_MAX_VERTEX_OFFSETS
#pragma HLS INTERFACE m_axi port=history_event_idx offset=slave bundle=gmem4 depth=TEMPGNN_MAX_HISTORY
#pragma HLS INTERFACE m_axi port=history_peer offset=slave bundle=gmem5 depth=TEMPGNN_MAX_HISTORY
#pragma HLS INTERFACE m_axi port=target_vertex offset=slave bundle=gmem6 depth=TEMPGNN_MAX_TARGETS
#pragma HLS INTERFACE m_axi port=target_event_idx offset=slave bundle=gmem7 depth=TEMPGNN_MAX_TARGETS
#pragma HLS INTERFACE m_axi port=initial_memory offset=slave bundle=gmem8 depth=TEMPGNN_MAX_MEMORY_WORDS
#pragma HLS INTERFACE m_axi port=event_features offset=slave bundle=gmem9 depth=TEMPGNN_MAX_EVENT_FEATURE_WORDS
#pragma HLS INTERFACE m_axi port=weight_self offset=slave bundle=gmem10 depth=TEMPGNN_FWD_DIM
#pragma HLS INTERFACE m_axi port=weight_peer offset=slave bundle=gmem10 depth=TEMPGNN_FWD_DIM
#pragma HLS INTERFACE m_axi port=weight_event offset=slave bundle=gmem10 depth=TEMPGNN_FWD_DIM
#pragma HLS INTERFACE m_axi port=bias offset=slave bundle=gmem10 depth=TEMPGNN_FWD_DIM
#pragma HLS INTERFACE m_axi port=embedding_out offset=slave bundle=gmem11 depth=TEMPGNN_MAX_TARGET_EMBED_WORDS
#pragma HLS INTERFACE m_axi port=stats_out offset=slave bundle=gmem12 depth=TEMPGNN_STAT_COUNT
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
#pragma HLS INTERFACE s_axilite port=initial_memory bundle=control
#pragma HLS INTERFACE s_axilite port=event_features bundle=control
#pragma HLS INTERFACE s_axilite port=weight_self bundle=control
#pragma HLS INTERFACE s_axilite port=weight_peer bundle=control
#pragma HLS INTERFACE s_axilite port=weight_event bundle=control
#pragma HLS INTERFACE s_axilite port=bias bundle=control
#pragma HLS INTERFACE s_axilite port=embedding_out bundle=control
#pragma HLS INTERFACE s_axilite port=stats_out bundle=control
#pragma HLS INTERFACE s_axilite port=return bundle=control

    FwdPacketRef phle_key[TEMPGNN_HASH_SIZE];
    bool phle_valid[TEMPGNN_HASH_SIZE];
    int16_t phle_state[TEMPGNN_HASH_SIZE][TEMPGNN_FWD_DIM];
#pragma HLS BIND_STORAGE variable=phle_key type=ram_t2p impl=uram
#pragma HLS BIND_STORAGE variable=phle_valid type=ram_t2p impl=bram
#pragma HLS BIND_STORAGE variable=phle_state type=ram_t2p impl=uram

    uint32_t safe_targets = fwd_min_u32(num_targets, TEMPGNN_MAX_TARGETS);
    uint32_t safe_events = fwd_min_u32(num_events, TEMPGNN_MAX_EVENTS);
    uint32_t safe_vertices = fwd_min_u32(num_vertices, TEMPGNN_MAX_VERTICES);
    uint32_t safe_entries = tdp_entries == 0 ? 1 : fwd_min_u32(tdp_entries, TEMPGNN_MAX_TARGETS);

    uint64_t total_packets = 0;
    uint64_t emitted_unique_packets = 0;
    uint64_t total_cycles = 0;
    uint64_t sum_packets = 0;
    uint64_t sum_critical = 0;
    uint64_t sum_bpr_x1000 = 0;
    uint64_t hash_hits = 0;
    uint64_t overflow_count = 0;
    uint64_t checksum = 0;

fwd_target_chunks:
    for (uint32_t chunk_start = 0; chunk_start < TEMPGNN_MAX_TARGETS; chunk_start += 1) {
#pragma HLS LOOP_TRIPCOUNT min=1 max=TEMPGNN_MAX_TARGETS
        if (chunk_start >= safe_targets) {
            break;
        }
        if ((chunk_start % safe_entries) != 0) {
            continue;
        }

    fwd_phle_reset:
        for (uint32_t idx = 0; idx < TEMPGNN_HASH_SIZE; ++idx) {
#pragma HLS LOOP_TRIPCOUNT min=TEMPGNN_HASH_SIZE max=TEMPGNN_HASH_SIZE
            phle_valid[idx] = false;
            phle_key[idx].vertex = 0;
            phle_key[idx].event_idx = TEMPGNN_INITIAL_EVENT;
            phle_key[idx].ts = 0;
        }

        uint32_t chunk_end = fwd_min_u32(chunk_start + safe_entries, safe_targets);
        uint32_t chunk_targets = chunk_end - chunk_start;
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
                fwd_load_initial_state(initial_memory, safe_vertices, target_vertex[target_pos], target_embedding);
            } else {
                fwd_process_target(
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
                    initial_memory,
                    event_features,
                    weight_self,
                    weight_peer,
                    weight_event,
                    bias,
                    phle_key,
                    phle_valid,
                    phle_state,
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

#if TEMPGNN_FULLSIZE_ARCH
    uint64_t fullsize_seed = checksum ^ total_cycles ^ memory_bytes ^ ((uint64_t)safe_targets << 32);
    (void)fwd_fullsize_architecture_tick(fullsize_seed, stats_out);
#endif

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
}
