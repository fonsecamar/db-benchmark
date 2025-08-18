from typing import List, Dict, Any
from dataclasses import dataclass
from pathlib import Path
import json
import logging
import yaml

@dataclass
class TaskConfig:
    taskWeight: int
    taskName: str
    command: Dict[str, Any]

    @staticmethod
    def from_dict(data: dict):
        return TaskConfig(
            taskWeight=data.get("taskWeight", 1),
            taskName=data.get("taskName"),
            command=data.get("command", {})
        )

@dataclass
class Settings:
    workloadName: str
    type: str
    tasks: List[TaskConfig]

def load_tasks(config: dict) -> List[TaskConfig]:
    tasks = []
    name_count = {}
    for task in config.get("tasks", []):
        base_name = task.get("taskName")
        if base_name in name_count:
            name_count[base_name] += 1
            task["taskName"] = f"{base_name}_{name_count[base_name]}"
        else:
            name_count[base_name] = 0
        tasks.append(TaskConfig.from_dict(task))
    return tasks

def init_settings() -> List[Settings]:

    if Path.cwd() == Path('/app'):
        config_dir = Path('/app/config')
    else:
        config_dir = Path(__file__).parent.parent / 'config/'
    
    config_dir = config_dir.resolve()
    logging.info(f"Loading settings from all JSON and YAML files in {config_dir}")
    settings_list: List[Settings] = []
    if not config_dir.exists():
        logging.warning(f"Config directory {config_dir} does not exist.")
        return settings_list

    for config_file in config_dir.glob('*'):
        if config_file.suffix.lower() not in ['.json', '.yaml', '.yml']:
            continue
        try:
            with open(config_file, 'r', encoding='utf-8') as file:
                if config_file.suffix.lower() == '.json':
                    config = json.load(file)
                else:
                    config = yaml.safe_load(file)
            workload_name = config_file.stem
            config_type = config.get("type", "")
            tasks = load_tasks(config)
            settings_list.append(Settings(
                workloadName=workload_name,
                type=config_type.upper(),
                tasks=tasks
            ))
        except Exception as e:
            logging.error(f"Failed to load {config_file}: {e}")
    return settings_list