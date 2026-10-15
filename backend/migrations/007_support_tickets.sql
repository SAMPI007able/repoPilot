create table if not exists support_tickets (
    id varchar(36) primary key,
    user_id varchar(36) not null references users(id) on delete cascade,
    category varchar(32) not null,
    subject varchar(200) not null,
    description_html text not null,
    status varchar(16) not null default 'OPEN',
    status_updated_by_user_id varchar(36) references users(id) on delete set null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    in_progress_at timestamptz,
    completed_at timestamptz,
    constraint ck_support_tickets_category check (
        category in ('CHAT_WITH_CODEBASE', 'TEST_GENERATION', 'IMPACT_ANALYSIS', 'PREVIEW', 'OTHER')
    ),
    constraint ck_support_tickets_status check (status in ('OPEN', 'IN_PROGRESS', 'COMPLETED'))
);

create index if not exists ix_support_tickets_user_id on support_tickets(user_id);
create index if not exists ix_support_tickets_category on support_tickets(category);
create index if not exists ix_support_tickets_status on support_tickets(status);
create index if not exists ix_support_tickets_created_at on support_tickets(created_at);

create table if not exists support_attachments (
    id varchar(36) primary key,
    user_id varchar(36) references users(id) on delete set null,
    storage_key text not null unique,
    content_type varchar(64) not null,
    size_bytes bigint not null,
    created_at timestamptz not null default now()
);

create index if not exists ix_support_attachments_user_id on support_attachments(user_id);
