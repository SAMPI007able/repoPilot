create table if not exists preview_environments (
    id varchar(36) primary key,
    workspace_id varchar(36) not null references workspaces(id) on delete cascade,
    status varchar(32) not null,
    repository_url text not null,
    commit_sha varchar(64) not null,
    manifest_revision integer not null,
    manifest jsonb not null,
    environment_names jsonb not null default '[]'::jsonb,
    idempotency_key varchar(128) not null,
    preview_url text,
    internal_url text,
    provider varchar(32) not null default 'local-docker',
    provider_state jsonb not null default '{}'::jsonb,
    log_storage_key text,
    error_code varchar(64),
    error_message text,
    expires_at timestamptz not null,
    maximum_expires_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    ready_at timestamptz,
    stopped_at timestamptz,
    constraint uq_preview_create_idempotency unique (workspace_id, idempotency_key)
);

create index if not exists ix_preview_environments_workspace_id on preview_environments(workspace_id);
create index if not exists ix_preview_environments_status on preview_environments(status);
create index if not exists ix_preview_environments_expires_at on preview_environments(expires_at);

create table if not exists preview_events (
    id varchar(36) primary key,
    preview_id varchar(36) not null references preview_environments(id) on delete cascade,
    status varchar(32) not null,
    message text not null,
    created_at timestamptz not null default now()
);

create index if not exists ix_preview_events_preview_id on preview_events(preview_id);
create index if not exists ix_preview_events_created_at on preview_events(created_at);
