# PostgreSQL Workload Configuration Guide

## Overview

This guide covers workload configuration for PostgreSQL and Azure Database for PostgreSQL. For generic configuration concepts, see [WORKLOAD_CONFIG_GUIDE](./WORKLOAD_CONFIG_GUIDE.md).

## Quick Start

```yaml
type: PGSQL
runStartUpFrequency: <Not yet supported>
tasks:
  - taskName: insert
    taskWeight: 50
    command:
      definition: INSERT INTO users (id, name, email, created_at) VALUES (@id, @name, @email, @created_at)
      batchSize: 100
      parameters:
        - name: "@id"
          type: guid
        - name: "@name"
          type: faker.name
        - name: "@email"
          type: faker.email
        - name: "@created_at"
          type: datetime
```

## Configuration Structure

### Command Definition

PostgreSQL uses a simplified configuration with automatic prepared statements:

```yaml
command:
  definition: <SQL_statement>
  parameters: [...]
  batchSize: <integer>  # Optional, default: 1
```

- Uses `@parameter_name` placeholders
- Automatically converts to prepared statements (`$1`, `$2`, etc.)
- All statements are parameterized for SQL injection protection

### Batch Operations

```yaml
command:
  definition: INSERT INTO cart (player_id, ticket_id, ticket_date) VALUES (@player_id, @ticket_id, @ticket_date)
  batchSize: 500  # Execute 500 inserts
```

- Batch operations generate multiple parameter sets
- Each execution gets unique parameter values
- Optimal for bulk inserts

## Best Practices

### 1. Index Strategy

**B-tree Indexes** (Default, most common):
```sql
-- Single column
CREATE INDEX idx_users_email ON users (email);

-- Composite index
CREATE INDEX idx_orders_customer_date ON orders (customer_id, order_date DESC);

-- Unique index
CREATE UNIQUE INDEX idx_users_username ON users (username);

-- Partial index (for filtered queries)
CREATE INDEX idx_active_users ON users (created_at) WHERE status = 'active';
```

**Specialized Indexes**:
```sql
-- GIN index for JSONB, arrays, full-text search
CREATE INDEX idx_data_gin ON logs USING GIN (metadata);

-- BRIN index for large sequential data (time-series)
CREATE INDEX idx_events_time_brin ON events USING BRIN (event_time);

-- Hash index (equality only, faster than B-tree)
CREATE INDEX idx_sessions_hash ON sessions USING HASH (session_id);

-- GiST index for geometric data, full-text
CREATE INDEX idx_locations_gist ON locations USING GIST (point);
```

**Index Guidelines**:
- Create indexes on columns used in WHERE, JOIN, ORDER BY
- Use partial indexes for frequently filtered subsets
- Use GIN for JSONB queries
- Monitor index usage: `pg_stat_user_indexes`

**PostgreSQL Indexing**: https://www.postgresql.org/docs/current/indexes.html

### 2. Data Types

**Use PostgreSQL-specific types**:
```sql
-- UUID
id UUID DEFAULT gen_random_uuid()

-- JSONB (binary JSON, supports indexing)
metadata JSONB

-- Arrays
tags TEXT[]

-- Range types
availability TSRANGE

-- Network types
ip_address INET

-- Enums
CREATE TYPE status_enum AS ENUM ('pending', 'active', 'inactive');
status status_enum
```

### 3. Write Optimization

**Batch Inserts**:
```yaml
- taskName: bulk_insert
  taskWeight: 70
  command:
    definition: INSERT INTO logs (id, message, timestamp) VALUES (@id, @message, @ts)
    batchSize: 1000  # 1000 inserts
```

**UPSERT (INSERT ... ON CONFLICT)**:
```yaml
- taskName: upsert
  taskWeight: 30
  command:
    definition: |
      INSERT INTO users (id, name, email) 
      VALUES (@id, @name, @email)
      ON CONFLICT (id) 
      DO UPDATE SET 
        name = EXCLUDED.name,
        email = EXCLUDED.email,
        updated_at = NOW()
```

**Tips**:
- Consider partitioning for very large tables

### 4. Read Optimization

**Efficient Queries**:
```yaml
- taskName: select_with_limit
  taskWeight: 60
  command:
    definition: |
      SELECT id, name, email 
      FROM users 
      WHERE created_at > @start_date 
      ORDER BY created_at DESC 
      LIMIT 100
```

**JSONB Queries**:
```yaml
- taskName: jsonb_query
  taskWeight: 20
  command:
    definition: |
      SELECT id, metadata->>'name' as name
      FROM logs
      WHERE metadata @> @filter::jsonb
    parameters:
      - name: "@filter"
        type: constant
        value: '{"status": "active"}'
        as: string
```

**Tips**:
- Always use LIMIT for pagination
- Use covering indexes (INCLUDE columns)
- Analyze queries with EXPLAIN ANALYZE
- Use materialized views for complex aggregations
- Consider table partitioning for range queries

### 5. Functions and Stored Procedures

**Calling Functions**:
```yaml
- taskName: call_function
  taskWeight: 30
  command:
    definition: CALL sp_cart_ins(@player_id, @ticket_id::uuid, @ticket_date, @contest, @numbers::jsonb)
    parameters:
      - name: "@player_id"
        type: random_int
        start: 1
        end: 1000000
      - name: "@ticket_id"
        type: guid
      - name: "@ticket_date"
        type: datetime
      - name: "@contest"
        type: random_int
        start: 1
        end: 1000
      - name: "@numbers"
        type: constant
        value: "[1,2,3,4,5,6]"
        as: string
```

**Note**: Type casting (`::<type>`) is often required for UUIDs, JSONB, arrays, etc.

## Example Workloads

### OLTP Workload

```yaml
type: PGSQL
tasks:
  - taskName: insert
    taskWeight: 30
    command:
      definition: INSERT INTO cart (player_id, ticket_id, ticket_date, contest, numbers) VALUES (@player_id, @ticket_id::uuid, @ticket_date, @contest, @numbers::jsonb)
      batchSize: 50
      parameters:
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000
        - name: "@ticket_id"
          type: guid
        - name: "@ticket_date"
          type: datetime
        - name: "@contest"
          type: random_int
          start: 1
          end: 1000
        - name: "@numbers"
          type: constant
          value: "[1,2,3,4,5,6]"
          as: string

  - taskName: select
    taskWeight: 60
    command:
      definition: SELECT ticket_id, ticket_date, contest FROM cart WHERE player_id = @player_id ORDER BY ticket_date DESC LIMIT 10
      parameters:
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000

  - taskName: update
    taskWeight: 5
    command:
      definition: UPDATE cart SET numbers = @numbers::jsonb WHERE player_id = @player_id
      parameters:
        - name: "@numbers"
          type: constant
          value: "[7,8,9,10,11,12]"
          as: string
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000

  - taskName: delete
    taskWeight: 5
    command:
      definition: DELETE FROM cart WHERE player_id = @player_id AND ticket_id = @ticket_id::uuid
      parameters:
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000
        - name: "@ticket_id"
          type: guid
```

### Time-Series Workload

```yaml
type: PGSQL
tasks:
  - taskName: insert_metrics
    taskWeight: 80
    command:
      definition: INSERT INTO metrics (device_id, timestamp, temperature, humidity) VALUES (@device_id, @ts, @temp, @humid)
      batchSize: 500
      parameters:
        - name: "@device_id"
          type: random_int
          start: 1
          end: 1000
        - name: "@ts"
          type: datetime
        - name: "@temp"
          type: random_int
          start: -20
          end: 50
        - name: "@humid"
          type: random_int
          start: 0
          end: 100

  - taskName: aggregate_metrics
    taskWeight: 20
    command:
      definition: |
        SELECT 
          device_id,
          DATE_TRUNC('hour', timestamp) as hour,
          AVG(temperature) as avg_temp,
          AVG(humidity) as avg_humid
        FROM metrics
        WHERE device_id = @device_id
          AND timestamp > NOW() - INTERVAL '24 hours'
        GROUP BY device_id, hour
        ORDER BY hour DESC
      parameters:
        - name: "@device_id"
          type: random_int
          start: 1
          end: 1000
```

## Performance Tips

### Azure Database for PostgreSQL

**Server Parameters**:
- Choose appropriate pricing tier (compute + storage)
- Enable connection pooling (PgBouncer)
- Configure high availability if needed
- Use read replicas for read-heavy workloads

**Azure PostgreSQL Documentation**: https://learn.microsoft.com/azure/postgresql/

### Query Performance

**EXPLAIN ANALYZE**:
```sql
EXPLAIN ANALYZE
SELECT * FROM cart WHERE player_id = 12345;
```

**Monitor Performance**:
```sql
-- Slow queries
SELECT * FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 10;

-- Index usage
SELECT * FROM pg_stat_user_indexes;

-- Table statistics
SELECT * FROM pg_stat_user_tables;

-- Cache hit ratio
SELECT sum(heap_blks_hit) / (sum(heap_blks_hit) + sum(heap_blks_read)) as cache_hit_ratio
FROM pg_statio_user_tables;
```

## Common Pitfalls

❌ **Don't**:
- Forget type casts for UUID, JSONB (`::<type>`)
- Use SELECT * (specify columns)
- Create too many indexes
- Ignore VACUUM and ANALYZE
- Use TEXT for small strings (use VARCHAR)
- Query JSONB without GIN indexes

✅ **Do**:
- Use prepared statements (automatic in this tool)
- Cast parameters correctly
- Update statistics regularly (ANALYZE)
- Monitor table bloat (VACUUM)
- Use appropriate index types
- Leverage PostgreSQL-specific features (JSONB, arrays, CTEs)

## Monitoring During Benchmarks

**Key Metrics**:
- Connection count
- Transaction rate (commits/sec)
- Cache hit ratio (> 99%)
- Query duration (p50, p95, p99)
- Table/index bloat
- Replication lag (if applicable)

**Extensions**:
```sql
-- Install pg_stat_statements
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Install auto_explain
LOAD 'auto_explain';
```

## Connection Configuration

When running benchmarks, provide:
- `pgsql_connection_string`: PostgreSQL connection string

**Format**: 
```
postgresql://user:password@host:5432/database?sslmode=require
```

**Azure Example**:
```
postgresql://myuser@myserver:password@myserver.postgres.database.azure.com:5432/mydb?sslmode=require
```

## References

- **Azure Database for PostgreSQL**: https://learn.microsoft.com/azure/postgresql/
- **PostgreSQL Documentation**: https://www.postgresql.org/docs/
- **JSONB**: https://www.postgresql.org/docs/current/datatype-json.html
- **Index Types**: https://www.postgresql.org/docs/current/indexes-types.html

## See Also

- [Generic Workload Configuration Guide](./WORKLOAD_CONFIG_GUIDE.md)
- Example configuration: `config/pgsql_workload.yaml`
