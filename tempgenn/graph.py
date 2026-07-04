from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass
from math import inf
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True, order=True)
class Event:
    """A timestamped interaction in a continuous-time temporal graph."""

    idx: int
    src: int
    dst: int
    ts: float

    def peer(self, vertex: int) -> int:
        if vertex == self.src:
            return self.dst
        if vertex == self.dst:
            return self.src
        raise ValueError(f"vertex {vertex} is not part of event {self.idx}")


@dataclass(frozen=True, order=True)
class PacketKey:
    """Memory state of one vertex immediately after one event.

    event_idx == -1 denotes the initial zero state before the event stream.
    """

    vertex: int
    event_idx: int
    ts: float

    @property
    def is_initial(self) -> bool:
        return self.event_idx < 0


@dataclass(frozen=True)
class TargetQuery:
    """A target vertex whose embedding/state is requested at a timestamp."""

    vertex: int
    timestamp: float
    event_idx: Optional[int] = None


HistoryEntry = Tuple[float, int, int]


class TemporalGraph:
    """Temporal graph with efficient latest-visible-state queries."""

    def __init__(self, events: Iterable[Tuple[int, int, float] | Event]):
        normalized: List[Tuple[int, int, float]] = []
        for event in events:
            if isinstance(event, Event):
                normalized.append((event.src, event.dst, float(event.ts)))
            else:
                src, dst, ts = event
                normalized.append((int(src), int(dst), float(ts)))

        normalized.sort(key=lambda item: item[2])
        self.events: List[Event] = [
            Event(idx=i, src=src, dst=dst, ts=ts)
            for i, (src, dst, ts) in enumerate(normalized)
        ]

        self.history: Dict[int, List[HistoryEntry]] = {}
        for event in self.events:
            self.history.setdefault(event.src, []).append((event.ts, event.idx, event.dst))
            if event.dst != event.src:
                self.history.setdefault(event.dst, []).append((event.ts, event.idx, event.src))

        self._history_ts: Dict[int, List[float]] = {
            vertex: [entry[0] for entry in entries]
            for vertex, entries in self.history.items()
        }

    @property
    def num_events(self) -> int:
        return len(self.events)

    @property
    def num_vertices(self) -> int:
        if not self.history:
            return 0
        return max(self.history) + 1

    def recent_interactions(
        self,
        vertex: int,
        before_ts: float,
        fanout: int,
    ) -> List[HistoryEntry]:
        """Return the most recent interactions of vertex before before_ts."""

        entries = self.history.get(vertex, [])
        if not entries or fanout <= 0:
            return []
        pos = bisect_left(self._history_ts[vertex], before_ts)
        start = max(0, pos - fanout)
        return list(reversed(entries[start:pos]))

    def state_packet(self, vertex: int, before_ts: float) -> PacketKey:
        """Latest visible memory packet of vertex before a timestamp."""

        entries = self.history.get(vertex, [])
        if not entries:
            return PacketKey(vertex=vertex, event_idx=-1, ts=-inf)

        pos = bisect_left(self._history_ts[vertex], before_ts)
        if pos == 0:
            return PacketKey(vertex=vertex, event_idx=-1, ts=-inf)
        ts, event_idx, _ = entries[pos - 1]
        return PacketKey(vertex=vertex, event_idx=event_idx, ts=ts)

    def packet_dependencies(self, packet: PacketKey) -> List[PacketKey]:
        """Packets needed to materialize a memory packet."""

        if packet.is_initial:
            return []
        event = self.events[packet.event_idx]
        peer = event.peer(packet.vertex)
        return [
            self.state_packet(packet.vertex, event.ts),
            self.state_packet(peer, event.ts),
        ]

    def targets_from_recent_events(self, count: int, endpoint: str = "dst") -> List[TargetQuery]:
        """Create target queries from the most recent events.

        The timestamp is nudged forward by a tiny amount so the event itself is
        visible to state_packet(). Synthetic timestamps are strictly increasing,
        and the CSV path sorts by timestamp before this method is used.
        """

        if count <= 0:
            return []
        selected = self.events[-count:]
        targets: List[TargetQuery] = []
        for event in selected:
            if endpoint == "src":
                vertex = event.src
            elif endpoint == "both":
                vertex = event.src if event.idx % 2 == 0 else event.dst
            else:
                vertex = event.dst
            targets.append(
                TargetQuery(
                    vertex=vertex,
                    timestamp=event.ts + 1e-9,
                    event_idx=event.idx,
                )
            )
        return targets

    def event_window_size(self, targets: Sequence[TargetQuery]) -> int:
        if not targets:
            return 0
        event_indices = [target.event_idx for target in targets if target.event_idx is not None]
        if not event_indices:
            max_ts = max(target.timestamp for target in targets)
            return bisect_left([event.ts for event in self.events], max_ts)
        return max(event_indices) - min(event_indices) + 1
