import logging
import re
import settings
import time

from cassandra.cluster import Cluster, NoHostAvailable
from cassandra.auth import PlainTextAuthProvider
from cassandra.policies import DCAwareRoundRobinPolicy
from cassandra import ConsistencyLevel, OperationTimedOut
from cassandra.concurrent import execute_concurrent_with_args
from datamanager import DataManager
from executors.base_executor import BaseExecutor
from pathlib import Path
from ssl import PROTOCOL_TLS_CLIENT, SSLContext, CERT_NONE, TLSVersion
from typing import Any, Dict, Optional, List

class CassandraExecutor(BaseExecutor):
    # Compile regex pattern once at class level
    _param_pattern = re.compile(r'@(\w+)')
    # Optimal concurrency for Cassandra bulk operations
    _MAX_CONCURRENCY = 100
    
    def __init__(self, environment: Any):
        super().__init__(environment)
        self.cluster: Optional[Cluster] = None
        self.session = None
        self._connect()
        self.prepared_statements: Dict[str, Dict[str, Any]] = {}

    def _connect(self) -> None:
        """Establish Cassandra cluster connection with timeout."""
        try:
            # Parse connection string or use individual parameters
            contact_points = self.environment.parsed_options.cassandra_contact_points.split(',')
            port = self.environment.parsed_options.cassandra_port
            
            # Set up authentication if provided
            auth_provider = None
            username = self.environment.parsed_options.cassandra_username
            password = self.environment.parsed_options.cassandra_password

            if username and password:
                auth_provider = PlainTextAuthProvider(username=username, password=password)

            # Set up load balancing policy
            load_balancing_policy = DCAwareRoundRobinPolicy()

            ssl_context = SSLContext(PROTOCOL_TLS_CLIENT)
            ssl_context.minimum_version = TLSVersion.TLSv1_3
            ssl_context.check_hostname = False
            ssl_context.verify_mode = CERT_NONE

            self.cluster = Cluster(
                contact_points=contact_points,
                port=port,
                auth_provider=auth_provider,
                ssl_context=ssl_context,
                load_balancing_policy=load_balancing_policy,
                protocol_version=4,
                connect_timeout=10,  # Timeout for initial connection
                control_connection_timeout=10  # Timeout for control queries
            )
            
            self.session = self.cluster.connect()
            logging.debug("Cassandra connection established.")
        except (NoHostAvailable, OperationTimedOut) as e:
            logging.error(f"Cassandra connection error: {e}")
            self.cluster = None
            self.session = None
        except Exception as e:
            logging.exception(f"Unexpected Cassandra connection error: {e}")
            self.cluster = None
            self.session = None

    def _disconnect(self) -> None:
        """Close Cassandra connection."""
        if self.session:
            self.session.shutdown()
            self.session = None
        if self.cluster:
            self.cluster.shutdown()
            self.cluster = None

    def run_startup(self, workloadName: str) -> None:
        """Execute CQL startup script to create keyspace, tables and indexes."""
        try:
            startup = Path(settings.get_config_path()) / f"{workloadName}_startup.cql"
            
            if not startup.exists():
                logging.warning(f"Startup script not found: {startup}")
                return

            logging.info(f"Executing startup script file: {startup}")

            with open(startup, 'r', encoding='utf-8') as file:
                cql_script = file.read()

            # Split CQL script into individual statements (Cassandra requires one statement per execute)
            # Remove comments and split by semicolon
            statements = []
            for line in cql_script.split('\n'):
                # Remove line comments
                line = re.sub(r'--.*$', '', line).strip()
                if line:
                    statements.append(line)
            
            # Join lines and split by semicolon
            full_script = ' '.join(statements)
            cql_statements = [stmt.strip() for stmt in full_script.split(';') if stmt.strip()]

            # Execute each statement individually
            success_count = 0
            error_count = 0
            for statement in cql_statements:
                try:
                    logging.debug(f"Executing CQL: {statement[:100]}...")
                    self.session.execute(statement)
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    logging.error(f"Error executing CQL statement: {statement[:100]}... Error: {e}")

            logging.info(f"Startup script execution completed: {success_count} successful, {error_count} errors")
            
        except FileNotFoundError:
            logging.warning(f"Startup script file not found: {startup}")
        except Exception as e:
            logging.error(f"Error occurred while executing startup script file: {startup}. Exception: {e}")

    def _prepare_statement(self, cql: str, task_name: str) -> Optional[Dict[str, Any]]:
        """Prepare a CQL statement for better performance."""
        if task_name not in self.prepared_statements:
            try:
                # Use class-level compiled pattern for better performance
                param_names = self._param_pattern.findall(cql)
                
                # Replace @param with ? for Cassandra prepared statements
                cql_prepared = self._param_pattern.sub('?', cql)
                
                prepared = self.session.prepare(cql_prepared)
                
                # Cache statement with unique param names as set for faster lookups
                self.prepared_statements[task_name] = {
                    'statement': prepared,
                    'param_names': param_names,
                    'unique_param_names': set(param_names)  # Cached for _generate_param_values
                }
                logging.debug(f"Prepared statement for task {task_name}: {cql_prepared} with params: {param_names}")
            except Exception as e:
                logging.error(f"Failed to prepare statement for task {task_name}: {e}")
                return None
        return self.prepared_statements[task_name]

    def execute(self, command: Dict, task_name: str) -> None:
        """Execute a Cassandra command using prepared statements with concurrent execution."""
        if self.session is None:
            logging.error("No Cassandra session available. Attempting to reconnect.")
            self._connect()
            if self.session is None:
                logging.error("Reconnection to Cassandra failed.")
                return

        # All preparation outside the timer
        command_def = command.get('definition', '')
        batch_size = command.get('batchSize', 1)
        params = command.get('parameters', [])
        param_definitions = {param.get('name', '').lstrip('@'): param for param in params}

        # Prepare statement (cached after first call)
        prepared_data = self._prepare_statement(command_def, task_name)
        if prepared_data is None:
            logging.error(f"Failed to prepare statement for task {task_name}")
            return

        # Set consistency level before timing (only if different)
        consistency_level = command.get('consistencyLevel')
        original_consistency = None
        if consistency_level:
            target_consistency = getattr(ConsistencyLevel, consistency_level.upper(), None)
            if target_consistency and target_consistency != self.session.default_consistency_level:
                original_consistency = self.session.default_consistency_level
                self.session.default_consistency_level = target_consistency

        # Generate all parameter values before timing
        if batch_size == 1:
            param_values = self._generate_param_values(prepared_data, param_definitions)
        else:
            # Use optimal concurrency (max 100 for best Cassandra performance)
            concurrency = min(batch_size, self._MAX_CONCURRENCY)
            parameters_list = [
                self._generate_param_values(prepared_data, param_definitions)
                for _ in range(batch_size)
            ]
        
        logging.debug(f"Executing command: {prepared_data} with params: {parameters_list if batch_size > 1 else param_values}, batch size: {batch_size}")

        start_time = time.perf_counter()
        
        try:
            if batch_size == 1:
                result = self.session.execute(prepared_data['statement'], param_values)
            else:
                execute_concurrent_with_args(
                    self.session,
                    prepared_data['statement'],
                    parameters_list,
                    concurrency=concurrency,
                    raise_on_first_error=False
                )
                result = None

            total_time = int((time.perf_counter() - start_time) * 1000)

            response_length = 0
            if result:
                response_length = sum(len(str(row)) for row in result)

            result = None

            # Restore consistency level after timing
            if original_consistency is not None:
                self.session.default_consistency_level = original_consistency

            logging.debug(f"Cassandra executed {batch_size} statements in {total_time}ms, response size: {response_length} bytes")
            self._fire_event('Cassandra', task_name, total_time, response_length=response_length)
            
        except (NoHostAvailable, OperationTimedOut) as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('Cassandra-Error', task_name, total_time, exception=e)
            logging.error(f"Cassandra connection error: {e}")
            
            # Restore consistency level even on error
            if original_consistency is not None:
                self.session.default_consistency_level = original_consistency
            
            # Attempt to reconnect on connection errors
            logging.info("Attempting to reconnect due to connection error")
            self._connect()
            
        except Exception as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('Cassandra-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing Cassandra command: {e}")
            
            # Restore consistency level even on error
            if original_consistency is not None:
                self.session.default_consistency_level = original_consistency

    def _generate_param_values(self, prepared_data: Dict, param_definitions: Dict) -> List[Any]:
        """Generate parameter values for a single execution."""
        # Early return if no parameters
        if not prepared_data['param_names']:
            return []
        
        # Use cached unique param names from prepared statement
        param_map = {}
        for param_name in prepared_data['unique_param_names']:
            if param_name in param_definitions:
                param_map[param_name] = DataManager.generate_param_value(param_definitions[param_name])[0]
            else:
                param_map[param_name] = None
        
        return [param_map.get(name) for name in prepared_data['param_names']]


