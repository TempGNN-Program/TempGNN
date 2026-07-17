#ifndef TEMPGNN_FORWARD_CACHE_KEY_HPP
#define TEMPGNN_FORWARD_CACHE_KEY_HPP

#include <cstddef>
#include <cstdint>
#include <vector>

static inline void tempgnn_cache_key_byte(uint64_t &key, uint8_t value) {
    key ^= value;
    key *= 1099511628211ull;
}

template <typename T>
static void tempgnn_cache_key_append(uint64_t &key, const std::vector<T> &values) {
    uint64_t bytes = static_cast<uint64_t>(values.size() * sizeof(T));
    for (uint32_t shift = 0; shift < 64; shift += 8) {
        tempgnn_cache_key_byte(key, static_cast<uint8_t>(bytes >> shift));
    }
    const auto *data = reinterpret_cast<const uint8_t *>(values.data());
    for (size_t idx = 0; idx < static_cast<size_t>(bytes); ++idx) {
        tempgnn_cache_key_byte(key, data[idx]);
    }
}

static uint64_t tempgnn_forward_cache_key(
    const std::vector<uint32_t> &event_src,
    const std::vector<uint32_t> &event_dst,
    const std::vector<uint32_t> &event_ts,
    const std::vector<uint32_t> &vertex_offsets,
    const std::vector<uint32_t> &history_event_idx,
    const std::vector<int16_t> &initial_memory,
    const std::vector<int16_t> &event_features,
    const std::vector<int16_t> &weight_self,
    const std::vector<int16_t> &weight_peer,
    const std::vector<int16_t> &weight_event,
    const std::vector<int16_t> &bias) {
    uint64_t key = 1469598103934665603ull;
    tempgnn_cache_key_append(key, event_src);
    tempgnn_cache_key_append(key, event_dst);
    tempgnn_cache_key_append(key, event_ts);
    tempgnn_cache_key_append(key, vertex_offsets);
    tempgnn_cache_key_append(key, history_event_idx);
    tempgnn_cache_key_append(key, initial_memory);
    tempgnn_cache_key_append(key, event_features);
    tempgnn_cache_key_append(key, weight_self);
    tempgnn_cache_key_append(key, weight_peer);
    tempgnn_cache_key_append(key, weight_event);
    tempgnn_cache_key_append(key, bias);
    return key;
}

#endif
