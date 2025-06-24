from locust import User, events
from executors.sql_executor import SQLExecutor
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
        type_upper = setting.type.upper()
        if type_upper in added_types:
            continue
        if type_upper == "SQL":
            parser.add_argument("--sql-server", type=str, is_required=True)
            parser.add_argument("--sql-user", type=str, is_required=True)
            parser.add_argument("--sql-password", type=str, is_required=True, is_secret=True)
            parser.add_argument("--sql-db-name", type=str, is_required=True)
        elif type_upper == "MONGODB":
            parser.add_argument("--mongodb-connection-string", type=str, is_required=True, is_secret=True)
        elif type_upper == "COSMOSDB":
            parser.add_argument("--cosmosdb-connection-string", type=str, is_required=True, is_secret=True)
        added_types.add(type_upper)

def get_executor(type_upper: str, environment: Any, workload_name: str):
    if type_upper == "SQL":
        return SQLExecutor(environment, workload_name)
    elif type_upper == "MONGODB":
        return MongoDBExecutor(environment, workload_name)
    elif type_upper == "COSMOSDB":
        return CosmosDBExecutor(environment, workload_name)
    else:
        logging.error(f"Unsupported type: {type_upper}. Supported types are SQL, MONGODB, and COSMOSDB.")
        return None

def create_task_function(command, task_name) -> Callable:
    def task_func(self):
        self.executor.execute(command, task_name)
    task_func.__name__ = task_name
    return task_func

def create_user_class(class_name: str, _type: str, _workload_name: str, tasks: List[Any]):
    type_upper = _type.upper()
    executor_factory = lambda env: get_executor(type_upper, env, _workload_name)

    class DynamicUser(User):
        def __init__(self, environment, *args, **kwargs):
            super().__init__(environment, *args, **kwargs)
            self.executor = executor_factory(environment)

    task_dict = {}
    for task_def in tasks:
        if task_def.taskWeightPct > 0:
            fullTaskName = f"{_workload_name}_{task_def.taskName}"
            func = create_task_function(task_def.command, fullTaskName)
            setattr(DynamicUser, task_def.taskName, func)
            logging.info(f"Adding task {task_def.taskName}:weight {task_def.taskWeightPct} to user class {class_name}")
            task_dict[func] = task_def.taskWeightPct
    
    DynamicUser.tasks = task_dict
    DynamicUser.__name__ = class_name
    return DynamicUser

classes = {}
for setting in all_profiles:
    new_class_name = f"{setting.workloadName.replace('_', '')}_{setting.type.upper()}_User"
    logging.info(f"Creating user class: {new_class_name}")
    classes[new_class_name] = create_user_class(new_class_name, setting.type, setting.workloadName, setting.tasks)

globals().update({cls.__name__: cls for cls in classes.values()})