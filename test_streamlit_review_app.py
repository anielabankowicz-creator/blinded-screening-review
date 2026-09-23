import unittest

from streamlit_review_app import (
    clear_ai_pairs,
    decision_mix_frame,
    format_exclusion_reasons,
    parse_exclusion_reasons,
    partition_record_ids,
    reviewer_display_names,
)


class PartitionRecordIdsTest(unittest.TestCase):
    def test_preserves_order_and_reports_missing_records(self) -> None:
        record_ids = ["RIS_0003", "RIS_0001", "RIS_0002"]
        records = {
            "RIS_0001": {"record_id": "RIS_0001"},
            "RIS_0003": {"record_id": "RIS_0003"},
        }

        available, missing = partition_record_ids(record_ids, records)

        self.assertEqual(available, ["RIS_0003", "RIS_0001"])
        self.assertEqual(missing, ["RIS_0002"])


class ExclusionReasonsTest(unittest.TestCase):
    def test_round_trip_multiple_reasons(self) -> None:
        reasons = ["Ineligible population", "No eligible student outcome"]

        stored = format_exclusion_reasons(reasons)

        self.assertEqual(stored, "Ineligible population; No eligible student outcome")
        self.assertEqual(parse_exclusion_reasons(stored), reasons)

    def test_format_removes_blanks_and_duplicates(self) -> None:
        self.assertEqual(
            format_exclusion_reasons(["Ineligible population", "", "Ineligible population"]),
            "Ineligible population",
        )


class ReviewerNamesTest(unittest.TestCase):
    def test_dashboard_uses_distinct_display_names(self) -> None:
        reviewers = [
            {"reviewer_id": "reviewer_a", "display_name": "Alice"},
            {"reviewer_id": "reviewer_b", "display_name": "Bob"},
        ]
        names = reviewer_display_names(reviewers)
        decisions = [
            {"reviewer_id": "reviewer_a", "decision": "Include"},
            {"reviewer_id": "reviewer_b", "decision": "Exclude"},
        ]

        frame = decision_mix_frame(decisions, names)

        self.assertEqual(names, {"reviewer_a": "Alice", "reviewer_b": "Bob"})
        self.assertEqual(set(frame["reviewer"]), {"Alice", "Bob"})

    def test_duplicate_display_names_include_account_id(self) -> None:
        reviewers = [
            {"reviewer_id": "reviewer_a", "display_name": "Reviewer"},
            {"reviewer_id": "reviewer_b", "display_name": "Reviewer"},
        ]

        self.assertEqual(
            reviewer_display_names(reviewers),
            {
                "reviewer_a": "Reviewer (reviewer_a)",
                "reviewer_b": "Reviewer (reviewer_b)",
            },
        )


class AiAgreementTest(unittest.TestCase):
    def test_clear_pairs_exclude_uncertain_decisions(self) -> None:
        pairs = [
            ("Include", "Include"),
            ("Exclude", "Exclude"),
            ("Include", "Unsure"),
            ("Unsure", "Exclude"),
        ]

        self.assertEqual(
            clear_ai_pairs(pairs),
            [("Include", "Include"), ("Exclude", "Exclude")],
        )


if __name__ == "__main__":
    unittest.main()
