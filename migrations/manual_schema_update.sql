-- Manual schema update for the Bookmark feature
-- This would typically be handled by Flask-Migrate

-- Drop table if it exists (optional, for idempotency during manual application)
-- DROP TABLE IF EXISTS bookmark;

CREATE TABLE bookmark (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(user_id) REFERENCES user(id) ON DELETE CASCADE,
    FOREIGN KEY(post_id) REFERENCES post(id) ON DELETE CASCADE,
    CONSTRAINT _user_post_bookmark_uc UNIQUE (user_id, post_id)
);

-- Optional: Create an index for faster lookups by timestamp if needed,
-- though the primary key and unique constraint already provide indexing.
-- CREATE INDEX ix_bookmark_timestamp ON bookmark (timestamp);
