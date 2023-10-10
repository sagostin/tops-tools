import re

string = "My phone number is +15551234567"
pattern = r'^(\+?1)?([2-9]\d{9})$'

match = re.search(pattern, string)
if match:
    prefix = match.group(1) if match.group(1) else ""
    phone_number = prefix + match.group(2)
    print("Phone number:", phone_number)
else:
    print("No phone number found.")
