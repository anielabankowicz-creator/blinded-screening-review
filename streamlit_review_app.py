from __future__ import annotations

import csv
import io
import math
import random
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from local_review_storage import LocalReviewStorage
from supabase_review_storage import StorageError, SupabaseReviewStorage, utc_now


DEFAULT_CSV = Path("TASO_fin_deduplicated_1129_screened.csv")
DEFAULT_SAMPLE_ID = "taso_financial_support_seed_20260914_n226"
DEFAULT_SEED = 20260914
DEFAULT_SAMPLE_SIZE = 226
SAMPLE_FRACTION = 0.20
DECISIONS = ["Include", "Exclude", "Unsure"]
AI_TO_REVIEW = {"Yes": "Include", "No": "Exclude", "Uncertain": "Unsure"}
SCREENING_CRITERIA = {
    "Population": {
        "include": "Undergraduate students enrolled in higher education, including financially or socioeconomically disadvantaged students. Mixed samples qualify when eligible students are reported separately or form most of the sample.",
        "exclude": "School pupils, prospective students not yet enrolled, further education or below-HE learners, postgraduate-only samples, or general student populations where support is unrelated to financial barriers.",
    },
    "Intervention": {
        "include": "Direct financial or in-kind support received after entry, such as bursaries, grants, need-linked scholarships, hardship funds, stipends, cash, fee waivers, accommodation, food, transport, technology, or study materials.",
        "exclude": "Repayable loans; financial education alone; academic, mentoring, or pastoral support alone; general funding policies without student-level support; or merit-only scholarships unrelated to need or target demographics.",
    },
    "Timing": {
        "include": "Support delivered wholly or partly after enrolment. Pre-entry awards may qualify when payments continue during higher education and post-entry outcomes are evaluated.",
        "exclude": "Support delivered entirely before entry and evaluated only through applications, admissions, or initial enrolment.",
    },
    "Comparator": {
        "include": "No support, usual provision, delayed support, or an alternative type or amount of support assessed using a credible counterfactual.",
        "exclude": "No comparison group or other credible counterfactual capable of supporting causal attribution.",
    },
    "Outcomes": {
        "include": "Retention, continuation, persistence, attendance, attainment, credits, completion, graduation, withdrawal, dropout, re-enrolment, progression, or relevant secondary outcomes such as wellbeing and financial stress.",
        "exclude": "Only applications, admissions, initial enrolment, awareness, take-up, satisfaction, expenditure, or administrative delivery outcomes.",
    },
    "Study design": {
        "include": "Randomised trials and credible quasi-experimental or appropriately adjusted comparison-group studies.",
        "exclude": "Qualitative-only, descriptive, uncontrolled before-and-after, simple cross-sectional, intervention-description, or process-only studies without causal analysis.",
    },
    "Publication": {
        "include": "Peer-reviewed articles, institutional or government reports, working papers, dissertations, theses, and sufficiently detailed preprints published from 2014 to the final 2026 search date, with English full text available.",
        "exclude": "Editorials, commentaries, protocols, news, conference abstracts, methodologically insufficient sources, pre-2014 publications, or sources without accessible English full text.",
    },
}
EXCLUSION_REASONS = [
    "Ineligible population",
    "No eligible financial or in-kind support intervention",
    "Repayable loan only",
    "Merit-only scholarship not linked to financial need or target demographics",
    "Support or outcomes entirely before higher education entry",
    "No credible comparator or counterfactual",
    "No eligible student outcome",
    "Ineligible study design",
    "General funding policy without an identifiable student-level intervention",
    "Ineligible publication type or insufficient information source",
    "Published before 2014",
    "English full text unavailable",
]


def main() -> None:
    st.set_page_config(page_title="Blinded screening review", page_icon=":material/rate_review:", layout="wide")

    storage = connect_storage()
    if storage is None:
        st.warning("Supabase is not configured or unavailable. Add credentials, install requirements, and run the schema first.")
        st.code("pip install -r requirements.txt\nstreamlit run streamlit_review_app.py")
        st.stop()

    sample_id = DEFAULT_SAMPLE_ID
    role, user = sidebar_identity(storage, sample_id)
    st.title("Blinded screening review", icon=":material/rate_review:")

    if not user:
        st.info("Choose who you are in the sidebar to start.")
        st.stop()

    if role == "lead":
        lead_dashboard(storage, sample_id)
    elif role == "adjudicator":
        adjudication_screen(storage, sample_id, user)
    else:
        reviewer_screen(storage, sample_id, user)


def sidebar_identity(storage: SupabaseReviewStorage | LocalReviewStorage, sample_id: str) -> tuple[str, dict[str, Any] | None]:
    with st.sidebar:
        st.header("Start here", icon=":material/person:")
        total = len(storage.get_sample_record_ids(sample_id))
        with st.container(border=True):
            st.markdown("**Workflow**")
            st.caption("1. Lead uploads AI spreadsheet")
            st.caption("2. App draws random QA sample")
            st.caption("3. Reviewer A and B screen it")
            st.caption("4. Dashboard shows review stats")
            st.metric("Active sample", total)
        if isinstance(storage, LocalReviewStorage):
            reviewers = {row["reviewer_id"]: row for row in storage.list_reviewers()}
            default_choice = "Lead" if not total else "Reviewer A"
            choice = st.segmented_control(
                "Who is using the app?",
                ["Lead", "Reviewer A", "Reviewer B", "Adjudicator"],
                default=default_choice,
            )
            mapping = {
                "Lead": ("lead", "lead"),
                "Reviewer A": ("reviewer", "reviewer_a"),
                "Reviewer B": ("reviewer", "reviewer_b"),
                "Adjudicator": ("adjudicator", "adjudicator"),
            }
            role, reviewer_id = mapping[choice]
            user = reviewers.get(reviewer_id)
            st.caption("Local mode saves progress on this computer.")
            if role == "reviewer":
                saved = len(storage.get_decisions(sample_id, user["reviewer_id"])) if user else 0
                total = len(storage.get_sample_record_ids(sample_id))
                st.metric("Your progress", f"{saved}/{total}")
            return role, user

        role = st.selectbox("Mode", ["reviewer", "adjudicator", "lead"], format_func=str.title)
        code = st.text_input("Access code", type="password")
        user = storage.authenticate(code, role=role) if code else None
        if user:
            st.success(f"Signed in as {user['display_name']}")
        elif code:
            st.error("Access code not recognised for this mode.")
        return role, user


def ensure_default_sample(storage: SupabaseReviewStorage | LocalReviewStorage, sample_id: str) -> None:
    if storage.get_sample_record_ids(sample_id):
        return
    rows = load_csv(DEFAULT_CSV)
    record_rows = [record_payload(row, index) for index, row in enumerate(rows, 1)]
    sampled = reproducible_sample([row["record_id"] for row in record_rows], DEFAULT_SAMPLE_SIZE, DEFAULT_SEED)
    storage.upsert_records(record_rows)
    storage.upsert_sample(sample_id, DEFAULT_SEED, DEFAULT_SAMPLE_SIZE, sampled)


@st.cache_resource(show_spinner=False)
def connect_storage() -> SupabaseReviewStorage | LocalReviewStorage | None:
    try:
        url = st.secrets.get("SUPABASE_URL", None)
        key = st.secrets.get("SUPABASE_ANON_KEY", None) or st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", None)
    except Exception:
        url = key = None
    try:
        return SupabaseReviewStorage(url=url, key=key)
    except StorageError:
        return LocalReviewStorage()


def lead_dashboard(storage: SupabaseReviewStorage | LocalReviewStorage, sample_id: str) -> None:
    st.subheader("Lead dashboard", icon=":material/admin_panel_settings:")
    st.caption("Reviewer screens remain blinded. AI comparison only appears here.")
    upload_tab, overview_tab, dashboard_tab, export_tab, accounts_tab = st.tabs(["Set up sample", "Review stats", "AI comparison", "Exports", "Accounts"])

    with upload_tab:
        sample_setup_panel(storage, sample_id)

    with overview_tab:
        records = keyed(storage.get_records(storage.get_sample_record_ids(sample_id)))
        decisions = storage.get_decisions(sample_id)
        adjudications = storage.get_adjudications(sample_id)
        reviewer_names = reviewer_display_names(storage.list_reviewers())
        if not records:
            st.info("Upload a spreadsheet and create the random sample first.")
        else:
            review_dashboard(
                records,
                decisions,
                adjudications,
                show_agreement=True,
                show_ai=False,
                reviewer_names=reviewer_names,
            )

    with accounts_tab:
        st.caption("Create separate access codes. Codes are hashed before storage; the app never displays existing codes.")
        cols = st.columns(4)
        reviewer_id = cols[0].text_input("Account ID", placeholder="reviewer_a")
        display_name = cols[1].text_input("Display name", placeholder="Reviewer A")
        account_role = cols[2].selectbox("Role", ["reviewer", "adjudicator", "lead"])
        access_code = cols[3].text_input("New access code", type="password")
        if st.button("Create or update account") and reviewer_id and display_name and access_code:
            storage.upsert_reviewer(reviewer_id, display_name, account_role, access_code)
            st.success("Account saved.")
        st.dataframe(
            [{k: v for k, v in row.items() if k != "access_code_hash"} for row in storage.list_reviewers()],
            width="stretch",
            hide_index=True,
        )

    with dashboard_tab:
        records = keyed(storage.get_records(storage.get_sample_record_ids(sample_id)))
        decisions = storage.get_decisions(sample_id)
        adjudications = keyed(storage.get_adjudications(sample_id), key="record_id")
        reviewer_names = reviewer_display_names(storage.list_reviewers())
        if not records:
            st.info("Upload a spreadsheet and create the random sample first.")
        else:
            st.write("AI decisions are visible here only, after lead sign-in.")
            show_metrics(records, decisions, adjudications, reviewer_names)

    with export_tab:
        records = keyed(storage.get_records(storage.get_sample_record_ids(sample_id)))
        decisions = storage.get_decisions(sample_id)
        adjudications = storage.get_adjudications(sample_id)
        export_rows = build_export(records, decisions, adjudications)
        csv_bytes = to_csv(export_rows)
        st.download_button("Download complete CSV export", csv_bytes, "review_export.csv", "text/csv")
        st.download_button("Download RIS export", to_ris(export_rows), "review_export.ris", "application/x-research-info-systems")
        try:
            excel_bytes = to_excel(export_rows)
            st.download_button(
                "Download Excel export",
                excel_bytes,
                "review_export.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        except Exception:
            st.info("Install pandas/openpyxl to enable Excel export.")


def sample_setup_panel(storage: SupabaseReviewStorage | LocalReviewStorage, sample_id: str) -> None:
    st.subheader("Set up the review sample", icon=":material/upload_file:")
    st.write("Upload the spreadsheet that contains the AI decisions. The app will save the records and draw the same reproducible random sample for both reviewers.")

    current_ids = storage.get_sample_record_ids(sample_id)
    with st.container(horizontal=True):
        st.metric("Current sample", len(current_ids), border=True)
        st.metric("Sample rule", "20%", border=True)
        st.metric("Random seed", DEFAULT_SEED, border=True)

    uploaded = st.file_uploader("AI-decided spreadsheet", type=["csv", "xlsx"])
    seed = st.number_input("Random seed", value=DEFAULT_SEED, step=1)

    if uploaded:
        rows = load_uploaded_rows(uploaded)
        sample_size = sample_size_for_rows(rows)
        ai_summary = ai_column_summary(rows)
        st.success(f"Loaded {len(rows)} rows from {uploaded.name}.")
        st.metric("Random sample size", sample_size)
        if not ai_summary["has_ai_decision"]:
            st.warning("I do not see an AI decision column such as `inclusion` or `ai_inclusion`. You can still review, but AI comparison stats will be unavailable.")
        else:
            st.caption(f"AI decision column found: `{ai_summary['column']}`")
        create_sample_button(storage, sample_id, rows, sample_size, int(seed), "Create 20% random sample from uploaded spreadsheet")
    else:
        st.caption("For this demo, you can also use the bundled 1,129-row AI-screened spreadsheet.")
        bundled_rows = load_csv(DEFAULT_CSV)
        bundled_sample_size = sample_size_for_rows(bundled_rows)
        st.caption(f"Bundled spreadsheet: {len(bundled_rows)} records, 20% sample = {bundled_sample_size}.")
        if st.button("Use bundled spreadsheet and create 20% sample"):
            save_sample(storage, sample_id, bundled_rows, bundled_sample_size, int(seed))
            st.success(f"Created a sample of {bundled_sample_size} from the bundled {len(bundled_rows)} records.")
            st.rerun()


def create_sample_button(
    storage: SupabaseReviewStorage | LocalReviewStorage,
    sample_id: str,
    rows: list[dict[str, Any]],
    sample_size: int,
    seed: int,
    label: str,
) -> None:
    if st.button(label, type="primary"):
        save_sample(storage, sample_id, rows, sample_size, seed)
        st.success(f"Created a sample of {min(sample_size, len(rows))} from {len(rows)} records.")
        st.rerun()


def save_sample(
    storage: SupabaseReviewStorage | LocalReviewStorage,
    sample_id: str,
    rows: list[dict[str, Any]],
    sample_size: int,
    seed: int,
) -> None:
    if len(rows) != 1129:
        st.warning(f"Loaded {len(rows)} records. The planned QA design expects 1,129 records.")
    record_rows = [record_payload(row, index) for index, row in enumerate(rows, 1)]
    sampled = reproducible_sample([row["record_id"] for row in record_rows], sample_size, seed)
    storage.upsert_records(record_rows)
    storage.upsert_sample(sample_id, seed, sample_size, sampled)


def ai_column_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"has_ai_decision": False, "column": ""}
    columns = set(rows[0].keys())
    for column in ["inclusion", "ai_inclusion", "AI decision", "ai_decision", "decision"]:
        if column in columns:
            return {"has_ai_decision": True, "column": column}
    return {"has_ai_decision": False, "column": ""}


def sample_size_for_rows(rows: list[dict[str, Any]]) -> int:
    return max(1, math.ceil(len(rows) * SAMPLE_FRACTION)) if rows else 0


def reviewer_screen(storage: SupabaseReviewStorage | LocalReviewStorage, sample_id: str, reviewer: dict[str, Any]) -> None:
    record_ids = storage.get_sample_record_ids(sample_id)
    if not record_ids:
        st.info("The lead needs to upload the AI spreadsheet and create the random sample before reviewing starts.")
        return
    records = keyed(storage.get_records(record_ids))
    available_ids, missing_ids = partition_record_ids(record_ids, records)
    if missing_ids:
        st.error(
            f"{len(missing_ids)} sampled record(s) could not be loaded. "
            "The lead should recreate the sample before reviews are locked."
        )
    if not available_ids:
        st.stop()
    existing = keyed(storage.get_decisions(sample_id, reviewer["reviewer_id"]), key="record_id")
    locked = bool(existing) and all(row.get("locked") for row in existing.values()) and len(existing) >= len(record_ids)

    st.subheader(f"Reviewing as {reviewer['display_name']}", icon=":material/edit_note:")
    st.caption("You are blinded to AI decisions and to the other reviewer.")
    review_tab, dashboard_tab = st.tabs(["Review records", "My dashboard"])

    with dashboard_tab:
        decisions = storage.get_decisions(sample_id)
        adjudications = storage.get_adjudications(sample_id)
        reviewer_dashboard(record_ids, decisions, reviewer)

    with review_tab:
        reviewer_workbench(
            storage,
            sample_id,
            reviewer,
            available_ids,
            records,
            existing,
            locked,
            sample_is_complete=not missing_ids,
        )


def reviewer_workbench(
    storage: SupabaseReviewStorage | LocalReviewStorage,
    sample_id: str,
    reviewer: dict[str, Any],
    record_ids: list[str],
    records: dict[str, dict[str, Any]],
    existing: dict[str, dict[str, Any]],
    locked: bool,
    sample_is_complete: bool,
) -> None:
    progress_cols = st.columns(3)
    progress_cols[0].metric("Saved", len(existing))
    progress_cols[1].metric("Remaining", max(len(record_ids) - len(existing), 0))
    progress_cols[2].metric("Sample", len(record_ids))
    st.progress(len(existing) / len(record_ids) if record_ids else 0.0, text=f"{len(existing)} of {len(record_ids)} records saved")

    if locked:
        st.success("Your submission is locked.")

    selected = record_selector(record_ids, records, existing)
    if not selected:
        st.stop()
    with st.container(border=True):
        render_record(records[selected])
    prior = existing.get(selected, {})
    render_screening_criteria(f"reviewer_{selected}")
    decision = st.segmented_control(
        "Your decision",
        DECISIONS,
        default=prior.get("decision", "Unsure"),
        key=f"reviewer_decision_{selected}",
    )
    with st.form(f"decision_{selected}", border=False):
        exclusion_reasons: list[str] = []
        if decision == "Exclude":
            prior_reasons = parse_exclusion_reasons(prior.get("exclusion_reason"))
            reason_options = EXCLUSION_REASONS + [reason for reason in prior_reasons if reason not in EXCLUSION_REASONS]
            exclusion_reasons = st.multiselect(
                "Exclusion criteria",
                reason_options,
                default=prior_reasons,
                help="Select every criterion that clearly applies.",
            )
        notes = st.text_area("Notes", value=prior.get("notes") or "", placeholder="Optional paper-specific notes")
        submitted = st.form_submit_button("Save and continue", type="primary", disabled=bool(prior.get("locked")))
    if submitted:
        if decision == "Exclude" and not exclusion_reasons:
            st.error("Select at least one exclusion criterion before saving an Exclude decision.")
            return
        storage.save_decision(
            {
                "sample_id": sample_id,
                "record_id": selected,
                "reviewer_id": reviewer["reviewer_id"],
                "decision": decision,
                "exclusion_reason": format_exclusion_reasons(exclusion_reasons),
                "notes": notes,
                "locked": False,
            }
        )
        st.toast("Saved")
        st.rerun()

    complete = (
        sample_is_complete
        and len(existing) >= len(record_ids)
        and all(row.get("decision") in DECISIONS for row in existing.values())
    )
    with st.expander("Finish and lock your review", icon=":material/lock:"):
        st.write("Lock only when every sampled record has been screened. Locked submissions cannot be edited.")
        if st.button("Lock my completed review", disabled=locked or not complete):
            storage.lock_reviewer(sample_id, reviewer["reviewer_id"])
            st.success("Submission locked.")
            st.rerun()
        if not complete:
            st.caption("This unlocks after all 226 records have a saved decision.")


def adjudication_screen(storage: SupabaseReviewStorage | LocalReviewStorage, sample_id: str, adjudicator: dict[str, Any]) -> None:
    record_ids = storage.get_sample_record_ids(sample_id)
    records = keyed(storage.get_records(record_ids))
    available_ids, missing_ids = partition_record_ids(record_ids, records)
    decisions = storage.get_decisions(sample_id)
    by_record: dict[str, list[dict[str, Any]]] = {}
    for row in decisions:
        by_record.setdefault(row["record_id"], []).append(row)
    conflicts = [
        rid for rid in available_ids
        if len({row["decision"] for row in by_record.get(rid, [])}) > 1
    ]
    adjudicated = keyed(storage.get_adjudications(sample_id), key="record_id")

    st.subheader("Blinded adjudication", icon=":material/rule:")
    st.caption("This screen shows reviewer decisions but keeps AI decisions hidden.")
    if missing_ids:
        st.error(
            f"{len(missing_ids)} sampled record(s) could not be loaded. "
            "The lead should recreate the sample to restore complete adjudication."
        )
    if not available_ids:
        st.info("No sampled records are available for adjudication.")
        return
    st.metric("Reviewer conflicts", len(conflicts))
    target_ids = conflicts or available_ids
    selected = st.selectbox("Record", target_ids, format_func=lambda rid: f"{rid}: {records.get(rid, {}).get('title', '')[:90]}")
    render_record(records[selected])
    st.write("Reviewer decisions")
    st.dataframe(
        [
            {
                "reviewer": row["reviewer_id"],
                "decision": row["decision"],
                "exclusion_reason": row.get("exclusion_reason"),
                "notes": row.get("notes"),
                "locked": row.get("locked"),
            }
            for row in by_record.get(selected, [])
        ],
        width="stretch",
        hide_index=True,
    )
    prior = adjudicated.get(selected, {})
    render_screening_criteria(f"adjudicator_{selected}")
    final_decision = st.segmented_control(
        "Final blinded decision",
        DECISIONS,
        default=prior.get("final_decision", "Unsure"),
        key=f"adjudicator_decision_{selected}",
    )
    with st.form(f"adjudicate_{selected}"):
        exclusion_reasons: list[str] = []
        if final_decision == "Exclude":
            prior_reasons = parse_exclusion_reasons(prior.get("reason"))
            reason_options = EXCLUSION_REASONS + [reason for reason in prior_reasons if reason not in EXCLUSION_REASONS]
            exclusion_reasons = st.multiselect(
                "Exclusion criteria",
                reason_options,
                default=prior_reasons,
                help="Select every criterion that supports the final exclusion.",
            )
        notes = st.text_area("Notes", value=prior.get("notes") or "")
        lock = st.checkbox("Lock this adjudication", value=bool(prior.get("locked")))
        submitted = st.form_submit_button("Save adjudication", disabled=bool(prior.get("locked")))
    if submitted:
        if final_decision == "Exclude" and not exclusion_reasons:
            st.error("Select at least one exclusion criterion before saving an Exclude decision.")
            return
        storage.save_adjudication(
            {
                "sample_id": sample_id,
                "record_id": selected,
                "adjudicator_id": adjudicator["reviewer_id"],
                "final_decision": final_decision,
                "reason": format_exclusion_reasons(exclusion_reasons),
                "notes": notes,
                "locked": lock,
                "submitted_at": utc_now() if lock else None,
            }
        )
        st.success("Adjudication saved.")
        st.rerun()


def show_metrics(
    records: dict[str, dict[str, Any]],
    decisions: list[dict[str, Any]],
    adjudications: dict[str, dict[str, Any]],
    reviewer_names: dict[str, str] | None = None,
) -> None:
    review_dashboard(
        records,
        decisions,
        list(adjudications.values()),
        show_agreement=True,
        show_ai=True,
        reviewer_names=reviewer_names,
    )


def review_dashboard(
    records: dict[str, dict[str, Any]],
    decisions: list[dict[str, Any]],
    adjudications: list[dict[str, Any]],
    *,
    show_agreement: bool,
    show_ai: bool,
    reviewer_names: dict[str, str] | None = None,
) -> None:
    reviewer_names = reviewer_names or {}
    reviewer_ids = sorted({row["reviewer_id"] for row in decisions})
    sample_size = len(records)
    by_reviewer = {reviewer_id: [row for row in decisions if row["reviewer_id"] == reviewer_id] for reviewer_id in reviewer_ids}
    conflict_ids = conflicting_record_ids(decisions)

    with st.container(horizontal=True):
        st.metric("Sample records", sample_size, border=True)
        st.metric("Reviewer decisions", len(decisions), border=True)
        st.metric("Conflicts", len(conflict_ids), border=True)
        st.metric("Adjudicated", len(adjudications), border=True)

    if reviewer_ids:
        progress_rows = [
            {
                "reviewer": reviewer_names.get(reviewer_id, reviewer_id),
                "saved": len(rows),
                "remaining": max(sample_size - len(rows), 0),
                "completion": safe_div(len(rows), sample_size) or 0,
            }
            for reviewer_id, rows in by_reviewer.items()
        ]
        with st.container(border=True):
            st.subheader("Reviewer progress", icon=":material/checklist:")
            st.dataframe(
                pd.DataFrame(progress_rows),
                hide_index=True,
                width="stretch",
                column_config={
                    "completion": st.column_config.ProgressColumn(
                        "Completion",
                        min_value=0,
                        max_value=1,
                        format="percent",
                    )
                },
            )

    if decisions:
        with st.container(border=True):
            st.subheader("Decision mix", icon=":material/bar_chart:")
            st.bar_chart(
                decision_mix_frame(decisions, reviewer_names),
                x="decision",
                y="count",
                color="reviewer",
            )

    if show_agreement and len(reviewer_ids) >= 2:
        a, b = reviewer_ids[:2]
        pair = pair_vectors(decisions, a, b)
        with st.container(border=True):
            st.subheader("Reviewer agreement", icon=":material/handshake:")
            with st.container(horizontal=True):
                st.metric("Compared records", len(pair), border=True)
                st.metric("Percent agreement", f"{percent_agreement(pair):.1%}" if pair else "n/a", border=True)
                st.metric("Cohen's kappa", f"{cohens_kappa(pair):.3f}" if pair else "n/a", border=True)
            st.dataframe(confusion_matrix(pair), width="stretch", hide_index=True)

    if show_ai:
        for reviewer_id in reviewer_ids:
            pair = reviewer_ai_vectors(records, decisions, reviewer_id)
            with st.container(border=True):
                reviewer_label = reviewer_names.get(reviewer_id, reviewer_id)
                st.subheader(f"{reviewer_label} vs AI", icon=":material/analytics:")
                cols = st.columns(6)
                ai_stats = binary_ai_stats(pair)
                cols[0].metric("Agreement", f"{percent_agreement(pair):.1%}" if pair else "n/a")
                cols[1].metric("Kappa", f"{cohens_kappa(pair):.3f}" if pair else "n/a")
                cols[2].metric("AI recall", pct(ai_stats.get("recall")))
                cols[3].metric("Specificity", pct(ai_stats.get("specificity")))
                cols[4].metric("PPV / NPV", f"{pct(ai_stats.get('ppv'))} / {pct(ai_stats.get('npv'))}")
                cols[5].metric("False-exclusion", pct(ai_stats.get("false_exclusion_rate")))
                st.dataframe(confusion_matrix(pair), width="stretch", hide_index=True)


def reviewer_dashboard(record_ids: list[str], decisions: list[dict[str, Any]], reviewer: dict[str, Any]) -> None:
    own = [row for row in decisions if row["reviewer_id"] == reviewer["reviewer_id"]]
    own_by_record = {row["record_id"]: row for row in own}
    total = len(record_ids)
    saved = len(own_by_record)
    locked = bool(own_by_record) and all(row.get("locked") for row in own_by_record.values()) and saved >= total

    with st.container(horizontal=True):
        st.metric("Saved", saved, border=True)
        st.metric("Remaining", max(total - saved, 0), border=True)
        st.metric("Completion", pct(safe_div(saved, total)), border=True)
        st.metric("Status", "Locked" if locked else "In progress", border=True)

    with st.container(border=True):
        st.subheader("Your decision mix", icon=":material/bar_chart:")
        if own:
            st.bar_chart(decision_mix_frame(own), x="decision", y="count")
        else:
            st.caption("No decisions saved yet.")

    reviewer_ids = sorted({row["reviewer_id"] for row in decisions})
    progress_rows = [
        {
            "reviewer": "You" if rid == reviewer["reviewer_id"] else "Other reviewer",
            "saved": len([row for row in decisions if row["reviewer_id"] == rid]),
            "completion": safe_div(len([row for row in decisions if row["reviewer_id"] == rid]), total) or 0,
        }
        for rid in reviewer_ids
    ]
    if progress_rows:
        with st.container(border=True):
            st.subheader("Review progress", icon=":material/groups:")
            st.caption("This shows progress only, not the other reviewer’s decisions.")
            st.dataframe(
                pd.DataFrame(progress_rows),
                hide_index=True,
                width="stretch",
                column_config={
                    "completion": st.column_config.ProgressColumn(
                        "Completion",
                        min_value=0,
                        max_value=1,
                        format="percent",
                    )
                },
            )


def decision_mix_frame(
    decisions: list[dict[str, Any]],
    reviewer_names: dict[str, str] | None = None,
) -> pd.DataFrame:
    reviewer_names = reviewer_names or {}
    counts = Counter(
        (
            reviewer_names.get(row.get("reviewer_id", "reviewer"), row.get("reviewer_id", "reviewer")),
            row.get("decision", "Unsure"),
        )
        for row in decisions
    )
    rows = [
        {"reviewer": reviewer, "decision": decision, "count": count}
        for (reviewer, decision), count in sorted(counts.items())
    ]
    return pd.DataFrame(rows or [{"reviewer": "", "decision": decision, "count": 0} for decision in DECISIONS])


def reviewer_display_names(reviewers: list[dict[str, Any]]) -> dict[str, str]:
    name_counts = Counter(row.get("display_name") or row.get("reviewer_id") for row in reviewers)
    return {
        row["reviewer_id"]: (
            f"{row.get('display_name') or row['reviewer_id']} ({row['reviewer_id']})"
            if name_counts[row.get("display_name") or row["reviewer_id"]] > 1
            else row.get("display_name") or row["reviewer_id"]
        )
        for row in reviewers
    }


def conflicting_record_ids(decisions: list[dict[str, Any]]) -> list[str]:
    by_record: dict[str, set[str]] = {}
    for row in decisions:
        by_record.setdefault(row["record_id"], set()).add(row["decision"])
    return sorted(record_id for record_id, values in by_record.items() if len(values) > 1)


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_uploaded_rows(uploaded: Any) -> list[dict[str, str]]:
    name = uploaded.name.lower()
    data = uploaded.getvalue()
    if name.endswith(".csv"):
        return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))
    if name.endswith(".ris"):
        return ris_to_rows(data.decode("utf-8", errors="replace"))
    if name.endswith(".xlsx"):
        import pandas as pd

        return pd.read_excel(io.BytesIO(data)).fillna("").astype(str).to_dict("records")
    raise ValueError("Unsupported upload type.")


def ris_to_rows(text: str) -> list[dict[str, str]]:
    from screen_taso_financial_support import join, pick, year_from

    records: list[dict[str, list[str]]] = []
    rec: dict[str, list[str]] = {}
    current_tag: str | None = None
    for raw in text.splitlines():
        if len(raw) >= 6 and raw[2:6] == "  - ":
            tag, value = raw[:2], raw[6:].strip()
            if tag == "TY":
                rec = {"TY": [value]}
                current_tag = tag
            elif tag == "ER":
                if rec:
                    records.append(rec)
                rec = {}
                current_tag = None
            else:
                rec.setdefault(tag, []).append(value)
                current_tag = tag
        elif current_tag and rec:
            rec[current_tag][-1] = f"{rec[current_tag][-1]} {raw.strip()}".strip()
    rows = []
    for idx, rec in enumerate(records, 1):
        rows.append(
            {
                "record_id": f"RIS_{idx:04d}",
                "title": pick(rec, "TI", "T1"),
                "abstract": pick(rec, "AB", "N2"),
                "authors": join(rec, "AU", "A1"),
                "year": year_from(rec),
                "journal": pick(rec, "JF", "JO", "T2", "JA"),
                "doi": pick(rec, "DO"),
                "url": pick(rec, "UR"),
                "publication_type": pick(rec, "TY", "PT"),
                "keywords": join(rec, "KW"),
                "source_record_id": pick(rec, "ID", "AN"),
            }
        )
    return rows


def record_payload(row: dict[str, Any], index: int) -> dict[str, Any]:
    record_id = row.get("record_id") or row.get("id") or row.get("source_record_id") or f"UPLOADED_{index:04d}"
    return {
        "record_id": str(record_id),
        "title": row.get("title", ""),
        "abstract": row.get("abstract", ""),
        "authors": row.get("authors", ""),
        "year": str(row.get("year", "")),
        "journal": row.get("journal", ""),
        "doi": row.get("doi", ""),
        "url": row.get("url", ""),
        "publication_type": row.get("publication_type", ""),
        "keywords": row.get("keywords", ""),
        "source_record_id": row.get("source_record_id", ""),
        "apparent_duplicate": row.get("apparent_duplicate", ""),
        "ai_inclusion": row.get("inclusion", ""),
        "ai_rationale": row.get("rationale", ""),
        "ai_evidence": row.get("evidence", ""),
        "ai_exclusion_reason": row.get("exclusion_reason", ""),
        "ai_overall_confidence": int(row["overall_confidence"]) if str(row.get("overall_confidence", "")).isdigit() else None,
        "ai_needs_human_review": row.get("needs_human_review", ""),
        "raw": row,
    }


def reproducible_sample(record_ids: list[str], sample_size: int, seed: int) -> list[str]:
    rng = random.Random(seed)
    return rng.sample(sorted(record_ids), min(sample_size, len(record_ids)))


def keyed(rows: list[dict[str, Any]], key: str = "record_id") -> dict[str, dict[str, Any]]:
    return {row[key]: row for row in rows if row.get(key)}


def partition_record_ids(
    record_ids: list[str],
    records: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    available = [record_id for record_id in record_ids if record_id in records]
    missing = [record_id for record_id in record_ids if record_id not in records]
    return available, missing


def record_selector(record_ids: list[str], records: dict[str, dict[str, Any]], existing: dict[str, dict[str, Any]]) -> str | None:
    pending = [rid for rid in record_ids if rid not in existing]
    options = pending + [rid for rid in record_ids if rid in existing]
    if not options:
        return None
    return st.selectbox(
        "Current record",
        options,
        format_func=lambda rid: f"{'Pending' if rid in pending else 'Saved'} | {rid}: {records.get(rid, {}).get('title', '')[:90]}",
    )


def render_record(row: dict[str, Any]) -> None:
    st.markdown(f"### {row.get('title') or 'Untitled'}")
    meta = " | ".join(str(row.get(k) or "") for k in ["authors", "year", "journal"] if row.get(k))
    if meta:
        st.caption(meta)
    st.write(row.get("abstract") or "No abstract available.")
    link_cols = st.columns(2)
    if row.get("doi"):
        link_cols[0].write(f"DOI: {row['doi']}")
    if row.get("url"):
        link_cols[1].write(row["url"])


def render_screening_criteria(key_suffix: str) -> None:
    with st.expander("Screening criteria", icon=":material/checklist:"):
        domain = st.selectbox(
            "Criteria domain",
            list(SCREENING_CRITERIA),
            key=f"criteria_domain_{key_suffix}",
        )
        criterion = SCREENING_CRITERIA[domain]
        st.markdown("**Include**")
        st.write(criterion["include"])
        st.markdown("**Exclude**")
        st.write(criterion["exclude"])


def parse_exclusion_reasons(value: Any) -> list[str]:
    if not value:
        return []
    return [reason.strip() for reason in str(value).split(";") if reason.strip()]


def format_exclusion_reasons(reasons: list[str]) -> str:
    return "; ".join(dict.fromkeys(reason.strip() for reason in reasons if reason.strip()))


def pair_vectors(decisions: list[dict[str, Any]], reviewer_a: str, reviewer_b: str) -> list[tuple[str, str]]:
    by_reviewer = {(row["reviewer_id"], row["record_id"]): row["decision"] for row in decisions}
    record_ids = {row["record_id"] for row in decisions if row["reviewer_id"] in {reviewer_a, reviewer_b}}
    return [
        (by_reviewer[(reviewer_a, rid)], by_reviewer[(reviewer_b, rid)])
        for rid in sorted(record_ids)
        if (reviewer_a, rid) in by_reviewer and (reviewer_b, rid) in by_reviewer
    ]


def reviewer_ai_vectors(records: dict[str, dict[str, Any]], decisions: list[dict[str, Any]], reviewer_id: str) -> list[tuple[str, str]]:
    pairs = []
    for row in decisions:
        if row["reviewer_id"] != reviewer_id:
            continue
        ai = AI_TO_REVIEW.get(records.get(row["record_id"], {}).get("ai_inclusion"))
        if ai:
            pairs.append((row["decision"], ai))
    return pairs


def percent_agreement(pairs: list[tuple[str, str]]) -> float:
    return sum(1 for a, b in pairs if a == b) / len(pairs) if pairs else 0.0


def cohens_kappa(pairs: list[tuple[str, str]]) -> float:
    if not pairs:
        return 0.0
    labels = sorted(set(DECISIONS) | {value for pair in pairs for value in pair})
    observed = percent_agreement(pairs)
    total = len(pairs)
    left = Counter(a for a, _ in pairs)
    right = Counter(b for _, b in pairs)
    expected = sum((left[label] / total) * (right[label] / total) for label in labels)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def confusion_matrix(pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    labels = DECISIONS
    return [
        {"reviewer": label, **{f"comparison_{col}": sum(1 for a, b in pairs if a == label and b == col) for col in labels}}
        for label in labels
    ]


def binary_ai_stats(pairs: list[tuple[str, str]]) -> dict[str, float | None]:
    binary = [(human, ai) for human, ai in pairs if human in {"Include", "Exclude"} and ai in {"Include", "Exclude"}]
    tp = sum(1 for human, ai in binary if human == "Include" and ai == "Include")
    tn = sum(1 for human, ai in binary if human == "Exclude" and ai == "Exclude")
    fp = sum(1 for human, ai in binary if human == "Exclude" and ai == "Include")
    fn = sum(1 for human, ai in binary if human == "Include" and ai == "Exclude")
    return {
        "recall": safe_div(tp, tp + fn),
        "specificity": safe_div(tn, tn + fp),
        "ppv": safe_div(tp, tp + fp),
        "npv": safe_div(tn, tn + fn),
        "false_exclusion_rate": safe_div(fn, tp + fn),
    }


def safe_div(num: int, den: int) -> float | None:
    return None if den == 0 else num / den


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1%}"


def build_export(records: dict[str, dict[str, Any]], decisions: list[dict[str, Any]], adjudications: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = {rid: dict(row) for rid, row in records.items()}
    for row in decisions:
        prefix = f"reviewer_{row['reviewer_id']}"
        out = output.setdefault(row["record_id"], {"record_id": row["record_id"]})
        out[f"{prefix}_decision"] = row.get("decision")
        out[f"{prefix}_exclusion_reason"] = row.get("exclusion_reason")
        out[f"{prefix}_notes"] = row.get("notes")
        out[f"{prefix}_locked"] = row.get("locked")
    for row in adjudications:
        out = output.setdefault(row["record_id"], {"record_id": row["record_id"]})
        out["adjudicated_decision"] = row.get("final_decision")
        out["adjudication_reason"] = row.get("reason")
        out["adjudication_notes"] = row.get("notes")
    return list(output.values())


def to_csv(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    fields = sorted({key for row in rows for key in row})
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def to_excel(rows: list[dict[str, Any]]) -> bytes:
    import pandas as pd

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, index=False, sheet_name="review_export")
    return buffer.getvalue()


def to_ris(rows: list[dict[str, Any]]) -> bytes:
    lines: list[str] = []
    for row in rows:
        lines.extend(
            [
                "TY  - JOUR",
                f"TI  - {row.get('title', '')}",
                f"AB  - {row.get('abstract', '')}",
                f"PY  - {row.get('year', '')}",
                f"DO  - {row.get('doi', '')}",
                f"UR  - {row.get('url', '')}",
                f"N1  - Final decision: {row.get('adjudicated_decision', '')}",
                "ER  -",
                "",
            ]
        )
    return "\n".join(lines).encode("utf-8")


if __name__ == "__main__":
    main()
