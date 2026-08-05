create table if not exists feature_flags (
    key varchar(100) primary key,
    enabled boolean not null default false,
    description varchar(500),
    updated_at timestamptz not null default now(),
    updated_by_user_id varchar(36) references users(id) on delete set null
);

create index if not exists ix_feature_flags_updated_by_user_id
    on feature_flags(updated_by_user_id);

insert into feature_flags (key, enabled, description)
values
    ('preview', false, 'Show and allow creation of realtime preview environments.'),
    ('code_quality', false, 'Show code-quality insights in a workspace.')
on conflict (key) do nothing;
