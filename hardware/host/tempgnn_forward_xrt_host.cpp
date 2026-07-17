#include "tempgnn_hls.hpp"
#include "tempgnn_forward_cache_key.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#if __has_include(<xrt/xrt_bo.h>)
#include <xrt/xrt_bo.h>
#include <xrt/xrt_device.h>
#include <xrt/xrt_kernel.h>
#else
#include <experimental/xrt_bo.h>
#include <experimental/xrt_device.h>
#include <experimental/xrt_kernel.h>
#endif

template <typename T>
static std::vector<T> read_binary_file(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("failed to open " + path);
    }
    input.seekg(0, std::ios::end);
    std::streamoff bytes = input.tellg();
    input.seekg(0, std::ios::beg);
    if (bytes < 0 || (bytes % static_cast<std::streamoff>(sizeof(T))) != 0) {
        throw std::runtime_error("invalid binary file size: " + path);
    }
    std::vector<T> values(static_cast<size_t>(bytes) / sizeof(T));
    if (!values.empty()) {
        input.read(reinterpret_cast<char *>(values.data()), bytes);
    }
    return values;
}

static bool file_exists(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    return static_cast<bool>(input);
}

static std::string join_path(const std::string &dir, const std::string &name) {
    if (dir.empty() || dir.back() == '/' || dir.back() == '\\') {
        return dir + name;
    }
    return dir + "/" + name;
}

template <typename T>
static xrt::bo make_and_copy_bo(
    xrt::device &device,
    xrt::kernel &kernel,
    const std::vector<T> &values,
    int arg_index) {
    if (values.empty()) {
        throw std::runtime_error("cannot create an empty XRT buffer");
    }
    xrt::bo bo(device, values.size() * sizeof(T), kernel.group_id(arg_index));
    auto mapped = bo.map<T *>();
    std::copy(values.begin(), values.end(), mapped);
    bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    return bo;
}

static void print_stats(const uint64_t *stats) {
    for (int idx = 0; idx < TEMPGNN_STAT_COUNT; ++idx) {
        std::cout << "stat[" << idx << "]=" << stats[idx] << "\n";
    }
}

static void print_embedding0(const int16_t *embedding, size_t words) {
    if (words < TEMPGNN_FWD_DIM) {
        return;
    }
    std::cout << "embedding[0]";
    for (uint32_t dim = 0; dim < TEMPGNN_FWD_DIM; ++dim) {
        std::cout << " " << embedding[dim];
    }
    std::cout << "\n";
}

template <typename T>
static bool compare_vector(const std::string &name, const T *actual, const std::vector<T> &expected) {
    for (size_t idx = 0; idx < expected.size(); ++idx) {
        if (actual[idx] != expected[idx]) {
            std::cerr << name << " mismatch at [" << idx << "]: actual=" << actual[idx]
                      << " expected=" << expected[idx] << "\n";
            return false;
        }
    }
    std::cout << name << ": PASS\n";
    return true;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0]
                  << " <tempgnn_forward_kernel.xclbin> <fixture_dir> [fanout=20] [depth=2]"
                  << " [tdp_entries=16] [enable_ddtc=1] [enable_oats=1] [device_index=0]\n";
        return 2;
    }

    const std::string xclbin_path = argv[1];
    const std::string fixture_dir = argv[2];
    uint32_t fanout = argc > 3 ? static_cast<uint32_t>(std::stoul(argv[3])) : 20;
    uint32_t depth = argc > 4 ? static_cast<uint32_t>(std::stoul(argv[4])) : 2;
    uint32_t tdp_entries = argc > 5 ? static_cast<uint32_t>(std::stoul(argv[5])) : 16;
    uint32_t enable_ddtc = argc > 6 ? static_cast<uint32_t>(std::stoul(argv[6])) : 1;
    uint32_t enable_oats = argc > 7 ? static_cast<uint32_t>(std::stoul(argv[7])) : 1;
    unsigned int device_index = argc > 8 ? static_cast<unsigned int>(std::stoul(argv[8])) : 0;

    auto event_src = read_binary_file<uint32_t>(join_path(fixture_dir, "event_src.bin"));
    auto event_dst = read_binary_file<uint32_t>(join_path(fixture_dir, "event_dst.bin"));
    auto event_ts = read_binary_file<uint32_t>(join_path(fixture_dir, "event_ts.bin"));
    auto vertex_offsets = read_binary_file<uint32_t>(join_path(fixture_dir, "vertex_offsets.bin"));
    auto history_event_idx = read_binary_file<uint32_t>(join_path(fixture_dir, "history_event_idx.bin"));
    auto history_peer = read_binary_file<uint32_t>(join_path(fixture_dir, "history_peer.bin"));
    auto target_vertex = read_binary_file<uint32_t>(join_path(fixture_dir, "target_vertex.bin"));
    auto target_event_idx = read_binary_file<uint32_t>(join_path(fixture_dir, "target_event_idx.bin"));
    auto initial_memory = read_binary_file<int16_t>(join_path(fixture_dir, "initial_memory.bin"));
    auto event_features = read_binary_file<int16_t>(join_path(fixture_dir, "event_features.bin"));
    auto weight_self = read_binary_file<int16_t>(join_path(fixture_dir, "weight_self.bin"));
    auto weight_peer = read_binary_file<int16_t>(join_path(fixture_dir, "weight_peer.bin"));
    auto weight_event = read_binary_file<int16_t>(join_path(fixture_dir, "weight_event.bin"));
    auto bias = read_binary_file<int16_t>(join_path(fixture_dir, "bias.bin"));
    uint64_t input_cache_key = tempgnn_forward_cache_key(
        event_src,
        event_dst,
        event_ts,
        vertex_offsets,
        history_event_idx,
        initial_memory,
        event_features,
        weight_self,
        weight_peer,
        weight_event,
        bias);

    if (event_src.size() != event_dst.size() || event_src.size() != event_ts.size()) {
        throw std::runtime_error("event arrays have inconsistent sizes");
    }
    if (history_event_idx.size() != history_peer.size()) {
        throw std::runtime_error("history arrays have inconsistent sizes");
    }
    if (target_vertex.size() != target_event_idx.size()) {
        throw std::runtime_error("target arrays have inconsistent sizes");
    }
    if (vertex_offsets.empty()) {
        throw std::runtime_error("vertex_offsets is empty");
    }
    if (initial_memory.size() < (vertex_offsets.size() - 1) * TEMPGNN_FWD_DIM) {
        throw std::runtime_error("initial_memory is too small");
    }
    if (event_features.size() < event_src.size() * TEMPGNN_FWD_DIM) {
        throw std::runtime_error("event_features is too small");
    }
    if (weight_self.size() != TEMPGNN_FWD_DIM || weight_peer.size() != TEMPGNN_FWD_DIM ||
        weight_event.size() != TEMPGNN_FWD_DIM || bias.size() != TEMPGNN_FWD_DIM) {
        throw std::runtime_error("forward weight vector size mismatch");
    }

    xrt::device device(device_index);
    auto uuid = device.load_xclbin(xclbin_path);
    xrt::kernel kernel(device, uuid, "tempgnn_forward_kernel");

    auto bo_event_src = make_and_copy_bo(device, kernel, event_src, 0);
    auto bo_event_dst = make_and_copy_bo(device, kernel, event_dst, 1);
    auto bo_event_ts = make_and_copy_bo(device, kernel, event_ts, 2);
    auto bo_vertex_offsets = make_and_copy_bo(device, kernel, vertex_offsets, 4);
    auto bo_history_event_idx = make_and_copy_bo(device, kernel, history_event_idx, 5);
    auto bo_history_peer = make_and_copy_bo(device, kernel, history_peer, 6);
    auto bo_target_vertex = make_and_copy_bo(device, kernel, target_vertex, 8);
    auto bo_target_event_idx = make_and_copy_bo(device, kernel, target_event_idx, 9);
    auto bo_initial_memory = make_and_copy_bo(device, kernel, initial_memory, 17);
    auto bo_event_features = make_and_copy_bo(device, kernel, event_features, 18);
    auto bo_weight_self = make_and_copy_bo(device, kernel, weight_self, 19);
    auto bo_weight_peer = make_and_copy_bo(device, kernel, weight_peer, 20);
    auto bo_weight_event = make_and_copy_bo(device, kernel, weight_event, 21);
    auto bo_bias = make_and_copy_bo(device, kernel, bias, 22);

    const size_t embedding_words = target_vertex.size() * TEMPGNN_FWD_DIM;
    xrt::bo bo_embedding(device, embedding_words * sizeof(int16_t), kernel.group_id(23));
    xrt::bo bo_stats(device, TEMPGNN_STAT_COUNT * sizeof(uint64_t), kernel.group_id(24));

    const auto kernel_start = std::chrono::steady_clock::now();
    auto run = kernel(
        bo_event_src,
        bo_event_dst,
        bo_event_ts,
        static_cast<uint32_t>(event_src.size()),
        bo_vertex_offsets,
        bo_history_event_idx,
        bo_history_peer,
        static_cast<uint32_t>(vertex_offsets.size() - 1),
        bo_target_vertex,
        bo_target_event_idx,
        static_cast<uint32_t>(target_vertex.size()),
        fanout,
        depth,
        tdp_entries,
        enable_ddtc,
        enable_oats,
        input_cache_key,
        bo_initial_memory,
        bo_event_features,
        bo_weight_self,
        bo_weight_peer,
        bo_weight_event,
        bo_bias,
        bo_embedding,
        bo_stats);
    run.wait();
    const auto kernel_end = std::chrono::steady_clock::now();
    const double kernel_ms =
        std::chrono::duration<double, std::milli>(kernel_end - kernel_start).count();
    const double targets_per_second =
        kernel_ms > 0.0 ? (static_cast<double>(target_vertex.size()) * 1000.0 / kernel_ms) : 0.0;

    bo_embedding.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    bo_stats.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    auto embedding = bo_embedding.map<int16_t *>();
    auto stats = bo_stats.map<uint64_t *>();

    std::cout << "kernel_time_ms=" << kernel_ms << "\n";
    std::cout << "throughput_targets_per_s=" << targets_per_second << "\n";
    std::cout << "input_cache_key=" << input_cache_key << "\n";
    print_stats(stats);
    print_embedding0(embedding, embedding_words);

    bool ok = true;
    const std::string expected_stats_path = join_path(fixture_dir, "expected_stats.bin");
    if (file_exists(expected_stats_path)) {
        auto expected_stats = read_binary_file<uint64_t>(expected_stats_path);
        if (expected_stats.size() != TEMPGNN_STAT_COUNT) {
            throw std::runtime_error("expected_stats.bin has wrong size");
        }
        ok &= compare_vector("expected_stats", stats, expected_stats);
    }

    const std::string expected_embedding_path = join_path(fixture_dir, "expected_embedding.bin");
    if (file_exists(expected_embedding_path)) {
        auto expected_embedding = read_binary_file<int16_t>(expected_embedding_path);
        if (expected_embedding.size() != embedding_words) {
            throw std::runtime_error("expected_embedding.bin has wrong size");
        }
        ok &= compare_vector("expected_embedding", embedding, expected_embedding);
    }

    return ok ? 0 : 1;
}
