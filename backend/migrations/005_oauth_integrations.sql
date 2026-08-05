create table if not exists oauth_connections (
    id varchar(36) primary key,
    user_id varchar(36) not null references users(id) on delete cascade,
    provider varchar(32) not null,
    access_token_ciphertext text not null,
    refresh_token_ciphertext text,
    token_type varchar(32) not null default 'Bearer',
    scopes jsonb not null default '[]'::jsonb,
    external_account_id varchar(255), external_account_name varchar(255), external_avatar_url text,
    expires_at timestamptz,
    created_at timestamptz not null default now(), updated_at timestamptz not null default now(),
    constraint uq_oauth_connection_user_provider unique (user_id, provider)
);
create index if not exists ix_oauth_connections_user_id on oauth_connections(user_id);

create table if not exists oauth_states (
    state_hash varchar(64) primary key,
    user_id varchar(36) not null references users(id) on delete cascade,
    provider varchar(32) not null,
    expires_at timestamptz not null,
    created_at timestamptz not null default now()
);
create index if not exists ix_oauth_states_user_id on oauth_states(user_id);
create index if not exists ix_oauth_states_expires_at on oauth_states(expires_at);
