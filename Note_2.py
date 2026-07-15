import pandas as pd
import os
import requests
import time
import json
import sys
from datetime import datetime, timedelta
import re
import subprocess
import webbrowser

def resolve_path(path):
    # froz path location
    if getattr(sys, "frozen", False):
        resolved_path = os.path.abspath(os.path.join(sys._MEIPASS, path))
    else:
        resolved_path = os.path.abspath(os.path.join(os.getcwd(), path))
    return resolved_path

script_directory = os.path.dirname(resolve_path(__file__))
API_KEY_FILE = os.path.join(script_directory,"api_key.cfg")
SECONDS_IN_A_WEEK = 7 * 24 * 60 * 60  # 7 days, 24 hours, 60 minutes, 60 seconds

def remove_files_in_folder(folder_paths):
    for folder_path in folder_paths:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

def pull_data(cleanup_start=True):
    def is_file_older_than_a_week(file_path):
        file_creation_time = os.path.getmtime(file_path)
        current_time = time.time()
        return current_time - file_creation_time > SECONDS_IN_A_WEEK

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

    def query_with_parameter_date(query_id, output_csv_path):
        api_key = get_api_key()

        print("Running Query...")

        # AUTO DATE
        today = datetime.today()
        yesterday = today - timedelta(days=1)

        date_from = yesterday.strftime('%Y-%m-%d')
        date_to = today.strftime('%Y-%m-%d')

        parameters = {"Date from": date_from,
                      "Date to": date_to}

        try:
            s = requests.Session()
            s.headers.update({'Authorization': f'Key {api_key}'})

            payload = {"max_age": 0,
                       "parameters": parameters}

            # Run query
            response = s.post(f'https://redash-my.ninjavan.co/api/queries/{query_id}/results',
                              data=json.dumps(payload),
                              headers={'Content-Type': 'application/json'})

            if response.status_code != 200:
                print(response.text)
                raise Exception('Refresh failed.')

            # Poll job until completed
            result_id = poll_job(s,'https://redash-my.ninjavan.co',response.json()['job'])

            if not result_id:
                raise Exception('Query execution failed.')

            # Download result
            response = s.get(f'https://redash-my.ninjavan.co/api/queries/{query_id}/results/{result_id}.json')

            if response.status_code != 200:
                raise Exception('Failed getting results.')

            result = response.json()['query_result']['data']['rows']

            print(f"Total number of data: {len(result)}\n")

            if not result:
                print("No data returned. File will not be downloaded.")
                return

            df = pd.DataFrame(result)
            df.to_csv(output_csv_path, index=False)

            print("File downloaded successfully.")

        except Exception as e:
            print(f"An error occurred: {e}")
            
           

            
    if cleanup_start:
        print("Cleaning File...")
        remove_files_in_folder([os.path.join(script_directory, "Temp"),os.path.join(script_directory, "Output")])
        print("File Cleaned!")
    else:
        print("Skipping start cleanup.")
    print("")
    print("Fetching data")        
    query_with_parameter_date(582,os.path.join(script_directory, "Temp/0_raw_pso.csv"))
    query_with_parameter_date(1234,os.path.join(script_directory, "Temp/0_raw_grn.csv"))
    query_with_parameter_date(1506,os.path.join(script_directory, "Temp/0_raw_rdo.csv"))
    print("Done!")
    print("")

def grn_creation(input_file,output_file):  
    df = pd.read_csv(input_file, dtype=str)
    df = df.fillna("")
    
    # =========================
    # Helper Function
    # =========================
    def clean_tracking(value):
        if pd.isna(value) or value == "":
            return ""
    
        value = str(value)
    
        # Remove PO Number (case insensitive)
        value = re.sub(r'po\s*number', '', value, flags=re.IGNORECASE)
    
        # Remove standalone PO
        value = re.sub(r'\bpo\b', '', value, flags=re.IGNORECASE)
    
        # Keep only letters and numbers
        value = re.sub(r'[^A-Za-z0-9]', '', value)
    
        return value + "GRN1"
    
    
    today = datetime.today().strftime("%Y-%m-%d")
    
    # =========================
    # Create Output DataFrame
    # =========================
    output = pd.DataFrame(index=df.index)
    
    output["global_shipper_id"] = "10643708"
    output["service_type"] = "RETURN"
    output["service_level"] = "STANDARD"
    
    output["reference.merchant_order_number"] = df["tracking_id"]
    
    output["from.name"] = df["delivery_name"]
    output["from.email"] = ""
    output["from.phone_number"] = "60123456789"
    
    output["from.address.address1"] = df["delivery_address1"]
    output["from.address.address2"] = df["delivery_address2"]
    output["from.address.country"] = "MY"
    output["from.address.area"] = ""
    output["from.address.city"] = df["delivery_city"]
    output["from.address.state"] = df["delivery_state"]
    output["from.address.postcode"] = df["delivery_postcode"]
    
    output["to.name"] = "B2B Ops"
    output["to.email"] = "my-b2b-support@ninjavan.co"
    output["to.phone_number"] = ""
    
    output["to.address.address1"] = "1, Persiaran Jubli Perak"
    output["to.address.address2"] = ""
    output["to.address.country"] = "MY"
    output["to.address.area"] = "Seksyen 22"
    output["to.address.city"] = "Shah Alam"
    output["to.address.state"] = "Selangor"
    output["to.address.postcode"] = "40300"
    
    output["parcel_job.delivery_start_date"] = today
    output["parcel_job.delivery_timeslot.start_time"] = "09:00"
    output["parcel_job.delivery_timeslot.end_time"] = "22:00"
    output["parcel_job.delivery_timeslot.timezone"] = "Asia/Kuala_Lumpur"
    
    output["parcel_job.delivery_instructions"] = ("Please collect GRN with PO number : " + df["shipper_reference"].astype(str))
    
    output["parcel_job.dimensions.weight"] = "1"
    output["parcel_job.is_pickup_required"] = "True"
    
    output["parcel_job.items.0.item_description"] = "GRN"
    output["parcel_job.items.0.quantity"] = "1"
    output["parcel_job.items.0.is_dangerous_good"] = "False"
    
    output["parcel_job.items.1.item_description"] = "-"
    output["parcel_job.items.1.quantity"] = "-"
    output["parcel_job.items.1.is_dangerous_good"] = "False"
    
    output["parcel_job.pickup_date"] = today
    output["parcel_job.pickup_timeslot.start_time"] = "09:00"
    output["parcel_job.pickup_timeslot.end_time"] = "22:00"
    output["parcel_job.pickup_timeslot.timezone"] = "Asia/Kuala_Lumpur"
    
    output["parcel_job.pickup_instructions"] = ""
    output["parcel_job.pickup_address_id"] = ""
    
    output["parcel_job.pickup_service_type"] = "SCHEDULED"
    output["parcel_job.pickup_service_level"] = "STANDARD"
    output["parcel_job.pickup_approximate_volume"] = "Less than 10 Parcels"
    
    output["parcel_job.pickup_address.name"] = df["delivery_name"]
    output["parcel_job.pickup_address.email"] = ""
    output["parcel_job.pickup_address.phone_number"] = "60123456789"
    
    output["parcel_job.pickup_address.address.address1"] = df["delivery_address1"]
    output["parcel_job.pickup_address.address.address2"] = df["delivery_address2"]
    output["parcel_job.pickup_address.address.country"] = "MY"
    output["parcel_job.pickup_address.address.area"] = ""
    output["parcel_job.pickup_address.address.city"] = df["delivery_city"]
    output["parcel_job.pickup_address.address.state"] = df["delivery_state"]
    output["parcel_job.pickup_address.address.postcode"] = df["delivery_postcode"]
    
    output["requested_tracking_number"] = (
        df["shipper_reference"]
        .apply(clean_tracking)
    )
    
    # =========================
    # Export CSV
    # =========================
    
    output.to_csv(output_file, index=False)

def pso_creation(input_file,output_file):
    df = pd.read_csv(input_file, dtype=str)
    df = df.fillna("")
    
    # =========================
    # Helper Function
    # =========================
    def convert_tracking(value):
        if pd.isna(value) or value == "":
            return ""
    
        value = str(value)
    
        # Skip the first 5 characters
        value = value[5:]
    
        return value + "-MYPSO"
    
    
    today = datetime.today().strftime("%Y-%m-%d")
    
    # =========================
    # Create Output DataFrame
    # =========================
    output = pd.DataFrame(index=df.index)
    
    output["global_shipper_id"] = "8903138"
    output["service_type"] = "RETURN"
    output["service_level"] = "STANDARD"
    
    output["reference.merchant_order_number"] = df["tracking_id"]
    
    output["from.name"] = df["delivery_name"]
    output["from.email"] = ""
    output["from.phone_number"] = "60123456789"
    
    output["from.address.address1"] = df["delivery_address1"]
    output["from.address.address2"] = df["delivery_address2"]
    output["from.address.country"] = "MY"
    output["from.address.area"] = ""
    output["from.address.city"] = df["delivery_city"]
    output["from.address.state"] = df["delivery_state"]
    output["from.address.postcode"] = df["delivery_postcode"]
    
    output["to.name"] = ("B2B Ops " + df["shipper_id"].astype(str))
    output["to.email"] = "nvmyreturndo@gmail.com"
    output["to.phone_number"] = ""
    
    output["to.address.address1"] = "1, Persiaran Jubli Perak"
    output["to.address.address2"] = ""
    output["to.address.country"] = "MY"
    output["to.address.area"] = "Seksyen 22"
    output["to.address.city"] = "Shah Alam"
    output["to.address.state"] = "Selangor"
    output["to.address.postcode"] = "40300"
    
    output["parcel_job.delivery_start_date"] = today
    output["parcel_job.delivery_timeslot.start_time"] = "09:00"
    output["parcel_job.delivery_timeslot.end_time"] = "22:00"
    output["parcel_job.delivery_timeslot.timezone"] = "Asia/Kuala_Lumpur"
    
    output["parcel_job.delivery_instructions"] = "Pickup PSO with RDO"
    
    output["parcel_job.dimensions.weight"] = "0.2"
    output["parcel_job.is_pickup_required"] = "True"
    
    output["parcel_job.items.0.item_description"] = "Pickup PSO with RDO"
    output["parcel_job.items.0.quantity"] = "1"
    output["parcel_job.items.0.is_dangerous_good"] = "False"
    
    output["parcel_job.items.1.item_description"] = "Pickup PSO with RDO"
    output["parcel_job.items.1.quantity"] = "Pickup PSO with RDO"
    output["parcel_job.items.1.is_dangerous_good"] = "False"
    
    output["parcel_job.pickup_date"] = today
    output["parcel_job.pickup_timeslot.start_time"] = "09:00"
    output["parcel_job.pickup_timeslot.end_time"] = "22:00"
    output["parcel_job.pickup_timeslot.timezone"] = "Asia/Kuala_Lumpur"
    
    output["parcel_job.pickup_instructions"] = "Pickup PSO with RDO"
    output["parcel_job.pickup_address_id"] = ""
    
    output["parcel_job.pickup_service_type"] = "SCHEDULED"
    output["parcel_job.pickup_service_level"] = "STANDARD"
    output["parcel_job.pickup_approximate_volume"] = "Less than 3 Parcels"
    
    output["parcel_job.pickup_address.name"] = df["delivery_name"]
    output["parcel_job.pickup_address.email"] = ""
    output["parcel_job.pickup_address.phone_number"] = "60123456789"
    
    output["parcel_job.pickup_address.address.address1"] = df["delivery_address1"]
    output["parcel_job.pickup_address.address.address2"] = df["delivery_address2"]
    output["parcel_job.pickup_address.address.country"] = "MY"
    output["parcel_job.pickup_address.address.area"] = ""
    output["parcel_job.pickup_address.address.city"] = df["delivery_city"]
    output["parcel_job.pickup_address.address.state"] = df["delivery_state"]
    output["parcel_job.pickup_address.address.postcode"] = df["delivery_postcode"]
    
    output["requested_tracking_number"] = (df["mother_tracking"].apply(convert_tracking))
    
    # =========================
    # Export CSV
    # =========================
    
    output.to_csv(output_file, index=False)
    
def rdo_creation(input_file,output_file):
    df = pd.read_csv(input_file, dtype=str)
    df = df.fillna("")
    
    today = datetime.today().strftime("%Y-%m-%d")
    
    # =========================
    # Create Output DataFrame
    # =========================
    output = pd.DataFrame(index=df.index)
    
    output["global_shipper_id"] = "10422486"
    output["service_type"] = "RDO RETURN"
    output["service_level"] = "STANDARD"
    
    output["reference.merchant_order_number"] = df["tracking_id"]
    output["from.name"] = df["delivery_name"]
    output["from.email"] = ""
    output["from.phone_number"] = "60123456789"
    
    output["from.address.address1"] = df["delivery_address1"]
    output["from.address.address2"] = df["delivery_address2"]
    output["from.address.country"] = "MY"
    output["from.address.area"] = ""
    output["from.address.city"] = df["delivery_city"]
    output["from.address.state"] = df["delivery_state"]
    output["from.address.postcode"] = df["delivery_postcode"]
    
    output["to.name"] = ("B2B Ops " + df["shipper_id"].astype(str))
    output["to.email"] = "nvmyreturndo@gmail.com"
    output["to.phone_number"] = ""
    
    output["to.address.address1"] = "1, Persiaran Jubli Perak"
    output["to.address.address2"] = ""
    output["to.address.country"] = "MY"
    output["to.address.area"] = "Seksyen 22"
    output["to.address.city"] = "Shah Alam"
    output["to.address.state"] = "Selangor"
    output["to.address.postcode"] = "40300"
    
    output["parcel_job.delivery_start_date"] = today
    output["parcel_job.delivery_timeslot.start_time"] = "09:00"
    output["parcel_job.delivery_timeslot.end_time"] = "22:00"
    output["parcel_job.delivery_timeslot.timezone"] = "Asia/Kuala_Lumpur"
    
    output["parcel_job.delivery_instructions"] = "Restock RDO"
    
    output["parcel_job.dimensions.weight"] = "0.2"
    output["parcel_job.is_pickup_required"] = "True"
    
    output["parcel_job.items.0.item_description"] = "Restock RDO"
    output["parcel_job.items.0.quantity"] = "1"
    output["parcel_job.items.0.is_dangerous_good"] = "False"
    
    output["parcel_job.items.1.item_description"] = "Restock RDO"
    output["parcel_job.items.1.quantity"] = "Restock RDO"
    output["parcel_job.items.1.is_dangerous_good"] = "False"
    
    output["parcel_job.pickup_date"] = today
    output["parcel_job.pickup_timeslot.start_time"] = "09:00"
    output["parcel_job.pickup_timeslot.end_time"] = "22:00"
    output["parcel_job.pickup_timeslot.timezone"] = "Asia/Kuala_Lumpur"
    
    output["parcel_job.pickup_instructions"] = "RDO Pickup"
    output["parcel_job.pickup_address_id"] = ""
    
    output["parcel_job.pickup_service_type"] = "SCHEDULED"
    output["parcel_job.pickup_service_level"] = "STANDARD"
    output["parcel_job.pickup_approximate_volume"] = "Less than 3 Parcels"
    
    output["parcel_job.pickup_address.name"] = df["delivery_name"]
    output["parcel_job.pickup_address.email"] = ""
    output["parcel_job.pickup_address.phone_number"] = "60123456789"
    
    output["parcel_job.pickup_address.address.address1"] = df["delivery_address1"]
    output["parcel_job.pickup_address.address.address2"] = df["delivery_address2"]
    output["parcel_job.pickup_address.address.country"] = "MY"
    output["parcel_job.pickup_address.address.area"] = ""
    output["parcel_job.pickup_address.address.city"] = df["delivery_city"]
    output["parcel_job.pickup_address.address.state"] = df["delivery_state"]
    output["parcel_job.pickup_address.address.postcode"] = df["delivery_postcode"]
    
    output["requested_tracking_number"] = df["mother_tracking"]
    output["master_tracking_number"] = df["mother_tracking"]
    
    # =========================
    # Export CSV
    # =========================
    
    output.to_csv(output_file, index=False)

def open_work_environment():

    # URLs to open
    urls = ["https://operatorv2.ninjavan.co/react/#/my/order-create-v4",
            "https://operatorv2.ninjavan.co/react/#/my/failed-pickup-management",
            "https://operatorv2.ninjavan.co/react/#/my/route-logs",
            "https://operatorv2.ninjavan.co/react/#/my/bulk-address-verification"]

    # Chrome path
    chrome_exe = "C:/Program Files/Google/Chrome/Application/chrome.exe"

    # Open URLs in order using the same approach as Note_5
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



def main(cleanup_start=True, cleanup_end=True, open_environment=True, wait_for_enter=True):
    
    print("======================================================================")
    print("==================== Part 0 : Data Preparation  =====================")
    print("======================================================================")
    
    pull_data(cleanup_start=cleanup_start)
    
    
    print("======================================================================")
    print("================== Part 1 : Execute Core Task  =====================")
    print("======================================================================")
    
    print("")
    print("Running Order Creation for PSO, RDO, & GRN.")
    try:
        grn_creation(os.path.join(script_directory, "Temp/0_raw_grn.csv"),
                     os.path.join(script_directory, "Output/1_oc_grn.csv"))
        print("GRN done")
    except Exception as e:
        print(f"GRN Failed: {e}")
    
    try:
        pso_creation(os.path.join(script_directory, "Temp/0_raw_pso.csv"),
                     os.path.join(script_directory, "Output/1_oc_pso.csv"))
        print("PSO done")
    except Exception as e:
        print(f"GRN Failed: {e}")
    
    try:
        rdo_creation(os.path.join(script_directory, "Temp/0_raw_rdo.csv"),
                     os.path.join(script_directory, "Output/1_oc_rdo.csv"))
        print("RDO done")
    except Exception as e:
        print(f"GRN Failed: {e}")
    
    print("Process completed!")
    print("")
    
    print("======================================================================")
    print("================== Part 3 : Compiling data  =========================")
    print("======================================================================")
    print("")
    if cleanup_end:
        remove_files_in_folder([os.path.join(script_directory, "Temp")])
    else:
        print("Skipping end cleanup.")
    print("Exceuting workig environtment")
    if open_environment:
        open_work_environment()
    if wait_for_enter:
        input("Press enter to continue..")
    
if __name__ == "__main__":
    main()
