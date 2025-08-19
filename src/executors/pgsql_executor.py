import psycopg
import logging
import time
from typing import Any, Dict, Optional
from executors.base_executor import BaseExecutor
from datamanager import DataManager
from psycopg import DatabaseError

class PGSQLExecutor(BaseExecutor):
    def __init__(self, environment: Any):
        super().__init__(environment)
        self.connection: Optional[psycopg.Connection] = None
        self._connect()
        self.prepared_params: Dict[str, str] = {}

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

    def execute(self, command: Dict, task_name: str) -> None:
        if self.connection is None:
            logging.error("No database connection available. Attempting to reconnect.")
            self._connect()
            if self.connection is None:
                logging.error("Reconnection failed.")
                return

        command_def = command.get('definition', '')
        # Check for batch_size parameter (default to 1 for single execution)
        batch_size = command.get('batchSize', 1)

        if task_name not in self.prepared_params:
            exec_command = self._replace_string_default(command_def)
            self.prepared_params[task_name] = exec_command
        else:
            exec_command = self.prepared_params[task_name]

        # Generate parameter values for batch execution
        param_values = []
        for _ in range(batch_size):
            batch_params = []
            for param in command.get('parameters', []):
                value, value_type = DataManager.generate_param_value(param)
                batch_params.append(value)
            param_values.append(tuple(batch_params))

        logging.debug(f"Executing PGSQL command: {exec_command} with {batch_size} batch params")

        start_time = time.perf_counter()
        try:
            with self.connection.cursor() as cursor:
                cursor.executemany(exec_command, param_values)
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL', task_name, total_time, response_length=batch_size)
        except DatabaseError as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL-Error', task_name, total_time, exception=e)
            logging.exception(f"Operational error executing command: {e}")
            self._connect()
        except Exception as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing command: {e}")