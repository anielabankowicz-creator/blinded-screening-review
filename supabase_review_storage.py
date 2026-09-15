from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_access_code(access_code: str) -> str:
    return hashlib.sha256(access_code.strip().encode("utf-8")).hexdigest()


class StorageError(RuntimeError):
    pass


class SupabaseReviewStorage:
    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_ANON_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        if not self.url or not self.key:
            raise StorageError("Supabase URL/key are not configured.")
        try:
            from supabase import create_client
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise StorageError("The supabase package is not installed.") from exc
        self.client = create_client(self.url, self.key)

    def list_reviewers(self) -> list[dict[str, Any]]:
        return self._select("review_reviewers", "*")

    def authenticate(self, access_code: str, role: str | None = None) -> dict[str, Any] | None:
        rows = (
            self.client.table("review_reviewers")
            .select("*")
            .eq("access_code_hash", hash_access_code(access_code))
            .execute()
            .data
            or []
        )
        if not rows:
            return None
        reviewer = rows[0]
        if role and reviewer.get("role") != role:
            return None
        return reviewer

    def upsert_reviewer(self, reviewer_id: str, display_name: str, role: str, access_code: str) -> None:
        self._upsert(
            "review_reviewers",
            {
                "reviewer_id": reviewer_id,
                "display_name": display_name,
                "role": role,
                "access_code_hash": hash_access_code(access_code),
                "is_active": True,
                "updated_at": utc_now(),
            },
            on_conflict="reviewer_id",
        )

    def upsert_records(self, rows: list[dict[str, Any]]) -> None:
        if rows:
            self._upsert("review_records", rows, on_conflict="record_id")

    def upsert_sample(self, sample_id: str, seed: int, sample_size: int, record_ids: list[str]) -> None:
        self._upsert(
            "review_samples",
            {
                "sample_id": sample_id,
                "seed": seed,
                "sample_size": sample_size,
                "source_record_count": 1129,
                "record_ids": record_ids,
                "updated_at": utc_now(),
            },
            on_conflict="sample_id",
        )
        assignments = [
            {"sample_id": sample_id, "record_id": record_id, "position": i + 1}
            for i, record_id in enumerate(record_ids)
        ]
        self._upsert("review_sample_records", assignments, on_conflict="sample_id,record_id")

    def get_sample_record_ids(self, sample_id: str) -> list[str]:
        rows = (
            self.client.table("review_sample_records")
            .select("record_id,position")
            .eq("sample_id", sample_id)
            .order("position")
            .execute()
            .data
            or []
        )
        return [row["record_id"] for row in rows]

    def get_records(self, record_ids: list[str] | None = None) -> list[dict[str, Any]]:
        query = self.client.table("review_records").select("*")
        if record_ids:
            query = query.in_("record_id", record_ids)
        return query.execute().data or []

    def get_decisions(self, sample_id: str, reviewer_id: str | None = None) -> list[dict[str, Any]]:
        query = self.client.table("review_decisions").select("*").eq("sample_id", sample_id)
        if reviewer_id:
            query = query.eq("reviewer_id", reviewer_id)
        return query.execute().data or []

    def save_decision(self, payload: dict[str, Any]) -> None:
        existing = (
            self.client.table("review_decisions")
            .select("locked")
            .eq("sample_id", payload["sample_id"])
            .eq("record_id", payload["record_id"])
            .eq("reviewer_id", payload["reviewer_id"])
            .execute()
            .data
            or []
        )
        if existing and existing[0].get("locked"):
            raise StorageError("This decision has already been locked.")
        payload["updated_at"] = utc_now()
        self._upsert("review_decisions", payload, on_conflict="sample_id,record_id,reviewer_id")

    def lock_reviewer(self, sample_id: str, reviewer_id: str) -> None:
        rows = self.get_decisions(sample_id, reviewer_id)
        now = utc_now()
        for row in rows:
            row["locked"] = True
            row["submitted_at"] = row.get("submitted_at") or now
            row["updated_at"] = now
        if rows:
            self._upsert("review_decisions", rows, on_conflict="sample_id,record_id,reviewer_id")

    def get_adjudications(self, sample_id: str) -> list[dict[str, Any]]:
        return self._select("review_adjudications", "*", sample_id=sample_id)

    def save_adjudication(self, payload: dict[str, Any]) -> None:
        existing = (
            self.client.table("review_adjudications")
            .select("locked")
            .eq("sample_id", payload["sample_id"])
            .eq("record_id", payload["record_id"])
            .execute()
            .data
            or []
        )
        if existing and existing[0].get("locked"):
            raise StorageError("This adjudication has already been locked.")
        payload["updated_at"] = utc_now()
        self._upsert("review_adjudications", payload, on_conflict="sample_id,record_id")

    def _select(self, table: str, columns: str, **filters: Any) -> list[dict[str, Any]]:
        query = self.client.table(table).select(columns)
        for key, value in filters.items():
            query = query.eq(key, value)
        return query.execute().data or []

    def _upsert(self, table: str, payload: Any, on_conflict: str) -> None:
        response = self.client.table(table).upsert(payload, on_conflict=on_conflict).execute()
        if getattr(response, "data", None) is None and getattr(response, "error", None):
            raise StorageError(str(response.error))
