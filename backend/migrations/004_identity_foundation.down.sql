drop index if exists ix_workspaces_owner_user_id;
alter table workspaces drop column if exists owner_user_id;
drop table if exists auth_identities;
drop table if exists users;
