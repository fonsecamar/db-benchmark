import logging
import pymssql
import settings
import time

from datamanager import DataManager
from executors.base_executor import BaseExecutor
from pathlib import Path
from pymssql import DatabaseError
from typing import Any, Dict, Optional

class SQLExecutor(BaseExecutor):
    def __init__(self, environment: Any):
        super().__init__(environment)
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
                autocommit=True,
                appname="locust-worker"
            )
        except Exception as e:
            logging.exception(f"Connection error occurred: {e}")
            self.connection = None

    def _disconnect(self) -> None:
        if self.connection:
            self.connection.close()
            self.connection = None

    def run_startup(self, workloadName: str) -> None:
        
        try:
            startup = Path(settings.get_config_path()) / f"{workloadName}_startup.sql"

            logging.info(f"Executing startup script file: {startup}")

            with open(startup, 'r', encoding='utf-8') as file:
                sql_commands = file.read()

            with self.connection.cursor(as_dict=True) as cursor:
                for command in sql_commands.split(';'):
                    command = command.strip()
                    if command:
                        cursor.execute(command)

            self._disconnect()
        except Exception as e:
            logging.error(f"Error occurred while executing startup script file: {startup}. Exception: {e}")

    def execute(self, command: Dict, task_name: str) -> None:
        if self.connection is None:
            logging.error("No database connection available. Attempting to reconnect.")
            self._connect()
            if self.connection is None:
                logging.error("Reconnection failed.")
                return

        batch_tuples: list[tuple] = []
        param_tuples = []
        param_values = []
        param_defs = []
        column_ids: list[int] = []
        param_def_str = None
        batch_size = 1

        command_def = command.get('definition', '')
        command_type = command.get('type', 'prepared').lower()
        if command_type not in ['ad-hoc', 'stored_procedure', 'prepared', 'bulk_insert']:
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
        elif command_type == 'bulk_insert':
            table_name = command.get('tableName', '')
            exec_command = table_name
            batch_size = command.get('batchSize', 1000)
            column_ids = command.get('columnIds', None)
        else:
            exec_command = command_def

        for _ in range(batch_size):
            param_values = []
            for param in command.get('parameters', []):
                value, value_type = DataManager.generate_param_value(param)
                param_values.append(value)
                if command_type == 'prepared' and param_def_str is None:
                    name = param.get('name')
                    sql_type = param.get('sqldatatype', value_type).upper()
                    param_defs.append(f"{name} {sql_type}")
            batch_tuples.append(tuple(param_values))

        if param_def_str is None:
            param_def_str = ', '.join(param_defs)

        if command_type == 'prepared':
            param_tuples.append(param_def_str)

        param_tuples = param_tuples + param_values

        logging.debug(f"Executing SQL {command_type} command: {exec_command} with params: {batch_tuples if command_type == 'bulk_insert' else param_tuples}, batch size: {batch_size}")

        if command_type == 'bulk_insert':
            db_op = lambda: self.connection.bulk_copy(table_name, batch_tuples, batch_size=batch_size, column_ids=column_ids)
        else:
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