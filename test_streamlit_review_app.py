import unittest

from streamlit_review_app import format_exclusion_reasons, parse_exclusion_reasons, partition_record_ids


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


if __name__ == "__main__":
    unittest.main()
