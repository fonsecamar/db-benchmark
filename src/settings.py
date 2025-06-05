from typing import List, Dict, Any
from decimal import Decimal
from dataclasses import dataclass

import os, json
import logging

@dataclass
class Parameter:
    name: str
    type: str
    start: int = None
    end: int = None
    value: str = None

@dataclass
class Command:
    definition: str
    parameters: List[Parameter]

@dataclass
class TaskConfig:
    taskWeightPct: Decimal
    taskName: str
    command: Command

    _existing_task_names = {"command": 0}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'TaskConfig':
        command = None

        if "command" in data:
            cmd_data = data.get("command", {})
            cmd_params = [Parameter(**param) for param in cmd_data.get("parameters", [])]
            command = Command(
                definition=cmd_data.get("definition", ""),
                parameters=cmd_params
            )
        
        taskName = data.get("taskName", "").lower()
        if not taskName:
            if command:
                operation = "command"
    
            TaskConfig._existing_task_names[operation] += 1
            taskName = f"{operation}_{TaskConfig._existing_task_names[operation]}"
        else:
            if taskName in TaskConfig._existing_task_names:
                TaskConfig._existing_task_names[taskName] += 1
                taskName = f"{taskName}_{TaskConfig._existing_task_names[taskName]}"
            else:
                TaskConfig._existing_task_names[taskName] = 0
        
        return TaskConfig(
            taskWeightPct=Decimal(data.get("taskWeightPct", 100)),
            taskName=taskName,
            command=command
        )

def init_settings() -> Dict:
    json_file_path = os.path.join(os.path.dirname(__file__), 'config/config.json')
    logging.info(f"Loading settings from {json_file_path}")
    if os.path.exists(json_file_path):
        with open(json_file_path, 'r') as file:
            config = json.load(file)
            return [TaskConfig.from_dict(task) for task in config]