# Workload Configuration Guide

## Overview

### What is a Workload File?

A workload file is a recipe that tells the benchmarking tool what operations to perform against your database and how often to perform them. Think of it like a script that simulates real-world user activity—some users might be reading data, others inserting new records, and some updating existing information.

### Why Use Workload Files?

Instead of writing custom code for every benchmark scenario, you can describe your test scenario in a simple YAML configuration file. For example:
- **E-commerce scenario**: Simulate 60% product searches, 30% cart insertions, 10% order updates
- **Analytics scenario**: Simulate 90% complex queries, 10% data ingestion
- **Social media scenario**: Simulate 50% feed reads, 40% post creation, 10% likes/comments

### How Does It Work?

The tool reads your workload file and repeatedly executes the defined tasks based on their weights (probability). Each task can have dynamic parameters that change on every execution—generating random IDs, timestamps, names, or any data pattern you need.

**Example**: A task with weight 70 in a workload with total weight 100 will execute approximately 70% of the time.

### What This Guide Covers

This guide explains the generic structure of workload configuration files that work across all database types (SQL Server, PostgreSQL, MongoDB, Cosmos DB, Cassandra). Each database has specific variations and features documented in their respective guides linked below.

## Configuration File Structure

Workload files are YAML-based and located in the `config/` directory. Each file defines tasks that simulate real-world database operations.

### Basic Structure

```yaml
type: <DatabaseType>
runStartUpFrequency: <Never|Once|Always>  # Optional
tasks:
  - taskName: <unique_task_name>
    taskWeight: <integer>
    command:
      # Command-specific configuration
```

## Key Concepts

### 1. Database Type
Specifies which database executor to use:
- `SQL` - Azure SQL Database / SQL Server
- `PGSQL` - PostgreSQL
- `MongoDB` - MongoDB / Azure Cosmos DB for MongoDB
- `CosmosDB` - Azure Cosmos DB for NoSQL
- `Cassandra` - Apache Cassandra / Azure Managed Instance for Apache Cassandra

### 2. Run Startup Frequency
Controls when startup scripts are executed:
- `Never` - Don't run startup script (default)
- `Once` - Run only on first execution
- `Always` - Run on every test execution

Sample startup scripts are located in `workloadsamples/<database>/<workload_name>_startup.<ext>` and typically create schemas, tables, indexes, etc, and must be placed in the same `config/` folder as the workload files.

### 3. Tasks

#### What is a Task?

A task represents a single type of database operation you want to test. Each task is like a player in your simulation—one player might be constantly reading product information, another might be adding items to carts, and another might be updating inventory.

**Common task examples**:
- `insert` - Add new records to the database
- `select` - Query/read existing data
- `update` - Modify existing records
- `delete` - Remove records
- `upsert` - Insert or update if exists

#### Task Weight: Controlling Frequency

The `taskWeight` determines how often each task runs compared to others. Think of it as a raffle where each task gets tickets:

**Simple example**:
```yaml
tasks:
  - taskName: read_product
    taskWeight: 70      # 70 tickets
  - taskName: add_to_cart
    taskWeight: 20      # 20 tickets
  - taskName: checkout
    taskWeight: 10      # 10 tickets
# Total: 100 tickets
```

In this scenario:
- `read_product` executes **70% of the time** (70 out of 100 tickets)
- `add_to_cart` executes **20% of the time** (20 out of 100 tickets)
- `checkout` executes **10% of the time** (10 out of 100 tickets)

**The math**: Task probability = `taskWeight / (sum of all taskWeights)`

**Another example with different totals**:
```yaml
tasks:
  - taskName: query
    taskWeight: 6       # 6/(6+3+1) = 60%
  - taskName: insert
    taskWeight: 3       # 3/(6+3+1) = 30%
  - taskName: delete
    taskWeight: 1       # 1/(6+3+1) = 10%
# Total: 10 tickets = same percentages as 60/30/10
```

**Special case**:
- `taskWeight: 0` - Task is completely disabled and never executes

💡 **Tip**: You don't need weights to sum to 100. Use whatever numbers make sense for your ratio. Weights of 2:1 are the same as 200:100 or 20:10.

### 4. Parameters
Define dynamic values for queries:

```yaml
parameters:
  - name: "@parameter_name"
    type: <parameter_type>
    # Additional type-specific options
```

#### Parameter Types

| Type | Description | Options |
|------|-------------|---------|
| `random_int` | Random integer | `start`, `end` |
| `guid` | UUID/GUID | - |
| `datetime` | Current timestamp | `format` (optional) |
| `constant` | Fixed value | `value`, `as` (type conversion) |
| `faker.<method>` | Faker library method | See Faker docs |

#### Parameter Type Conversion

Use the `as` field to convert parameter values:
- `as: string` - Convert to string
- `as: int` - Convert to integer
- `as: float` - Convert to float

```yaml
- name: "@player_id"
  type: random_int
  start: 1
  end: 1000000
  as: string  # Returns string instead of int
```

#### Faker Integration

Use any Faker method with dot notation:

```yaml
- name: "@email"
  type: faker.email

- name: "@full_name"
  type: faker.name

- name: "@ip_address"
  type: faker.ipv4

- name: "@timestamp"
  type: faker.date_time.timestamp
```

**Faker Documentation**: https://faker.readthedocs.io/

### 5. Batch Operations

Most databases support batch operations for bulk inserts:

```yaml
command:
  batchSize: 1000  # Execute 1000 operations at once
```

- `batchSize: 1` - Single operation (default)
- `batchSize: > 1` - Bulk operation with multiple parameter sets
- Each operation in the batch gets a unique set of generated parameter values

## Performance Considerations

### Task Weight Distribution
- Use weights to simulate realistic workload patterns
- Read-heavy: Higher weights on SELECT operations
- Write-heavy: Higher weights on INSERT/UPDATE operations
- Balanced: Equal weights across operations

### Batch Size Guidelines
- **Small batches (1-100)**: Good for testing individual operation latency
- **Medium batches (100-1000)**: Balanced throughput testing
- **Large batches (1000+)**: Maximum throughput testing

⚠️ **Warning**: Very large batch sizes may cause memory issues or timeouts.

### Parameter Ranges
- Use realistic ranges for random parameters
- Consider your data volume and distribution
- Avoid skewed distributions that don't reflect production

## Database-Specific Guides

For detailed configuration examples and best practices for each database:

- **[SQL Server / Azure SQL](./SQL_WORKLOAD_GUIDE.md)**
- **[PostgreSQL](./PGSQL_WORKLOAD_GUIDE.md)**
- **[MongoDB](./MONGODB_WORKLOAD_GUIDE.md)**
- **[Cosmos DB](./COSMOSDB_WORKLOAD_GUIDE.md)**
- **[Cassandra](./CASSANDRA_WORKLOAD_GUIDE.md)**

## Common Patterns

### Read-Heavy Workload
```yaml
tasks:
  - taskName: select
    taskWeight: 80
  - taskName: insert
    taskWeight: 15
  - taskName: update
    taskWeight: 5
```

### Write-Heavy Workload
```yaml
tasks:
  - taskName: insert
    taskWeight: 60
  - taskName: update
    taskWeight: 25
  - taskName: select
    taskWeight: 15
```

### Balanced Workload
```yaml
tasks:
  - taskName: select
    taskWeight: 40
  - taskName: insert
    taskWeight: 30
  - taskName: update
    taskWeight: 20
  - taskName: delete
    taskWeight: 10
```

## Troubleshooting

### Task Not Executing
- Check `taskWeight` is > 0
- Verify parameter names match between definition and parameters
- Check logs for connection errors

### Parameter Generation Errors
- Ensure parameter types are valid
- Verify Faker methods exist
- Check type conversion compatibility

### Performance Issues
- Reduce batch sizes if seeing timeouts
- Adjust task weights to reduce load
- Check database connection settings

## Next Steps

1. Review your database-specific guide
2. Copy an example configuration from `config/` directory
3. Modify parameters and tasks for your use case
4. Test with low user count first
5. Scale up gradually

For more information about running benchmarks, see [README](../README.md).
