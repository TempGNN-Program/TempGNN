#include "tempgnn_hls.hpp"
#include "tempgnn_forward_cache_key.hpp"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <numeric>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
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

static constexpr uint32_t TEMPGNN_FORWARD_MAX_CUS = 32;

template <typename T>
static std::vector<T> read_binary_file(const std::string &path) {
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

static std::string join_path(const std::string &directory, const std::string &name) {
    if (!directory.empty() && (directory.back() == '/' || directory.back() == '\\')) {
        return directory + name;
    }
    return directory + "/" + name;
}

static bool file_exists(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    return static_cast<bool>(input);
}

template <typename T>
static std::unique_ptr<xrt::bo> make_and_copy_bo(
    xrt::device &device,
    xrt::kernel &kernel,
    const std::vector<T> &values,
    int arg_index) {
    auto bo = std::make_unique<xrt::bo>(
        device,
        values.size() * sizeof(T),
        kernel.group_id(arg_index));
    auto mapped = bo->template map<T *>();
    std::copy(values.begin(), values.end(), mapped);
    bo->sync(XCL_BO_SYNC_BO_TO_DEVICE);
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

struct ForwardWorker {
    std::unique_ptr<xrt::kernel> kernel;
    std::unique_ptr<xrt::run> run;
    std::array<std::unique_ptr<xrt::bo>, 25> bo;
    std::vector<uint32_t> target_positions;
    uint32_t target_count = 0;
};

static std::vector<uint64_t> aggregate_worker_stats(
    const std::vector<std::vector<uint64_t>> &partial_stats,
    uint32_t enable_ddtc,
    uint32_t enable_oats,
    uint32_t tdp_entries) {
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
    uint64_t total_packets = stats[TEMPGNN_STAT_TOTAL_PACKETS];
    uint64_t unique_packets = stats[TEMPGNN_STAT_UNIQUE_PACKETS];
    stats[TEMPGNN_STAT_PACKET_REUSE_X1000] =
        unique_packets == 0 ? 0 : total_packets * 1000u / unique_packets;
    stats[TEMPGNN_STAT_AVG_PACKETS_X1000] = targets == 0 ? 0 : total_packets * 1000u / targets;
    stats[TEMPGNN_STAT_AVG_CRITICAL_X1000] = targets == 0 ? 0 : sum_critical * 1000u / targets;
    stats[TEMPGNN_STAT_AVG_BPR_X1000] = targets == 0 ? 0 : sum_bpr_x1000 / targets;
    stats[TEMPGNN_STAT_ENABLE_DDTC] = enable_ddtc;
    stats[TEMPGNN_STAT_ENABLE_OATS] = enable_oats;
    stats[TEMPGNN_STAT_TDP_ENTRIES] = tdp_entries;
    return stats;
}

int main(int argc, char **argv) {
    if (argc < 4) {
        std::cerr << "Usage: " << argv[0]
                  << " <xclbin> <fixture_dir> <kernel_name> [fanout=10] [depth=1]"
                  << " [tdp_entries=16] [enable_ddtc=1] [enable_oats=1] [device=0]"
                  << " [warmup=1] [iterations=5] [gate_prefix]\n";
        return 2;
    }

    const std::string xclbin_path = argv[1];
    const std::string fixture_dir = argv[2];
    const std::string kernel_name = argv[3];
    uint32_t fanout = argc > 4 ? static_cast<uint32_t>(std::stoul(argv[4])) : 10;
    uint32_t depth = argc > 5 ? static_cast<uint32_t>(std::stoul(argv[5])) : 1;
    uint32_t requested_entries = argc > 6 ? static_cast<uint32_t>(std::stoul(argv[6])) : 16;
    uint32_t enable_ddtc = argc > 7 ? static_cast<uint32_t>(std::stoul(argv[7])) : 1;
    uint32_t enable_oats = argc > 8 ? static_cast<uint32_t>(std::stoul(argv[8])) : 1;
    unsigned int device_index = argc > 9 ? static_cast<unsigned int>(std::stoul(argv[9])) : 0;
    uint32_t warmup = argc > 10 ? static_cast<uint32_t>(std::stoul(argv[10])) : 1;
    uint32_t iterations = argc > 11 ? static_cast<uint32_t>(std::stoul(argv[11])) : 5;
    std::string gate_prefix = argc > 12 ? argv[12] : "";
    if (kernel_name != "tempgnn_forward_kernel") {
        throw std::runtime_error("parallel host only supports tempgnn_forward_kernel");
    }
    if (warmup == 0 || iterations == 0) {
        throw std::runtime_error("warmup and iterations must be positive");
    }
    uint32_t tdp_entries = requested_entries == 0
                               ? 1
                               : std::min(requested_entries, static_cast<uint32_t>(TEMPGNN_MAX_TARGETS));

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
    if (target_vertex.size() != target_event_idx.size() || target_vertex.empty()) {
        throw std::runtime_error("target arrays have inconsistent or empty sizes");
    }
    if (vertex_offsets.size() < 2 ||
        initial_memory.size() < (vertex_offsets.size() - 1) * TEMPGNN_FWD_DIM ||
        event_features.size() < event_src.size() * TEMPGNN_FWD_DIM) {
        throw std::runtime_error("fixture arrays do not satisfy forward-path dimensions");
    }
    if (event_src.size() > TEMPGNN_MAX_EVENTS ||
        vertex_offsets.size() - 1 > TEMPGNN_MAX_VERTICES ||
        history_event_idx.size() > TEMPGNN_MAX_HISTORY) {
        throw std::runtime_error("fixture exceeds compiled forward-kernel capacity");
    }
    if (weight_self.size() != TEMPGNN_FWD_DIM || weight_peer.size() != TEMPGNN_FWD_DIM ||
        weight_event.size() != TEMPGNN_FWD_DIM || bias.size() != TEMPGNN_FWD_DIM) {
        throw std::runtime_error("weight vector size mismatch");
    }

    std::string expected_embedding_path =
        join_path(fixture_dir, "expected_tempgnn_forward_kernel_embedding.bin");
    std::string expected_stats_path =
        join_path(fixture_dir, "expected_tempgnn_forward_kernel_stats.bin");
    if (!file_exists(expected_embedding_path)) {
        expected_embedding_path = join_path(fixture_dir, "expected_embedding.bin");
        expected_stats_path = join_path(fixture_dir, "expected_stats.bin");
    }
    auto expected_embedding = read_binary_file<int16_t>(expected_embedding_path);
    auto expected_stats = read_binary_file<uint64_t>(expected_stats_path);
    if (expected_embedding.size() != target_vertex.size() * TEMPGNN_FWD_DIM ||
        expected_stats.size() != TEMPGNN_STAT_COUNT) {
        throw std::runtime_error("golden output size mismatch");
    }

    xrt::device device(device_index);
    auto uuid = device.load_xclbin(xclbin_path);
    std::vector<std::unique_ptr<xrt::kernel>> kernels;
    for (uint32_t index = 1; index <= TEMPGNN_FORWARD_MAX_CUS; ++index) {
        std::string cu_name = kernel_name + ":{" + kernel_name + "_" + std::to_string(index) + "}";
        try {
            kernels.push_back(std::make_unique<xrt::kernel>(device, uuid, cu_name));
        } catch (const std::exception &) {
            if (index == 1) {
                kernels.push_back(std::make_unique<xrt::kernel>(device, uuid, kernel_name));
            }
            break;
        }
    }

    uint32_t chunks = static_cast<uint32_t>((target_vertex.size() + tdp_entries - 1u) / tdp_entries);
    uint32_t active_cus = std::min<uint32_t>(static_cast<uint32_t>(kernels.size()), chunks);
    if (active_cus == 0) {
        throw std::runtime_error("xclbin exposes no usable TempGNN compute unit");
    }
    kernels.resize(active_cus);

    std::vector<ForwardWorker> workers(active_cus);
    for (uint32_t index = 0; index < active_cus; ++index) {
        auto &worker = workers[index];
        worker.kernel = std::move(kernels[index]);
        for (uint32_t chunk = index; chunk < chunks; chunk += active_cus) {
            uint32_t target_begin = chunk * tdp_entries;
            uint32_t target_end = std::min<uint32_t>(
                target_begin + tdp_entries,
                static_cast<uint32_t>(target_vertex.size()));
            for (uint32_t target = target_begin; target < target_end; ++target) {
                worker.target_positions.push_back(target);
            }
        }
        worker.target_count = static_cast<uint32_t>(worker.target_positions.size());
        if (worker.target_count > TEMPGNN_MAX_TARGETS) {
            throw std::runtime_error("per-CU target partition exceeds compiled kernel capacity");
        }
        std::vector<uint32_t> worker_target_vertex;
        std::vector<uint32_t> worker_target_event_idx;
        worker_target_vertex.reserve(worker.target_count);
        worker_target_event_idx.reserve(worker.target_count);
        for (uint32_t target : worker.target_positions) {
            worker_target_vertex.push_back(target_vertex[target]);
            worker_target_event_idx.push_back(target_event_idx[target]);
        }

        worker.bo[0] = make_and_copy_bo(device, *worker.kernel, event_src, 0);
        worker.bo[1] = make_and_copy_bo(device, *worker.kernel, event_dst, 1);
        worker.bo[2] = make_and_copy_bo(device, *worker.kernel, event_ts, 2);
        worker.bo[4] = make_and_copy_bo(device, *worker.kernel, vertex_offsets, 4);
        worker.bo[5] = make_and_copy_bo(device, *worker.kernel, history_event_idx, 5);
        worker.bo[6] = make_and_copy_bo(device, *worker.kernel, history_peer, 6);
        worker.bo[8] = make_and_copy_bo(device, *worker.kernel, worker_target_vertex, 8);
        worker.bo[9] = make_and_copy_bo(device, *worker.kernel, worker_target_event_idx, 9);
        worker.bo[17] = make_and_copy_bo(device, *worker.kernel, initial_memory, 17);
        worker.bo[18] = make_and_copy_bo(device, *worker.kernel, event_features, 18);
        worker.bo[19] = make_and_copy_bo(device, *worker.kernel, weight_self, 19);
        worker.bo[20] = make_and_copy_bo(device, *worker.kernel, weight_peer, 20);
        worker.bo[21] = make_and_copy_bo(device, *worker.kernel, weight_event, 21);
        worker.bo[22] = make_and_copy_bo(device, *worker.kernel, bias, 22);
        worker.bo[23] = std::make_unique<xrt::bo>(
            device,
            worker.target_count * TEMPGNN_FWD_DIM * sizeof(int16_t),
            worker.kernel->group_id(23));
        worker.bo[24] = std::make_unique<xrt::bo>(
            device,
            TEMPGNN_STAT_COUNT * sizeof(uint64_t),
            worker.kernel->group_id(24));

        worker.run = std::make_unique<xrt::run>(*worker.kernel);
        auto &run = *worker.run;
        auto &bo = worker.bo;
        run.set_arg(0, *bo[0]);
        run.set_arg(1, *bo[1]);
        run.set_arg(2, *bo[2]);
        run.set_arg(3, static_cast<uint32_t>(event_src.size()));
        run.set_arg(4, *bo[4]);
        run.set_arg(5, *bo[5]);
        run.set_arg(6, *bo[6]);
        run.set_arg(7, static_cast<uint32_t>(vertex_offsets.size() - 1));
        run.set_arg(8, *bo[8]);
        run.set_arg(9, *bo[9]);
        run.set_arg(10, worker.target_count);
        run.set_arg(11, fanout);
        run.set_arg(12, depth);
        run.set_arg(13, tdp_entries);
        run.set_arg(14, enable_ddtc);
        run.set_arg(15, enable_oats);
        run.set_arg(16, input_cache_key);
        run.set_arg(17, *bo[17]);
        run.set_arg(18, *bo[18]);
        run.set_arg(19, *bo[19]);
        run.set_arg(20, *bo[20]);
        run.set_arg(21, *bo[21]);
        run.set_arg(22, *bo[22]);
        run.set_arg(23, *bo[23]);
        run.set_arg(24, *bo[24]);
    }

    auto launch = [&]() {
        for (auto &worker : workers) {
            worker.run->start();
        }
        for (auto &worker : workers) {
            worker.run->wait();
        }
    };

    std::vector<int16_t> embedding(expected_embedding.size(), 0);
    auto collect = [&]() {
        std::vector<std::vector<uint64_t>> partial_stats;
        partial_stats.reserve(workers.size());
        for (auto &worker : workers) {
            worker.bo[23]->sync(XCL_BO_SYNC_BO_FROM_DEVICE);
            worker.bo[24]->sync(XCL_BO_SYNC_BO_FROM_DEVICE);
            auto worker_embedding = worker.bo[23]->map<int16_t *>();
            for (uint32_t local_target = 0; local_target < worker.target_count; ++local_target) {
                uint32_t global_target = worker.target_positions[local_target];
                std::copy_n(
                    worker_embedding + local_target * TEMPGNN_FWD_DIM,
                    TEMPGNN_FWD_DIM,
                    embedding.begin() + global_target * TEMPGNN_FWD_DIM);
            }
            auto worker_stats = worker.bo[24]->map<uint64_t *>();
            partial_stats.emplace_back(worker_stats, worker_stats + TEMPGNN_STAT_COUNT);
        }
        return aggregate_worker_stats(partial_stats, enable_ddtc, enable_oats, tdp_entries);
    };

    for (uint32_t idx = 0; idx < warmup; ++idx) {
        launch();
    }
    auto warmup_stats = collect();
    uint64_t warmup_embedding_checksum = embedding_checksum(embedding.data(), embedding.size());
    uint64_t warmup_kernel_checksum = warmup_stats[TEMPGNN_STAT_CHECKSUM];
    uint64_t warmup_targets = warmup_stats[TEMPGNN_STAT_TARGETS];

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

    auto stats = collect();
    double mean = std::accumulate(timings.begin(), timings.end(), 0.0) / timings.size();
    double total = std::chrono::duration<double, std::milli>(measurement_end - measurement_start).count();
    uint64_t host_checksum = embedding_checksum(embedding.data(), embedding.size());
    uint64_t expected_host_checksum = embedding_checksum(expected_embedding.data(), expected_embedding.size());
    bool repeat_consistent = warmup_targets == stats[TEMPGNN_STAT_TARGETS] &&
                             warmup_kernel_checksum == stats[TEMPGNN_STAT_CHECKSUM] &&
                             warmup_embedding_checksum == host_checksum;
    bool golden_consistent = embedding == expected_embedding && stats == expected_stats;
    bool valid = stats[TEMPGNN_STAT_TARGETS] == target_vertex.size() &&
                 stats[TEMPGNN_STAT_CHECKSUM] != 0 && host_checksum != 0 &&
                 repeat_consistent && golden_consistent;

    std::cout << std::setprecision(12);
    std::cout << "kernel_name=" << kernel_name << "\n";
    std::cout << "compute_units=" << active_cus << "\n";
    std::cout << "kernel_time_ms=" << mean << "\n";
    std::cout << "kernel_time_p50_ms=" << percentile(timings, 0.50) << "\n";
    std::cout << "kernel_time_p95_ms=" << percentile(timings, 0.95) << "\n";
    std::cout << "measurement_window_ms=" << total << "\n";
    std::cout << "iterations=" << iterations << "\n";
    std::cout << "warmup_iterations=" << warmup << "\n";
    std::cout << "num_targets=" << target_vertex.size() << "\n";
    std::cout << "input_cache_key=" << input_cache_key << "\n";
    std::cout << "warmup_kernel_checksum=" << warmup_kernel_checksum << "\n";
    std::cout << "warmup_embedding_checksum=" << warmup_embedding_checksum << "\n";
    std::cout << "expected_kernel_checksum=" << expected_stats[TEMPGNN_STAT_CHECKSUM] << "\n";
    std::cout << "expected_embedding_checksum=" << expected_host_checksum << "\n";
    std::cout << "kernel_checksum=" << stats[TEMPGNN_STAT_CHECKSUM] << "\n";
    std::cout << "embedding_checksum=" << host_checksum << "\n";
    std::cout << "repeat_consistency=" << (repeat_consistent ? "PASS" : "FAIL") << "\n";
    std::cout << "golden_validation=" << (golden_consistent ? "PASS" : "FAIL") << "\n";
    std::cout << "validation=" << (valid ? "PASS" : "FAIL") << "\n";
    for (uint32_t idx = 0; idx < TEMPGNN_STAT_COUNT; ++idx) {
        std::cout << "stat[" << idx << "]=" << stats[idx] << "\n";
    }
    return valid ? 0 : 1;
}
