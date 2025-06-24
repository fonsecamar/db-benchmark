import re
import copy

class BaseExecutor:
    abstract = True
    def __init__(self, environment, workload_name):
        self.environment = environment
        self.workload_name = workload_name
        self.parsedCommands = {}

    def _fire_event(self, request_type, name, response_time, exception=None, response_length=0):
        self.environment.events.request.fire(
            request_type=request_type,
            name=name,
            response_time=response_time,
            exception=exception,
            response_length=response_length,
        )

    def _connect(self):
        """Override in subclass if needed."""
        pass

    def _replace_string_params(self, sql, mapping) -> str:
        # Replace all @variables with their placeholder
        def replacer(match):
            var = match.group(0)
            return mapping.get(var, "%s")  # Default to %s if not found
        return re.sub(r'@\w+', replacer, sql)
    
    def _replace_string_default(self, sql) -> str:
        # Replace all @variables with default %s placeholder
        return re.sub(r'@\w+', "%s", sql)


    # Utility to map all parameter names to their paths in a single pass
    def _map_all_param_paths(self, obj, param_names):
        result = {param: [] for param in param_names}
        def recurse(o, current_path=None):
            if current_path is None:
                current_path = []
            if isinstance(o, dict):
                for k, v in o.items():
                    for param in param_names:
                        if v == param:
                            result[param].append(current_path + [k])
                    if isinstance(v, (dict, list)):
                        recurse(v, current_path + [k])
            elif isinstance(o, list):
                for idx, item in enumerate(o):
                    for param in param_names:
                        if item == param:
                            result[param].append(current_path + [idx])
                    if isinstance(item, (dict, list)):
                        recurse(item, current_path + [idx])
        recurse(obj)
        return result

    def _replace_json_param_at_paths(self, obj, paths, value):
        """
        Replace all occurrences at the given paths in obj with value.
        """
        for path in paths:
            target = obj
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = value
        return obj

    def _replace_all_params(self, obj, param_paths_dict, param_values):
        obj_copy = copy.deepcopy(obj)
        for param, paths in param_paths_dict.items():
            self._replace_json_param_at_paths(obj_copy, paths, param_values[param])
        return obj_copy    

    def execute(self, command):
        raise NotImplementedError("Subclasses must implement this method.")
