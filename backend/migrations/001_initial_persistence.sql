create table if not exists workspaces (
    id varchar(36) primary key,
    repo_url text not null,
    repo_name varchar(255) not null,
    commit_sha varchar(64),
    default_branch varchar(255),
    status varchar(32) not null,
    stats jsonb not null default '{}'::jsonb,
    package_info jsonb,
    graph_preview jsonb not null default '[]'::jsonb,
    docs_summary jsonb not null default '[]'::jsonb,
    active_artifact_id varchar(36),
    error text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    indexed_at timestamptz
);

create index if not exists ix_workspaces_repo_url on workspaces(repo_url);
create index if not exists ix_workspaces_status on workspaces(status);

create table if not exists workspace_builds (
    id varchar(36) primary key,
    workspace_id varchar(36) not null references workspaces(id) on delete cascade,
    status varchar(32) not null,
    stages jsonb not null default '[]'::jsonb,
    error text,
    started_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz not null default now()
);

create index if not exists ix_workspace_builds_workspace_id
    on workspace_builds(workspace_id);
create index if not exists ix_workspace_builds_status
    on workspace_builds(status);

create table if not exists artifacts (
    id varchar(36) primary key,
    workspace_id varchar(36) not null references workspaces(id) on delete cascade,
    kind varchar(64) not null,
    storage_key text not null unique,
    content_type varchar(128) not null,
    schema_version integer not null default 1,
    checksum_sha256 varchar(64) not null,
    compressed_size bigint not null,
    created_at timestamptz not null default now()
);

create index if not exists ix_artifacts_workspace_id on artifacts(workspace_id);
