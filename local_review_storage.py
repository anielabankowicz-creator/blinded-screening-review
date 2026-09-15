from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from supabase_review_storage import StorageError, hash_access_code, utc_now


class LocalReviewStorage:
    def __init__(self, path: str | Path = "review_app_local_state.json") -> None:
        self.path = Path(path)
        if not self.path.exists():
            self._write(self._empty_state())
        state = self._read()
        if not state["review_reviewers"]:
            self.upsert_reviewer("lead", "Local Lead", "lead", "lead-demo")
        self._ensure_default_account("reviewer_a", "Reviewer A", "reviewer", "reviewer-a")
        self._ensure_default_account("reviewer_b", "Reviewer B", "reviewer", "reviewer-b")
        self._ensure_default_account("adjudicator", "Adjudicator", "adjudicator", "adjudicator-demo")

    def list_reviewers(self) -> list[dict[str, Any]]:
        return list(self._read()["review_reviewers"].values())

    def authenticate(self, access_code: str, role: str | None = None) -> dict[str, Any] | None:
        code_hash = hash_access_code(access_code)
        for reviewer in self._read()["review_reviewers"].values():
            if reviewer.get("access_code_hash") == code_hash and (role is None or reviewer.get("role") == role):
                return reviewer
        return None

    def upsert_reviewer(self, reviewer_id: str, display_name: str, role: str, access_code: str) -> None:
        state = self._read()
        existing = state["review_reviewers"].get(reviewer_id, {})
        state["review_reviewers"][reviewer_id] = {
            **existing,
            "reviewer_id": reviewer_id,
            "display_name": display_name,
            "role": role,
            "access_code_hash": hash_access_code(access_code),
            "is_active": True,
            "updated_at": utc_now(),
            "created_at": existing.get("created_at") or utc_now(),
        }
        self._write(state)

    def upsert_records(self, rows: list[dict[str, Any]]) -> None:
        state = self._read()
        for row in rows:
            state["review_records"][row["record_id"]] = row
        self._write(state)

    def upsert_sample(self, sample_id: str, seed: int, sample_size: int, record_ids: list[str]) -> None:
        state = self._read()
        state["review_samples"][sample_id] = {
            "sample_id": sample_id,
            "seed": seed,
            "sample_size": sample_size,
            "source_record_count": 1129,
            "record_ids": record_ids,
            "updated_at": utc_now(),
        }
        state["review_sample_records"][sample_id] = [
            {"sample_id": sample_id, "record_id": record_id, "position": i + 1}
            for i, record_id in enumerate(record_ids)
        ]
        self._write(state)

    def get_sample_record_ids(self, sample_id: str) -> list[str]:
        rows = self._read()["review_sample_records"].get(sample_id, [])
        return [row["record_id"] for row in sorted(rows, key=lambda row: row["position"])]

    def get_records(self, record_ids: list[str] | None = None) -> list[dict[str, Any]]:
        records = self._read()["review_records"]
        if not record_ids:
            return list(records.values())
        return [records[record_id] for record_id in record_ids if record_id in records]

    def get_decisions(self, sample_id: str, reviewer_id: str | None = None) -> list[dict[str, Any]]:
        rows = [
            row for row in self._read()["review_decisions"]
            if row["sample_id"] == sample_id and (reviewer_id is None or row["reviewer_id"] == reviewer_id)
        ]
        return rows

    def save_decision(self, payload: dict[str, Any]) -> None:
        state = self._read()
        key = (payload["sample_id"], payload["record_id"], payload["reviewer_id"])
        kept = []
        for row in state["review_decisions"]:
            row_key = (row["sample_id"], row["record_id"], row["reviewer_id"])
            if row_key == key and row.get("locked"):
                raise StorageError("This decision has already been locked.")
            if row_key != key:
                kept.append(row)
        kept.append({**payload, "updated_at": utc_now()})
        state["review_decisions"] = kept
        self._write(state)

    def lock_reviewer(self, sample_id: str, reviewer_id: str) -> None:
        state = self._read()
        now = utc_now()
        for row in state["review_decisions"]:
            if row["sample_id"] == sample_id and row["reviewer_id"] == reviewer_id:
                row["locked"] = True
                row["submitted_at"] = row.get("submitted_at") or now
                row["updated_at"] = now
        self._write(state)

    def get_adjudications(self, sample_id: str) -> list[dict[str, Any]]:
        return [row for row in self._read()["review_adjudications"] if row["sample_id"] == sample_id]

    def save_adjudication(self, payload: dict[str, Any]) -> None:
        state = self._read()
        key = (payload["sample_id"], payload["record_id"])
        kept = []
        for row in state["review_adjudications"]:
            row_key = (row["sample_id"], row["record_id"])
            if row_key == key and row.get("locked"):
                raise StorageError("This adjudication has already been locked.")
            if row_key != key:
                kept.append(row)
        kept.append({**payload, "updated_at": utc_now()})
        state["review_adjudications"] = kept
        self._write(state)

    def _read(self) -> dict[str, Any]:
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, state: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _empty_state(self) -> dict[str, Any]:
        return {
            "review_records": {},
            "review_samples": {},
            "review_sample_records": {},
            "review_reviewers": {},
            "review_decisions": [],
            "review_adjudications": [],
        }

    def _ensure_default_account(self, reviewer_id: str, display_name: str, role: str, access_code: str) -> None:
        if reviewer_id not in self._read()["review_reviewers"]:
            self.upsert_reviewer(reviewer_id, display_name, role, access_code)
