import datetime
from collections import defaultdict
from xml.etree import ElementTree

import jwt
import requests


# Constants (should be securely managed)
def load_private_key_from_file() -> str:
    with open("onevoice-certs/private.key", "r") as file:
        return file.read()


PRIVATE_KEY = load_private_key_from_file()
SECURITY_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"  # provided by OneVoice
APPLICATION_NAME = "YourAppName"  # Replace with your application's name
ONEVOICE_LNP_API_ENDPOINT = "https://{Environment}/api/v1/orders_lnp/"  # Replace with the actual OneVoice API endpoint

ucontrol_username = ""
ucontrol_password = ""


def get_sip_trunks(ucontrol_username, ucontrol_password):
    base_url = "https://api.thinktel.ca/rest.svc/SipTrunks"
    headers = {"Content-Type": "text/json", "Accept": "text/json"}

    response = requests.get(base_url, headers=headers, auth=(ucontrol_username, ucontrol_password))

    if response.status_code != 200:
        print(f"Error getting SIP trunks. Status code: {response.status_code} - {response.text}")
        return []

    try:
        return response.json()
    except ValueError:
        print(f"Error parsing JSON from response: {response.text}")
        return []


def get_dids_for_trunk(number, ucontrol_username, ucontrol_password, page_from=0, page_size=1000):
    base_url = f"https://api.thinktel.ca/rest.svc/SipTrunks/{number}/Dids?PageFrom={page_from}&PageSize={page_size}"
    headers = {"Content-Type": "text/json", "Accept": "text/json"}

    try:
        response = requests.get(base_url, headers=headers, auth=(ucontrol_username, ucontrol_password))
        response.raise_for_status()
        return response.json()
    except Exception as err:
        print(f"Error getting DIDs for trunk {number}: {err}")
        return []


def get_911_info_for_number(number, ucontrol_username, ucontrol_password):
    base_url = f"https://api.thinktel.ca/rest.svc/V911s/{number}"
    headers = {"Content-Type": "text/json", "Accept": "text/json"}

    response = requests.get(base_url, headers=headers, auth=(ucontrol_username, ucontrol_password))

    if response.status_code != 200:
        print(f"Error getting 911 info for number {number}. Status code: {response.status_code} - {response.text}")
        return None

    try:
        return response.json()
    except ValueError:
        print(f"Error parsing JSON from response: {response.text}")
        return None


def check_did_in_thinktel(number_to_check, ucontrol_username, ucontrol_password):
    try:
        number_to_check_int = int(number_to_check)
    except ValueError:
        print(f"Invalid number provided: {number_to_check}. Please provide a valid 10-digit number.")
        return False

    trunks = get_sip_trunks(ucontrol_username, ucontrol_password)

    for trunk in trunks:
        trunk_number = trunk.get("Number")
        if trunk_number:
            dids = get_dids_for_trunk(trunk_number, ucontrol_username, ucontrol_password)
            for did in dids:
                did_number = did.get("Number")
                if did_number == number_to_check_int:
                    print(f"The number {number_to_check} exists as a 911 DID.")
                    return True
    # print(f"The number {number_to_check} does not exist as a 911 DID.")
    return False


def get_npa_nxx(phone_number: str) -> tuple:
    return phone_number[:3], phone_number[3:6]


def request_npa_nxx_info(npa: str, nxx: str) -> dict:
    url = f"https://localcallingguide.com/xmlprefix.php?npa={npa}&nxx={nxx}"
    response = requests.get(url)

    if response.status_code != 200:
        raise Exception("Failed to fetch data from API")

    tree = ElementTree.fromstring(response.content)
    prefixdata = tree.find('prefixdata')

    data = {}
    for child in prefixdata:
        data[child.tag] = child.text

    return data


def generate_jwt(application_name: str) -> str:
    payload = {
        "iss": application_name,
        "aud": "OneVoice",
        "exp": int((datetime.datetime.utcnow() + datetime.timedelta(seconds=30)).timestamp()),
        "sid": SECURITY_ID
    }

    headers = {
        "alg": "RS256",
        "typ": "JWT"
    }

    token = jwt.encode(payload, PRIVATE_KEY, algorithm='RS256', headers=headers)

    return token


def request_with_jwt(url: str, jwt_token: str) -> requests.Response:
    headers = {
        'Authorization': f'Bearer {jwt_token}'
    }

    response = requests.get(url, headers=headers)

    return response


def process_ports(numbers: list):
    # Generate a JWT
    jwt_token = generate_jwt(APPLICATION_NAME)

    for number in numbers:
        # Create the LNP request payload based on your documentation
        lnp_request_payload = {
            "type": "lnp",
            "parameters": {
                "provider_type": "wireline",
                "requested_due_date": "2023-10-10",
                "address": {
                    "street_name": "123 Main St",
                    "street_number": "456",
                    "city": "Example City",
                    "region": "CA",
                    "postal_code": "12345"
                },
                "existing_account_num": "555-111-222",
                "local_service_provider": "AB12",
                "end_user_name": "John Doe",
                "dids": [number],
                "did_ranges": [],
                "loa_date": "2023-09-15",
                "customer_specific_object": {
                    "transaction_id": "trans123",
                    "customer_id": "cust456"
                }
            }
        }

        # Use the JWT to make an authenticated POST request to submit the LNP request
        api_url = ONEVOICE_LNP_API_ENDPOINT
        response = request_with_jwt(api_url, jwt_token, method="POST", data=lnp_request_payload)

        # Check if the request was successful
        if response.status_code == 200:
            print(f"Successfully submitted LNP request for number: {number}")
        else:
            print(f"Failed to submit LNP request for number: {number}")

            # Handle specific error cases based on the response content
            if response.status_code == 400:
                errors = response.json().get("errors", [])
                for error in errors:
                    print(f"Error: {error}")


from collections import defaultdict
import csv
import json

if __name__ == "__main__":
    numbers_str = input("Enter a list of 10-digit phone numbers separated by commas: ")
    numbers = [num.strip() for num in numbers_str.split(",")]

    rate_center_groups = defaultdict(list)
    info911 = None
    numbers_911 = []

    for number in numbers:
        is911 = check_did_in_thinktel(number, ucontrol_username, ucontrol_password)

        if is911:
            # If it's a 911 number, increment the count and store its info
            numbers_911.append(number)

            if len(numbers_911) == 1:
                info911 = get_911_info_for_number(number, ucontrol_username, ucontrol_password)
        else:
            npa, nxx = get_npa_nxx(number)
            info = request_npa_nxx_info(npa, nxx)
            rate_center = info['rc']
            rate_center_groups[rate_center].append(number)

    if len(numbers_911) == 1:
        # If there's only one 911 number, print its info for other numbers
        for number in numbers:
            if number not in numbers_911:
                print(f"911 Info (fetched from ThinkTel) - {number}: " + str(info911))
    elif len(numbers_911) > 1:
        # If there are multiple 911 numbers, throw an error
        print("Error: Multiple 911 numbers detected. Requires human intervention.")
    else:
        # If there are no 911 numbers, proceed to process numbers
        if len(rate_center_groups) == 1:
            print("All numbers belong to the same rate center.")
            process_ports(numbers)
        else:
            for rc, nums in rate_center_groups.items():
                print(f"Processing port for rate center: {rc}")
                process_ports(nums)

    # Export the data to a CSV file
    csv_file_path = input("Enter the filename/path for the CSV file: ")
    with open(csv_file_path, 'w', newline='') as csv_file:
        fieldnames = [
            'PhoneNumber',
            'LastName',
            'FirstName',
            'StreetNumber',
            'SuiteApt',
            'StreetName',
            'City',
            'ProvinceState',
            'PostalCodeZip',
            'OtherAddressInfo',
            'EnhancedCapable'
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for number in numbers:
            is911 = numbers_911.__contains__(number)
            data = {
                'PhoneNumber': str(number),
                'LastName': info911['LastName'],
                'FirstName': info911['FirstName'],
                'StreetNumber': info911['StreetNumber'],
                'SuiteApt': info911['SuiteNumber'],
                'StreetName': info911['StreetName'],
                'City': info911['City'],
                'ProvinceState': info911['ProvinceState'],
                'PostalCodeZip': info911['PostalZip'],
                'OtherAddressInfo': info911['OtherInfo'],
                'EnhancedCapable': 'N' if is911 else 'N'
            }
            if not is911:
                writer.writerow(data)
