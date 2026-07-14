#include "baseline_hls.hpp"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
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
    if (bytes <= 0 || (bytes % static_cast<std::streamoff>(sizeof(T))) != 0) {
        throw std::runtime_error("invalid binary file size: " + path);
    }
    std::vector<T> values(static_cast<size_t>(bytes) / sizeof(T));
    input.read(reinterpret_cast<char *>(values.data()), bytes);
    if (!input) {
        throw std::runtime_error("failed to read " + path);
    }
    return values;
}

static std::string join_path(const std::string &dir, const std::string &name) {
    if (!dir.empty() && (dir.back() == '/' || dir.back() == '\\')) {
        return dir + name;
    }
    return dir + "/" + name;
}

static bool file_exists(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    return static_cast<bool>(input);
}

template <typename T>
static xrt::bo make_and_copy_bo(
    xrt::device &device,
    xrt::kernel &kernel,
    const std::vector<T> &values,
    int arg_index) {
    xrt::bo bo(device, values.size() * sizeof(T), kernel.group_id(arg_index));
    auto mapped = bo.map<T *>();
    std::copy(values.begin(), values.end(), mapped);
    bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
    return bo;
}

static double percentile(std::vector<double> values, double fraction) {
    if (values.empty()) {
        return 0.0;
    }
    std::sort(values.begin(), values.end());
    double position = fraction * static_cast<double>(values.size() - 1);
    size_t lower = static_cast<size_t>(position);
    size_t upper = std::min(lower + 1, values.size() - 1);
    double weight = position - static_cast<double>(lower);
    return values[lower] * (1.0 - weight) + values[upper] * weight;
}

static uint64_t embedding_checksum(const int16_t *values, size_t count) {
    uint64_t checksum = 1469598103934665603ull;
    for (size_t idx = 0; idx < count; ++idx) {
        checksum ^= static_cast<uint16_t>(values[idx]);
        checksum *= 1099511628211ull;
    }
    return checksum;
}

int main(int argc, char **argv) {
    if (argc < 4) {
        std::cerr << "Usage: " << argv[0]
                  << " <xclbin> <fixture_dir> <kernel_name> [fanout=10] [depth=1]"
                  << " [arg13=0] [arg14=1] [arg15=1] [device=0] [warmup=1] [iterations=5]"
                  << " [gate_prefix]\n";
        return 2;
    }

    const std::string xclbin_path = argv[1];
    const std::string fixture_dir = argv[2];
    const std::string kernel_name = argv[3];
    uint32_t fanout = argc > 4 ? static_cast<uint32_t>(std::stoul(argv[4])) : 10;
    uint32_t depth = argc > 5 ? static_cast<uint32_t>(std::stoul(argv[5])) : 1;
    uint32_t arg13 = argc > 6 ? static_cast<uint32_t>(std::stoul(argv[6])) : 0;
    uint32_t arg14 = argc > 7 ? static_cast<uint32_t>(std::stoul(argv[7])) : 1;
    uint32_t arg15 = argc > 8 ? static_cast<uint32_t>(std::stoul(argv[8])) : 1;
    unsigned int device_index = argc > 9 ? static_cast<unsigned int>(std::stoul(argv[9])) : 0;
    uint32_t warmup = argc > 10 ? static_cast<uint32_t>(std::stoul(argv[10])) : 1;
    uint32_t iterations = argc > 11 ? static_cast<uint32_t>(std::stoul(argv[11])) : 5;
    std::string gate_prefix = argc > 12 ? argv[12] : "";
    if (warmup == 0 || iterations == 0) {
        throw std::runtime_error("warmup and iterations must be positive");
    }

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

    if (event_src.size() != event_dst.size() || event_src.size() != event_ts.size()) {
        throw std::runtime_error("event arrays have inconsistent sizes");
    }
    if (history_event_idx.size() != history_peer.size()) {
        throw std::runtime_error("history arrays have inconsistent sizes");
    }
    if (target_vertex.size() != target_event_idx.size()) {
        throw std::runtime_error("target arrays have inconsistent sizes");
    }
    if (vertex_offsets.size() < 2 ||
        initial_memory.size() < (vertex_offsets.size() - 1) * BASELINE_DIM ||
        event_features.size() < event_src.size() * BASELINE_DIM) {
        throw std::runtime_error("fixture arrays do not satisfy the forward-path dimensions");
    }
    if (weight_self.size() != BASELINE_DIM || weight_peer.size() != BASELINE_DIM ||
        weight_event.size() != BASELINE_DIM || bias.size() != BASELINE_DIM) {
        throw std::runtime_error("weight vector size mismatch");
    }
    std::string expected_embedding_path =
        join_path(fixture_dir, "expected_" + kernel_name + "_embedding.bin");
    std::string expected_stats_path =
        join_path(fixture_dir, "expected_" + kernel_name + "_stats.bin");
    if (kernel_name == "tempgnn_forward_kernel" && !file_exists(expected_embedding_path)) {
        expected_embedding_path = join_path(fixture_dir, "expected_embedding.bin");
        expected_stats_path = join_path(fixture_dir, "expected_stats.bin");
    }
    auto expected_embedding = read_binary_file<int16_t>(expected_embedding_path);
    auto expected_stats = read_binary_file<uint64_t>(expected_stats_path);
    if (expected_embedding.size() != target_vertex.size() * BASELINE_DIM ||
        expected_stats.size() != BASELINE_STAT_COUNT) {
        throw std::runtime_error("golden output size mismatch");
    }

    xrt::device device(device_index);
    auto uuid = device.load_xclbin(xclbin_path);
    xrt::kernel kernel(device, uuid, kernel_name);
    auto bo_event_src = make_and_copy_bo(device, kernel, event_src, 0);
    auto bo_event_dst = make_and_copy_bo(device, kernel, event_dst, 1);
    auto bo_event_ts = make_and_copy_bo(device, kernel, event_ts, 2);
    auto bo_vertex_offsets = make_and_copy_bo(device, kernel, vertex_offsets, 4);
    auto bo_history_event_idx = make_and_copy_bo(device, kernel, history_event_idx, 5);
    auto bo_history_peer = make_and_copy_bo(device, kernel, history_peer, 6);
    auto bo_target_vertex = make_and_copy_bo(device, kernel, target_vertex, 8);
    auto bo_target_event_idx = make_and_copy_bo(device, kernel, target_event_idx, 9);
    auto bo_initial_memory = make_and_copy_bo(device, kernel, initial_memory, 16);
    auto bo_event_features = make_and_copy_bo(device, kernel, event_features, 17);
    auto bo_weight_self = make_and_copy_bo(device, kernel, weight_self, 18);
    auto bo_weight_peer = make_and_copy_bo(device, kernel, weight_peer, 19);
    auto bo_weight_event = make_and_copy_bo(device, kernel, weight_event, 20);
    auto bo_bias = make_and_copy_bo(device, kernel, bias, 21);

    size_t embedding_words = target_vertex.size() * BASELINE_DIM;
    xrt::bo bo_embedding(device, embedding_words * sizeof(int16_t), kernel.group_id(22));
    xrt::bo bo_stats(device, BASELINE_STAT_COUNT * sizeof(uint64_t), kernel.group_id(23));

    auto launch = [&]() {
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
            arg13,
            arg14,
            arg15,
            bo_initial_memory,
            bo_event_features,
            bo_weight_self,
            bo_weight_peer,
            bo_weight_event,
            bo_bias,
            bo_embedding,
            bo_stats);
        run.wait();
    };

    for (uint32_t idx = 0; idx < warmup; ++idx) {
        launch();
    }
    bo_embedding.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    bo_stats.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    auto embedding = bo_embedding.map<int16_t *>();
    auto stats = bo_stats.map<uint64_t *>();
    uint32_t kernel_checksum_index = kernel_name == "tempgnn_forward_kernel" ? 11u : 10u;
    uint64_t warmup_embedding_checksum = embedding_checksum(embedding, embedding_words);
    uint64_t warmup_kernel_checksum = stats[kernel_checksum_index];
    uint64_t warmup_targets = stats[0];

    if (!gate_prefix.empty()) {
        {
            std::ofstream ready(gate_prefix + ".ready", std::ios::trunc);
            if (!ready) {
                throw std::runtime_error("failed to create measurement ready file");
            }
            ready << "ready\n";
        }
        auto gate_deadline = std::chrono::steady_clock::now() + std::chrono::seconds(120);
        while (!file_exists(gate_prefix + ".go")) {
            if (std::chrono::steady_clock::now() > gate_deadline) {
                throw std::runtime_error("timed out waiting for measurement gate");
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }
    std::vector<double> timings;
    timings.reserve(iterations);
    auto measurement_start = std::chrono::steady_clock::now();
    for (uint32_t idx = 0; idx < iterations; ++idx) {
        auto start = std::chrono::steady_clock::now();
        launch();
        auto end = std::chrono::steady_clock::now();
        timings.push_back(std::chrono::duration<double, std::milli>(end - start).count());
    }
    auto measurement_end = std::chrono::steady_clock::now();

    bo_embedding.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    bo_stats.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    double mean = std::accumulate(timings.begin(), timings.end(), 0.0) / timings.size();
    double total = std::chrono::duration<double, std::milli>(measurement_end - measurement_start).count();
    uint64_t host_checksum = embedding_checksum(embedding, embedding_words);
    uint64_t expected_host_checksum =
        embedding_checksum(expected_embedding.data(), expected_embedding.size());
    bool repeat_consistent = warmup_targets == stats[0] &&
                             warmup_kernel_checksum == stats[kernel_checksum_index] &&
                             warmup_embedding_checksum == host_checksum;
    bool golden_consistent =
        std::equal(expected_embedding.begin(), expected_embedding.end(), embedding) &&
        std::equal(expected_stats.begin(), expected_stats.end(), stats);
    bool valid = stats[0] == target_vertex.size() && stats[kernel_checksum_index] != 0 &&
                 host_checksum != 0 && repeat_consistent && golden_consistent;

    std::cout << std::setprecision(12);
    std::cout << "kernel_name=" << kernel_name << "\n";
    std::cout << "kernel_time_ms=" << mean << "\n";
    std::cout << "kernel_time_p50_ms=" << percentile(timings, 0.50) << "\n";
    std::cout << "kernel_time_p95_ms=" << percentile(timings, 0.95) << "\n";
    std::cout << "measurement_window_ms=" << total << "\n";
    std::cout << "iterations=" << iterations << "\n";
    std::cout << "warmup_iterations=" << warmup << "\n";
    std::cout << "num_targets=" << target_vertex.size() << "\n";
    std::cout << "warmup_kernel_checksum=" << warmup_kernel_checksum << "\n";
    std::cout << "warmup_embedding_checksum=" << warmup_embedding_checksum << "\n";
    std::cout << "expected_kernel_checksum=" << expected_stats[kernel_checksum_index] << "\n";
    std::cout << "expected_embedding_checksum=" << expected_host_checksum << "\n";
    std::cout << "kernel_checksum=" << stats[kernel_checksum_index] << "\n";
    std::cout << "embedding_checksum=" << host_checksum << "\n";
    std::cout << "repeat_consistency=" << (repeat_consistent ? "PASS" : "FAIL") << "\n";
    std::cout << "golden_validation=" << (golden_consistent ? "PASS" : "FAIL") << "\n";
    std::cout << "validation=" << (valid ? "PASS" : "FAIL") << "\n";
    for (uint32_t idx = 0; idx < BASELINE_STAT_COUNT; ++idx) {
        std::cout << "stat[" << idx << "]=" << stats[idx] << "\n";
    }
    return valid ? 0 : 1;
}
