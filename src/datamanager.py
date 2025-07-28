from datetime import datetime, timezone
from faker import Faker
from bson import ObjectId

import random
import uuid
import re

class DataManager:
    faker = Faker()

    @staticmethod
    def generate_param_value(param, values=None):
        param_type = param.get('type').lower()
        values = values or {}

        if param_type == "guid":
            return str(uuid.uuid4()), "uniqueidentifier"
        elif param_type == "objectid":
            return str(ObjectId())
        elif param_type == "date":
            return datetime.now(timezone.utc).strftime("%Y-%m-%d"), "date"
        elif param_type == "datetime":
            format = param.get('format', "%Y-%m-%dT%H:%M:%SZ")
            return datetime.strptime(datetime.now(timezone.utc).strftime(format), format), "datetime"
        elif param_type == "datetimeiso":
            return datetime.now(timezone.utc).isoformat(), "datetime"
        elif param_type == "random_int":
            return random.randint(param.get('start'), param.get('end')), "int"
        elif param_type == "random_int_as_string":
            return str(random.randint(param.get('start'), param.get('end'))), "varchar(255)"
        #elif param_type == "sequential_int":
        #    return self.get_sequential_value(f"{config_context}_{param['name']}", param['start'])
        #elif param_type == "sequential_int_as_string":
        #    return str(self.get_sequential_value(f"{config_context}_{param['name']}", param['start']))
        elif param_type == "random_list":
            return random.choice(param.get('list')), "varchar(255)"
        elif param_type == "random_bool":
            return random.choice([True, False]), "bit"
        elif param_type == "random_string":
            length = param.get('length', 10)  # Default to 10 characters if not specified
            
            if length <= 0:
                return "", "varchar(255)"
            elif length < 5:
                # For very short strings, use random letters/words
                chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ "
                result = ''.join(random.choice(chars) for _ in range(length))
                return result.strip() or 'a' * length, "varchar(255)"
            else:
                # Generate random text using faker and truncate/pad to exact length
                text = DataManager.faker.text(max_nb_chars=length * 2)  # Generate more text than needed
                # Clean the text (remove newlines and extra spaces)
                clean_text = ' '.join(text.split())
                # Truncate to exact length or pad if too short
                if len(clean_text) >= length:
                    return clean_text[:length], "varchar(255)"
                else:
                    # Pad with additional characters if the generated text is too short
                    additional_text = DataManager.faker.text(max_nb_chars=length)
                    combined_text = ' '.join((clean_text + ' ' + additional_text).split())
                    return combined_text[:length], "varchar(255)"
        elif param_type == "faker.timestamp":
            return DataManager.faker.date_time().timestamp(), "datetime"
        elif param_type == "faker.firstname":
            return DataManager.faker.first_name(), "varchar(255)"
        elif param_type == "faker.lastname":
            return DataManager.faker.last_name(), "varchar(255)"
        elif param_type == "faker.fullname":
            return DataManager.faker.name(), "varchar(255)"
        elif param_type == "faker.dateofbirth":
            return DataManager.faker.date_of_birth().strftime("%Y-%m-%d"), "date"
        elif param_type == "faker.address":
            return DataManager.faker.address(), "varchar(255)"
        elif param_type == "faker.phone":
            return DataManager.faker.phone_number(), "varchar(255)"
        elif param_type == "faker.email":
            return DataManager.faker.email(), "varchar(255)"
        elif param_type == "faker.ipv6":
            return DataManager.faker.ipv6(), "varchar(255)"
        elif param_type == "faker.ipv4":
            return DataManager.faker.ipv4(), "varchar(255)"
        elif param_type == "faker.msisdn":
            return DataManager.faker.msisdn(), "varchar(255)"
        elif param_type == "constant_string":
            return param.get('value'), "varchar(255)"
        elif param_type == "constant_int":
            return int(param.get('value')), "int"
        elif param_type == "concat":
            sb = []
            idx = 0
            for match in re.finditer(r"\{@\w+\}", param.get('value')):
                sb.append(param.get('value')[idx:match.start()])
                key = match.group(0)[2:-1]
                sb.append(str(values[key]))
                idx = match.end()
            if len(param.get('value')) > idx:
                sb.append(param.get('value')[idx:])
            return ''.join(sb), "varchar(255)"
        else:
            return "", "varchar(255)"