from __future__ import annotations

import unittest

from tempgenn.functional import TinyTGNNStateModel
from tempgenn.simulator import SimulationConfig, simulate_batch
from tempgenn.synthetic import generate_synthetic_graph
from tempgenn.tdp import TDPBuilder


class TDPReproductionTests(unittest.TestCase):
    def test_overlap_metrics_are_well_formed(self) -> None:
        graph = generate_synthetic_graph(vertices=128, edges=1200, seed=4)
        targets = graph.targets_from_recent_events(64)
        metrics = simulate_batch(
            graph,
            targets,
            SimulationConfig(fanout=8, depth=2, tdp_entries=8),
        )

        self.assertGreater(metrics.total_tdp_packets, 0)
        self.assertGreater(metrics.unique_tdp_packets, 0)
        self.assertLessEqual(metrics.unique_tdp_packets, metrics.total_tdp_packets)
        self.assertGreaterEqual(metrics.avg_branch_parallelism_ratio, 0.0)
        self.assertLessEqual(metrics.avg_branch_parallelism_ratio, 1.0)
        self.assertGreater(metrics.speedup_vs_wo_oats, 0.0)

    def test_recursive_packet_state_matches_chronological_update(self) -> None:
        graph = generate_synthetic_graph(vertices=32, edges=160, seed=11)
        targets = graph.targets_from_recent_events(16)
        tdps = TDPBuilder(graph, fanout=4, depth=None).build_many(targets)

        result = TinyTGNNStateModel(graph).verify_tdps(tdps, sample_limit=500)

        self.assertTrue(result.passed)
        self.assertGreater(result.packets_checked, 0)


if __name__ == "__main__":
    unittest.main()
