from locust import User, events
from executors.sql_executor import SQLExecutor
from executors.pgsql_executor import PGSQLExecutor
from executors.mongodb_executor import MongoDBExecutor
from executors.cosmosdb_executor import CosmosDBExecutor
import settings
import logging
from typing import List, Any, Callable

logging.basicConfig(level=logging.INFO)
all_profiles = settings.init_settings()

@events.init_command_line_parser.add_listener
def _(parser):
    added_types = set()
    for setting in all_profiles:
        load_type = setting.type
        if load_type in added_types:
            continue
        if load_type == "SQL":
            parser.add_argument("--sql-server", type=str, is_required=True)
            parser.add_argument("--sql-user", type=str, is_required=True)
            parser.add_argument("--sql-password", type=str, is_required=True, is_secret=True)
            parser.add_argument("--sql-db-name", type=str, is_required=True)
        elif load_type == "PGSQL":
            parser.add_argument("--pgsql-connection-string", type=str, is_required=True, is_secret=True)
        elif load_type == "MONGODB":
            parser.add_argument("--mongodb-connection-string", type=str, is_required=True, is_secret=True)
        elif load_type == "COSMOSDB":
            parser.add_argument("--cosmosdb-connection-string", type=str, is_required=True, is_secret=True)
        added_types.add(load_type)

def get_executor(load_type: str, environment: Any, workload_name: str):
    if load_type == "SQL":
        return SQLExecutor(environment, workload_name)
    elif load_type == "PGSQL":
        return PGSQLExecutor(environment, workload_name)
    elif load_type == "MONGODB":
        return MongoDBExecutor(environment, workload_name)
    elif load_type == "COSMOSDB":
        return CosmosDBExecutor(environment, workload_name)
    else:
        logging.error(f"Unsupported type: {load_type}. Supported types are SQL, PGSQL, MONGODB, and COSMOSDB.")
        return None

def create_task_function(command, task_name) -> Callable:
    def task_func(self):
        self.executor.execute(command, task_name)
    task_func.__name__ = task_name
    return task_func

def create_user_class(class_name: str, load_type: str, workload_name: str, tasks: List[Any]):
    executor_factory = lambda env: get_executor(load_type, env, workload_name)

    class DynamicUser(User):
        def __init__(self, environment, *args, **kwargs):
            super().__init__(environment, *args, **kwargs)
            self.executor = executor_factory(environment)

        def on_stop(self):
            if self.executor:
                try:
                    self.executor._disconnect()
                except Exception as e:
                    logging.error(f"Error disconnecting executor: {e}")
            return super().on_stop()

    task_list = []
    for task_def in tasks:
        fullTaskName = f"{workload_name}_{task_def.taskName}"
        func = create_task_function(task_def.command, fullTaskName)
        setattr(DynamicUser, task_def.taskName, func)
        logging.info(f"Adding task {task_def.taskName}:weight {task_def.taskWeightPct} to user class {class_name}")
        for i in range(task_def.taskWeightPct):
            task_list.append(func)
    
    DynamicUser.tasks = task_list
    DynamicUser.__name__ = class_name
    return DynamicUser

classes = {}
for setting in all_profiles:
    load_type = setting.type
    new_class_name = f"{setting.workloadName.replace('_', '')}_{load_type}_User"
    logging.info(f"Creating user class: {new_class_name}")
    classes[new_class_name] = create_user_class(new_class_name, load_type, setting.workloadName, setting.tasks)

globals().update({cls.__name__: cls for cls in classes.values()})