import pandas as pd
import os
import requests
import time
import json
import sys
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




                                # ==============================================
                                # ========== function for General Use ==========   
                                # ==============================================



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



                                # ======================================
                                # ========== function for Tag ==========        
                                # ======================================



def query_with_parameter(csv_path, query_id, column_name, output_csv_path):

    api_key = get_api_key()
    print("Running Query with Parameters...")

    # Read CSV and extract parameter values
    df_input = pd.read_csv(csv_path)

    values = (
        df_input[column_name]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )

    parameter_string = ",".join([f"'{x}'" for x in values])

    parameters = {column_name: parameter_string}

    s = requests.Session()
    s.headers.update({
        'Authorization': f'Key {api_key}',
        'Content-Type': 'application/json'
    })

    payload = {
        "parameters": parameters,
        "max_age": 0
    }

    response = s.post(f'https://redash-my.ninjavan.co/api/queries/{query_id}/results', json=payload)

    if response.status_code != 200:
        print("Status Code:", response.status_code)
        print("Response:", response.text)
        raise Exception("Query failed")

    result_id = poll_job(s, 'https://redash-my.ninjavan.co', response.json()['job'])

    if result_id:

        response = s.get(f'https://redash-my.ninjavan.co/api/queries/{query_id}/results/{result_id}.json')
        result = response.json()['query_result']['data']['rows']
        df = pd.DataFrame(result)

        print(f"Total number of data: {len(df)}")

        df.to_csv(output_csv_path, index=False)
       
def open_work_environment():

    # URLs to open
    urls = [
        "https://operatorv2.ninjavan.co/react/#/my/order-tag-management",
        "https://operatorv2.ninjavan.co/react/#/my/order-tag-management",
        "https://operatorv2.ninjavan.co/react/#/my/order-tag-management",
        "https://drive.google.com/drive/folders/1LCZvi843dEEiF0sHBc6_7hEE5HtJb7HE"
        
    ]

    # Chrome path
    chrome_exe = "C:/Program Files/Google/Chrome/Application/chrome.exe"

    # Open URLs in order using the standardized approach
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



                                # =================================================
                                # ========== function for Ticket On hold ========== 
                                # =================================================



def filter_column(input_path, column_name, output_folder):
    
    # Read main file
    df = pd.read_csv(input_path)

    # Check column exists
    if column_name not in df.columns:
        print(f"Column '{column_name}' not found.")
        return

    # Create output folder if not exist
    os.makedirs(output_folder, exist_ok=True)

    # Get unique values
    unique_values = df[column_name].dropna().unique()

    for value in unique_values:
        # Filter rows
        filtered_df = df[df[column_name] == value]

        # Clean filename (remove invalid characters)
        safe_value = str(value).replace("/", "_").replace("\\", "_").replace(" ", "_")

        output_file = os.path.join(output_folder, f"2_{safe_value}.csv")

        filtered_df.to_csv(output_file, index=False)

        print(f"Created: {safe_value}.csv")

    print("Splitting completed.")

def sample_by_ratio(input_file,output_file,group_column,target_ratios,total_limit=100,random_state=1):

    try:

        # Read CSV
        df = pd.read_csv(input_file)

        # If total rows already lower/equal than limit
        if len(df) <= total_limit:
            df.to_csv(output_file, index=False)
            print(f"Total rows <= {total_limit}. Saved all rows.")
            return df

        selected_parts = []
        extra_groups = {}
        remaining_needed = total_limit

        # FIRST PASS
        # Prioritize target ratio
        for group_value, ratio in target_ratios.items():

            target_count = round(total_limit * ratio)

            group_df = df[df[group_column] == group_value]

            available = len(group_df)

            take_count = min(target_count, available)

            # Sample rows
            sampled = group_df.sample(
                n=take_count,
                random_state=random_state
            )

            selected_parts.append(sampled)

            remaining_needed -= take_count

            # Save leftover rows
            leftover = group_df.drop(sampled.index)

            if len(leftover) > 0:
                extra_groups[group_value] = leftover

            print(
                f"{group_value} | "
                f"Target: {target_count} | "
                f"Available: {available} | "
                f"Taken: {take_count}"
            )

        # SECOND PASS
        # Fill balance from remaining groups
        if remaining_needed > 0 and len(extra_groups) > 0:

            extra_pool = pd.concat(
                extra_groups.values(),
                ignore_index=False
            )

            if len(extra_pool) > remaining_needed:
                extra_pool = extra_pool.sample(
                    n=remaining_needed,
                    random_state=random_state
                )

            selected_parts.append(extra_pool)

            print(f"Added extra balance rows: {len(extra_pool)}")

        # Combine all selected rows
        final_df = pd.concat(
            selected_parts,
            ignore_index=True
        )

        # Save
        final_df.to_csv(output_file, index=False)

        print(f"\nFinal row count: {len(final_df)}")
        print(f"Saved to: {output_file}")

        return final_df

    except FileNotFoundError:
        print(f"Skipped. File not found: {input_file}")
        return None

def take_top_rows(input_file,output_file,total_rows=100):

    try:

        # Read CSV
        df = pd.read_csv(input_file)

        # Sort ascending by reference_check
        df = df.sort_values(
            by="reference_check",
            ascending=True
        )

        # Take top rows
        sampled_df = df.head(total_rows)

        # Save output
        sampled_df.to_csv(output_file, index=False)

        print(f"Saved {len(sampled_df)} rows to: {output_file}")

        return sampled_df

    except FileNotFoundError:
        print(f"Skipped. File not found: {input_file}")
        return None

def create_ticket_csv(
    input_file,
    output_file,
    tracking_column,
    type_value,
    sub_type_value,
    investigating_group_value,
    assignee_email_value,
    investigating_hub_id_value,
    entry_source_value="",
    ticket_notes_value=""
):

    try:

        # Read CSV
        df = pd.read_csv(input_file)

        # Create output dataframe
        output_df = pd.DataFrame({
            "tracking_id": df[tracking_column],
            "type": type_value,
            "sub_type": sub_type_value,
            "investigating_group": investigating_group_value,
            "assignee_email": assignee_email_value,
            "investigating_hub_id": investigating_hub_id_value,
            "entry_source": entry_source_value,
            "ticket_notes": ticket_notes_value
        })

        # Save output
        output_df.to_csv(output_file, index=False)

        print(f"Ticket CSV created: {output_file}")

        return output_df

    except FileNotFoundError:
        print(f"Skipped. File not found: {input_file}")
        return None

def combine_csv_files(files, folder_path, output_path):
    dfs = []

    for file in files:
        file_path = os.path.join(folder_path, file)

        # Check exist + not empty
        if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            try:
                df = pd.read_csv(file_path)
                dfs.append(df)
            except pd.errors.EmptyDataError:
                print(f"{file} is empty. Skipping...")
        else:
            print(f"{file} does not exist or is empty. Skipping...")

    # Combine if valid dataframe exist
    if dfs:
        combined_df = pd.concat(dfs, ignore_index=True)
        combined_df.to_csv(output_path, index=False)

        print("CSV files combined successfully!")
        return combined_df   # optional (can reuse later)

    else:
        print("No valid CSV files to combine.")
        return None


                                # ======================================
                                # ========== Main Function =============        
                                # ======================================



def main_tagging_process():

    print("Fetching data...")
    query_normal(710,os.path.join(script_directory, "Temp/0_tag_raw_1.csv"))
    
    df = pd.read_csv(os.path.join(script_directory, "Temp/0_tag_raw_1.csv"))
    filtered_df1 = df[df['tag_type'] == 'Prior']
    filtered_df2 = df[df['tag_type'] == 'RTS']
    selected_columns = ['tracking_id',	'tag_type',	'Tagging_for']
    final_df1 = filtered_df1[selected_columns]
    final_df2 = filtered_df2[selected_columns]
    final_df1.to_csv(os.path.join(script_directory, "Output/tag_prio.csv"), index=False)
    final_df2.to_csv(os.path.join(script_directory, "Output/tag_RTS.csv"), index=False)
    print("Data pull raw tag done")
    
    query_normal(679,os.path.join(script_directory, "Temp/0_restock_list.csv"))
    query_with_parameter(os.path.join(script_directory, "Temp/0_restock_list.csv"),
                         1266,
                         "global_shipper_id",
                         os.path.join(script_directory, "Output/tag_restock.csv"))
    
    print("Data pull raw tag done")
    print("") 

def main_ticket_on_hold_process():
    print("Fetching data...")
    
    query_normal(695,os.path.join(script_directory, "Temp/0_raw_1.csv"))
    query_normal(616,os.path.join(script_directory, "Temp/0_raw_2.csv"))
    query_normal(1428,os.path.join(script_directory, "Temp/0_raw_3.csv"))
    
    
    combine_csv_files(["0_raw_1.csv", "0_raw_2.csv", "0_raw_3.csv"],
                      os.path.join(script_directory, "Temp"),
                      os.path.join(script_directory, "Temp/1_combined_pet.csv"))
    
    print("")
    print("Creating Pull out file")
    
    df = pd.read_csv(os.path.join(script_directory, "Temp/1_combined_pet.csv"))
    filtered_df = df[df['route_check'] == 'Pull out']
    select_column = ['tracking_id']
    filter_df = filtered_df[select_column]
    filter_df.to_csv(os.path.join(script_directory, "Output/Pull_out.csv"), index=False)
    
    print("Pull out file created")
    print("")
    
    print("File catgorization...")
    
    filter_column(os.path.join(script_directory, "Temp/1_combined_pet.csv"),
                        "Validation",
                        os.path.join(script_directory, "Temp"))
    
    
    print("")
    print("Calculation for ration sapartion...")
    
    sample_by_ratio(os.path.join(script_directory, "Temp/2_FS.csv"),
                    os.path.join(script_directory, "Temp/3_FS.csv"),
                    group_column="reference_check",
                    target_ratios={
                        4610784: 0.4,
                        5554395: 0.4,
                        6716867: 0.2
                        },
                    total_limit=100)
    
    take_top_rows(os.path.join(script_directory, "Temp/2_Shien.csv"),
                  os.path.join(script_directory, "Temp/3_Shien.csv"),
                  total_rows=100)
    
    
    take_top_rows(os.path.join(script_directory, "Temp/2_Tiktok_Intergration.csv"),
                  os.path.join(script_directory, "Temp/3_Tiktok_Intergration.csv"),
                  total_rows=500)
    
    
    take_top_rows(os.path.join(script_directory, "Temp/2_VN-SM.csv"),
                     os.path.join(script_directory, "Temp/3_VN-SM.csv"),
                     total_rows=500)
    
    take_top_rows(os.path.join(script_directory, "Temp/2_Tiktok_Local.csv"),
                  os.path.join(script_directory, "Temp/3_Tiktok_Local.csv"),
                  total_rows=500)
    
    
    
    create_ticket_csv(os.path.join(script_directory, "Temp/3_FS.csv"),
                      os.path.join(script_directory, "Temp/4_FS.csv"),
                      tracking_column="tracking_id",
                      type_value="PH",
                      sub_type_value="SQ",
                      investigating_group_value="RCY",
                      assignee_email_value="fariz.maswan@ninjavan.co",
                      investigating_hub_id_value=60)
    
    create_ticket_csv(os.path.join(script_directory, "Temp/3_Shien.csv"),
                      os.path.join(script_directory, "Temp/4_Shien.csv"),
                      tracking_column="tracking_id",
                      type_value="PH",
                      sub_type_value="SQ",
                      investigating_group_value="RCY",
                      assignee_email_value="thai.an@ninjavan.co",
                      investigating_hub_id_value=60)
    
    
    create_ticket_csv(os.path.join(script_directory, "Temp/3_Tiktok_Intergration.csv"),
                      os.path.join(script_directory, "Temp/4_Tiktok_Intergration.csv"),
                      tracking_column="tracking_id",
                      type_value="PH",
                      sub_type_value="SQ",
                      investigating_group_value="RCY",
                      assignee_email_value="oong.seakyee@ninjavan.co",
                      investigating_hub_id_value=60)
    
    create_ticket_csv(os.path.join(script_directory, "Temp/3_VN.csv"),
                      os.path.join(script_directory, "Temp/4_VN.csv"),
                      tracking_column="tracking_id",
                      type_value="PH",
                      sub_type_value="SQ",
                      investigating_group_value="RCY",
                      assignee_email_value="ariff.sulaiman@ninjavan.co",
                      investigating_hub_id_value=60)
    
    create_ticket_csv(os.path.join(script_directory, "Temp/3_Tiktok_Local.csv"),
                      os.path.join(script_directory, "Temp/4_Tiktok_Local.csv"),
                      tracking_column="tracking_id",
                      type_value="PH",
                      sub_type_value="SQ",
                      investigating_group_value="RCY",
                      assignee_email_value="syahida.abdkadir@ninjavan.co",
                      investigating_hub_id_value=60)
    
    
    
    combine_csv_files(["4_FS.csv", "4_Shien.csv", "4_Tiktok_Intergration.csv","4_VN.csv","4_Tiktok_Local.csv"],
                      os.path.join(script_directory, "Temp"),
                      os.path.join(script_directory, "Output/Ticket_creation.csv"))
    
def main_overview_all_process():
    
    csv_files = [os.path.join(script_directory, "Temp/4_FS.csv"),
                 os.path.join(script_directory, "Temp/4_Shien.csv"),
                 os.path.join(script_directory, "Temp/4_Tiktok_Intergration.csv"),
                 os.path.join(script_directory, "Temp/4_VN.csv"),
                 os.path.join(script_directory, "Temp/4_Tiktok_Local.csv")]
    
    print("")
    print("======================================================================")
    print("===================== Ticket Process completed  ======================")
    print("======================================================================")
    print("")
    print("")
    print("Ticket Summary:")
    print("")
    for file in csv_files:
    
        # Skip if file does not exist
        if not os.path.exists(file):
            continue
    
        df = pd.read_csv(file)
        # Extract filename without extension
        name = os.path.splitext(os.path.basename(file))[0]
        # Remove "4_" from filename
        name = name.replace("4_", "")
    
        print(f"{name} = {len(df)}")
        print("")
    
    
    print("======================================================================")
    print("===================== Tag Process completed  =========================")
    print("======================================================================")
    
    print("")
    print("Tagging Summary:")
    print("")
    files = [os.path.join(script_directory, "Temp/0_tag_raw_1.csv"),
             os.path.join(script_directory, "Output/tag_restock.csv")]
    df_list = [pd.read_csv(file, low_memory=False) for file in files]
    df = pd.concat(df_list, ignore_index=True)
    result = (df.groupby(["tag_type", "Tagging_for"]).size().reset_index(name="count"))
    
    for _, row in result.iterrows():
        print(f"{row['tag_type']} - {row['Tagging_for']} = {row['count']}")
    


def main():
    
    print("Cleaning old file...")
    remove_files_in_folder([os.path.join(script_directory, "Temp"),os.path.join(script_directory, "Output")])
    print("file cleaned!")
    print("")
    
    main_tagging_process()
    main_ticket_on_hold_process()
    main_overview_all_process()
    
    open_work_environment() 
    remove_files_in_folder([os.path.join(script_directory, "Temp")])
    
    print("")
    print("")
    print("")
    print("Process complete!")
    input("Press enter to continue...")
    
if __name__ == "__main__":
    main()    
    
    
