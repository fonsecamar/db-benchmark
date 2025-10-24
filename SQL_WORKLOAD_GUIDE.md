# SQL Server / Azure SQL Workload Configuration Guide

## Overview

This guide covers workload configuration for SQL Server and Azure SQL Database. For generic configuration concepts, see [WORKLOAD_CONFIG_GUIDE](./WORKLOAD_CONFIG_GUIDE.md).

## Quick Start

```yaml
type: SQL
runStartUpFrequency: Once
tasks:
  - taskName: insert
    taskWeight: 50
    command:
      type: prepared
      definition: INSERT INTO users (id, name, email) VALUES (@id, @name, @email)
      parameters:
        - name: "@id"
          type: guid
        - name: "@name"
          type: faker.name
        - name: "@email"
          type: faker.email
```

## Configuration Structure

### Command Types

SQL Server supports multiple execution types:

```yaml
command:
  type: <execution_type>
  definition: <SQL_statement>
  # Type-specific options
```

#### Execution Types

**1. Prepared Statement** (Recommended for most operations)
```yaml
type: prepared
definition: INSERT INTO cart (player_id, ticket_id, ticket_date) VALUES (@player_id, @ticket_id, @ticket_date)
```
- Uses parameterized queries (SQL injection safe)
- Best performance for repeated queries
- Automatic query plan caching

**2. Ad-Hoc Query**
```yaml
type: ad-hoc
definition: SELECT * FROM cart WHERE player_id = @player_id
```
- Executes query directly
- Parameter values substituted before execution
- Use for SELECT queries or one-time operations

**3. Stored Procedure**
```yaml
type: stored_procedure
definition: sp_cart_ins
parameters:
  - name: "@player_id"
    type: random_int
    start: 1
    end: 1000000
```
- Calls existing stored procedure
- Best for complex business logic
- Pre-compiled execution plans
- Parameter sequence must match the procedure

**4. Bulk Insert**
```yaml
type: bulk_insert
tableName: cart
batchSize: 1000
parameters:
  - name: "@player_id"
    type: random_int
    start: 1
    end: 1000000
```
- Uses SQL Server bulk insert API
- Fastest method for large data loads
- Minimal logging option available

### Startup Script

Create `config/<workload_name>_startup.sql`:

```sql
-- Create database
IF NOT EXISTS (SELECT * FROM sys.databases WHERE name = 'BenchmarkDB')
BEGIN
    CREATE DATABASE BenchmarkDB;
END
GO

USE BenchmarkDB;
GO

-- Create table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'cart')
BEGIN
    CREATE TABLE cart (
        player_id INT NOT NULL,
        ticket_id UNIQUEIDENTIFIER NOT NULL,
        ticket_date DATETIME2 NOT NULL,
        contest INT NOT NULL,
        numbers NVARCHAR(MAX),
        CONSTRAINT PK_cart PRIMARY KEY CLUSTERED (player_id, ticket_id)
    );
END
GO

-- Create indexes
CREATE NONCLUSTERED INDEX IX_cart_ticket_date 
ON cart (ticket_date) 
INCLUDE (player_id, contest);
GO

-- Create stored procedure
CREATE OR ALTER PROCEDURE sp_cart_ins
    @player_id INT,
    @ticket_id UNIQUEIDENTIFIER,
    @ticket_date DATETIME2,
    @contest INT,
    @numbers NVARCHAR(MAX)
AS
BEGIN
    SET NOCOUNT ON;
    
    INSERT INTO cart (player_id, ticket_id, ticket_date, contest, numbers)
    VALUES (@player_id, @ticket_id, @ticket_date, @contest, @numbers);
END
GO
```

## Best Practices

### 1. Index Strategy

**Clustered Index** (Primary Key):
```sql
-- Identity column
CREATE TABLE orders (
    order_id INT IDENTITY(1,1) PRIMARY KEY,
    customer_id INT,
    order_date DATETIME2
);

-- Natural key
CREATE TABLE products (
    product_code VARCHAR(20) PRIMARY KEY,
    name NVARCHAR(100)
);
```

**Nonclustered Indexes**:
```sql
-- Single column
CREATE NONCLUSTERED INDEX IX_orders_customer_id 
ON orders (customer_id);

-- Composite index
CREATE NONCLUSTERED INDEX IX_orders_customer_date 
ON orders (customer_id, order_date DESC);

-- Covering index (INCLUDE)
CREATE NONCLUSTERED INDEX IX_orders_customer_date_covering 
ON orders (customer_id, order_date)
INCLUDE (total_amount, status);
```

**Index Guidelines**:
- Create clustered index on every table
- Index foreign key columns
- Index columns in WHERE, JOIN, ORDER BY clauses
- Use INCLUDE for covering indexes
- Monitor index usage with DMVs

**SQL Server Indexing**: https://learn.microsoft.com/sql/relational-databases/indexes/indexes

### 2. Write Optimization

**Prepared Statements** (Best for OLTP):
```yaml
- taskName: insert
  taskWeight: 60
  command:
    type: prepared
    definition: INSERT INTO cart (player_id, ticket_id, ticket_date, contest, numbers) VALUES (@player_id, @ticket_id, @ticket_date, @contest, @numbers)
```

**Bulk Insert** (Best for data loading):
```yaml
- taskName: bulk_insert
  taskWeight: 40
  command:
    type: bulk_insert
    tableName: cart
    batchSize: 5000  # Insert 5000 rows at once
```

**Tips**:
- Use bulk insert for > 100 rows
- Consider table partitioning for large tables
- Use appropriate transaction isolation levels
- Monitor tempdb usage during bulk operations

### 3. Read Optimization

**Prepared Statement with Parameters**:
```yaml
- taskName: select_by_player
  taskWeight: 70
  command:
    type: prepared
    definition: SELECT TOP 100 player_id, ticket_id, ticket_date FROM cart WHERE player_id = @player_id ORDER BY ticket_date DESC
    parameters:
      - name: "@player_id"
        type: random_int
        start: 1
        end: 1000000
```

**Tips**:
- Always use TOP or OFFSET/FETCH for pagination
- Use appropriate join types (INNER, LEFT)
- Avoid SELECT * (specify columns)
- Use WITH (NOLOCK) cautiously (dirty reads)
- Analyze query plans regularly

### 4. Stored Procedures

**Benefits**:
- Pre-compiled execution plans
- Reduced network traffic
- Centralized business logic
- Better security (grant EXECUTE only)

```yaml
- taskName: complex_operation
  taskWeight: 30
  command:
    type: stored_procedure
    definition: sp_process_order
    parameters:
      - name: "@order_id"
        type: random_int
        start: 1
        end: 1000000
      - name: "@status"
        type: constant
        value: "completed"
        as: string
```

**Stored Procedure Best Practices**:
```sql
CREATE PROCEDURE sp_process_order
    @order_id INT,
    @status NVARCHAR(20)
AS
BEGIN
    SET NOCOUNT ON;  -- Reduce network traffic
    
    BEGIN TRY
        BEGIN TRANSACTION;
        
        -- Business logic here
        UPDATE orders 
        SET status = @status, 
            updated_at = GETUTCDATE()
        WHERE order_id = @order_id;
        
        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0
            ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END
```

### 5. Data Types

**Use Appropriate Types**:
```sql
-- Good
player_id INT                    -- 4 bytes
ticket_id UNIQUEIDENTIFIER       -- 16 bytes (GUID)
ticket_date DATETIME2(3)         -- Millisecond precision
contest SMALLINT                 -- 2 bytes (0-32K)
numbers NVARCHAR(100)            -- Variable length

-- Avoid
player_id BIGINT                 -- Overkill for < 2B records
ticket_date DATETIME             -- Less precise, same size
numbers NVARCHAR(MAX)            -- Stored off-row if > 8KB
```

**JSON Support**:
```yaml
parameters:
  - name: "@metadata"
    type: constant
    value: '{"source": "api", "version": 2}'
    as: string

# In table
metadata NVARCHAR(MAX) CHECK (ISJSON(metadata) = 1)
```

## Example Workloads

### OLTP Workload (Mixed Operations)

```yaml
type: SQL
runStartUpFrequency: Once
tasks:
  - taskName: insert
    taskWeight: 30
    command:
      type: prepared
      definition: INSERT INTO cart (player_id, ticket_id, ticket_date, contest, numbers) VALUES (@player_id, @ticket_id, @ticket_date, @contest, @numbers)
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
      type: prepared
      definition: SELECT TOP 10 ticket_id, ticket_date, contest FROM cart WHERE player_id = @player_id ORDER BY ticket_date DESC
      parameters:
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000

  - taskName: update
    taskWeight: 5
    command:
      type: prepared
      definition: UPDATE cart SET numbers = @numbers WHERE player_id = @player_id AND ticket_id = @ticket_id
      parameters:
        - name: "@numbers"
          type: constant
          value: "[7,8,9,10,11,12]"
          as: string
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000
        - name: "@ticket_id"
          type: guid

  - taskName: delete
    taskWeight: 5
    command:
      type: prepared
      definition: DELETE FROM cart WHERE player_id = @player_id AND ticket_id = @ticket_id
      parameters:
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000
        - name: "@ticket_id"
          type: guid
```

### High-Volume Insert Workload

```yaml
type: SQL
tasks:
  - taskName: bulk_insert
    taskWeight: 90
    command:
      type: bulk_insert
      tableName: event_log
      batchSize: 10000
      parameters:
        - name: "@event_id"
          type: guid
        - name: "@user_id"
          type: random_int
          start: 1
          end: 1000000
        - name: "@event_type"
          type: constant
          value: "page_view"
          as: string
        - name: "@timestamp"
          type: datetime

  - taskName: select_recent
    taskWeight: 10
    command:
      type: prepared
      definition: SELECT TOP 100 event_id, event_type, timestamp FROM event_log WHERE user_id = @user_id ORDER BY timestamp DESC
      parameters:
        - name: "@user_id"
          type: random_int
          start: 1
          end: 1000000
```

## Performance Tips

### Azure SQL Specific

**Service Tier Selection**:
| Workload Type | Recommended Tier |
|--------------|------------------|
| Read-heavy | General Purpose |
| Write-heavy | Business Critical |
| Analytics | Hyperscale |

**DTU vs vCore**:
- DTU: Fixed compute/storage ratio
- vCore: Independent scaling (recommended)

**Azure SQL Documentation**: https://learn.microsoft.com/azure/azure-sql/

### Query Performance

**Use Query Store**:
```sql
-- Enable Query Store
ALTER DATABASE BenchmarkDB 
SET QUERY_STORE = ON;

-- Find slow queries
SELECT TOP 10 
    query_id,
    avg_duration/1000 as avg_duration_ms,
    last_execution_time
FROM sys.query_store_runtime_stats
ORDER BY avg_duration DESC;
```

**Monitor with DMVs**:
```sql
-- Missing indexes
SELECT * FROM sys.dm_db_missing_index_details;

-- Index usage
SELECT * FROM sys.dm_db_index_usage_stats;

-- Wait statistics
SELECT * FROM sys.dm_os_wait_stats;
```

## Common Pitfalls

❌ **Don't**:
- Use SELECT * (specify columns)
- Create too many indexes (slows writes)
- Use NOLOCK everywhere (data inconsistency)
- Ignore execution plans
- Use VARCHAR(MAX) for small strings
- Use cursors for set-based operations

✅ **Do**:
- Use parameterized queries (SQL injection safe)
- Analyze query plans regularly
- Update statistics frequently
- Use appropriate isolation levels
- Implement proper error handling
- Monitor resource usage (CPU, IO, memory)

## Monitoring During Benchmarks

**Key Metrics**:
- DTU/CPU percentage
- Data IO percentage
- Log IO percentage
- Memory usage
- Wait statistics
- Query duration (p50, p95, p99)

**Azure Monitor**:
```
- Set up alerts for high DTU
- Monitor query performance with Query Performance Insight
- Use Intelligent Performance for recommendations
```

## Connection Configuration

When running benchmarks, provide:
- `sql_connection_string`: SQL Server connection string

**Format**: 
```
Server=server.database.windows.net;Database=mydb;User ID=user;Password=pass;Encrypt=True;TrustServerCertificate=False;
```

## References

- **SQL Server Documentation**: https://learn.microsoft.com/sql/sql-server/
- **Azure SQL Database**: https://learn.microsoft.com/azure/azure-sql/database/
- **Query Performance Tuning**: https://learn.microsoft.com/sql/relational-databases/performance/performance-monitoring-and-tuning-tools
- **Indexing Best Practices**: https://learn.microsoft.com/sql/relational-databases/indexes/indexes
- **Execution Plans**: https://learn.microsoft.com/sql/relational-databases/performance/execution-plans

## See Also

- [Generic Workload Configuration Guide](./WORKLOAD_CONFIG_GUIDE.md)
- Example configuration: `config/sql_workload.yaml`
