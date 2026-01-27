import logging
import psycopg
import settings
import time

from datamanager import DataManager
from executors.base_executor import BaseExecutor
from pathlib import Path
from psycopg import DatabaseError
from typing import Any, Dict, Optional, List, Tuple, Callable

class PGSQLExecutor(BaseExecutor):
    def __init__(self, environment: Any):
        super().__init__(environment)
        self.connection: Optional[psycopg.Connection] = None
        self._connect()
        self.prepared_statements: Dict[str, str] = {}
        self.cached_queries: Dict[str, str] = {}

    def _connect(self) -> None:
        try:
            if self.connection and not self.connection.closed:
                self.connection.close()
        except Exception as e:
            logging.exception(f"Error closing existing connection: {e}")

        try:
            self.connection = psycopg.connect(
                conninfo=self.environment.parsed_options.pgsql_connection_string,
                autocommit=True
            )
        except Exception as e:
            logging.exception(f"Connection error occurred: {e}")
            self.connection = None
    
    def _disconnect(self) -> None:
        if self.connection and not self.connection.closed:
            self.connection.close()
            self.connection = None

    def run_startup(self, workloadName: str) -> None:
        try:
            startup = Path(settings.get_config_path()) / f"{workloadName}_startup.sql"

            logging.info(f"Executing startup script file: {startup}")

            with open(startup, 'r', encoding='utf-8') as file:
                sql_commands = file.read()

            with self.connection.cursor() as cursor:
                for command in sql_commands.split(';'):
                    command = command.strip()
                    if command:
                        cursor.execute(command)

            self._disconnect()
        except Exception as e:
            logging.error(f"Error occurred while executing startup script file: {startup}. Exception: {e}")

    @staticmethod
    def _format_sql_value(value: Any) -> str:
        """Format a Python value as a SQL literal string."""
        if isinstance(value, str):
            return f"'{value.replace("'", "''")}'"
        elif value is None:
            return 'NULL'
        elif isinstance(value, bool):
            return 'TRUE' if value else 'FALSE'
        else:
            return str(value)

    def _prepare_statement(self, sql: str, task_name: str, param_map: Dict[str, Dict]) -> Optional[str]:
        """Prepare a PostgreSQL statement for better performance."""
        if task_name in self.prepared_statements:
            return self.prepared_statements[task_name]
        
        try:
            prepared_name = f"prepared_{task_name.replace(' ', '_').replace('-', '_')}"
            params_in_query = self._param_pattern.findall(sql)
            
            # Build parameter types in order (params_in_query already includes @)
            param_types = []
            for param_name in params_in_query:
                param_def = param_map.get(param_name)
                if param_def:
                    param_types.append(param_def.get('sqldatatype') or 
                                     DataManager.generate_param_value(param_def, db_type='pgsql')[1])
                else:
                    logging.warning(f"Parameter {param_name} not found, defaulting to VARCHAR(8000)")
                    param_types.append('VARCHAR(8000)')
            
            # Convert @param to $1, $2, etc.
            prepare_query = sql
            for idx, param_name in enumerate(params_in_query, 1):
                prepare_query = prepare_query.replace(param_name, f'${idx}')
            
            # Execute PREPARE statement
            prepare_statement = f"PREPARE {prepared_name}({', '.join(param_types)}) AS {prepare_query}"
            logging.debug(f"Prepared statement: {prepare_statement}")
            
            with self.connection.cursor() as cursor:
                cursor.execute(prepare_statement)
            
            self.prepared_statements[task_name] = prepared_name
            return prepared_name
            
        except Exception as e:
            logging.error(f"Failed to prepare statement for {task_name}: {e}")
            return None

    def _generate_param_values(self, params_in_query: List[str], all_values: Dict[str, Any], 
                               command_type: str) -> List:
        """Generate parameter values for execution based on command type."""
        values = []
        for param_name in params_in_query:
            if param_name in all_values:
                values.append(all_values[param_name])
            else:
                logging.warning(f"Parameter {param_name} not found")
                values.append(None)
        
        if command_type == 'prepared':
            # Format as SQL literals for EXECUTE
            return [self._format_sql_value(v) for v in values]
        else:
            # Return as list for executemany
            return values

    def execute(self, command: Dict, task_name: str) -> None:
        """Execute a PostgreSQL command with support for ad-hoc, prepared, and parameterized queries."""
        if self.connection is None:
            logging.error("No database connection available. Attempting to reconnect.")
            self._connect()
            if self.connection is None:
                logging.error("Reconnection failed.")
                return

        # Extract and validate command properties
        sql = command.get('definition', '')
        command_type = command.get('type', 'ad-hoc').lower()
        if command_type not in ('ad-hoc', 'prepared'):
            command_type = 'ad-hoc'
        
        batch_size = command.get('batchSize', 1)
        parameters = command.get('parameters', [])
        
        # Create parameter lookup map (names already include @ from YAML)
        param_map = {p.get('name', ''): p for p in parameters}
        params_in_query = self._param_pattern.findall(sql)
        
        # Get or create cached execution command
        cache_key = f"{task_name}_{command_type}"
        if cache_key not in self.cached_queries:
            if command_type == 'prepared':
                prepared_name = self._prepare_statement(sql, task_name, param_map)
                if prepared_name is None:
                    return
                self.cached_queries[cache_key] = f"EXECUTE {prepared_name}"
            elif command_type == 'ad-hoc':
                # Convert @params to %s for parameterized execution
                exec_query = sql
                for param_name in params_in_query:
                    exec_query = exec_query.replace(param_name, '%s')
                self.cached_queries[cache_key] = exec_query
            else:
                self.cached_queries[cache_key] = sql
        
        exec_command = self.cached_queries[cache_key]
        
        # Generate parameter values for all batch executions
        param_values_list = []
        for _ in range(batch_size):
            all_values = {}
            for param_name, param_def in param_map.items():
                value, _ = DataManager.generate_param_value(param_def, all_values)
                all_values[param_name] = value
            param_values_list.append(self._generate_param_values(params_in_query, all_values, command_type))
        
        # For prepared statements, format each set of values into EXECUTE command
        if command_type == 'prepared':
            exec_commands = [f"{exec_command}({', '.join(vals)})" for vals in param_values_list]
            exec_func = lambda cursor: cursor.executemany('SELECT %s', [[cmd] for cmd in exec_commands]) if len(exec_commands) > 1 else cursor.execute(exec_commands[0])
        else:
            exec_func = lambda cursor: cursor.executemany(exec_command, param_values_list)
        
        logging.debug(f"Executing command: {exec_command}, type: {command_type}, batch_size: {batch_size}, params: {param_values_list[:3] if len(param_values_list) > 3 else param_values_list}")
        
        # Execute with timing
        start_time = time.perf_counter()
        try:
            with self.connection.cursor() as cursor:
                exec_func(cursor)
            
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL', task_name, total_time, response_length=batch_size)
        except DatabaseError as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL-Error', task_name, total_time, exception=e)
            logging.exception(f"Database error: {e}")
            self._connect()
        except Exception as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing command: {e}")