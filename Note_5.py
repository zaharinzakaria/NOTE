import pandas as pd
import os
import requests
import time
import json
import sys
from datetime import datetime
import os
import glob
import pandas as pd
import sys
import re
import time
import requests
import json
import csv
import configparser
from concurrent.futures import ThreadPoolExecutor, as_completed
import webbrowser
import subprocess


def resolve_path(path):
    # froz path location
    if getattr(sys, "frozen", False):
        resolved_path = os.path.abspath(os.path.join(sys._MEIPASS, path))
    else:
        resolved_path = os.path.abspath(os.path.join(os.getcwd(), path))
    return resolved_path

script_directory = os.path.dirname(resolve_path(__file__))
API_KEY_FILE = os.path.join(script_directory, "api_key.cfg")
LOGIN_KEY_FILE = os.path.join(script_directory, "avos_login_key.cfg")
TOKEN_KEY_FILE = os.path.join(script_directory, "token.cfg")
OUTPUT_DIRECTORY = os.path.join(script_directory, "Output")
TEMP_DIRECTORY = os.path.join(script_directory, "Temp")
FIND_TRANSACTIONS_URL = "https://walrus.ninjavan.co/my/core/route-group-templates/transactions"
ROUTE_GROUPS_URL = "https://walrus.ninjavan.co/my/route/2.0/route-groups"
SECONDS_IN_A_WEEK = 7 * 24 * 60 * 60
SECONDS_IN_A_DAY = 16 * 60 * 60

UPLOAD_JOBS = [
    {"route_group_id": 805507, "route_group_name": "zone B", "csv_file": "Zone B.csv"},
    {"route_group_id": 805511, "route_group_name": "Zone C", "csv_file": "Zone C.csv"},
    {"route_group_id": 805513, "route_group_name": "Zone D", "csv_file": "Zone D.csv"},
    {"route_group_id": 805515, "route_group_name": "Zone E", "csv_file": "Zone E.csv"},
    {"route_group_id": 805514, "route_group_name": "Zone F", "csv_file": "Zone F.csv"},
    {"route_group_id": 805512, "route_group_name": "Zone G", "csv_file": "Zone G.csv"},
    {"route_group_id": 805508, "route_group_name": "Zone H", "csv_file": "Zone H.csv"},
    {"route_group_id": 805510, "route_group_name": "Zone I", "csv_file": "Zone I.csv"},
    {"route_group_id": 805509, "route_group_name": "Zone J", "csv_file": "Zone J.csv"},
]

def is_file_older_than(file_path, seconds):
    file_creation_time = os.path.getmtime(file_path)
    current_time = time.time()
    return current_time - file_creation_time > seconds

def is_file_older_than_a_week(file_path):
    file_creation_time = os.path.getmtime(file_path)
    current_time = time.time()
    return current_time - file_creation_time > SECONDS_IN_A_WEEK

def remove_files_in_folder(folder_paths):
    for folder_path in folder_paths:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

def build_opv2_headers(token):
    return {
        "accept": "application/json, text/plain, */*",
        "authorization": f"Bearer {token}",
        "content-type": "application/json",
        "origin": "https://operatorv2.ninjavan.co",
        "referer": "https://operatorv2.ninjavan.co/",
        "user-agent": "Mozilla/5.0",
    }

def get_token_key():
    if os.path.exists(TOKEN_KEY_FILE) and not is_file_older_than(TOKEN_KEY_FILE, SECONDS_IN_A_DAY):
        with open(TOKEN_KEY_FILE, "r", encoding="utf-8") as file:
            return file.read().strip()

    if os.path.exists(TOKEN_KEY_FILE):
        os.remove(TOKEN_KEY_FILE)
        print("Old OPv2 access code removed")

    token = input("Enter your OPv2 access code: ").strip()
    with open(TOKEN_KEY_FILE, "w", encoding="utf-8") as file:
        file.write(token)

    return token

def validate_opv2_access_code():
    while True:
        token = get_token_key()
        response = requests.get(ROUTE_GROUPS_URL, headers=build_opv2_headers(token))

        if response.status_code == 200:
            return

        if response.status_code in (401, 403):
            print("OPv2 access code expired or invalid. Updating credential...")
            if os.path.exists(TOKEN_KEY_FILE):
                os.remove(TOKEN_KEY_FILE)
            continue

        print("OPv2 access code check failed")
        print("Status Code:", response.status_code)
        print(response.text)
        raise Exception("OPv2 access code check failed.")

def credential_check():
    print("Credential Checking")
    print("")
    print("==Redash==")
    get_api_key()
    print("status ok")

    print("")
    print("==OPv2==")
    validate_opv2_access_code()
    print("status ok")

def get_api_key():
    if os.path.exists(API_KEY_FILE) and not is_file_older_than_a_week(API_KEY_FILE):
        with open(API_KEY_FILE, 'r') as file:
            return file.read().strip()
    else:
        # Delete the old file if it exists
        if os.path.exists(API_KEY_FILE):
            os.remove(API_KEY_FILE)
            print("API key file deleted as it was older than a week.")
        # Ask for a new API key
        api_key = input("Enter your API key: ").strip()
        with open(API_KEY_FILE, 'w') as file:
            file.write(api_key)
        return api_key

def poll_job(s, redash_url, job):
    while job['status'] not in (3,4):
        response = s.get('{}/api/jobs/{}'.format(redash_url, job['id']))
        job = response.json()['job']
        time.sleep(1)
    if job['status'] == 3:
        return job['query_result_id']
    return None


def get_fresh_query(redash_url, query_id, api_key):
    s = requests.Session()
    s.headers.update({'Authorization': 'Key {}'.format(api_key)})
    payload = dict(max_age=0)
    response = s.post('{}/api/queries/{}/results'.format(redash_url, query_id), data=json.dumps(payload))
    if response.status_code != 200:
        raise Exception('Refresh failed.')
    result_id = poll_job(s, redash_url, response.json()['job'])
    if result_id:
        response = s.get('{}/api/queries/{}/results/{}.json'.format(redash_url, query_id, result_id))
        if response.status_code != 200:
            raise Exception('Failed getting results.')
    else:
        raise Exception('Query execution failed.')
    return response.json()['query_result']['data']['rows']

def query_normal(query_id, output_csv_path):
    api_key = get_api_key()
    print("Running Query...")

    try:
        result = get_fresh_query('https://redash-my.ninjavan.co/', query_id, api_key)
        print(f"Total number of data: {len(result)}\n")

        # Check if result is empty
        if not result:
            print("No data returned. File will not be downloaded.")
            return

        df = pd.DataFrame(result)
        df.to_csv(output_csv_path, index=False)
        print("File downloaded successfully.")

    except Exception as e:
        print(f"An error occurred: {e}")

def query_normal_date(query_id, output_csv_path):
    api_key = get_api_key()
    print("Running Query...")

    try:
        result = get_fresh_query('https://redash-my.ninjavan.co/', query_id, api_key)
        print(f"Total number of data: {len(result)}\n")

        # Check if result is empty
        if not result:
            print("No data returned. File will not be downloaded.")
            return

        df = pd.DataFrame(result)

        # Generate date string
        date_str = datetime.now().strftime("%Y%m%d")

        # Add date before .csv
        output_csv_path = output_csv_path.replace(".csv",
                                                  f"_{date_str}.csv")

        df.to_csv(output_csv_path, index=False)

        print(f"File downloaded successfully: {output_csv_path}")

    except Exception as e:
        print(f"An error occurred: {e}")


def fetch_and_save_query(query_id, zone_name, redash_url, api_key, output_folder):
    try:
        df = pd.DataFrame(get_fresh_query(redash_url, query_id, api_key))
        df.to_csv(os.path.join(output_folder, f"{zone_name}.csv"), index=False)
        print(f"✅ Extracted {zone_name}")
    except Exception as e:
        print(f"❌ Error Query ID: {query_id} ({zone_name}): {e}")

def pull_all_queries_parallel(query_map, redash_url):
    os.makedirs(os.path.join(script_directory, "Temp"), exist_ok=True)
    with ThreadPoolExecutor(max_workers=len(query_map)) as executor:
        futures = [
            executor.submit(fetch_and_save_query, qid, name, redash_url, get_api_key(), os.path.join(script_directory, "Temp"))
            for qid, name in query_map.items()
        ]
        for future in as_completed(futures):
            pass  # Just wait for all to complete

def fix_multiple_polygon():
    def fix_wkt(wkt: str) -> str:
        if not isinstance(wkt, str):
            return wkt
        
        # Find all polygon parts
        polygons = re.findall(r'POLYGON\s*\(\([^)]+\)\)', wkt)
        
        if len(polygons) > 1:
            # Convert to GEOMETRYCOLLECTION
            return "GEOMETRYCOLLECTION (" + ", ".join(polygons) + ")"
        else:
            # If it's already one polygon or already a GEOMETRYCOLLECTION, return as-is
            return wkt
    
    df = pd.read_csv(os.path.join(script_directory, "Temp/raw_polygon.csv"))
    # Assuming WKT is in the first column (A)
    df.iloc[:, 0] = df.iloc[:, 0].apply(fix_wkt)
    df.to_csv(os.path.join(script_directory, "Temp\clean_polygon.csv"), index=False)
    print("✅ Polygon Fixed")


def Set_up_mathcing():
    df = pd.read_csv(os.path.join(script_directory, "Temp/clean_polygon.csv"))
    df["G"] = df.groupby("matching_hub_id").cumcount() + 1
    df["G"] = df["matching_hub_id"].astype(str) + "n" + df["G"].astype(str)
    df.to_csv(os.path.join(script_directory, "Temp/clean_polygon_with_G.csv"), index=False)
    print("File saved clean_polygon_with_G!")
    
    
    df = pd.read_csv(os.path.join(script_directory, "Temp/Latest_Driver.csv"))
    df["E"] = df.groupby("matching_hub_id").cumcount() + 1
    df["E"] = df["matching_hub_id"].astype(str) + "n" + df["E"].astype(str)
    df.to_csv(os.path.join(script_directory, "Temp/Latest_Driver_with_E.csv"), index=False)
    print("File saved Latest_Driver_with_E!")

def KML_match():
    raw_df = pd.read_csv(os.path.join(script_directory, "Temp/clean_polygon_with_G.csv"))
    driver_df = pd.read_csv(os.path.join(script_directory, "Temp/Latest_Driver_with_E.csv"))
    
    # Merge on G <-> E
    merged = raw_df.merge(
        driver_df[["E", "name", "driver_id", "Driver_name"]],
        left_on="G", right_on="E", how="left"
    )
    
    # --- Fallback: matching_hub_id ---
    fallback_idx = merged["name"].isna()
    
    merged.loc[fallback_idx, "name"] = merged.loc[fallback_idx, "matching_hub_id"].map(dict(zip(driver_df["matching_hub_id"], driver_df["name"])))
    merged.loc[fallback_idx, "driver_id"] = merged.loc[fallback_idx, "matching_hub_id"].map(dict(zip(driver_df["matching_hub_id"], driver_df["driver_id"])))
    merged.loc[fallback_idx, "Driver_name"] = merged.loc[fallback_idx, "matching_hub_id"].map(dict(zip(driver_df["matching_hub_id"], driver_df["Driver_name"])))
    
    # Drop helper columns
    merged.drop(columns=["matching_hub_id", "G", "E"], inplace=True, errors="ignore")
    
    # Reorder
    final_cols = ["WKT", "name", "driver_id", "Driver_name", "zone_name", "hub_name", "description", "Zone"]
    merged = merged[final_cols]
    
    merged.to_csv(os.path.join(script_directory, "Output/2_Update_KML_Driver.csv"), index=False)
    
    print("File saved Update_KML_Driver")

def calculation_1():
    for file_name in os.listdir(os.path.join(script_directory, "Temp")):
        if file_name.lower().endswith('.csv'):
            input_path = os.path.join(os.path.join(script_directory, "Temp"), file_name)
            
            # Read CSV file
            df = pd.read_csv(input_path)

            # Check if "to RG" column exists
            if "to RG" in df.columns:
                print(f"Ready for upload: {file_name} (id_count: {len(df)})")
            else:
                print(f"'to RG' column not found in: {file_name}")

def calculation_2():
    combined_df = pd.concat([pd.read_csv(f) for f in glob.glob(os.path.join(script_directory, "Temp", "*.csv"))], ignore_index=True)
    filtered_df = combined_df[combined_df["AV_Check"] == "Re-AV"]
    filtered_df = filtered_df[["WIP", "latitude", "longitude"]]
    filtered_df.to_csv(os.path.join(script_directory, "Output", "1_Re-Address Verification.csv"), index=False)
    print("✅ Filtered CSV created successfully")
    
class ApiClient:
    def __init__(self):
        self.token = get_token_key()
        self.headers = build_opv2_headers(self.token)

    def refresh_token(self):
        if os.path.exists(TOKEN_KEY_FILE):
            os.remove(TOKEN_KEY_FILE)

        self.token = get_token_key()
        self.headers = build_opv2_headers(self.token)

    def get(self, url):
        response = requests.get(url, headers=self.headers)

        if response.status_code in (401, 403):
            print("Token expired or invalid. Requesting new token...")
            self.refresh_token()
            response = requests.get(url, headers=self.headers)

        return response

    def post(self, url, payload):
        response = requests.post(url, headers=self.headers, json=payload)

        if response.status_code in (401, 403):
            print("Token expired or invalid. Requesting new token...")
            self.refresh_token()
            response = requests.post(url, headers=self.headers, json=payload)

        return response

def read_transaction_ids(csv_path):
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, "r", newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        if not reader.fieldnames:
            raise ValueError(f"{os.path.basename(csv_path)} has no header row.")

        id_column = "to RG" if "to RG" in reader.fieldnames else reader.fieldnames[0]

        ids = []
        for row in reader:
            raw_id = str(row[id_column]).strip()
            if raw_id:
                ids.append(int(raw_id))

    if not ids:
        raise ValueError(f"No IDs found in {os.path.basename(csv_path)}.")

    return ids

def save_json(data, output_path):
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

def save_csv(rows, output_path):
    if not rows:
        return

    fieldnames = sorted({key for row in rows for key in row.keys()})
    with open(output_path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def safe_name(name):
    return name.replace(" ", "_").replace("/", "_")

def fail_response(label, response):
    print(f"{label} failed")
    print("Status Code:", response.status_code)
    print(response.text)

def load_route_groups(client):
    response = client.get(ROUTE_GROUPS_URL)
    if response.status_code != 200:
        fail_response("Route group lookup", response)
        return {}

    data = response.json()
    route_groups = data.get("data", {}).get("routeGroups", [])
    return {route_group.get("id"): route_group for route_group in route_groups}

def find_transactions(client, job, transaction_ids):
    zone_name = safe_name(job["route_group_name"])
    output_json = os.path.join(TEMP_DIRECTORY, f"multi_{zone_name}_action1_transactions_response.json")
    output_csv = os.path.join(TEMP_DIRECTORY, f"multi_{zone_name}_action1_transactions_response.csv")

    response = client.post(FIND_TRANSACTIONS_URL, {"ids": transaction_ids})
    if response.status_code != 200:
        fail_response(f"Action 1 for {job['route_group_name']}", response)
        return None

    transactions = response.json()
    save_json(transactions, output_json)
    save_csv(transactions, output_csv)
    return transactions

def add_to_route_group(client, job, transaction_ids):
    route_group_id = job["route_group_id"]
    zone_name = safe_name(job["route_group_name"])
    output_json = os.path.join(TEMP_DIRECTORY, f"multi_{zone_name}_action2_add_route_group_response.json")
    url = f"https://walrus.ninjavan.co/my/route/1.0/route-groups/{route_group_id}/references?append=true"
    payload = {
        "pickupAppointmentJobIds": [],
        "pudoPickupAppointmentJobIds": [],
        "reservationIds": [],
        "transactionIds": transaction_ids,
    }

    response = client.post(url, payload)
    if response.status_code != 200:
        fail_response(f"Action 2 for {job['route_group_name']}", response)
        return None

    result = response.json()
    save_json(result, output_json)
    return result

def process_upload_job(client, route_groups_by_id, job):
    csv_path = os.path.join(TEMP_DIRECTORY, job["csv_file"])
    transaction_ids = read_transaction_ids(csv_path)
    route_group = route_groups_by_id.get(job["route_group_id"])

    print("======================================================================")
    print(f"{job['route_group_name']} -> Route Group {job['route_group_id']}")
    print("======================================================================")
    print(f"CSV file: {csv_path}")
    print(f"IDs found in CSV: {len(transaction_ids)}")

    if route_group is None:
        print(f"Route group {job['route_group_id']} was not found. Skipping.")
        return False

    print(f"Route group found: {route_group.get('id')} - {route_group.get('name')}")

    transactions = find_transactions(client, job, transaction_ids)
    if transactions is None:
        return False

    print(f"Transactions returned from Action 1: {len(transactions)}")

    result = add_to_route_group(client, job, transaction_ids)
    if result is None:
        return False

    route_group_response = result.get("data", {}).get("routeGroup", {})
    added_ids = route_group_response.get("transactionIds", [])
    print(f"Action 2 success: {route_group_response.get('id')} - {route_group_response.get('name')}")
    print(f"Transaction IDs now in response: {len(added_ids)}")
    print("")
    return True

def multi_upload_route_groups():
    os.makedirs(TEMP_DIRECTORY, exist_ok=True)
    client = ApiClient()
    route_groups_by_id = load_route_groups(client)

    success_count = 0
    failed_jobs = []

    for job in UPLOAD_JOBS:
        try:
            if process_upload_job(client, route_groups_by_id, job):
                success_count += 1
            else:
                failed_jobs.append(job["route_group_name"])
        except Exception as error:
            failed_jobs.append(job["route_group_name"])
            print(f"{job['route_group_name']} failed with error:")
            print(error)
            print("")

    print("======================================================================")
    print("Multi Upload Completed")
    print("======================================================================")
    print(f"Successful jobs: {success_count} of {len(UPLOAD_JOBS)}")
    if failed_jobs:
        print("Failed jobs:")
        for job_name in failed_jobs:
            print(f"- {job_name}")

def open_work_environment():

    # URLs to open
    urls = [
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",
        "https://operatorv2.ninjavan.co/react/#/my/zonal-routing",

    ]

    # Chrome path
    chrome_exe = "C:/Program Files/Google/Chrome/Application/chrome.exe"

    # Open URLs in order
    if os.path.exists(chrome_exe):
        subprocess.Popen([chrome_exe, "--new-window", urls[0]])
        time.sleep(1)
        for url in urls[1:]:
            subprocess.Popen([chrome_exe, "--new-tab", url])
            time.sleep(1)
    else:
        for url in urls:
            webbrowser.open_new_tab(url)
            time.sleep(1)

    # Files / folders to open
    paths_to_open = [os.path.join(script_directory, "Output/manual_av_shipper_address.csv")]

    # Open if exists, otherwise skip
    for path in paths_to_open:
        if os.path.exists(path):
            os.startfile(path)

def main():
    print("======================================================================")
    print("========================  Rounting KV  ===============================")
    print("======================================================================")        


    credential_check()
    print(" ")
    remove_files_in_folder([os.path.join(script_directory, "Output"),os.path.join(script_directory, "Temp")])
    print("File Cleaned!")
    print(" ")
    print("Query Start...")
    query_normal(1074,os.path.join(script_directory, "Temp/raw_polygon.csv"))
    query_normal(1075,os.path.join(script_directory, "Temp/Latest_Driver.csv"))
    fix_multiple_polygon()
    Set_up_mathcing()
    KML_match()
    print("Driver list ready!")
    print("Running next query...")
    pull_all_queries_parallel({1353: 'Zone B',1354: 'Zone C',1355: 'Zone D',1356: 'Zone E',
                               1357: 'Zone F',1358: 'Zone G',1359: 'Zone H',1360: 'Zone I',1361: 'Zone J'}, redash_url='https://redash-my.ninjavan.co/')
    print("Query Successfull!")
    print(" ")
    print("Calculation start...")
    calculation_1()
    calculation_2()
    print("Uploading route groups...")
    multi_upload_route_groups()




    print("======================================================================")
    print("========================  Generate Report  ===========================")
    print("======================================================================")        
            


    query_normal_date(1348,os.path.join(script_directory, "Output/3_route_record_RPU.csv"))
    query_normal_date(567,os.path.join(script_directory, "Output/3_route_record_RTS.csv"))
    query_normal_date(338,os.path.join(script_directory, "Output/3_route_record_Velocity.csv"))
    print("")

    print("======================================================================")
    print("========================  Report Completed  ===========================")
    print("======================================================================") 
    remove_files_in_folder([os.path.join(script_directory, "Temp")])
    open_work_environment()
    print("Process Completed")
    input("Press enter to continue...")


if __name__ == "__main__":
    main()

    
    
    
    
