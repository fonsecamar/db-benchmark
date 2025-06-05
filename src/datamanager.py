from datetime import datetime, timezone
from faker import Faker

import random
import re
import uuid
#from bson import ObjectId

class DataManager:
    faker = Faker()

    @staticmethod
    def replace_sql_vars(sql, mapping) -> str:
        # Replace all @variables with their placeholder
        def replacer(match):
            var = match.group(0)
            return mapping.get(var, "%s")  # Default to %s if not found
        return re.sub(r'@\w+', replacer, sql)

    @staticmethod
    def generate_param_value(param, values=None):
        param_type = param.type.lower()
        values = values or {}

        if param_type == "guid":
            return str(uuid.uuid4()), "%s"
        #elif param_type == "objectid":
        #    return str(ObjectId())
        elif param_type == "date":
            return datetime.now(timezone.utc).strftime("%Y-%m-%d"), "%s"
        elif param_type == "datetime":
            return datetime.now(timezone.utc), "%s"
        elif param_type == "datetimeISO":
            return datetime.now(timezone.utc).isoformat(), "%s"
        elif param_type == "random_int":
            return random.randint(param.start, param.end), "%d"
        elif param_type == "random_int_as_string":
            return str(random.randint(param.start, param.end)), "%s"
        #elif param_type == "sequential_int":
        #    return self.get_sequential_value(f"{config_context}_{param['name']}", param['start'])
        #elif param_type == "sequential_int_as_string":
        #    return str(self.get_sequential_value(f"{config_context}_{param['name']}", param['start']))
        elif param_type == "random_list":
            return random.choice(param.list), "%s"
        elif param_type == "random_bool":
            return random.choice([True, False]), "%s"
        elif param_type == "faker.timestamp":
            return DataManager.faker.date_time().timestamp(), "%d"
        elif param_type == "faker.firstname":
            return DataManager.faker.first_name(), "%s"
        elif param_type == "faker.lastname":
            return DataManager.faker.last_name(), "%s"
        elif param_type == "faker.fullname":
            return DataManager.faker.name(), "%s"
        elif param_type == "faker.dateofbirth":
            return DataManager.faker.date_of_birth().strftime("%Y-%m-%d"), "%s"
        elif param_type == "faker.address":
            return DataManager.faker.address(), "%s"
        elif param_type == "faker.phone":
            return DataManager.faker.phone_number(), "%s"
        elif param_type == "faker.email":
            return DataManager.faker.email(), "%s"
        elif param_type == "constant_string":
            return param.value, "%s"
        elif param_type == "constant_int64":
            return int(param.value), "%d"
        elif param_type == "concat":
            sb = []
            idx = 0
            for match in re.finditer(r"\{@\w+\}", param.value):
                sb.append(param.value[idx:match.start()])
                key = match.group(0)[2:-1]
                sb.append(str(values[key]))
                idx = match.end()
            if len(param.value) > idx:
                sb.append(param.value[idx:])
            return ''.join(sb), "%s"
        else:
            return "", "%s"