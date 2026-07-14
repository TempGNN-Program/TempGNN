from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.stage_u280_artifacts import (
    REPORT_PATTERNS,
    REQUIRED_REPORTS,
    find_report,
    parse_assignments,
    redact_text,
    validate_required_reports,
)


class StageU280ArtifactsTest(unittest.TestCase):
    def test_parse_assignments_requires_all_systems(self) -> None:
        values = [
            "TempGNN=/tmp/t",
            "MATG=/tmp/m",
            "ViTeGNN=/tmp/v",
            "RTGA=/tmp/r",
        ]
        parsed = parse_assignments(
            values, "--build", required={"TempGNN", "MATG", "ViTeGNN", "RTGA"}
        )
        self.assertEqual(parsed["RTGA"], Path("/tmp/r"))

    def test_redact_text_prefers_long_paths(self) -> None:
        text = "/home/private/repo by private on private-host"
        redacted = redact_text(
            text,
            {
                "/home/private/repo": "/home/ae_reviewer/TempGNN",
                "private": "ae_reviewer",
                "private-host": "u280-ae-host",
            },
        )
        self.assertEqual(
            redacted, "/home/ae_reviewer/TempGNN by ae_reviewer on u280-ae-host"
        )

    def test_find_report_honors_pattern_priority(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            preferred = root / "dr_timing_summary.rpt"
            fallback = root / "large_timing_summary_routed.rpt"
            preferred.write_text("preferred", encoding="utf-8")
            fallback.write_text("fallback" * 100, encoding="utf-8")
            selected = find_report(
                root,
                ("**/dr_timing_summary.rpt", "**/*timing_summary_routed.rpt"),
            )
            self.assertEqual(selected, preferred)
            final_reports = root / "_x" / "reports" / "link" / "imp"
            final_reports.mkdir(parents=True)
            utilization = final_reports / "impl_1_kernel_util_routed.rpt"
            utilization.write_text("routed kernel utilization", encoding="utf-8")
            self.assertEqual(
                find_report(root, REPORT_PATTERNS["post_route_utilization.rpt"]),
                utilization,
            )

    def test_required_build_evidence_is_enforced(self) -> None:
        complete = {name: "sha256" for name in REQUIRED_REPORTS}
        validate_required_reports("MATG", complete)
        complete.pop("post_route_timing.rpt")
        with self.assertRaisesRegex(SystemExit, "post_route_timing.rpt"):
            validate_required_reports("MATG", complete)


if __name__ == "__main__":
    unittest.main()
