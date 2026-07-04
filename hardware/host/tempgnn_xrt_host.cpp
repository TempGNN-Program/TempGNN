#include <algorithm>
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

static std::vector<uint32_t> read_u32_file(const std::string &path) {
    std::ifstream input(path, std::ios::binary);
    if (!input) {
        throw std::runtime_error("failed to open " + path);
    }
    input.seekg(0, std::ios::end);
    std::streamoff bytes = input.tellg();
    input.seekg(0, std::ios::beg);
    if (bytes < 0 || (bytes % sizeof(uint32_t)) != 0) {
        throw std::runtime_error("invalid uint32 file size: " + path);
    }
    std::vector<uint32_t> values(static_cast<size_t>(bytes) / sizeof(uint32_t));
    input.read(reinterpret_cast<char *>(values.data()), bytes);
    return values;
}

static void copy_to_bo(xrt::bo &bo, const std::vector<uint32_t> &values) {
    auto mapped = bo.map<uint32_t *>();
    std::copy(values.begin(), values.end(), mapped);
    bo.sync(XCL_BO_SYNC_BO_TO_DEVICE);
}

static std::string join_path(const std::string &dir, const std::string &name) {
    if (dir.empty() || dir.back() == '/' || dir.back() == '\\') {
        return dir + name;
    }
    return dir + "/" + name;
}

int main(int argc, char **argv) {
    if (argc < 3) {
        std::cerr << "Usage: " << argv[0]
                  << " <tempgnn_kernel.xclbin> <fixture_dir> [fanout=20] [depth=2] [tdp_entries=16]"
                  << " [enable_ddtc=1] [enable_oats=1] [device_index=0]\n";
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

    auto event_src = read_u32_file(join_path(fixture_dir, "event_src.bin"));
    auto event_dst = read_u32_file(join_path(fixture_dir, "event_dst.bin"));
    auto event_ts = read_u32_file(join_path(fixture_dir, "event_ts.bin"));
    auto vertex_offsets = read_u32_file(join_path(fixture_dir, "vertex_offsets.bin"));
    auto history_event_idx = read_u32_file(join_path(fixture_dir, "history_event_idx.bin"));
    auto history_peer = read_u32_file(join_path(fixture_dir, "history_peer.bin"));
    auto target_vertex = read_u32_file(join_path(fixture_dir, "target_vertex.bin"));
    auto target_event_idx = read_u32_file(join_path(fixture_dir, "target_event_idx.bin"));

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

    xrt::device device(device_index);
    auto uuid = device.load_xclbin(xclbin_path);
    xrt::kernel kernel(device, uuid, "tempgnn_kernel");

    auto make_u32_bo = [&](const std::vector<uint32_t> &values, int arg_index) {
        return xrt::bo(device, values.size() * sizeof(uint32_t), kernel.group_id(arg_index));
    };

    auto bo_event_src = make_u32_bo(event_src, 0);
    auto bo_event_dst = make_u32_bo(event_dst, 1);
    auto bo_event_ts = make_u32_bo(event_ts, 2);
    auto bo_vertex_offsets = make_u32_bo(vertex_offsets, 4);
    auto bo_history_event_idx = make_u32_bo(history_event_idx, 5);
    auto bo_history_peer = make_u32_bo(history_peer, 6);
    auto bo_target_vertex = make_u32_bo(target_vertex, 8);
    auto bo_target_event_idx = make_u32_bo(target_event_idx, 9);
    xrt::bo bo_stats(device, 16 * sizeof(uint64_t), kernel.group_id(16));

    copy_to_bo(bo_event_src, event_src);
    copy_to_bo(bo_event_dst, event_dst);
    copy_to_bo(bo_event_ts, event_ts);
    copy_to_bo(bo_vertex_offsets, vertex_offsets);
    copy_to_bo(bo_history_event_idx, history_event_idx);
    copy_to_bo(bo_history_peer, history_peer);
    copy_to_bo(bo_target_vertex, target_vertex);
    copy_to_bo(bo_target_event_idx, target_event_idx);

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
        bo_stats);
    run.wait();

    bo_stats.sync(XCL_BO_SYNC_BO_FROM_DEVICE);
    auto stats = bo_stats.map<uint64_t *>();
    for (int idx = 0; idx < 16; ++idx) {
        std::cout << "stat[" << idx << "]=" << stats[idx] << "\n";
    }
    return 0;
}
