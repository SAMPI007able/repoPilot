create table if not exists runtime_manifests (
    id varchar(36) primary key,
    workspace_id varchar(36) not null unique references workspaces(id) on delete cascade,
    manifest_version varchar(16) not null,
    manifest jsonb not null,
    analysis_summary jsonb not null,
    evidence jsonb not null default '[]'::jsonb,
    warnings jsonb not null default '[]'::jsonb,
    unsupported_reasons jsonb not null default '[]'::jsonb,
    supported boolean not null default true,
    approved boolean not null default false,
    revision integer not null default 1,
    approved_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists ix_runtime_manifests_workspace_id
    on runtime_manifests(workspace_id);
