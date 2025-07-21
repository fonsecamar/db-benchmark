import pymssql
import logging
import time
from typing import Any, Dict, Optional
from executors.base_executor import BaseExecutor
from datamanager import DataManager
from pymssql import DatabaseError

class SQLExecutor(BaseExecutor):
    def __init__(self, environment: Any, workload_name: str):
        super().__init__(environment, workload_name)
        self.connection: Optional[pymssql.Connection] = None
        self._connect()
        self.prepared_params: Dict[str, str] = {}

    def _connect(self) -> None:
        try:
            if self.connection:
                self.connection.close()
        except Exception as e:
            logging.exception(f"Error closing existing connection: {e}")

        try:
            self.connection = pymssql.connect(
                host=self.environment.parsed_options.sql_server,
                user=self.environment.parsed_options.sql_user,
                password=self.environment.parsed_options.sql_password,
                database=self.environment.parsed_options.sql_db_name,
                autocommit=True
            )
        except Exception as e:
            logging.exception(f"Connection error occurred: {e}")
            self.connection = None

    def _disconnect(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

    def execute(self, command: Dict, task_name: str) -> None:
        if self.connection is None:
            logging.error("No database connection available. Attempting to reconnect.")
            self._connect()
            if self.connection is None:
                logging.error("Reconnection failed.")
                return

        param_tuples = []
        param_values = []
        param_defs = []
        param_def_str = None

        command_def = command.get('definition', '')
        command_type = command.get('type', 'prepared').lower()
        if command_type not in ['ad-hoc', 'stored_procedure', 'prepared']:
            command_type = 'ad-hoc'

        if command_type == 'prepared':
            exec_command = 'sp_executesql'
            param_tuples.append(command_def)
            if task_name in self.prepared_params:
                param_def_str = self.prepared_params[task_name]
        elif command_type == 'ad-hoc':
            if task_name not in self.prepared_params:
                exec_command = self._replace_string_default(command_def)
                self.prepared_params[task_name] = exec_command
            else:
                exec_command = self.prepared_params[task_name]
        else:
            exec_command = command_def

        for param in command.get('parameters', []):
            value, value_type = DataManager.generate_param_value(param)
            param_values.append(value)
            if command_type == 'prepared' and param_def_str is None:
                name = param.get('name')
                sql_type = param.get('sqldatatype', value_type).upper()
                param_defs.append(f"{name} {sql_type}")

        if param_def_str is None:
            param_def_str = ', '.join(param_defs)

        if command_type == 'prepared':
            param_tuples.append(param_def_str)

        param_tuples = param_tuples + param_values

        logging.debug(f"Executing SQL {command_type} command: {exec_command} with params: {param_tuples}")

        # Prepare the database operation as a lambda for precise timing
        def db_op():
            with self.connection.cursor(as_dict=True) as cursor:
                if command_type == 'ad-hoc':
                    cursor.execute(exec_command, tuple(param_tuples))
                else:
                    cursor.callproc(exec_command, tuple(param_tuples))

        start_time = time.perf_counter()
        try:
            db_op()
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('SQL', task_name, total_time, response_length=1)
        except DatabaseError as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('SQL-Error', task_name, total_time, exception=e)
            logging.exception(f"Operational error executing command: {e}")
            self._connect()
        except Exception as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('SQL-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing command: {e}")