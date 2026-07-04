from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable

import numpy as np

from .graph import Event, PacketKey, TemporalGraph
from .tdp import TDP


@dataclass
class FunctionalCheckResult:
    packets_checked: int
    max_abs_error: float

    @property
    def passed(self) -> bool:
        return self.max_abs_error < 1e-7


class TinyTGNNStateModel:
    """A deterministic memory-update model for semantic checks.

    This is not a trained TGNN from the paper. It is a compact stateful model
    used to verify that recursive packet materialization matches chronological
    memory updates on the same temporal dependencies.
    """

    def __init__(self, graph: TemporalGraph, dim: int = 8):
        self.graph = graph
        self.dim = dim
        self.zero = np.zeros(dim, dtype=np.float64)

    def verify_tdps(self, tdps: Iterable[TDP], sample_limit: int = 2000) -> FunctionalCheckResult:
        packets = []
        seen = set()
        for tdp in tdps:
            for packet in tdp.non_initial_packets():
                if packet not in seen:
                    packets.append(packet)
                    seen.add(packet)
                if len(packets) >= sample_limit:
                    break
            if len(packets) >= sample_limit:
                break

        if not packets:
            return FunctionalCheckResult(packets_checked=0, max_abs_error=0.0)

        baseline = self.timestamp_ordered_packet_states(max(packet.event_idx for packet in packets))
        memo: Dict[PacketKey, np.ndarray] = {}
        max_error = 0.0
        for packet in packets:
            recursive = self.recursive_state(packet, memo)
            expected = baseline[packet]
            max_error = max(max_error, float(np.max(np.abs(recursive - expected))))
        return FunctionalCheckResult(packets_checked=len(packets), max_abs_error=max_error)

    def timestamp_ordered_packet_states(self, max_event_idx: int) -> Dict[PacketKey, np.ndarray]:
        states: Dict[int, np.ndarray] = {}
        packet_states: Dict[PacketKey, np.ndarray] = {}

        events = self.graph.events[: max_event_idx + 1]
        pos = 0
        while pos < len(events):
            group_ts = events[pos].ts
            end = pos + 1
            while end < len(events) and events[end].ts == group_ts:
                end += 1

            pending: list[tuple[int, np.ndarray, int, np.ndarray]] = []

            for event in events[pos:end]:
                src_old = states.get(event.src, self.zero)
                dst_old = states.get(event.dst, self.zero)

                src_new = self._update(src_old, dst_old, event, event.src)
                dst_new = self._update(dst_old, src_old, event, event.dst)

                packet_states[PacketKey(event.src, event.idx, event.ts)] = src_new.copy()
                packet_states[PacketKey(event.dst, event.idx, event.ts)] = dst_new.copy()
                pending.append((event.src, src_new, event.dst, dst_new))

            for src, src_new, dst, dst_new in pending:
                states[src] = src_new
                states[dst] = dst_new
            pos = end

        return packet_states

    def recursive_state(
        self,
        packet: PacketKey,
        memo: Dict[PacketKey, np.ndarray],
    ) -> np.ndarray:
        if packet.is_initial:
            return self.zero
        stack = [packet]
        while stack:
            current = stack[-1]
            if current.is_initial or current in memo:
                stack.pop()
                continue

            event = self.graph.events[current.event_idx]
            peer = event.peer(current.vertex)
            self_dependency = self.graph.state_packet(current.vertex, event.ts)
            peer_dependency = self.graph.state_packet(peer, event.ts)
            missing = [
                dependency
                for dependency in (self_dependency, peer_dependency)
                if not dependency.is_initial and dependency not in memo
            ]
            if missing:
                stack.extend(missing)
                continue

            self_old = self.zero if self_dependency.is_initial else memo[self_dependency]
            peer_old = self.zero if peer_dependency.is_initial else memo[peer_dependency]
            memo[current] = self._update(self_old, peer_old, event, current.vertex)
            stack.pop()

        return memo[packet]

    def _update(
        self,
        self_state: np.ndarray,
        peer_state: np.ndarray,
        event: Event,
        vertex: int,
    ) -> np.ndarray:
        feature = self._event_feature(event, vertex)
        return np.tanh(0.61 * self_state + 0.31 * peer_state + 0.08 * feature)

    def _event_feature(self, event: Event, vertex: int) -> np.ndarray:
        base = event.idx + 1 + (17 if vertex == event.dst else 0)
        values = [np.sin(base * (i + 1) * 0.013) for i in range(self.dim)]
        return np.asarray(values, dtype=np.float64)
