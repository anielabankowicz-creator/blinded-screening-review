-- Non-destructive schema for blinded dual-review screening.
-- Run in Supabase SQL editor after reviewing it. It creates new tables only.

create table if not exists review_records (
    record_id text primary key,
    title text,
    abstract text,
    authors text,
    year text,
    journal text,
    doi text,
    url text,
    publication_type text,
    keywords text,
    source_record_id text,
    apparent_duplicate text,
    ai_inclusion text,
    ai_rationale text,
    ai_evidence text,
    ai_exclusion_reason text,
    ai_overall_confidence integer,
    ai_needs_human_review text,
    raw jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists review_samples (
    sample_id text primary key,
    seed integer not null,
    sample_size integer not null,
    source_record_count integer not null,
    record_ids jsonb not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists review_sample_records (
    sample_id text not null references review_samples(sample_id) on delete cascade,
    record_id text not null references review_records(record_id) on delete cascade,
    position integer not null,
    created_at timestamptz not null default now(),
    primary key (sample_id, record_id),
    unique (sample_id, position)
);

create table if not exists review_reviewers (
    reviewer_id text primary key,
    display_name text not null,
    role text not null check (role in ('reviewer', 'adjudicator', 'lead')),
    access_code_hash text not null unique,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists review_decisions (
    sample_id text not null references review_samples(sample_id) on delete cascade,
    record_id text not null references review_records(record_id) on delete cascade,
    reviewer_id text not null references review_reviewers(reviewer_id) on delete restrict,
    decision text not null check (decision in ('Include', 'Exclude', 'Unsure')),
    exclusion_reason text,
    notes text,
    locked boolean not null default false,
    submitted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (sample_id, record_id, reviewer_id)
);

create table if not exists review_adjudications (
    sample_id text not null references review_samples(sample_id) on delete cascade,
    record_id text not null references review_records(record_id) on delete cascade,
    adjudicator_id text not null references review_reviewers(reviewer_id) on delete restrict,
    final_decision text not null check (final_decision in ('Include', 'Exclude', 'Unsure')),
    reason text,
    notes text,
    locked boolean not null default false,
    submitted_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (sample_id, record_id)
);

create index if not exists idx_review_decisions_reviewer on review_decisions(sample_id, reviewer_id);
create index if not exists idx_review_decisions_record on review_decisions(sample_id, record_id);
create index if not exists idx_review_adjudications_sample on review_adjudications(sample_id);
