#include "baseline_hls.hpp"

#include <algorithm>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

template <typename T>
static std::vector<T> read_binary(const std::string &path) {
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    if (!input) {
        throw std::runtime_error("failed to open " + path);
    }
    auto bytes = input.tellg();
    input.seekg(0);
    if (bytes <= 0 || bytes % static_cast<std::streamoff>(sizeof(T)) != 0) {
        throw std::runtime_error("invalid file size: " + path);
    }
    std::vector<T> values(static_cast<size_t>(bytes) / sizeof(T));
    input.read(reinterpret_cast<char *>(values.data()), bytes);
    return values;
}

template <typename T>
static void write_binary(const std::string &path, const std::vector<T> &values) {
    std::ofstream output(path, std::ios::binary | std::ios::trunc);
    if (!output) {
        throw std::runtime_error("failed to create " + path);
    }
    output.write(
        reinterpret_cast<const char *>(values.data()),
        static_cast<std::streamsize>(values.size() * sizeof(T)));
    if (!output) {
        throw std::runtime_error("failed to write " + path);
    }
}

static std::string path_join(const std::string &root, const std::string &name) {
    return root + "/" + name;
}

static bool file_exists(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    return input.good();
}

using Kernel = void (*)(BASELINE_KERNEL_ARGUMENTS);

static uint64_t embedding_checksum(const std::vector<int16_t> &values) {
    uint64_t checksum = 1469598103934665603ull;
    for (int16_t value : values) {
        checksum ^= static_cast<uint16_t>(value);
        checksum *= 1099511628211ull;
    }
    return checksum;
}

static bool run_kernel(
    const std::string &name,
    Kernel kernel,
    const std::vector<uint32_t> &event_src,
    const std::vector<uint32_t> &event_dst,
    const std::vector<uint32_t> &event_ts,
    const std::vector<uint32_t> &vertex_offsets,
    const std::vector<uint32_t> &history_event_idx,
    const std::vector<uint32_t> &history_peer,
    const std::vector<uint32_t> &target_vertex,
    const std::vector<uint32_t> &target_event_idx,
    const std::vector<int16_t> &initial_memory,
    const std::vector<int16_t> &event_features,
    const std::vector<int16_t> &weight_self,
    const std::vector<int16_t> &weight_peer,
    const std::vector<int16_t> &weight_event,
    const std::vector<int16_t> &bias,
    uint32_t fanout,
    uint32_t depth,
    uint32_t model_id,
    uint32_t mode,
    const std::string &root,
    bool write_expected) {
    std::vector<int16_t> first(target_vertex.size() * BASELINE_DIM);
    std::vector<int16_t> second(first.size());
    std::vector<uint64_t> first_stats(BASELINE_STAT_COUNT);
    std::vector<uint64_t> second_stats(BASELINE_STAT_COUNT);
    auto invoke = [&](std::vector<int16_t> &output, std::vector<uint64_t> &stats) {
        kernel(
            event_src.data(), event_dst.data(), event_ts.data(), event_src.size(),
            vertex_offsets.data(), history_event_idx.data(), history_peer.data(),
            vertex_offsets.size() - 1, target_vertex.data(), target_event_idx.data(),
            target_vertex.size(), fanout, depth, model_id, mode, 1, initial_memory.data(),
            event_features.data(), weight_self.data(), weight_peer.data(), weight_event.data(),
            bias.data(), output.data(), stats.data());
    };
    invoke(first, first_stats);
    invoke(second, second_stats);
    bool ok = first == second && first_stats == second_stats &&
              first_stats[BASELINE_STAT_TARGETS] == target_vertex.size() &&
              first_stats[BASELINE_STAT_OUTPUT_WORDS] == first.size() &&
              first_stats[BASELINE_STAT_CHECKSUM] != 0 &&
              first_stats[BASELINE_STAT_INVALID_INPUTS] == 0;
    uint64_t host_checksum = embedding_checksum(first);
    std::string kernel_name = name == "MATG" ? "matg_kernel" :
                              name == "ViTeGNN" ? "vitegnn_kernel" : "rtga_kernel";
    std::string expected_embedding_path =
        path_join(root, "expected_" + kernel_name + "_embedding.bin");
    std::string expected_stats_path = path_join(root, "expected_" + kernel_name + "_stats.bin");
    bool golden_checked = false;
    bool golden_ok = true;
    if (!write_expected && file_exists(expected_embedding_path) && file_exists(expected_stats_path)) {
        auto expected_embedding = read_binary<int16_t>(expected_embedding_path);
        auto expected_stats = read_binary<uint64_t>(expected_stats_path);
        golden_checked = true;
        golden_ok = first == expected_embedding && first_stats == expected_stats;
        ok &= golden_ok;
    }
    if (ok && write_expected) {
        write_binary(expected_embedding_path, first);
        write_binary(expected_stats_path, first_stats);
    }
    std::cout << name << " checksum=" << first_stats[BASELINE_STAT_CHECKSUM]
              << " embedding_checksum=" << host_checksum
              << " scanned=" << first_stats[BASELINE_STAT_SCANNED]
              << " selected=" << first_stats[BASELINE_STAT_SELECTED]
              << " golden=" << (golden_checked ? (golden_ok ? "PASS" : "FAIL") : "NOT_FOUND")
              << " result=" << (ok ? "PASS" : "FAIL") << "\n";
    return ok;
}

int main(int argc, char **argv) {
    if (argc != 4 && argc != 7 && argc != 8) {
        std::cerr << "Usage: " << argv[0]
                  << " <fixture_dir> <fanout> <depth> <model_id> <mode> <MATG|ViTeGNN|RTGA|all> [--write]\n"
                  << "Legacy form: <fixture_dir> <fanout> <model_id>\n";
        return 2;
    }
    std::string root = argv[1];
    uint32_t fanout = static_cast<uint32_t>(std::stoul(argv[2]));
    uint32_t depth = argc == 4 ? 1u : static_cast<uint32_t>(std::stoul(argv[3]));
    uint32_t model_id = static_cast<uint32_t>(std::stoul(argv[argc == 4 ? 3 : 4]));
    uint32_t mode = argc == 4 ? 1u : static_cast<uint32_t>(std::stoul(argv[5]));
    std::string requested = argc == 4 ? "all" : argv[6];
    bool write_expected = argc == 8 && std::string(argv[7]) == "--write";
    auto event_src = read_binary<uint32_t>(path_join(root, "event_src.bin"));
    auto event_dst = read_binary<uint32_t>(path_join(root, "event_dst.bin"));
    auto event_ts = read_binary<uint32_t>(path_join(root, "event_ts.bin"));
    auto vertex_offsets = read_binary<uint32_t>(path_join(root, "vertex_offsets.bin"));
    auto history_event_idx = read_binary<uint32_t>(path_join(root, "history_event_idx.bin"));
    auto history_peer = read_binary<uint32_t>(path_join(root, "history_peer.bin"));
    auto target_vertex = read_binary<uint32_t>(path_join(root, "target_vertex.bin"));
    auto target_event_idx = read_binary<uint32_t>(path_join(root, "target_event_idx.bin"));
    auto initial_memory = read_binary<int16_t>(path_join(root, "initial_memory.bin"));
    auto event_features = read_binary<int16_t>(path_join(root, "event_features.bin"));
    auto weight_self = read_binary<int16_t>(path_join(root, "weight_self.bin"));
    auto weight_peer = read_binary<int16_t>(path_join(root, "weight_peer.bin"));
    auto weight_event = read_binary<int16_t>(path_join(root, "weight_event.bin"));
    auto bias = read_binary<int16_t>(path_join(root, "bias.bin"));

    bool ok = true;
    if (requested == "all" || requested == "MATG") {
        ok &= run_kernel("MATG", matg_kernel, event_src, event_dst, event_ts, vertex_offsets,
                         history_event_idx, history_peer, target_vertex, target_event_idx,
                         initial_memory, event_features, weight_self, weight_peer, weight_event, bias,
                         fanout, depth, model_id, mode, root, write_expected);
    }
    if (requested == "all" || requested == "ViTeGNN") {
        ok &= run_kernel("ViTeGNN", vitegnn_kernel, event_src, event_dst, event_ts, vertex_offsets,
                         history_event_idx, history_peer, target_vertex, target_event_idx,
                         initial_memory, event_features, weight_self, weight_peer, weight_event, bias,
                         fanout, depth, model_id, mode, root, write_expected);
    }
    if (requested == "all" || requested == "RTGA") {
        ok &= run_kernel("RTGA", rtga_kernel, event_src, event_dst, event_ts, vertex_offsets,
                         history_event_idx, history_peer, target_vertex, target_event_idx,
                         initial_memory, event_features, weight_self, weight_peer, weight_event, bias,
                         fanout, depth, model_id, mode, root, write_expected);
    }
    if (requested != "all" && requested != "MATG" && requested != "ViTeGNN" && requested != "RTGA") {
        std::cerr << "unknown solution: " << requested << "\n";
        return 2;
    }
    return ok ? 0 : 1;
}
