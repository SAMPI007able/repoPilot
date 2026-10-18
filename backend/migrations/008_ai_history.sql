CREATE TABLE IF NOT EXISTS test_generations (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    workspace_id VARCHAR(36) NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    mode VARCHAR(16) NOT NULL,
    test_type VARCHAR(32) NOT NULL,
    target TEXT,
    scenario TEXT,
    prompt TEXT NOT NULL,
    markdown TEXT NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS ix_test_generations_user_id ON test_generations(user_id);
CREATE INDEX IF NOT EXISTS ix_test_generations_workspace_id ON test_generations(workspace_id);
CREATE INDEX IF NOT EXISTS ix_test_generations_request_hash ON test_generations(request_hash);
CREATE INDEX IF NOT EXISTS ix_test_generations_created_at ON test_generations(created_at);
CREATE INDEX IF NOT EXISTS ix_test_generations_owner_workspace_created
    ON test_generations(user_id, workspace_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_test_generations_owner_workspace_hash
    ON test_generations(user_id, workspace_id, request_hash);
