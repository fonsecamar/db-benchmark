import psycopg
import logging
import time
from typing import Any, Dict, Optional
from executors.base_executor import BaseExecutor
from datamanager import DataManager
from psycopg import DatabaseError

class PGSQLExecutor(BaseExecutor):
    def __init__(self, environment: Any, workload_name: str):
        super().__init__(environment, workload_name)
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

        param_values = []

        command_def = command.get('definition', '')
        command_type = command.get('type', 'prepared').lower()
        if command_type not in ['ad-hoc', 'prepared']:
            command_type = 'ad-hoc'

        if task_name not in self.prepared_params:
            exec_command = self._replace_string_default(command_def)
            self.prepared_params[task_name] = exec_command
        else:
            exec_command = self.prepared_params[task_name]

        for param in command.get('parameters', []):
            value, value_type = DataManager.generate_param_value(param)
            param_values.append(value)

        logging.debug(f"Executing PGSQL {command_type} command: {exec_command} with params: {param_values}")

        start_time = time.perf_counter()
        try:
            with self.connection.cursor() as cursor:
                cursor.execute(exec_command, tuple(param_values), prepare=(command_type == 'prepared'))
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL', task_name, total_time, response_length=1)
        except DatabaseError as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL-Error', task_name, total_time, exception=e)
            logging.exception(f"Operational error executing command: {e}")
            self._connect()
        except Exception as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('PGSQL-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing command: {e}")