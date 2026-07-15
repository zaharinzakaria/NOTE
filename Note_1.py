# from __future__ import annotations

import os
import time
import sys
import configparser
import pandas as pd
import requests
import json
import webbrowser
import zipfile
import re
import subprocess
from datetime import datetime
import csv as _csv
import shutil
import argparse
import getpass
from pathlib import Path
from typing import Any



def resolve_path(path):
    # froz path location
    if getattr(sys, "frozen", False):
        resolved_path = os.path.abspath(os.path.join(sys._MEIPASS, path))
    else:
        resolved_path = os.path.abspath(os.path.join(os.getcwd(), path))
    return resolved_path





DEFAULT_BASE_URL = "https://ola.saladinltd.com"
SWEEP_PAGE_PATH = "/pool/rover-sweep"
SWEEP_RUN_PATH = "/pool/rover-sweep/run"
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_MAX_WAIT = 2 * 60 * 60
DEFAULT_LOGIN_WAIT = 10 * 60
REQUEST_TIMEOUT = 60

script_directory = os.path.dirname(resolve_path(__file__))
SCRIPT_DIR = Path(script_directory)
DEFAULT_API_KEY_FILE = SCRIPT_DIR / "api_key.cfg"
DEFAULT_LOGIN_FILE = SCRIPT_DIR / "avos_login_key.cfg"
DEFAULT_OUTPUT_FILE = Path(os.path.join(script_directory, "Temp/result_rover_sweep.zip"))
DEFAULT_CHROME_PROFILE = Path.home() / ".rts_av_chrome_profile"





API_KEY_FILE = os.path.join(script_directory,"api_key.cfg")
LOGIN_KEY_FILE = os.path.join(script_directory,"avos_login_key.cfg")
TOKEN_KEY_FILE = os.path.join(script_directory, "token.cfg")
ROUTE_GROUPS_URL = "https://walrus.ninjavan.co/my/route/2.0/route-groups"
SECONDS_IN_A_WEEK = 7 * 24 * 60 * 60  # 7 days, 24 hours, 60 minutes, 60 seconds
SECONDS_IN_A_DAY = 16 * 60 * 60

def remove_files_in_folder(folder_paths):
    for folder_path in folder_paths:
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

def is_file_older_than(file_path, seconds):
    file_creation_time = os.path.getmtime(file_path)
    current_time = time.time()
    return current_time - file_creation_time > seconds

def is_file_older_than_a_week(file_path):
    file_creation_time = os.path.getmtime(file_path)
    current_time = time.time()
    return current_time - file_creation_time > SECONDS_IN_A_WEEK



def create_login_file(username, password):
    config = configparser.ConfigParser()
    config["login"] = {
        "username": username,
        "password": password
    }

    with open(LOGIN_KEY_FILE, "w") as configfile:
        config.write(configfile)

    print("New login file created.")

def get_login_credentials():

    # Case 1: File does NOT exist → create new
    if not os.path.exists(LOGIN_KEY_FILE):
        print("Login file not found. Creating new one...")
        username = input("Enter username: ")
        password = input("Enter password: ")
        create_login_file(username, password)
        return username, password

    # Case 2: File exists but older than 7 days → delete + recreate
    if is_file_older_than_a_week(LOGIN_KEY_FILE):
        print("Login file expired. Updating credential...")
        os.remove(LOGIN_KEY_FILE)

        username = input("Enter username: ")
        password = input("Enter password: ")
        create_login_file(username, password)
        return username, password

    # Case 3: File exists and valid → read
    config = configparser.ConfigParser()
    config.read(LOGIN_KEY_FILE)

    if "login" in config:
        username = config["login"].get("username")
        password = config["login"].get("password")

        if username and password:
            print("Using saved credentials.")
            return username, password

    # fallback (corrupted file)
    print("Login file invalid. Recreating...")
    os.remove(LOGIN_KEY_FILE)

    username = input("Enter username: ")
    password = input("Enter password: ")
    create_login_file(username, password)
    return username, password

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

def get_api_key():
    if os.path.exists(API_KEY_FILE) and not is_file_older_than_a_week(API_KEY_FILE):
        with open(API_KEY_FILE, 'r') as file:
            return file.read().strip()
    else:
        # Delete the old file if it exists
        if os.path.exists(API_KEY_FILE):
            os.remove(API_KEY_FILE)
            print("API key file expired. Updating credential...")
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



def run_avos_pipeline(input_file, output_file,avos_type):
    
    # ==============================
    # CHECK INPUT FILE
    # ==============================
    if not os.path.exists(input_file):
        print(f"Input file not found: {input_file}")
        print("Skipping AVOS pipeline...\n")
        return

    BASE_URL = "http://avnjv36kx:5000"

    session = requests.Session()

    # ==============================
    # LOAD OR CREATE CONFIG
    # ==============================

    config = configparser.ConfigParser()
    config.read(LOGIN_KEY_FILE)
    
    username = config["login"]["username"]
    password = config["login"]["password"]
    
    print("Using saved credentials")

    # ==============================
    # LOGIN
    # ==============================

    print("Logging in AVos...")

    payload = {
        "username": username,
        "password": password
    }

    session.post(f"{BASE_URL}/login", data=payload)

    if "session" not in session.cookies.get_dict():
        print("Login failed")
        return

    print("Login success")

    # ==============================
    # RUN AVOS
    # ==============================

    print("Uploading AVOS file...")

    with open(input_file, "rb") as f:

        files = {
            "file": ("data.csv", f, "text/csv")
        }

        response = session.post(f"{BASE_URL}/manual/{avos_type}/run", files=files)

    data = response.json()

    job_id = data["job_id"]

    print("Job ID:", job_id)

    # ==============================
    # WAIT JOB FINISH
    # ==============================

    next_cursor = 0

    while True:

        log_url = f"{BASE_URL}/api/job/{job_id}/log?after={next_cursor}"

        response = session.get(log_url)

        data = response.json()

        status = data["status"]

        for line in data["lines"]:
            print(line)

        if status == "done":
            print("AVOS job finished")
            break

        next_cursor = data["next"]

        time.sleep(2)

    # ==============================
    # DOWNLOAD RESULT
    # ==============================

    print("Downloading result...")

    response = session.get(f"{BASE_URL}/api/job/{job_id}/download")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "wb") as f:
        f.write(response.content)

    print(f"File downloaded: {output_file}")

def combine_csv_files(csv_files, output_file):
    df_list = []

    for file in csv_files:
        if os.path.exists(file):
            print(f"Reading: {file}")
            df_list.append(pd.read_csv(file))
        else:
            print(f"Skipped (not found): {file}")

    if not df_list:
        print("No valid CSV files found.")
        return

    combined_df = pd.concat(df_list, ignore_index=True)
    combined_df.to_csv(output_file, index=False)

def open_work_environment():

    # URLs to open
    urls = [
        "https://operatorv2.ninjavan.co/react/#/my/failed-delivery-management",
        "https://operatorv2.ninjavan.co/react/#/my/order",
        "https://operatorv2.ninjavan.co/react/#/my/route-group",
        "https://operatorv2.ninjavan.co/react/#/my/bulk-address-verification",
        "https://operatorv2.ninjavan.co/react/#/my/shipper-address"
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

    # Files / folders to open
    paths_to_open = [os.path.join(script_directory, "Output/1_manual_av_shipper_address.csv")]

    # Open if exists, otherwise skip
    for path in paths_to_open:
        if os.path.exists(path):
            os.startfile(path)


class ApiClient:
    def __init__(self):
        self.token = get_token_key()
        self.headers = {
            "accept": "application/json, text/plain, */*",
            "authorization": f"Bearer {self.token}",
            "origin": "https://operator-react.ninjavan.co",
            "referer": "https://operator-react.ninjavan.co/",
            "user-agent": "Mozilla/5.0"
        }

    def get(self, url):
        response = requests.get(url, headers=self.headers)

        # Token invalid → refresh once
        if response.status_code in (401, 403):
            print("🔐 Token expired or invalid. Requesting new token...")

            if os.path.exists(TOKEN_KEY_FILE):
                os.remove(TOKEN_KEY_FILE)

            self.token = get_token_key()
            self.headers["authorization"] = f"Bearer {self.token}"

            response = requests.get(url, headers=self.headers)

        return response

def network_header_response(url,output_file,response_header):
    client = ApiClient()
    response = client.get(url)

    if response.status_code != 200:
        print("❌ API request failed")
        print("Status Code:", response.status_code)
        print(response.text)
        return

    json_data = response.json()
    assignee_rules = json_data.get(response_header, [])
    df = pd.DataFrame(assignee_rules)
    df.to_csv(output_file,index=False)

    print("✅ network connection success!")


def network_all(url,output_file):
    client = ApiClient()
    response = client.get(url)

    if response.status_code != 200:
        print("❌ API request failed")
        print("Status Code:", response.status_code)
        print(response.text)
        return
    
    data = response.json() # <-- already a list
    df = pd.DataFrame(data) # Convert to DataFrame (auto columns)
    df.to_csv(output_file,index=False)

    print("✅ network connection success!")


def clean_user_file(
    input_file,
    output_file,
    columns_rename,
    selected_columns,
    lowercase_columns=None,
    duplicate_columns=None
):


    # Read CSV
    df = pd.read_csv(input_file)

    # Rename columns
    df = df.rename(columns=columns_rename)

    # Keep selected columns only
    df = df[selected_columns]

    # Convert selected columns to lowercase
    if lowercase_columns:
        df[lowercase_columns] = (
            df[lowercase_columns]
            .fillna("")
            .apply(lambda x: x.str.lower())
        )

    # Remove duplicate rows
    if duplicate_columns:
        before_count = len(df)

        df = df.drop_duplicates(
            subset=duplicate_columns,
            keep="first"
        )

        removed_count = before_count - len(df)

        print(f"Removed {removed_count} duplicate rows.")

    # Export CSV
    df.to_csv(output_file, index=False)

    print(f"Done! Data cleaned!:\n{output_file}")


def combine_file(file1,file2,lookup_value,output_file):
    
    # Read CSV files
    df1 = pd.read_csv(file1)
    df2 = pd.read_csv(file2)
    
    # Merge using common column
    merged_df = pd.merge(df1, df2, on=lookup_value,how="left")

    # Save result
    merged_df.to_csv(output_file, index=False)


def tng_ticket_process():
    def clean_postcode(postcode: str) -> str:
        """Remove any alphabet and special characters from postcode, keeping digits only."""
        if not isinstance(postcode, str):
            return postcode
        return re.sub(r"[^0-9]", "", postcode)
    
    
    def clean_address(address: str, postcode_cleaned: str) -> str:
        """
        Clean a raw address string by applying the following rules in order:
          1. Remove special characters except alphabets, numbers, '-', '/', '\'.
          2. Lowercase everything.
          3. Remove postcode value (already cleaned) from address.
          4. Remove duplicate words (preserving first occurrence).
          5. Strip leading/trailing spaces and collapse extra internal spaces.
        """
        if not isinstance(address, str):
            return address
    
        # Rule 1 — Strip special chars (keep alphanumeric, '-', '/', '\')
        address = re.sub(r"[^a-zA-Z0-9\-/\\\ ]", " ", address)
    
        # Rule 2 — Lowercase
        address = address.lower()
    
        # Rule 3 — Remove cleaned postcode value from address
        if isinstance(postcode_cleaned, str) and postcode_cleaned:
            escaped = re.escape(postcode_cleaned)
            address = re.sub(r"\b" + escaped + r"\b", " ", address)
    
        # Rule 4 — Remove duplicate words (case-insensitive, first occurrence wins)
        seen = []
        seen_set = set()
        for word in address.split():
            if word.lower() not in seen_set:
                seen.append(word)
                seen_set.add(word.lower())
        address = " ".join(seen)
    
        # Rule 5 — Strip leading/trailing spaces, collapse extra internal spaces
        address = re.sub(r" {2,}", " ", address).strip()
    
        return address
    
    
    def main(input_file: str, output_file: str):
        # Auto-detect delimiter (comma, tab, pipe, semicolon)
        with open(input_file, "r", encoding="utf-8") as f:
            sample = f.read(2048)
        dialect = _csv.Sniffer().sniff(sample, delimiters=",\t|;")
        df = pd.read_csv(input_file, sep=dialect.delimiter, dtype=str)
    
        # Normalise column names
        df.columns = df.columns.str.strip()
    
        if "address" not in df.columns or "postcode" not in df.columns:
            raise ValueError(
                f"Expected columns 'address' and 'postcode', found: {list(df.columns)}"
            )
    
        # Clean postcode first (digits only), then use it to clean address
        df["postcode_cleaned"] = df["postcode"].apply(clean_postcode)
        df["address_cleaned"] = df.apply(
            lambda row: clean_address(row["address"], row["postcode_cleaned"]), axis=1
        )
    
        # Output: drop original address & postcode columns; keep everything else
        other_cols = [c for c in df.columns if c not in ("address", "postcode",
                                                           "address_cleaned", "postcode_cleaned")]
        output_df = df[other_cols + ["address_cleaned", "postcode_cleaned"]]
        output_df.to_csv(output_file, index=False)
    
        print("Done!")
    
    
    # ── keyword loader ────────────────────────────────────────────────────────────
    
    def load_locality_keywords(keywords_file: str) -> set[str]:
        """
        Load locality keywords from a JSON or CSV file.
    
        JSON — a flat array of strings:
            ["jalan", "kampung", "taman", ...]
    
        CSV  — a single column (with or without a header called 'keyword'):
            keyword
            jalan
            kampung
            ...
    
        All keywords are lowercased on load.
        """
        ext = keywords_file.rsplit(".", 1)[-1].lower()
    
        if ext == "json":
            with open(keywords_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("JSON keywords file must be a flat array, e.g. [\"jalan\", ...]")
            return {kw.strip().lower() for kw in data if isinstance(kw, str) and kw.strip()}
    
        elif ext == "csv":
            with open(keywords_file, "r", encoding="utf-8", newline="") as f:
                sample = f.read(1024)
                f.seek(0)
                has_header = _csv.Sniffer().has_header(sample)
                reader = _csv.reader(f)
                if has_header:
                    next(reader)  # skip header row
                return {row[0].strip().lower() for row in reader if row and row[0].strip()}
    
        else:
            raise ValueError(f"Unsupported keywords file format: '.{ext}'. Use .json or .csv")
    
    
    # ── helpers ───────────────────────────────────────────────────────────────────
    
    def has_alphanumeric_token(tokens: list[str]) -> bool:
        """Return True if any token is a combo of letters+digits (e.g. 'a23-01', 'b2')."""
        for token in tokens:
            core = re.sub(r"[-/\\]", "", token)
            if re.search(r"[a-zA-Z]", core) and re.search(r"[0-9]", core):
                return True
        return False
    
    
    def has_pure_number_token(tokens: list[str]) -> bool:
        """Return True if any token is purely numeric (after stripping hyphens/slashes)."""
        for token in tokens:
            core = re.sub(r"[-/\\]", "", token)
            if re.fullmatch(r"[0-9]+", core):
                return True
        return False
    
    
    def is_all_numbers(tokens: list[str]) -> bool:
        """Return True if EVERY token is purely numeric."""
        return all(re.fullmatch(r"[0-9]+", re.sub(r"[-/\\]", "", t)) for t in tokens)
    
    
    def get_flags(address: str, locality_keywords: set[str]) -> list[str]:
        """
        Evaluate an address string against all flagging rules.
        Returns a list of flag codes that apply (empty = address is clean).
    
        Flag codes
        ----------
        FLAG_0 : blank, null, or whitespace-only address
        FLAG_1 : 3 or fewer tokens
        FLAG_2 : 4–5 tokens with no numbers and no alphanumeric token (e.g. a23-01)
        FLAG_3 : every token is a plain number
        FLAG_4 : 4–5 tokens but none contains a locality keyword (substring match)
        """
        # FLAG_0 — blank, null, or whitespace-only
        if not isinstance(address, str) or not address.strip():
            return ["FLAG_0"]
    
        tokens = address.split()
        n = len(tokens)
        flags = []
    
        # FLAG 1 — 3 or fewer tokens
        if n <= 3:
            flags.append("FLAG_1")
    
        # FLAG 3 — all tokens are plain numbers (check before FLAG 2)
        if is_all_numbers(tokens):
            flags.append("FLAG_3")
    
        # FLAG 2 — 4 or 5 tokens, no numbers and no alphanumeric token
        if n in (4, 5):
            has_number = has_pure_number_token(tokens)
            has_alphanum = has_alphanumeric_token(tokens)
            if not has_number and not has_alphanum:
                flags.append("FLAG_2")
    
        # FLAG 4 — 4 or 5 tokens, no locality keyword present
        # Uses substring match so merged tokens like "42ajalan" still resolve to "jalan"
        if n in (4, 5):
            found = any(
                kw in token.lower()
                for token in tokens
                for kw in locality_keywords
            )
            if not found:
                flags.append("FLAG_4")
    
        return flags
    
    
    # ── static columns ───────────────────────────────────────────────────────────
    
    # Values copied as-is to every row in the output.
    # Edit here whenever any static field needs to change.
    STATIC_COLUMNS = {
        "type":                 "PE",
        "sub_type":             "IA",
        "investigating_group":  "RCY",
        "assignee_email":       "noras.fawilah@ninjavan.co",
        "investigating_hub_id": "60",
        "entry_source":         "GN",
        "ticket_notes":         "Incomplete tng address",
    }
    
    # Final column order in the output file.
    # Columns not listed here that exist in the data will be silently dropped.
    COLUMN_ORDER = [
        "address_cleaned",
        "order_id",
        "oc",
        "postcode_cleaned",
        "flags",
        "is_flagged",
        "tracking_id",
        "type",
        "sub_type",
        "investigating_group",
        "assignee_email",
        "investigating_hub_id",
        "entry_source",
        "ticket_notes",
    ]
    
    
    # ── main ──────────────────────────────────────────────────────────────────────
    
    def main2(input_file: str, output_file: str, keywords_file: str):
        # Load locality keywords from external file
        locality_keywords = load_locality_keywords(keywords_file)
        print(f"Loaded {len(locality_keywords)} locality keywords from '{keywords_file}': {sorted(locality_keywords)}")
    
        # Auto-detect delimiter
        with open(input_file, "r", encoding="utf-8") as f:
            sample = f.read(2048)
        dialect = _csv.Sniffer().sniff(sample, delimiters=",\t|;")
        df = pd.read_csv(input_file, sep=dialect.delimiter, dtype=str)
    
        df.columns = df.columns.str.strip()
    
        if "address_cleaned" not in df.columns:
            raise ValueError(
                f"Expected column 'address_cleaned', found: {list(df.columns)}"
            )
    
        # Evaluate flags (pass keywords into each call)
        flag_results = df["address_cleaned"].apply(
            lambda addr: get_flags(addr, locality_keywords)
        )
    
        df["flags"]      = flag_results.apply(lambda f: ", ".join(f) if f else "")
        df["is_flagged"] = flag_results.apply(lambda f: bool(f))
    
        # Stamp static columns onto every row
        for col, val in STATIC_COLUMNS.items():
            df[col] = val
    
        # Apply final column order; keep only columns that exist in the dataframe
        final_cols = [c for c in COLUMN_ORDER if c in df.columns]
        missing    = [c for c in COLUMN_ORDER if c not in df.columns]
        if missing:
            print(f"Note: columns not found in data and skipped: {missing}")
        output_df = df[final_cols]
    
        output_df.to_csv(output_file, index=False)
    
        total   = len(output_df)
        flagged = output_df["is_flagged"].sum()
        print("Done!")
        print(f"Flagged: {flagged}/{total} rows\n")
    
    
    query_normal(1331,os.path.join(script_directory, "Temp/1_tng_bad_address.csv"))
    
    main(input_file=os.path.join(script_directory, "Temp/1_tng_bad_address.csv"),   # ← change to your actual input filename
         output_file=os.path.join(script_directory, "Temp/2_tng_output.csv")        # ← change to your desired output filename
         )

    result_calculation = os.path.join(script_directory, "Temp/3_result.csv")
        
    main2(input_file=os.path.join(script_directory, "Temp/2_tng_output.csv"),                  # ← output from clean_address.py
          output_file=result_calculation,                                                      # ← result of this script
          keywords_file=os.path.join(script_directory, "Database/tng_keyword_list.json"),      # ← swap to .csv if preferred
          )
    
    df = pd.read_csv(result_calculation)
    filtered_df = df[df["is_flagged"] == True]
    selected_columns = ['tracking_id',	'type',	'sub_type',	'investigating_group',	'assignee_email',	'investigating_hub_id',	'entry_source',	'ticket_notes']
    final_df = filtered_df[selected_columns]
    final_df.to_csv(os.path.join(script_directory, "Output/ticket_tng_(one_time_only).csv"), index=False)
    
    
    
    today_date = datetime.now().strftime("%Y%m%d")
    output_file = os.path.join(script_directory,"Output",f"Record_{today_date}.csv")
    shutil.copy(result_calculation, output_file)

    print("Process completed!")
    print("")




class OLAError(RuntimeError):
    """Raised when OLA rejects a request or the SWEEP job fails."""


class OLAAuthenticationError(OLAError):
    """Raised when the saved OLA/Cloudflare browser session is not usable."""


def get_saved_login_credentials(path: Path) -> tuple[str, str] | None:
    """Read the saved OLA application login without displaying it."""
    if not path.exists():
        return None
    config = configparser.ConfigParser()
    config.read(path, encoding="utf-8")
    username = config.get("login", "username", fallback="").strip()
    password = config.get("login", "password", fallback="").strip()
    if not username or not password:
        return None
    return username, password


def _read_secret_file(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _write_secret_file(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip(), encoding="utf-8")


def get_rover_api_key(path: Path, refresh: bool = False) -> str:
    """Load the Redash API key, prompting only when it is unavailable."""
    api_key = None if refresh else _read_secret_file(path)
    if api_key:
        print(f"Using Redash API key from {path.name}")
        return api_key

    api_key = getpass.getpass("Enter the Redash API key: ").strip()
    if not api_key:
        raise OLAError("A Redash API key is required.")
    _write_secret_file(path, api_key)
    print(f"Redash API key saved to {path.name}")
    return api_key


def _session_from_chrome(driver: Any, base_url: str) -> requests.Session:
    """Copy the automated Chrome session into requests without user action."""
    session = requests.Session()
    try:
        user_agent = driver.execute_script("return navigator.userAgent")
    except Exception:
        user_agent = "Mozilla/5.0"

    session.headers.update(
        {
            "Accept": "*/*",
            "Origin": base_url,
            "Referer": f"{base_url}{SWEEP_PAGE_PATH}",
            "User-Agent": str(user_agent),
        }
    )

    for cookie in driver.get_cookies():
        options: dict[str, str] = {}
        if cookie.get("domain"):
            options["domain"] = cookie["domain"]
        if cookie.get("path"):
            options["path"] = cookie["path"]
        session.cookies.set(cookie["name"], cookie["value"], **options)
    return session


def _is_authenticated(session: requests.Session, base_url: str) -> bool:
    """Check the read-only Redash-key status endpoint."""
    try:
        response = session.get(
            f"{base_url}/api/redash-key",
            timeout=15,
            allow_redirects=True,
        )
    except requests.RequestException:
        return False

    final_url = response.url.lower().rstrip("/")
    if (
        response.status_code != 200
        or "cloudflareaccess.com" in final_url
        or final_url.endswith("/login")
    ):
        return False

    try:
        data = response.json()
        return isinstance(data, dict) and "valid" in data
    except requests.JSONDecodeError:
        return False


def _login_to_ola_application(
    session: requests.Session,
    base_url: str,
    credentials: tuple[str, str] | None,
) -> bool:
    """Use the saved application login after Cloudflare allows the request."""
    if credentials is None or "CF_Authorization" not in session.cookies.get_dict():
        return False

    username, password = credentials
    try:
        response = session.post(
            f"{base_url}/login",
            data={"username": username, "password": password},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException:
        return False
    return _is_authenticated(session, base_url)


def create_authenticated_session(
    base_url: str,
    chrome_profile: Path = DEFAULT_CHROME_PROFILE,
    login_wait: float = DEFAULT_LOGIN_WAIT,
    show_browser: bool = False,
    login_file: Path = DEFAULT_LOGIN_FILE,
) -> requests.Session:
    """Reuse or renew OLA authentication and return a requests session."""
    try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
    except ImportError as exc:
        raise OLAError(
            "Selenium is required. Install it with: pip install selenium"
        ) from exc

    chrome_profile = chrome_profile.expanduser().resolve()
    chrome_profile.mkdir(parents=True, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={chrome_profile}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--start-maximized")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if not show_browser:
        options.add_argument("--headless=new")

    driver = None
    try:
        if show_browser:
            print("Opening OLA sign-in in Chrome...")
        else:
            print("Checking saved OLA sign-in...")

        try:
            driver = webdriver.Chrome(options=options)
        except WebDriverException as exc:
            raise OLAError(
                "Could not start Chrome automation. Close any Chrome window "
                "using the RTS automation profile, then try again. "
                f"Details: {exc}"
            ) from exc

        driver.get(f"{base_url}{SWEEP_PAGE_PATH}")
        deadline = time.monotonic() + login_wait
        announced = False
        credentials = get_saved_login_credentials(login_file)

        while time.monotonic() < deadline:
            try:
                session = _session_from_chrome(driver, base_url)
            except WebDriverException as exc:
                raise OLAError(
                    "The Chrome sign-in window was closed before OLA was ready."
                ) from exc

            if _is_authenticated(session, base_url):
                print("OLA sign-in is active.")
                return session
            if _login_to_ola_application(session, base_url, credentials):
                print(f"OLA application login used from {login_file.name}.")
                return session
            session.close()

            if not show_browser:
                raise OLAAuthenticationError(
                    "The saved Cloudflare sign-in is missing or expired."
                )

            if not announced:
                print(
                    "Complete the OLA sign-in in the opened Chrome window. "
                    "Use Google or the emailed login code shown by Cloudflare."
                )
                print("This is normally needed only on the first run or after expiry.")
                announced = True
            time.sleep(2)

        raise OLAError(
            f"OLA sign-in was not completed within {login_wait / 60:.0f} minutes."
        )
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def _check_response(response: requests.Response, action: str) -> None:
    """Turn HTTP and expired-login responses into useful messages."""
    response_url = response.url.lower().rstrip("/")
    login_url = "cloudflareaccess.com" in response_url or response_url.endswith("/login")

    if response.status_code in (401, 403) or login_url:
        raise OLAAuthenticationError(
            "OLA authentication failed or expired."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()[:500]
        if detail:
            raise OLAError(f"Could not {action}: {exc}. Server response: {detail}") from exc
        raise OLAError(f"Could not {action}: {exc}") from exc


def _json_response(response: requests.Response, action: str) -> dict[str, Any]:
    _check_response(response, action)
    try:
        data = response.json()
    except requests.JSONDecodeError as exc:
        raise OLAError(f"Could not {action}: OLA returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise OLAError(f"Could not {action}: OLA returned an unexpected response.")
    return data


def save_redash_key(
    session: requests.Session,
    api_key: str,
    base_url: str = DEFAULT_BASE_URL,
) -> None:
    print("Saving Redash API key to OLA...")
    response = session.post(
        f"{base_url}/api/redash-key",
        json={"key": api_key},
        timeout=REQUEST_TIMEOUT,
    )
    _check_response(response, "save the Redash API key")
    print("Redash API key is active.")


def start_sweep_process(
    session: requests.Session,
    base_url: str = DEFAULT_BASE_URL,
) -> str:
    print("Starting the ROVER SWEEP process...")
    response = session.post(
        f"{base_url}{SWEEP_RUN_PATH}",
        timeout=REQUEST_TIMEOUT,
    )
    data = _json_response(response, "start the ROVER SWEEP process")
    job_id = data.get("job_id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise OLAError("OLA did not return a job_id after starting SWEEP.")
    print(f"Job ID: {job_id}")
    return job_id


def wait_for_job(
    session: requests.Session,
    job_id: str,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_wait: float = DEFAULT_MAX_WAIT,
    base_url: str = DEFAULT_BASE_URL,
) -> None:
    """Print new log lines until the SWEEP job reports completion."""
    cursor = 0
    started_at = time.monotonic()

    while True:
        if time.monotonic() - started_at > max_wait:
            raise OLAError(
                f"SWEEP job did not finish within {max_wait / 60:.0f} minutes. "
                f"Job ID: {job_id}"
            )

        response = session.get(
            f"{base_url}/api/job/{job_id}/log",
            params={"after": cursor},
            timeout=REQUEST_TIMEOUT,
        )
        data = _json_response(response, "read the SWEEP job log")

        lines = data.get("lines", [])
        if isinstance(lines, list):
            for line in lines:
                print(str(line), flush=True)

        next_cursor = data.get("next", cursor)
        if isinstance(next_cursor, int) and next_cursor >= cursor:
            cursor = next_cursor

        status = str(data.get("status", "")).lower()
        if status == "done":
            print("ROVER SWEEP job finished.")
            return

        if status in {"error", "failed", "cancelled", "canceled"}:
            message = (
                data.get("special_error_message")
                or data.get("special_error")
                or f"SWEEP job ended with status '{status}'."
            )
            raise OLAError(str(message))

        time.sleep(poll_interval)


def download_result(
    session: requests.Session,
    job_id: str,
    output_file: Path,
    base_url: str = DEFAULT_BASE_URL,
) -> Path:
    print("Downloading ROVER SWEEP result ZIP...")
    response = session.get(
        f"{base_url}/api/job/{job_id}/download",
        stream=True,
        timeout=REQUEST_TIMEOUT,
    )
    _check_response(response, "download the SWEEP result")

    output_file = output_file.resolve()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    partial_file = output_file.with_name(output_file.name + ".part")

    try:
        with partial_file.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    file_handle.write(chunk)

        with partial_file.open("rb") as file_handle:
            if file_handle.read(4) != b"PK\x03\x04":
                raise OLAError("OLA's SWEEP download was not a valid ZIP file.")

        os.replace(partial_file, output_file)
    finally:
        if partial_file.exists():
            partial_file.unlink()

    print(f"Downloaded: {output_file}")
    return output_file


def sweep_run_rts_av(
    output_file: Path | str = DEFAULT_OUTPUT_FILE,
    *,
    api_key_file: Path | str = DEFAULT_API_KEY_FILE,
    login_file: Path | str = DEFAULT_LOGIN_FILE,
    chrome_profile: Path | str = DEFAULT_CHROME_PROFILE,
    refresh_api_key: bool = False,
    show_browser: bool = False,
    base_url: str = DEFAULT_BASE_URL,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    max_wait: float = DEFAULT_MAX_WAIT,
    login_wait: float = DEFAULT_LOGIN_WAIT,
) -> bool:
    """Run OLA RTS ROVER SWEEP and download its result ZIP."""
    try:
        api_key = get_rover_api_key(Path(api_key_file), refresh_api_key)
        base_url = base_url.rstrip("/")
        try:
            session = create_authenticated_session(
                base_url,
                Path(chrome_profile),
                login_wait,
                show_browser,
                Path(login_file),
            )
        except OLAAuthenticationError:
            if show_browser:
                raise
            print("Saved OLA/Cloudflare sign-in needs to be renewed.")
            print("Opening a visible Chrome window now...")
            session = create_authenticated_session(
                base_url,
                Path(chrome_profile),
                login_wait,
                True,
                Path(login_file),
            )
        try:
            save_redash_key(session, api_key, base_url)
            job_id = start_sweep_process(session, base_url)
            wait_for_job(session, job_id, poll_interval, max_wait, base_url)
            download_result(session, job_id, Path(output_file), base_url)
        finally:
            session.close()
        return True
    except (OLAError, OSError, requests.RequestException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run OLA RTS ROVER SWEEP and download its ZIP result."
    )
    parser.add_argument(
        "--api-key-file",
        type=Path,
        default=DEFAULT_API_KEY_FILE,
        help=f"Redash API key file (default: {DEFAULT_API_KEY_FILE.name})",
    )
    parser.add_argument(
        "--chrome-profile",
        type=Path,
        default=DEFAULT_CHROME_PROFILE,
        help="Persistent Chrome profile used for OLA sign-in.",
    )
    parser.add_argument(
        "--login-file",
        type=Path,
        default=DEFAULT_LOGIN_FILE,
        help=f"OLA application login file (default: {DEFAULT_LOGIN_FILE.name}).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="Downloaded ZIP path (default: Temp/result_rover_sweep.zip)",
    )
    parser.add_argument(
        "--refresh-api-key",
        action="store_true",
        help="Prompt for a new Redash API key and replace the saved key.",
    )
    parser.add_argument(
        "--login",
        action="store_true",
        help="Show Chrome to renew Cloudflare sign-in; normally not needed.",
    )
    parser.add_argument(
        "--base-url",
        default=DEFAULT_BASE_URL,
        help=f"OLA server URL (default: {DEFAULT_BASE_URL}).",
    )
    parser.add_argument(
        "--login-wait-minutes",
        type=float,
        default=DEFAULT_LOGIN_WAIT / 60,
        help="Maximum time for interactive Chrome sign-in (default: 10).",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=DEFAULT_POLL_INTERVAL,
        help="Seconds between log checks (default: 2).",
    )
    parser.add_argument(
        "--max-wait-minutes",
        type=float,
        default=DEFAULT_MAX_WAIT / 60,
        help="Maximum job wait in minutes (default: 120).",
    )
    return parser.parse_args()

def rover_sweep_pipeline() -> int:
    args = parse_args()
    try:
        if args.poll_interval <= 0:
            raise OLAError("--poll-interval must be greater than zero.")
        if args.max_wait_minutes <= 0:
            raise OLAError("--max-wait-minutes must be greater than zero.")
        if args.login_wait_minutes <= 0:
            raise OLAError("--login-wait-minutes must be greater than zero.")

        success = sweep_run_rts_av(
            output_file=args.output,
            api_key_file=args.api_key_file,
            login_file=args.login_file,
            chrome_profile=args.chrome_profile,
            refresh_api_key=args.refresh_api_key,
            show_browser=args.login,
            base_url=args.base_url,
            poll_interval=args.poll_interval,
            max_wait=args.max_wait_minutes * 60,
            login_wait=args.login_wait_minutes * 60,
        )

        if not success:
            return 1
        
        zip_file = os.path.join(script_directory, "Temp", "result_rover_sweep.zip")
        output_folder = os.path.join(script_directory, "Output")
        
        # Create the output folder if it doesn't exist
        os.makedirs(output_folder, exist_ok=True)
        
        # Extract the ZIP file
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(output_folder)
        
        print(f"Successfully extracted to:\n{output_folder}")
        
        return 0 if success else 1
    except KeyboardInterrupt:
        print("\nStopped by user.", file=sys.stderr)
        return 130
    except (OLAError, OSError, requests.RequestException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

def main(cleanup_start=True, cleanup_end=True, open_environment=True, wait_for_enter=True):
    print("======================================================================")
    print("==================== Part 0 : Data Preparation  =====================")
    print("======================================================================")
    
    print("Credential Checking")
    print("")
    print("==Redash==")
    get_api_key()
    print("status ok")    

    print("")
    print("==AVOS==")
    username, password = get_login_credentials()
    print("status ok")

    print("")
    print("==OPv2==")
    validate_opv2_access_code()
    print("status ok")
    

    if cleanup_start:
        remove_files_in_folder([os.path.join(script_directory, "Temp"),os.path.join(script_directory, "Output")])
        print("File Cleaned.")
    else:
        print("Skipping start cleanup.")
    print("")
    
    print("======================================================================")
    print("================== Part 1 : Execute Direct Task  =====================")
    print("======================================================================")
    
    print("")
    print("Running RTS Postcode KV to EM")
    query_normal(1273,os.path.join(script_directory, "Output/3_upload_rts_kv_em.csv"))
    print("Done")
    print("")
    
    print("Running AV Sweep")
    query_normal(1099,os.path.join(script_directory, "Output/2_upload_av_sweep_latlong_repair.csv"))
    print("Done")
    print("")
    
    print("Running Reschedule Cold Chain")
    query_normal(339,os.path.join(script_directory, "Output/4_upload_fdm_reschedule_cold_chain.csv"))
    print("Done")
    print("")

    print("======================================================================")
    print("=================== Part 2 : Execute Heavy Task  =====================")
    print("======================================================================")    
    
    print("")
    print("Running AV AON to 3PL")
    try:
        query_normal(337, os.path.join(script_directory, "Temp/0_raw_aon_3pl.csv"))
        df = pd.read_csv(os.path.join(script_directory, "Temp/0_raw_aon_3pl.csv"))
        selected_df = df[['waypoint_id', 'latitude', 'longitude']]
        selected_df.to_csv(os.path.join(script_directory, "Output/2_upload_av_aon_3pl.csv"), index=False)
        print("Done")
        print("")  
    except Exception:
        print("No data. Skipping to next proceess")
        print("")

    print("Running AV SIP")
    try:
        query_normal(347, os.path.join(script_directory, "Temp/0_raw_sip.csv"))
        df = pd.read_csv(os.path.join(script_directory, "Temp/0_raw_sip.csv"))
        selected_df = df[['waypoint_id', 'latitude', 'longitude']]
        selected_df.to_csv(os.path.join(script_directory, "Output/2_upload_av_sip.csv"), index=False)
        print("Done")
        print("")
    except Exception:
        print("No data. Skipping to next proceess")
        print("")
    
    
    print("Running AV Shipper Address")
    
    query_normal(1350,os.path.join(script_directory, "Temp/1_input_casim_shipper_address.csv"))

    print("Using CSGO...")
    try:
        run_avos_pipeline(os.path.join(script_directory, "Temp/1_input_casim_shipper_address.csv"),
                              os.path.join(script_directory, "Temp/1_result_csgo_shipper_address.zip"),
                              "csgo")
        # extract zip file and reconstruct upload file    
        with zipfile.ZipFile(os.path.join(script_directory, "Temp/1_result_csgo_shipper_address.zip"), 'r') as zip_ref:
            zip_ref.extractall(os.path.join(script_directory, "Temp"))
            print("Done")
            print("")
   
    

        print("Casim process...")
        df = pd.read_csv(os.path.join(script_directory, "Temp/casim.csv"))
        selected_columns = ['tracking_number', 'full_address','waypoint_id', 'latitude', 'longitude']
        df[selected_columns].to_csv(os.path.join(script_directory, "Temp/3_result_casim_shipper_address.csv"), index=False)
        print("Done")
        print("")
    except Exception:
        print("No data. Skipping to next proceess")
        print("")


    print("Slam process...")
    try:   
        # Slam result compilation
        df = pd.read_csv(os.path.join(script_directory, "Temp/slam.csv"))
        df[['latitude', 'longitude']] = df['LL'].str.split(',', expand=True)
        selected_columns = ['tracking_number', 'waypoint_id', 'latitude', 'longitude',]
        df[selected_columns].to_csv(os.path.join(script_directory, "Temp/2_raw_result_slam_shipper_address.csv"),index=False)
        
        file_a = pd.read_csv(os.path.join(script_directory, "Temp/2_raw_result_slam_shipper_address.csv"))
        file_b = pd.read_csv(os.path.join(script_directory, "Temp/1_input_casim_shipper_address.csv"))
        
        file_a = file_a[['tracking_number', 'waypoint_id','latitude','longitude']]
        file_b = file_b[['tracking_number', 'full_address']]
        
        merged_df = pd.merge(file_a,file_b,on='tracking_number',how='left')
        selected_columns = ['tracking_number', 'full_address','waypoint_id', 'latitude', 'longitude']
        merged_df[selected_columns].to_csv(os.path.join(script_directory, "Temp/3_result_slam_shipper_address.csv"), index=False)
        print("Done")
        print("")
    except Exception:
        print("No data. Skipping to next proceess")
        print("")

    
    try:
        print("Papercut process...")
        df = pd.read_csv(os.path.join(script_directory, "Temp/manual.csv"))
        if df.empty:
            print("manual.csv contains no data. Skipping run_avos_pipeline.")
            print("")
        else:
            run_avos_pipeline(os.path.join(script_directory, "Temp/manual.csv"),
                              os.path.join(script_directory, "Temp/2_raw_result_papercut_shipper_address.csv"),
                              "papercut")
        
            # Read CSV files
            file_a = pd.read_csv(os.path.join(script_directory, "Temp/2_raw_result_papercut_shipper_address.csv"))
            file_b = pd.read_csv(os.path.join(script_directory, "Temp/1_input_casim_shipper_address.csv"))
            
            # Keep required columns only
            file_a = file_a[['tracking_number','latitude','longitude']]
            file_b = file_b[['tracking_number', 'full_address','waypoint_id']]
            
            # Merge using tracking_number
            merged_df = pd.merge(file_a,file_b,on='tracking_number',how='left')
            selected_columns = ['tracking_number', 'full_address','waypoint_id', 'latitude', 'longitude']
            merged_df[selected_columns].to_csv(os.path.join(script_directory, "Temp/3_result_papercut_shipper_address.csv"), index=False)
            print("Done")
            print("")
    except Exception:
        print("No data. Skipping to next proceess")
        print("")
     
    """
    try:
        print("Running TNG Address Issue Ticket...")
        tng_ticket_process()
    
    except Exception:
        print("No data. Skipping to next proceess")
        print("")
    """

    
    print("======================================================================")
    print("================== Part 3 : Compiling data  =========================")
    print("======================================================================")
    
    try:
        print("")
        print("Compiling data...")
        combine_csv_files([os.path.join(script_directory, "Temp/3_result_casim_shipper_address.csv"),
                           os.path.join(script_directory, "Temp/3_result_slam_shipper_address.csv"),
                           os.path.join(script_directory, "Temp/3_result_papercut_shipper_address.csv")],
                          os.path.join(script_directory, "Temp/4_all_compile_result_shipper_address.csv"))
        
        # renaming column
        df = pd.read_csv(os.path.join(script_directory, "Temp/4_all_compile_result_shipper_address.csv"))
        df.rename(columns={"tracking_number": "Address ID",
                           "full_address": "Pickup address",
                           "waypoint_id": "Global shipper ID"},
                  inplace=True)
        df.to_csv(os.path.join(script_directory, "Temp/5_new_all_compile_result_shipper_address.csv"), index=False)
    
        # split latlong and no latlong
        df = pd.read_csv(os.path.join(script_directory, "Temp/5_new_all_compile_result_shipper_address.csv"))
        df_has_latitude = df[df["latitude"].notna() & (df["latitude"].astype(str).str.strip() != "")]
        df_no_latitude = df[df["latitude"].isna() | (df["latitude"].astype(str).str.strip() == "")]
        df_has_latitude.to_csv(os.path.join(script_directory, "Output/2_upload_av_shipper_address.csv"), index=False)
        df_no_latitude.to_csv(os.path.join(script_directory, "Output/1_manual_av_shipper_address.csv"), index=False)
        print("Done")
        print("")
    except Exception:
        print("No data. Skipping to next proceess")
        print("")



    print("======================================================================")
    print("=================== Update - Pet Assignee ============================")
    print("======================================================================")

        
    
    print("Pulling data...")
    network_header_response("https://walrus.ninjavan.co/my/mpm/assignee-rules/all",
                   os.path.join(script_directory, "Temp/0_assignee_email.csv"),
                   "assignee_rules")
    
    network_all("https://walrus.ninjavan.co/my/sort/2.0/lite/hubs?active_only=true",
                os.path.join(script_directory, "Temp/0_assignee_hubs.csv"))
    
    network_all("https://walrus.ninjavan.co/my/ticketing/users",
                os.path.join(script_directory, "Temp/0_assignee_user_name.csv"))
    
    print("Download data completed!")
    print("")
    
    
    
    print("======================================================================")
    print("==================== Part 1 : Data Calculation =======================")
    print("======================================================================")
    
    
    print("Cleaning data for calculation...")
    clean_user_file(os.path.join(script_directory, "Temp/0_assignee_user_name.csv"),
                    os.path.join(script_directory, "Temp/1_assignee_user_name.csv"),
                    {"name": "Assignee", "email": "Email"},
                    ["Email","Assignee"],
                    ["Assignee","Email"],
                    duplicate_columns=['Email']
                    )
    
    clean_user_file(os.path.join(script_directory, "Temp/0_assignee_email.csv"),
                    os.path.join(script_directory, "Temp/1_assignee_email.csv"),
                    {"investigating_hub_id": "Hub Id", "investigating_dept": "Acronym", "assignee_email": "Email"},
                    ["Hub Id", "Acronym", "Email"],
                    ["Email"],
                    duplicate_columns=None
                    )
    
    clean_user_file(os.path.join(script_directory, "Temp/0_assignee_hubs.csv"),
                    os.path.join(script_directory, "Temp/1_assignee_hubs.csv"),
                    {"id": "Hub Id", "name": "Hub Name","facility_type": "Facility Type"},
                    ["Hub Id", "Hub Name","Facility Type"],
                    lowercase_columns=None,
                    duplicate_columns=None
                    )
    
    print("Data cleaned! preparing for calculation..")
    print("")
    
    
    print("======================================================================")
    print("==================== Part 2 : Data matching  ======================")
    print("======================================================================")
    
    print("Combining multiple packet file and first tier matching...")
    combine_file(os.path.join(script_directory, "Temp/1_assignee_hubs.csv"),
                os.path.join(script_directory, "Temp/1_assignee_email.csv"),
                "Hub Id", 
                os.path.join(script_directory, "Temp/2_hub_email.csv"))
    
    
    combine_file(os.path.join(script_directory, "Temp/2_hub_email.csv"),
                os.path.join(script_directory, "Temp/1_assignee_user_name.csv"),
                "Email", 
                os.path.join(script_directory, "Temp/2_hub_email_name.csv"))
    
    
    df = pd.read_csv(os.path.join(script_directory, "Temp/2_hub_email_name.csv"))
    df = df[['Hub Name','Acronym','Email','Hub Id']]
    df.to_csv(os.path.join(script_directory, "Temp/3_new_update_assignee.csv"),  index=False)

    df = pd.read_csv(os.path.join(script_directory, "Temp/3_new_update_assignee.csv"))
    
    # Clean the column first
    df["Acronym"] = df["Acronym"].fillna("").astype(str).str.strip()
    
    # Mapping rules
    acronym_mapping = {
        "B2B": "B2B",
        "Cold Chain": "CC",
        "Cross Border": "XB",
        "Fleet (First Mile)": "FLT-FM",
        "Fleet (Last Mile)": "FLT-LM",
        "Freight (Middle Mile)": "FRT-MM",
        "Others": "OTH",
        "PUDO": "PUDO",
        "Recovery": "RCY",
        "Sort (Warehouse)": "SORT"
    }
    
    # Apply mapping
    df["Acronym"] = df["Acronym"].replace(acronym_mapping)
    
    # Replace blank values with SORT
    df.loc[df["Acronym"] == "", "Acronym"] = "SORT"
    
    # Save output
    df.to_csv(os.path.join(script_directory, "Output/5_update_pet_assingnee.csv"), index=False)
    
    print("")
    
    
    print("======================================================================")
    print("==================== Update - Holding Driver =========================")
    print("======================================================================")
    
    query_normal(1550, os.path.join(script_directory, "Output/5_update_holding_driver.csv"))
    
    
    # Open chrome & file
    print("Launching related operator & file")
    print("")
    if open_environment:
        rover_result = rover_sweep_pipeline()
        if rover_result != 0:
            print("Rover Sweep failed; the work environment will not be opened.", file=sys.stderr)
            return rover_result
        open_work_environment()
    if cleanup_end:
        remove_files_in_folder([os.path.join(script_directory, "Temp")])
    else:
        print("Skipping end cleanup.")
    
    print("")
    print("Process completed!")
    print("")
    if wait_for_enter:
        input("Press Enter to continue...")
        

if __name__ == "__main__":
    raise SystemExit(main())
