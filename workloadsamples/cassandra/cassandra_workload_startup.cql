-- Create Keyspace
CREATE KEYSPACE IF NOT EXISTS benchmark
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 1
}
AND durable_writes = true;

-- Use the keyspace
USE benchmark;

-- Create users table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    name TEXT,
    email TEXT,
    created_at TIMESTAMP
);

-- Create index on name for filtering queries
CREATE INDEX IF NOT EXISTS idx_users_name ON users (name);

-- Create user_stats table for batch operations
CREATE TABLE IF NOT EXISTS user_stats (
    user_id UUID PRIMARY KEY,
    login_count INT
);

-- Optional: Create index on email if needed
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
