# Cassandra Workload Configuration Guide

## Overview

This guide covers workload configuration for Apache Cassandra and Azure Managed Instance for Apache Cassandra. For generic configuration concepts, see [WORKLOAD_CONFIG_GUIDE](./WORKLOAD_CONFIG_GUIDE.md).

## Quick Start

```yaml
type: Cassandra
runStartUpFrequency: Once
tasks:
  - taskName: insert_user
    taskWeight: 60
    command:
      definition: "INSERT INTO keyspace.table (id, name, email) VALUES (@id, @name, @email)"
      parameters:
        - name: "@id"
          type: guid
        - name: "@name"
          type: faker.name
        - name: "@email"
          type: faker.email
      consistencyLevel: ONE
      batchSize: 100
```

## Configuration Structure

### Command Definition

```yaml
command:
  definition: "<CQL_STATEMENT>"
  parameters: [...]
  consistencyLevel: <CONSISTENCY_LEVEL>  # Optional
  batchSize: <integer>  # Optional, default: 1
```

#### CQL Statement
- Use `@parameter_name` for parameters (e.g., `@id`, `@email`)
- Parameters are automatically converted to prepared statement placeholders (`?`)
- Supports all CQL operations: INSERT, SELECT, UPDATE, DELETE

#### Consistency Level
Specify read/write consistency:
- `ONE` - Fastest, lowest consistency (recommended for writes)
- `QUORUM` - Balanced consistency
- `LOCAL_QUORUM` - Datacenter-aware quorum
- `ALL` - Highest consistency, slowest

**Default**: Session default (typically `ONE`)

**Cassandra Consistency Documentation**: https://cassandra.apache.org/doc/latest/cassandra/architecture/dynamo.html#tunable-consistency

### Batch Operations

Cassandra executor uses **concurrent execution** for optimal performance:

```yaml
batchSize: 256  # Executes 256 INSERTs concurrently
```

- **Optimal batch size**: 100-500 for bulk inserts
- **Max concurrency**: 100 parallel operations (automatically limited)
- Each batch operation gets unique parameter values

⚠️ **Important**: Cassandra BATCH statements are NOT used for bulk loading. The executor uses `execute_concurrent_with_args` for better performance.

## Startup Script

Create `config/<workload_name>_startup.cql`:

```cql
-- Create Keyspace
CREATE KEYSPACE IF NOT EXISTS benchmark
WITH replication = {
    'class': 'SimpleStrategy',
    'replication_factor': 3
}
AND durable_writes = true;

-- Use the keyspace
USE benchmark;

-- Create table
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY,
    name TEXT,
    email TEXT,
    created_at TIMESTAMP
);

-- Create index
CREATE INDEX IF NOT EXISTS idx_users_email ON users (email);
```

**Startup Script Features**:
- Automatically splits by `;` statements
- Removes comments (`--`)
- Continues execution even if statements fail
- Logs success/error count

## Best Practices

### 1. Data Modeling

**Partition Key Design**:
```cql
-- Good: Single partition key for point queries
CREATE TABLE users_by_id (
    user_id UUID PRIMARY KEY,
    name TEXT,
    email TEXT
);

-- Good: Composite partition key for time-series
CREATE TABLE events (
    sensor_id UUID,
    event_time TIMESTAMP,
    value DOUBLE,
    PRIMARY KEY ((sensor_id), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
```

**Avoid**:
- Wide partitions (> 100MB)
- ALLOW FILTERING in production queries
- Secondary indexes on high-cardinality columns

**Cassandra Data Modeling**: https://cassandra.apache.org/doc/latest/cassandra/data_modeling/

### 2. Write Optimization

```yaml
# High-throughput writes
- taskName: bulk_insert
  taskWeight: 80
  command:
    definition: "INSERT INTO keyspace.logs (id, timestamp, message) VALUES (@id, @ts, @msg)"
    batchSize: 256
    consistencyLevel: ONE  # Fastest writes
```

**Tips**:
- Use `consistencyLevel: ONE` for write-heavy workloads
- Batch size 100-500 for optimal throughput
- Avoid UPDATE operations (writes are inserts in Cassandra)

### 3. Read Optimization

```yaml
# Point query (efficient)
- taskName: select_by_partition_key
  taskWeight: 60
  command:
    definition: "SELECT * FROM keyspace.users WHERE user_id = @id"
    consistencyLevel: LOCAL_QUORUM

# Range query on clustering key (efficient)
- taskName: select_time_range
  taskWeight: 30
  command:
    definition: "SELECT * FROM keyspace.events WHERE sensor_id = @id AND event_time > @start AND event_time < @end"
```

**Tips**:
- Always query by partition key
- Use clustering keys for range queries
- Avoid `ALLOW FILTERING` (indicates poor data model)
- Use `LIMIT` to control result size

### 4. Consistency Trade-offs

| Operation | Recommended Consistency | Reason |
|-----------|------------------------|--------|
| User registration | QUORUM | Data integrity |
| Session writes | ONE | Speed over consistency |
| Financial transactions | ALL | Data accuracy critical |
| Analytics reads | ONE | Eventual consistency OK |

## Example Workloads

### High-Throughput Write Workload

```yaml
type: Cassandra
tasks:
  - taskName: insert_sensor_data
    taskWeight: 90
    command:
      definition: "INSERT INTO sensors.sensor_data (sensor_id, timestamp, temperature, humidity) VALUES (@sensor_id, @ts, @temp, @humid)"
      batchSize: 200
      consistencyLevel: ONE
      parameters:
        - name: "@sensor_id"
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

  - taskName: read_latest_data
    taskWeight: 10
    command:
      definition: "SELECT * FROM sensors.sensor_data WHERE sensor_id = @sensor_id LIMIT 10"
      consistencyLevel: ONE
      parameters:
        - name: "@sensor_id"
          type: random_int
          start: 1
          end: 1000
```

### Balanced CRUD Workload

```yaml
type: Cassandra
tasks:
  - taskName: insert_user
    taskWeight: 40
    command:
      definition: "INSERT INTO user.users (id, name, email, created_at) VALUES (@id, @name, @email, @ts)"
      batchSize: 50
      consistencyLevel: QUORUM
      parameters:
        - name: "@id"
          type: guid
        - name: "@name"
          type: faker.name
        - name: "@email"
          type: faker.email
        - name: "@ts"
          type: datetime

  - taskName: select_user
    taskWeight: 50
    command:
      definition: "SELECT * FROM user.users WHERE id = @id"
      consistencyLevel: ONE
      parameters:
        - name: "@id"
          type: guid

  - taskName: delete_user
    taskWeight: 10
    command:
      definition: "DELETE FROM user.users WHERE id = @id"
      consistencyLevel: QUORUM
      parameters:
        - name: "@id"
          type: guid
```

## Performance Tips

### Batch Size Guidelines
| Operation Type | Recommended Batch Size |
|---------------|----------------------|
| Single writes | 1 |
| Bulk inserts | 100-500 |

### Monitoring
Key metrics to track during benchmarking:
- Write latency (p50, p95, p99)
- Read latency
- Tombstone count (excessive deletes)
- Compaction statistics
- Partition size distribution

## Common Pitfalls

❌ **Don't**:
- Use BATCH statements for bulk loading (use `batchSize` instead)
- Query without partition key
- Create secondary indexes on high-cardinality columns
- Use `ALLOW FILTERING` in production
- Store large blobs in Cassandra

✅ **Do**:
- Design schema around query patterns
- Use partition keys effectively
- Leverage clustering keys for sorting
- Monitor partition sizes
- Use appropriate consistency levels

## Connection Configuration

When running benchmarks, provide:
- `cassandra_contact_points`: Comma-separated list of nodes
- `cassandra_port`: CQL native protocol port (default: 9042)
- `cassandra_username`: Authentication username (if enabled)
- `cassandra_password`: Authentication password (if enabled)

For Azure Managed Instance for Apache Cassandra:
- Uses TLS 1.3 encryption
- Requires username/password authentication
- Contact points are cluster node IPs

## References

- **Azure Managed Instance**: https://learn.microsoft.com/azure/managed-instance-apache-cassandra/
- **Cassandra Documentation**: https://cassandra.apache.org/doc/latest/
- **Data Modeling**: https://cassandra.apache.org/doc/latest/cassandra/data_modeling/
- **CQL Reference**: https://cassandra.apache.org/doc/latest/cassandra/cql/
- **Performance Tuning**: https://cassandra.apache.org/doc/latest/cassandra/operating/


## See Also

- [Generic Workload Configuration Guide](./WORKLOAD_CONFIG_GUIDE.md)
- Example configuration: `config/cassandra_workload.yaml`
