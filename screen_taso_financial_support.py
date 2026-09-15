#!/usr/bin/env python3
from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path


RIS_PATH = Path("/Users/anielabankowicz/Downloads/TASO_fin_deduplicated_1129.ris")
OUT_PATH = Path("TASO_fin_deduplicated_1129_screened.csv")


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def low(text: str) -> str:
    return norm(text).lower()


def has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text, flags=re.I) for pattern in patterns)


def first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.I)
        if match:
            return match.group(0)
    return ""


def parse_ris(path: Path) -> list[dict[str, list[str]]]:
    records: list[dict[str, list[str]]] = []
    rec: dict[str, list[str]] = {}
    current_tag: str | None = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
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
            rec[current_tag][-1] = norm(rec[current_tag][-1] + " " + raw.strip())
    return records


def pick(rec: dict[str, list[str]], *tags: str) -> str:
    for tag in tags:
        vals = [norm(v) for v in rec.get(tag, []) if norm(v)]
        if vals:
            return vals[0]
    return ""


def join(rec: dict[str, list[str]], *tags: str) -> str:
    vals: list[str] = []
    for tag in tags:
        vals.extend(norm(v) for v in rec.get(tag, []) if norm(v))
    return "; ".join(vals)


def year_from(rec: dict[str, list[str]]) -> str:
    raw = " ".join([pick(rec, "PY"), pick(rec, "Y1"), pick(rec, "DA")])
    match = re.search(r"(19|20)\d{2}", raw)
    return match.group(0) if match else ""


POP_EXCLUDE = [
    r"\bdoctoral\b", r"\bphd\b", r"\bdoctorate\b", r"\bgraduate nursing\b",
    r"\bpostgraduate\b", r"\bgraduate students?\b", r"\bmasters?\b",
    r"\bmedical residents?\b", r"\bresidency\b",
    r"\bhigh school\b", r"\bsecondary school\b", r"\bschool pupils?\b",
    r"\bmiddle school\b", r"\belementary\b", r"\bk-12\b", r"\bprospective students?\b",
]
HE_POP = [
    r"\bundergraduate", r"\bcollege students?\b", r"\buniversity students?\b",
    r"\bpostsecondary students?\b", r"\bhigher education\b", r"\btertiary education\b",
    r"\bcommunity college\b", r"\bfreshmen\b", r"\bfirst-year students?\b",
    r"\bbaccalaureate\b", r"\bdegree-seeking\b",
]
FINANCIAL_SUPPORT = [
    r"\bneed[- ]based grants?\b", r"\bgrants?\b", r"\bbursar(y|ies)\b",
    r"\bscholarships?\b", r"\bfinancial aid\b", r"\bfinancial support\b",
    r"\bhardship funds?\b", r"\bstipends?\b", r"\bcash transfers?\b",
    r"\bfee waivers?\b", r"\btuition waivers?\b", r"\btuition discount",
    r"\btuition subsidy\b", r"\bpell grants?\b", r"\bmaintenance grants?\b",
    r"\bfood pantr(y|ies)\b", r"\bfood scholarships?\b", r"\bmeal vouchers?\b",
    r"\baccommodation support\b", r"\bhousing assistance\b", r"\btransport(ation)? support\b",
    r"\btechnology grants?\b", r"\bstudy material(s)?\b",
]
INSTITUTIONAL_POLICY = [
    r"\bperformance[- ]based funding\b", r"\bperformance funding\b",
    r"\bfunding formula\b", r"\binstitutional grants?\b",
    r"\btitle iii grants?\b", r"\bresearch grants?\b",
    r"\bstate appropriations?\b", r"\bdistrict revenue\b",
    r"\binstitutional policy\b", r"\btuition fees?\b",
    r"\btest[- ]optional admission\b",
]
DIRECT_STUDENT_SUPPORT = [
    r"\bneed[- ]based grants?\b", r"\bpell grants?\b", r"\bmaintenance grants?\b",
    r"\bbursar(y|ies)\b", r"\bscholarships?\b", r"\bfinancial aid\b",
    r"\bfinancial support\b", r"\bhardship funds?\b", r"\bstipends?\b",
    r"\bcash transfers?\b", r"\bfee waivers?\b", r"\btuition waivers?\b",
    r"\btuition-free aid\b", r"\btuition promise\b", r"\bfree tuition\b",
    r"\bfood pantr(y|ies)\b", r"\bmeal vouchers?\b", r"\bhousing assistance\b",
    r"\btransport(ation)? support\b", r"\btechnology grants?\b",
]
FINANCIAL_SUPPORT_TITLE = [
    r"\bgrants?\b", r"\bbursar(y|ies)\b", r"\bscholarships?\b",
    r"\bfinancial aid\b", r"\bfinancial support\b", r"\bstudent aid\b",
    r"\bneed[- ]based aid\b", r"\bmerit aid\b", r"\bfinancial incentives?\b",
    r"\bpell\b", r"\bfree tuition\b", r"\btuition[- ]free\b",
    r"\btuition discount", r"\btuition waiver", r"\bhardship\b",
    r"\bemergency financial assistance\b", r"\bfood pantr(y|ies)\b",
    r"\bhousing assistance\b", r"\btransportation disadvantage\b",
]
SUPPORT_AS_INTERVENTION = [
    r"\beffects? of .{0,80}\b(financial aid|grant aid|grants?|scholarships?|student aid|need[- ]based aid|pell|free tuition|tuition[- ]free|financial support)",
    r"\bimpacts? of .{0,80}\b(financial aid|grant aid|grants?|scholarships?|student aid|need[- ]based aid|pell|free tuition|tuition[- ]free|financial support)",
    r"\b(financial aid|grant aid|grants?|scholarships?|student aid|need[- ]based aid|pell|free tuition|tuition[- ]free|financial support).{0,80}\b(effects?|impacts?|improves?|increases?|reduces?|affects?|evaluation|evaluat)",
    r"\beligible for .{0,60}\b(financial aid|grants?|scholarships?|pell|tuition)",
    r"\breceiv(e|ed|ing).{0,60}\b(financial aid|grants?|scholarships?|pell|financial support)",
    r"\boffer(s|ed)?.{0,60}\b(financial aid|grants?|scholarships?|need[- ]based grant)",
]
NON_ELIGIBLE_INTERVENTION = [
    r"\bstudent loans?\b", r"\brepayable\b", r"\bdebt\b",
    r"\bfinancial literacy\b", r"\bfinancial education\b", r"\bfinancial counselling\b",
    r"\bfinancial counseling\b", r"\bmentoring\b", r"\badvising\b",
    r"\bacademic support\b", r"\bpastoral support\b",
]
LOAN_ONLY = [
    r"\bstudent loans?\b", r"\bfederal loans?\b", r"\bloan aid\b",
    r"\bsubsidized loans?\b", r"\bunsubsidized loans?\b", r"\bstate-guaranteed loan\b",
]
PRE_ENTRY = [
    r"\bapplications?\b", r"\badmissions?\b", r"\benroll?ment\b",
    r"\bcollege choice\b", r"\bcollege-going\b", r"\baccess to college\b",
    r"\bmatriculation\b", r"\bpre[- ]college\b", r"\bearly information\b",
]
POST_ENTRY_OUTCOMES = [
    r"\bretention\b", r"\bcontinuation\b", r"\bpersist(ence|ing)?\b",
    r"\battendance\b", r"\bacademic performance\b", r"\bacademic attainment\b",
    r"\bcredits?\b", r"\bcredit accumulation\b", r"\bcompletion\b",
    r"\bgraduation\b", r"\bwithdraw(al|ing)?\b", r"\bdrop[- ]?out\b",
    r"\bre[- ]?enrol", r"\bprogression\b", r"\bgpa\b", r"\bgrades?\b",
    r"\bdegree completion\b", r"\btime to degree\b", r"\bwellbeing\b",
    r"\bmental health\b", r"\bfinancial stress\b", r"\bbelonging\b",
    r"\bengagement\b", r"\bemployment\b",
]
ONLY_INELIGIBLE_OUTCOMES = [
    r"\bawareness\b", r"\btake[- ]up\b", r"\bsatisfaction\b",
    r"\bexpenditure\b", r"\badministrative\b", r"\bimplementation\b",
]
CAUSAL_DESIGN = [
    r"\brandomi[sz]ed\b", r"\brct\b", r"\bcluster random",
    r"\bregression discontinuity\b", r"\bdifference[- ]in[- ]differences\b",
    r"\bdiff[- ]in[- ]diff\b", r"\binstrumental variables?\b",
    r"\binterrupted time series\b", r"\bsynthetic control\b",
    r"\bpropensity score\b", r"\bmatching\b", r"\bmatched\b",
    r"\bnatural experiment\b", r"\bquasi[- ]experimental\b",
    r"\bcausal\b", r"\bcounterfactual\b", r"\bcontrol(l?ed)? for\b",
    r"\badjust(ed|ing) for\b", r"\bcomparison group\b",
    r"\bfixed effects?\b", r"\bpanel data\b", r"\bmatched comparison\b",
]
STRONG_CAUSAL_DESIGN = [
    r"\brandomi[sz]ed\b", r"\brct\b", r"\bcluster random",
    r"\bregression discontinuity\b", r"\bdifference[- ]in[- ]differences\b",
    r"\bdiff[- ]in[- ]diff\b", r"\binstrumental variables?\b",
    r"\binterrupted time series\b", r"\bsynthetic control\b",
    r"\bpropensity score\b", r"\bmatching\b", r"\bmatched\b",
    r"\bnatural experiment\b", r"\bquasi[- ]experimental\b",
    r"\bcounterfactual\b", r"\bcomparison group\b", r"\bfixed effects?\b",
    r"\bpanel data\b", r"\bmatched comparison\b",
]
NON_CAUSAL_DESIGN = [
    r"\bqualitative\b", r"\binterviews?\b", r"\bfocus groups?\b",
    r"\bscoping review\b", r"\bsystematic review\b", r"\bliterature review\b",
    r"\bcase stud(y|ies)\b", r"\bdescriptive\b", r"\bcross[- ]sectional\b",
    r"\bcorrelat(ion|ional)\b", r"\bprotocol\b", r"\bcommentary\b",
    r"\beditorial\b", r"\bprocess evaluation\b",
]


def assess(row: dict[str, str]) -> dict[str, str]:
    core = low(" ".join([row["title"], row["abstract"]]))
    core = core.replace("national postsecondary student aid study", "")
    text = low(" ".join([row["title"], row["abstract"], row["publication_type"]]))
    title_text = low(row["title"])
    year = int(row["year"]) if row["year"].isdigit() else None

    he = has_any(text, HE_POP)
    pop_bad = has_any(text, POP_EXCLUDE)
    support = has_any(core, FINANCIAL_SUPPORT)
    direct_support = has_any(core, DIRECT_STUDENT_SUPPORT)
    support_title = has_any(title_text, FINANCIAL_SUPPORT_TITLE)
    support_intervention = support_title or has_any(core, SUPPORT_AS_INTERVENTION)
    non_support = has_any(text, NON_ELIGIBLE_INTERVENTION)
    outcome = has_any(text, POST_ENTRY_OUTCOMES)
    pre_entry = has_any(text, PRE_ENTRY)
    causal = has_any(text, CAUSAL_DESIGN)
    strong_causal = has_any(text, STRONG_CAUSAL_DESIGN)
    noncausal = has_any(text, NON_CAUSAL_DESIGN)
    only_admin = has_any(text, ONLY_INELIGIBLE_OUTCOMES) and not outcome
    institutional_policy = has_any(core, INSTITUTIONAL_POLICY)
    loan_only = has_any(text, LOAN_ONLY) and not has_any(text, [
        r"\bgrants?\b", r"\bscholarships?\b", r"\bbursar(y|ies)\b", r"\bhardship funds?\b",
        r"\bstipends?\b", r"\bcash transfers?\b", r"\bfee waivers?\b",
        r"\btuition waivers?\b", r"\bpell grants?\b", r"\bmaintenance grants?\b",
        r"\bfood pantr(y|ies)\b", r"\bmeal vouchers?\b", r"\bhousing assistance\b",
    ])

    pubtype = low(row["publication_type"])
    if year is not None and year < 2014:
        return decision("No", "Published before the eligible date range.", "The bibliographic year is before 2014.", "Publication date before 2014", 95)
    if re.search(r"\bconference abstract\b|\bconference paper\b|\bnews\b|\beditorial\b|\bcommentary\b|\bprotocol\b", pubtype + " " + title_text):
        return decision("No", "Publication type is not eligible for evidence synthesis.", "The record appears to be an excluded publication type.", "Ineligible publication type", 90)
    if has_any(text, [r"\bscoping review\b", r"\bsystematic review\b", r"\bliterature review\b", r"\bmeta-analysis\b"]):
        return decision("No", "Review article rather than an eligible primary impact study.", "The abstract describes a review of existing literature.", "Ineligible study design", 95)
    if pop_bad and not has_any(text, [r"\bundergraduate", r"\bcollege students?\b", r"\buniversity students?\b"]):
        return decision("No", "Population is outside eligible undergraduate higher education students.", "The title or abstract focuses on doctoral, graduate, school-level, or prospective students.", "Ineligible population", 88)
    if noncausal and not causal and support:
        return decision("No", "Design does not indicate a credible causal counterfactual.", "The abstract describes a qualitative, descriptive, cross-sectional, or review design.", "Ineligible study design", 88)
    if not support:
        if non_support:
            return decision("No", "Intervention is not direct financial or in-kind support.", "The abstract refers to loans, financial literacy, mentoring, advising, or non-financial support rather than eligible support.", "Ineligible intervention", 84)
        return decision("No", "No eligible post-entry financial or in-kind support intervention is identifiable.", "The title and abstract do not describe grants, bursaries, scholarships, hardship funds, waivers, or comparable direct support.", "No eligible financial support intervention", 82)
    if institutional_policy and not direct_support:
        return decision("No", "The record concerns institutional funding, tuition policy, or admissions policy rather than an identifiable student-level financial support intervention.", "The title or abstract describes funding formulas, institutional grants, tuition fees, or admissions policy rather than direct support to students.", "General funding policy without student-level intervention", 86)
    if has_any(core, [r"\bpell grant (recipients|students)\b", r"\bpell recipients\b"]) and not support_intervention:
        return decision("No", "Aid status is used as a student characteristic rather than the evaluated intervention.", "The title or abstract mentions Pell recipients or Pell Grant students but does not evaluate the aid as the intervention.", "No eligible financial support intervention", 84)
    if loan_only:
        return decision("No", "The financial intervention is repayable student loan support, which is excluded.", "The title or abstract focuses on student loans or loan aid rather than non-repayable or in-kind support.", "Ineligible intervention", 90)
    if non_support and not has_any(text, [r"\bgrants?\b", r"\bscholarships?\b", r"\bpell\b", r"\bbursar", r"\bfinancial aid\b", r"\bwaiver"]):
        return decision("No", "Support appears to be excluded financial education, loans, or non-financial student support.", "The abstract does not identify direct non-repayable financial or in-kind assistance.", "Ineligible intervention", 82)
    if pre_entry and not outcome and not has_any(text, [r"\bcollege students?\b", r"\buniversity students?\b", r"\bpersist", r"\bretention", r"\bcompletion", r"\bgraduation"]):
        return decision("No", "Financial support is evaluated only for pre-entry access or enrolment outcomes.", "The abstract focuses on applications, admissions, enrolment, or college choice rather than post-entry outcomes.", "Ineligible timing/outcome", 84)
    if only_admin:
        return decision("No", "Outcomes are administrative or implementation-focused rather than eligible student outcomes.", "The abstract reports awareness, take-up, satisfaction, expenditure, or delivery outcomes only.", "Ineligible outcome", 82)
    if he and support and support_intervention and outcome and strong_causal and not (noncausal and not causal):
        ev = evidence_from(row, [FINANCIAL_SUPPORT, POST_ENTRY_OUTCOMES, CAUSAL_DESIGN])
        return decision("Yes", "Title/abstract indicate eligible HE students, direct financial support, eligible student outcomes, and a credible counterfactual design.", ev, "", 90)
    if support and outcome and causal:
        ev = evidence_from(row, [FINANCIAL_SUPPORT, POST_ENTRY_OUTCOMES, CAUSAL_DESIGN])
        return decision("Uncertain", "Potentially eligible financial-support impact study, but population or post-entry eligibility is not fully clear from the abstract.", ev, "Unclear population or timing", 68, review=True)
    if support and outcome and not causal:
        ev = evidence_from(row, [FINANCIAL_SUPPORT, POST_ENTRY_OUTCOMES])
        return decision("Uncertain", "Potentially eligible support and outcome, but the title/abstract does not clearly establish a credible comparison design.", ev, "Unclear study design/counterfactual", 62, review=True)
    if support and causal and not outcome:
        ev = evidence_from(row, [FINANCIAL_SUPPORT, CAUSAL_DESIGN])
        return decision("Uncertain", "Financial support and possible causal design are present, but eligible post-entry outcomes are unclear.", ev, "Unclear eligible outcome", 58, review=True)
    if support:
        ev = evidence_from(row, [FINANCIAL_SUPPORT])
        return decision("Uncertain", "Direct financial support is mentioned, but title/abstract do not provide enough information on population, outcome, timing, or design.", ev, "Insufficient information", 50, review=True)
    return decision("No", "No eligible financial support intervention is identifiable.", "The title and abstract do not describe eligible direct financial or in-kind support.", "No eligible financial support intervention", 80)


def evidence_from(row: dict[str, str], groups: list[list[str]]) -> str:
    text = " ".join([row["title"], row["abstract"]])
    parts: list[str] = []
    labels = ["support", "outcome", "design"]
    for label, patterns in zip(labels, groups):
        match = first_match(text, patterns)
        if match:
            parts.append(f"{label}: mentions {match.lower()}")
    return "; ".join(parts) if parts else "Relevant eligibility details are suggested in the title or abstract."


def decision(inclusion: str, rationale: str, evidence: str, reason: str, confidence: int, review: bool | None = None) -> dict[str, str]:
    needs_review = review if review is not None else (inclusion == "Uncertain" or confidence < 70)
    return {
        "inclusion": inclusion,
        "rationale": rationale,
        "evidence": evidence,
        "exclusion_reason": "" if inclusion == "Yes" else reason,
        "overall_confidence": str(confidence),
        "needs_human_review": "Yes" if needs_review else "No",
    }


def main() -> None:
    records = parse_ris(RIS_PATH)
    title_year: defaultdict[tuple[str, str], list[int]] = defaultdict(list)
    rows: list[dict[str, str]] = []
    for idx, rec in enumerate(records, 1):
        title = pick(rec, "TI", "T1")
        year = year_from(rec)
        key = (low(title), year)
        if title:
            title_year[key].append(idx)
        source_id = pick(rec, "ID", "AN")
        rows.append(
            {
                "record_id": f"RIS_{idx:04d}",
                "title": title,
                "abstract": pick(rec, "AB", "N2"),
                "authors": join(rec, "AU", "A1"),
                "year": year,
                "journal": pick(rec, "JF", "JO", "T2", "JA"),
                "doi": pick(rec, "DO"),
                "url": pick(rec, "UR"),
                "publication_type": pick(rec, "TY", "PT"),
                "keywords": join(rec, "KW"),
                "source_record_id": source_id,
            }
        )

    dup_indexes = {i for indexes in title_year.values() if len(indexes) > 1 for i in indexes}
    duplicate_groups = sum(1 for indexes in title_year.values() if len(indexes) > 1)
    for row in rows:
        screened = assess(row)
        row.update(screened)
        row["apparent_duplicate"] = "Yes" if int(row["record_id"].split("_")[1]) in dup_indexes else "No"

    fields = [
        "record_id", "title", "abstract", "authors", "year", "journal", "doi", "url",
        "publication_type", "keywords", "inclusion", "rationale", "evidence",
        "exclusion_reason", "overall_confidence", "needs_human_review",
        "source_record_id", "apparent_duplicate",
    ]
    with OUT_PATH.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    counts = Counter(row["inclusion"] for row in rows)
    reasons = Counter(row["exclusion_reason"] for row in rows if row["exclusion_reason"])
    review_count = sum(1 for row in rows if row["needs_human_review"] == "Yes")
    print(f"records={len(rows)}")
    print(f"missing_titles={sum(1 for row in rows if not row['title'])}")
    print(f"missing_abstracts={sum(1 for row in rows if not row['abstract'])}")
    print(f"duplicate_groups={duplicate_groups}")
    print(f"duplicate_records={len(dup_indexes)}")
    print(f"output={OUT_PATH.resolve()}")
    print("inclusion_counts=" + repr(dict(counts)))
    print(f"human_review={review_count}")
    print("exclusion_reasons=" + repr(dict(reasons.most_common())))


if __name__ == "__main__":
    main()
