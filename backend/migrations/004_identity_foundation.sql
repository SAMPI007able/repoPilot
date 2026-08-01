create table if not exists users (
    id varchar(36) primary key,
    primary_email varchar(320) not null,
    display_name varchar(255), avatar_url text,
    status varchar(32) not null, role varchar(16) not null default 'USER',
    email_verified boolean not null default false,
    created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
    last_login_at timestamptz, deleted_at timestamptz
);
create index if not exists ix_users_primary_email on users(primary_email);
create index if not exists ix_users_status on users(status);

create table if not exists auth_identities (
    id varchar(36) primary key,
    user_id varchar(36) not null references users(id) on delete cascade,
    issuer varchar(512) not null, subject varchar(512) not null, provider varchar(64) not null,
    created_at timestamptz not null default now(), last_authenticated_at timestamptz not null default now(),
    constraint uq_auth_identity_issuer_subject unique (issuer, subject)
);
create index if not exists ix_auth_identities_user_id on auth_identities(user_id);

alter table workspaces add column if not exists owner_user_id varchar(36) references users(id) on delete set null;
create index if not exists ix_workspaces_owner_user_id on workspaces(owner_user_id);
