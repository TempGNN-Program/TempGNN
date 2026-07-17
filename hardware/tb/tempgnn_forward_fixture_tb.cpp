#include "tempgnn_hls.hpp"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

template <typename T>
static std::vector<T> read_binary(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("failed to open " + path);
    }
    input.seekg(0, std::ios::end);
    std::streamoff bytes = input.tellg();
    input.seekg(0, std::ios::beg);
    if (bytes <= 0 || bytes % static_cast<std::streamoff>(sizeof(T)) != 0) {
        throw std::runtime_error("invalid binary file size: " + path);
    }
    std::vector<T> values(static_cast<size_t>(bytes) / sizeof(T));
    input.read(reinterpret_cast<char *>(values.data()), bytes);
    if (!input) {
        throw std::runtime_error("failed to read " + path);
    }
    return values;
}

static std::string path_join(const std::string &directory, const std::string &name) {
    return directory + "/" + name;
}

int main(int argc, char **argv) {
    if (argc != 4 && argc != 5) {
        std::cerr << "Usage: " << argv[0] << " <fixture_dir> <fanout> <depth> [workers=1]\n";
        return 2;
    }

    const std::string fixture = argv[1];
    const uint32_t fanout = static_cast<uint32_t>(std::stoul(argv[2]));
    const uint32_t depth = static_cast<uint32_t>(std::stoul(argv[3]));
    const uint32_t requested_workers = argc == 5 ? static_cast<uint32_t>(std::stoul(argv[4])) : 1;
    if (requested_workers == 0) {
        throw std::runtime_error("workers must be positive");
    }
    auto event_src = read_binary<uint32_t>(path_join(fixture, "event_src.bin"));
    auto event_dst = read_binary<uint32_t>(path_join(fixture, "event_dst.bin"));
    auto event_ts = read_binary<uint32_t>(path_join(fixture, "event_ts.bin"));
    auto vertex_offsets = read_binary<uint32_t>(path_join(fixture, "vertex_offsets.bin"));
    auto history_event_idx = read_binary<uint32_t>(path_join(fixture, "history_event_idx.bin"));
    auto history_peer = read_binary<uint32_t>(path_join(fixture, "history_peer.bin"));
    auto target_vertex = read_binary<uint32_t>(path_join(fixture, "target_vertex.bin"));
    auto target_event_idx = read_binary<uint32_t>(path_join(fixture, "target_event_idx.bin"));
    auto initial_memory = read_binary<int16_t>(path_join(fixture, "initial_memory.bin"));
    auto event_features = read_binary<int16_t>(path_join(fixture, "event_features.bin"));
    auto weight_self = read_binary<int16_t>(path_join(fixture, "weight_self.bin"));
    auto weight_peer = read_binary<int16_t>(path_join(fixture, "weight_peer.bin"));
    auto weight_event = read_binary<int16_t>(path_join(fixture, "weight_event.bin"));
    auto bias = read_binary<int16_t>(path_join(fixture, "bias.bin"));
    auto expected_embedding = read_binary<int16_t>(
        path_join(fixture, "expected_tempgnn_forward_kernel_embedding.bin"));
    auto expected_stats = read_binary<uint64_t>(
        path_join(fixture, "expected_tempgnn_forward_kernel_stats.bin"));

    constexpr uint32_t tdp_entries = 16;
    constexpr uint64_t input_cache_key = 0x54474e4e46495854ull;
    uint32_t chunks = static_cast<uint32_t>((target_vertex.size() + tdp_entries - 1u) / tdp_entries);
    uint32_t workers = std::min(requested_workers, chunks);
    std::vector<int16_t> embedding(expected_embedding.size(), 0);
    std::vector<std::vector<uint64_t>> partial_stats;

    for (uint32_t worker = 0; worker < workers; ++worker) {
        std::vector<uint32_t> target_positions;
        std::vector<uint32_t> worker_target_vertex;
        std::vector<uint32_t> worker_target_event_idx;
        for (uint32_t chunk = worker; chunk < chunks; chunk += workers) {
            uint32_t target_begin = chunk * tdp_entries;
            uint32_t target_end = std::min<uint32_t>(
                target_begin + tdp_entries,
                static_cast<uint32_t>(target_vertex.size()));
            for (uint32_t target = target_begin; target < target_end; ++target) {
                target_positions.push_back(target);
                worker_target_vertex.push_back(target_vertex[target]);
                worker_target_event_idx.push_back(target_event_idx[target]);
            }
        }
        uint32_t worker_targets = static_cast<uint32_t>(target_positions.size());
        std::vector<int16_t> worker_embedding(worker_targets * TEMPGNN_FWD_DIM, 0);
        partial_stats.emplace_back(TEMPGNN_STAT_COUNT, 0);
        tempgnn_forward_kernel(
            event_src.data(),
            event_dst.data(),
            event_ts.data(),
            static_cast<uint32_t>(event_src.size()),
            vertex_offsets.data(),
            history_event_idx.data(),
            history_peer.data(),
            static_cast<uint32_t>(vertex_offsets.size() - 1),
            worker_target_vertex.data(),
            worker_target_event_idx.data(),
            worker_targets,
            fanout,
            depth,
            tdp_entries,
            1,
            1,
            input_cache_key,
            initial_memory.data(),
            event_features.data(),
            weight_self.data(),
            weight_peer.data(),
            weight_event.data(),
            bias.data(),
            worker_embedding.data(),
            partial_stats.back().data());
        for (uint32_t local_target = 0; local_target < worker_targets; ++local_target) {
            uint32_t global_target = target_positions[local_target];
            std::copy_n(
                worker_embedding.begin() + local_target * TEMPGNN_FWD_DIM,
                TEMPGNN_FWD_DIM,
                embedding.begin() + global_target * TEMPGNN_FWD_DIM);
        }
    }

    std::vector<uint64_t> stats(TEMPGNN_STAT_COUNT, 0);
    uint64_t sum_critical = 0;
    uint64_t sum_bpr_x1000 = 0;
    for (const auto &partial : partial_stats) {
        stats[TEMPGNN_STAT_TARGETS] += partial[TEMPGNN_STAT_TARGETS];
        stats[TEMPGNN_STAT_TOTAL_PACKETS] += partial[TEMPGNN_STAT_TOTAL_PACKETS];
        stats[TEMPGNN_STAT_UNIQUE_PACKETS] += partial[TEMPGNN_STAT_UNIQUE_PACKETS];
        stats[TEMPGNN_STAT_CYCLES] += partial[TEMPGNN_STAT_CYCLES];
        stats[TEMPGNN_STAT_MEMORY_BYTES] += partial[TEMPGNN_STAT_MEMORY_BYTES];
        stats[TEMPGNN_STAT_HASH_HITS] += partial[TEMPGNN_STAT_HASH_HITS];
        stats[TEMPGNN_STAT_OVERFLOWS] += partial[TEMPGNN_STAT_OVERFLOWS];
        stats[TEMPGNN_STAT_CHECKSUM] ^= partial[TEMPGNN_STAT_CHECKSUM];
        sum_critical += partial[TEMPGNN_STAT_PARTIAL_REDUCTIONS] >> 32u;
        sum_bpr_x1000 += partial[TEMPGNN_STAT_PARTIAL_REDUCTIONS] & 0xffffffffull;
    }
    uint64_t targets = stats[TEMPGNN_STAT_TARGETS];
    uint64_t unique_packets = stats[TEMPGNN_STAT_UNIQUE_PACKETS];
    stats[TEMPGNN_STAT_PACKET_REUSE_X1000] =
        unique_packets == 0 ? 0 : stats[TEMPGNN_STAT_TOTAL_PACKETS] * 1000u / unique_packets;
    stats[TEMPGNN_STAT_AVG_PACKETS_X1000] =
        targets == 0 ? 0 : stats[TEMPGNN_STAT_TOTAL_PACKETS] * 1000u / targets;
    stats[TEMPGNN_STAT_AVG_CRITICAL_X1000] = targets == 0 ? 0 : sum_critical * 1000u / targets;
    stats[TEMPGNN_STAT_AVG_BPR_X1000] = targets == 0 ? 0 : sum_bpr_x1000 / targets;
    stats[TEMPGNN_STAT_ENABLE_DDTC] = 1;
    stats[TEMPGNN_STAT_ENABLE_OATS] = 1;
    stats[TEMPGNN_STAT_TDP_ENTRIES] = tdp_entries;

    bool embedding_matches = embedding == expected_embedding;
    bool stats_match = stats == expected_stats;
    std::cout << "fixture=" << fixture << "\n";
    std::cout << "workers=" << workers << "\n";
    std::cout << "embedding=" << (embedding_matches ? "PASS" : "FAIL") << "\n";
    std::cout << "stats=" << (stats_match ? "PASS" : "FAIL") << "\n";
    if (!embedding_matches) {
        for (size_t idx = 0; idx < embedding.size(); ++idx) {
            if (embedding[idx] != expected_embedding[idx]) {
                std::cout << "embedding_mismatch[" << idx << "]=" << embedding[idx]
                          << " expected=" << expected_embedding[idx] << "\n";
                break;
            }
        }
    }
    if (!stats_match) {
        for (size_t idx = 0; idx < stats.size(); ++idx) {
            if (stats[idx] != expected_stats[idx]) {
                std::cout << "stat_mismatch[" << idx << "]=" << stats[idx]
                          << " expected=" << expected_stats[idx] << "\n";
            }
        }
    }
    return embedding_matches && stats_match ? 0 : 1;
}
