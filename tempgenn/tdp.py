from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from .graph import PacketKey, TargetQuery, TemporalGraph


@dataclass
class TDP:
    target: TargetQuery
    roots: List[PacketKey]
    packets: Set[PacketKey] = field(default_factory=set)
    edges: Set[Tuple[PacketKey, PacketKey]] = field(default_factory=set)
    depths: Dict[PacketKey, int] = field(default_factory=dict)

    def non_initial_packets(self) -> Set[PacketKey]:
        return {packet for packet in self.packets if not packet.is_initial}

    @property
    def work(self) -> int:
        return len(self.non_initial_packets())

    @property
    def critical_path_length(self) -> int:
        if not self.depths:
            return 0
        return max(self.depths.values())

    @property
    def branch_parallelism_ratio(self) -> float:
        """Proxy for BPR: work outside the critical dependency chain."""

        if self.work <= 0:
            return 0.0
        return max(0.0, 1.0 - (self.critical_path_length / self.work))


class TDPBuilder:
    """Build target-centric dependency packets with bounded expansion."""

    def __init__(self, graph: TemporalGraph, fanout: int = 20, depth: Optional[int] = 2):
        self.graph = graph
        self.fanout = fanout
        self.depth = depth

    def build(self, target: TargetQuery) -> TDP:
        tdp = TDP(target=target, roots=[])

        self_packet = self.graph.state_packet(target.vertex, target.timestamp)
        tdp.roots.append(self_packet)

        for ts, _, neighbor in self.graph.recent_interactions(
            target.vertex,
            target.timestamp,
            self.fanout,
        ):
            tdp.roots.append(self.graph.state_packet(neighbor, ts))

        seen_roots = []
        root_set = set()
        for root in tdp.roots:
            if root not in root_set:
                seen_roots.append(root)
                root_set.add(root)
        tdp.roots = seen_roots

        for root in tdp.roots:
            self._expand(tdp, root, remaining_depth=self.depth, depth_from_root=1)
        return tdp

    def build_many(self, targets: List[TargetQuery]) -> List[TDP]:
        return [self.build(target) for target in targets]

    def _expand(
        self,
        tdp: TDP,
        packet: PacketKey,
        remaining_depth: Optional[int],
        depth_from_root: int,
    ) -> None:
        if packet in tdp.packets and tdp.depths.get(packet, 0) >= depth_from_root:
            return

        tdp.packets.add(packet)
        if not packet.is_initial:
            tdp.depths[packet] = max(tdp.depths.get(packet, 0), depth_from_root)

        if packet.is_initial:
            return
        if remaining_depth is not None and remaining_depth <= 0:
            return

        next_depth = None if remaining_depth is None else remaining_depth - 1
        for dependency in self.graph.packet_dependencies(packet):
            tdp.edges.add((packet, dependency))
            self._expand(tdp, dependency, next_depth, depth_from_root + 1)
