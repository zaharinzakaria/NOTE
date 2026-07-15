import os
import subprocess
import sys
import time
import webbrowser
import pandas as pd
import requests
import json
import configparser
import zipfile
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

script_directory = os.path.dirname(resolve_path(__file__))
API_KEY_FILE = os.path.join(script_directory,"api_key.cfg")
LOGIN_KEY_FILE = os.path.join(script_directory,"avos_login_key.cfg")
SECONDS_IN_A_WEEK = 7 * 24 * 60 * 60  # 7 days, 24 hours, 60 minutes, 60 seconds

DEFAULT_BASE_URL = "https://ola.saladinltd.com"
DEFAULT_CHROME_PROFILE = os.path.join(os.path.expanduser("~"), ".rts_av_chrome_profile")
DEFAULT_LOGIN_FILE = os.path.join(script_directory, "avos_login_key.cfg")
DEFAULT_LOGIN_WAIT = 10 * 60
REQUEST_TIMEOUT = 60

ROVER_DEFAULT_BASE_URL = "https://ola.saladinltd.com"
ROVER_DEFAULT_POLL_INTERVAL = 2.0
ROVER_DEFAULT_MAX_WAIT = 2 * 60 * 60
ROVER_DEFAULT_LOGIN_WAIT = 10 * 60
ROVER_REQUEST_TIMEOUT = 60
ROVER_SCRIPT_DIR = Path(script_directory)
ROVER_DEFAULT_API_KEY_FILE = ROVER_SCRIPT_DIR / "api_key.cfg"
ROVER_DEFAULT_LOGIN_FILE = ROVER_SCRIPT_DIR / "avos_login_key.cfg"
ROVER_DEFAULT_OUTPUT_FILE = Path(os.path.join(script_directory, "Temp/result_rover.zip"))
ROVER_DEFAULT_CHROME_PROFILE = Path.home() / ".rts_av_chrome_profile"

def remove_files_in_folder(folder_paths):
    for folder_path in folder_paths:
        if not os.path.exists(folder_path):
            continue
        for filename in os.listdir(folder_path):
            file_path = os.path.join(folder_path, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

def is_file_older_than_a_week(file_path):
    file_creation_time = os.path.getmtime(file_path)
    current_time = time.time()
    return current_time - file_creation_time > SECONDS_IN_A_WEEK

def open_work_environment():

    # URLs to open
    urls = [
        "https://operatorv2.ninjavan.co/react/#/my/failed-delivery-management",
        "https://operatorv2.ninjavan.co/react/#/my/bulk-address-verification",

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
       

def direct_match_multiple_address(
    file1,
    file2,
    matched_file,
    unmatched_file,
    match_columns,
    lookup_column='latlong_rts'
):
    try:
        print(f"Direct matching on: {match_columns}")
        print(f"Lookup column(s): {lookup_column}")

        # =========================================================
        # READ FILES
        # =========================================================
        df1 = pd.read_csv(file1, encoding='latin1')
        df2 = pd.read_csv(file2, encoding='latin1')

        if df1.empty:
            print("file1 is empty. Nothing to process.")
            return

        # =========================================================
        # NORMALIZE match_columns
        # Supports:
        # - 'address1'
        # - ('address1',)
        # - ['address1']
        # - ('ref_no', 'address1')
        # =========================================================
        if isinstance(match_columns, str):
            match_columns = [match_columns]
        else:
            match_columns = list(match_columns)

        # =========================================================
        # NORMALIZE lookup_column
        # Supports:
        # - 'latlong_rts'
        # - ['latitude', 'longitude']
        # =========================================================
        if isinstance(lookup_column, str):
            lookup_columns = [lookup_column]
        else:
            lookup_columns = list(lookup_column)

        print(f"Normalized match columns: {match_columns}")
        print(f"Normalized lookup columns: {lookup_columns}")

        # =========================================================
        # VALIDATE COLUMNS
        # =========================================================
        required_file1 = match_columns + ['waypoint_id']
        required_file2 = match_columns + lookup_columns

        for col in required_file1:
            if col not in df1.columns:
                raise ValueError(f"Missing '{col}' in file1")

        for col in required_file2:
            if col not in df2.columns:
                raise ValueError(f"Missing '{col}' in file2")

        # =========================================================
        # REDUCE FILE2
        # =========================================================
        df2_lookup = df2[
            match_columns + lookup_columns
        ].drop_duplicates()

        # =========================================================
        # MERGE
        # =========================================================
        merged_df = pd.merge(
            df1,
            df2_lookup,
            on=match_columns,
            how='left'
        )

        # =========================================================
        # CHECK VALID LOOKUP VALUES
        # all lookup columns must:
        # - not be null
        # - not be empty string
        # =========================================================
        has_value = (
            merged_df[lookup_columns]
            .notna()
            .all(axis=1)
        )

        for col in lookup_columns:
            has_value &= (
                merged_df[col]
                .astype(str)
                .str.strip()
                != ''
            )

        # =========================================================
        # MATCHED
        # =========================================================
        matched_df = merged_df.loc[
            has_value,
            ['waypoint_id'] + lookup_columns
        ]

        # =========================================================
        # UNMATCHED
        # =========================================================
        unmatched_df = merged_df.loc[
            ~has_value,
            df1.columns
        ]

        # =========================================================
        # SAVE MATCHED
        # =========================================================
        if not matched_df.empty:
            matched_df.to_csv(matched_file, index=False)
            print(f"Matched file saved: {matched_file}")
            print(f"Matched rows: {len(matched_df)}")
        else:
            print("No matched records found.")

        # =========================================================
        # SAVE UNMATCHED
        # =========================================================
        unmatched_df.to_csv(unmatched_file, index=False)

        print(f"Unmatched file saved: {unmatched_file}")
        print(f"Unmatched rows: {len(unmatched_df)}")

        print("Processing complete.")

    except Exception as e:
        print(f"Error: {e}")


class OLAAuthenticationError(RuntimeError):
    pass


def get_saved_login_credentials():
    if not os.path.exists(DEFAULT_LOGIN_FILE):
        return None

    config = configparser.ConfigParser()
    config.read(DEFAULT_LOGIN_FILE, encoding="utf-8")
    username = config.get("login", "username", fallback="").strip()
    password = config.get("login", "password", fallback="").strip()
    if not username or not password:
        return None
    return username, password


def session_from_chrome(driver):
    session = requests.Session()
    try:
        user_agent = driver.execute_script("return navigator.userAgent")
    except Exception:
        user_agent = "Mozilla/5.0"

    session.headers.update({
        "Accept": "*/*",
        "Origin": DEFAULT_BASE_URL,
        "Referer": f"{DEFAULT_BASE_URL}/manual/csgo",
        "User-Agent": str(user_agent),
    })

    for cookie in driver.get_cookies():
        cookie_options = {}
        if cookie.get("domain"):
            cookie_options["domain"] = cookie["domain"]
        if cookie.get("path"):
            cookie_options["path"] = cookie["path"]
        session.cookies.set(cookie["name"], cookie["value"], **cookie_options)
    return session


def is_ola_authenticated(session):
    try:
        response = session.get(
            f"{DEFAULT_BASE_URL}/api/redash-key",
            timeout=15,
            allow_redirects=True,
        )
    except requests.RequestException:
        return False

    final_url = response.url.lower().rstrip("/")
    if (response.status_code != 200
            or "cloudflareaccess.com" in final_url
            or final_url.endswith("/login")):
        return False

    try:
        return isinstance(response.json(), dict)
    except requests.JSONDecodeError:
        return False


def login_to_ola_application(session):
    credentials = get_saved_login_credentials()
    if credentials is None or "CF_Authorization" not in session.cookies.get_dict():
        return False

    username, password = credentials
    try:
        response = session.post(
            f"{DEFAULT_BASE_URL}/login",
            data={"username": username, "password": password},
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException:
        return False
    return is_ola_authenticated(session)


def create_authenticated_session(show_browser=False):
    try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
    except ImportError as error:
        raise OLAAuthenticationError(
            "Selenium is required. Install it with: pip install selenium"
        ) from error

    chrome_profile = os.path.abspath(DEFAULT_CHROME_PROFILE)
    os.makedirs(chrome_profile, exist_ok=True)

    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={chrome_profile}")
    options.add_argument("--profile-directory=Default")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    if show_browser:
        options.add_argument("--start-maximized")
    else:
        options.add_argument("--headless=new")

    driver = None
    try:
        try:
            driver = webdriver.Chrome(options=options)
        except WebDriverException as error:
            raise OLAAuthenticationError(f"Could not start Chrome: {error}") from error

        driver.get(f"{DEFAULT_BASE_URL}/manual/csgo")
        deadline = time.monotonic() + DEFAULT_LOGIN_WAIT
        announced = False

        while time.monotonic() < deadline:
            session = session_from_chrome(driver)
            if is_ola_authenticated(session):
                print("OLA sign-in is active.")
                return session
            if login_to_ola_application(session):
                print("OLA application login successful.")
                return session
            session.close()

            if not show_browser:
                raise OLAAuthenticationError("Saved Cloudflare sign-in is missing or expired.")
            if not announced:
                print("Complete the OLA sign-in in the opened Chrome window.")
                announced = True
            time.sleep(2)

        raise OLAAuthenticationError("OLA sign-in was not completed within 10 minutes.")
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


def get_ola_session():
    try:
        return create_authenticated_session(show_browser=False)
    except OLAAuthenticationError as error:
        print(f"OLA login needs attention: {error}")
        answer = input("Open Chrome to renew OLA login now? [y/N]: ").strip().lower()
        if answer in {"y", "yes"}:
            return create_authenticated_session(show_browser=True)
        raise


def run_avos_pipeline(input_file, output_file, avos_type):
    
    # ==============================
    # CHECK INPUT FILE
    # ==============================
    if not os.path.exists(input_file):
        print(f"Input file not found: {input_file}")
        print("Skipping AVOS pipeline...\n")
        return False

    # ==============================
    # LOGIN
    # ==============================
    try:
        session = get_ola_session()
    except Exception as error:
        print(f"OLA login failed: {error}")
        print("Cloudflare login was not renewed.")
        return False

    try:
        # ==============================
        # RUN AVOS
        # ==============================

        print("Uploading AVOS file...")

        with open(input_file, "rb") as file_handle:
            files = {"file": ("data.csv", file_handle, "text/csv")}
            response = session.post(
                f"{DEFAULT_BASE_URL}/manual/{avos_type}/run",
                files=files,
                timeout=REQUEST_TIMEOUT,
            )
        response.raise_for_status()

        data = response.json()
        job_id = data["job_id"]
        print("Job ID:", job_id)

        # ==============================
        # WAIT JOB FINISH
        # ==============================

        next_cursor = 0
        while True:
            response = session.get(
                f"{DEFAULT_BASE_URL}/api/job/{job_id}/log",
                params={"after": next_cursor},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            status = str(data.get("status", "")).lower()

            for line in data.get("lines", []):
                print(line)

            if status == "done":
                print("AVOS job finished")
                break
            if status in {"error", "failed", "cancelled", "canceled"}:
                message = data.get("special_error_message") or status
                print(f"AVOS job failed: {message}")
                return False

            next_cursor = data.get("next", next_cursor)
            time.sleep(2)

        # ==============================
        # DOWNLOAD RESULT
        # ==============================

        print("Downloading result...")
        response = session.get(
            f"{DEFAULT_BASE_URL}/api/job/{job_id}/download",
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        with open(output_file, "wb") as file_handle:
            file_handle.write(response.content)

        print(f"File downloaded: {output_file}")
        return True
    except (KeyError, ValueError, requests.RequestException) as error:
        print(f"AVOS process failed: {error}")
        return False
    finally:
        session.close()



def combine_csv_files(file_list, output_path):

    df_list = []

    for file in file_list:
        try:
            df = pd.read_csv(file)
            df_list.append(df)
            print(f"Loaded: {file}")
        except Exception as e:
            print(f"Error reading {file}: {e}")

    if df_list:
        combined_df = pd.concat(df_list, ignore_index=True)
        combined_df.to_csv(output_path, index=False)
        print(f"\n✅ Combined file saved at: {output_path}")
    else:
        print("❌ No files were combined.")


def csgo_pipeline():

    try:
        fp_1 = os.path.join(script_directory, "Temp/8_to_avos_csgo.csv")
        fp_2 = os.path.join(script_directory, "Temp/9_result_csgo.zip")
        fp_folder = os.path.join(script_directory, "Temp")

        if not run_avos_pipeline(fp_1, fp_2, "csgo"):
            return

        # Extract ZIP
        if not os.path.exists(fp_2):
            print(f"Result ZIP not found: {fp_2}")
            print("No data. Skipping to next process")
            return

        with zipfile.ZipFile(fp_2, 'r') as zip_ref:
            zip_ref.extractall(fp_folder)

        # Rename extracted files
        rename_map = {
            "manual.csv": "10_manual.csv",
            "casim.csv": "10_casim.csv",
            "slam.csv": "10_slam.csv"
        }

        for old_name, new_name in rename_map.items():
            old_path = os.path.join(fp_folder, old_name)
            new_path = os.path.join(fp_folder, new_name)

            if os.path.exists(old_path):
                os.rename(old_path, new_path)
                print(f"Renamed {old_name} -> {new_name}")

        print("Files extracted and renamed successfully.")

    except Exception as e:
        print(f"Error: {e}")
        print("No data. Skipping to next process")
        return
    
    casim_file = os.path.join(script_directory, "Temp/10_casim.csv")
    slam_file = os.path.join(script_directory, "Temp/10_slam.csv")
    fp_casim = os.path.join(script_directory, "Temp/11_output_casim.csv")
    fp_slam = os.path.join(script_directory, "Temp/11_output_slam.csv")
    
    
    try:
        df_casim = pd.read_csv(casim_file)
        select_column_casim = df_casim[['waypoint_id',	'latitude',	'longitude']]
        select_column_casim.to_csv(fp_casim,index=False)
    except Exception as e:
        print(f"Error: {e}")
        print("No data. Skipping to next process")
        
    
    try:
        df_slam = pd.read_csv(slam_file)
        df_slam[['latitude', 'longitude']] = (
            df_slam['LL']
            .str.split(',', expand=True)
            .apply(lambda col: col.str.strip())
            .astype(float)
        )
        
        # Remove original LL column
        df_slam = df_slam.drop(columns=['LL', 'address',	'address_db',	'postcode_clean',	'tracking_number', 'score'])
        
        df_slam.to_csv(fp_slam, index=False)
    except Exception as e:
        print(f"Error: {e}")
        print("No data. Skipping to next process")

        

def papercut_pipeline():
    
    fp_manual = os.path.join(script_directory, "Temp/10_manual.csv")
    fp_result_papercut = os.path.join(script_directory, "Temp/12_result_papercut_ooz.csv")
    fp_raw_ooz = os.path.join(script_directory, "Temp/2_raw_av_rpu.csv")
    
    try:
        if not run_avos_pipeline(fp_manual,fp_result_papercut,"papercut"):
            return

    except Exception:
        print("No data. Skipping to next proceess")
        print("")
        return

    if not os.path.exists(fp_result_papercut):
        print(f"Papercut result file not found: {fp_result_papercut}")
        print("No data. Skipping to next process")
        return
        
    df_1 = pd.read_csv(fp_result_papercut)
    df_2 = pd.read_csv(fp_raw_ooz)

    selected_column = df_1[['tracking_number', 'latitude', 'longitude']]
    merged = selected_column.merge(df_2[['tracking_number', 'waypoint_id', 'address', 'postcode']], on='tracking_number', how='left')

    # latitude is empty (NaN or blank)
    manual_av = merged[
        merged['latitude'].isna() |
        (merged['latitude'].astype(str).str.strip() == '')
    ][['tracking_number', 'address', 'postcode', 'waypoint_id']]

    # latitude is not empty
    upload_av = merged[
        merged['latitude'].notna() &
        (merged['latitude'].astype(str).str.strip() != '')
    ][['waypoint_id', 'latitude', 'longitude']]


    upload_av.to_csv(os.path.join(script_directory, "Temp/14_output_papercut.csv"), index=False)
    manual_av.to_csv(os.path.join(script_directory, "Output/3_manual.csv"), index=False)
    
    
    
    combine_csv_files([os.path.join(script_directory,"Temp/4_upload_1st_check_point.csv"),
                       os.path.join(script_directory,"Temp/6_upload_2nd_check_point.csv"),
                       os.path.join(script_directory,"Temp/11_output_casim.csv"),
                       os.path.join(script_directory, "Temp/11_output_slam.csv"),
                       os.path.join(script_directory, "Temp/14_output_papercut.csv")
                       ],
                      os.path.join(script_directory,"Output/2_upload_rpu_av.csv"))


class RoverOLAError(RuntimeError):
    """Raised when OLA rejects a request or a ROVER job fails."""


def rover_get_saved_login_credentials(path: Path) -> tuple[str, str] | None:
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


def _rover_read_secret_file(path: Path) -> str | None:
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def _rover_write_secret_file(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip(), encoding="utf-8")


def rover_get_api_key(path: Path, refresh: bool = False) -> str:
    """Load the Redash API key, prompting only when it is unavailable."""
    api_key = None if refresh else _rover_read_secret_file(path)
    if api_key:
        print(f"Using Redash API key from {path.name}")
        return api_key

    api_key = getpass.getpass("Enter the Redash API key: ").strip()
    if not api_key:
        raise RoverOLAError("A Redash API key is required.")
    _rover_write_secret_file(path, api_key)
    print(f"Redash API key saved to {path.name}")
    return api_key


def _rover_session_from_chrome(driver: Any, base_url: str) -> requests.Session:
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
            "Referer": f"{base_url}/pool/rover",
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


def _rover_is_authenticated(session: requests.Session, base_url: str) -> bool:
    """Check the same read-only endpoint used when the Rover page opens."""
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
        return isinstance(response.json(), dict)
    except requests.JSONDecodeError:
        return False


def _rover_login_to_ola_application(
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
            timeout=ROVER_REQUEST_TIMEOUT,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.RequestException:
        return False
    return _rover_is_authenticated(session, base_url)


def rover_create_authenticated_session(
    base_url: str,
    chrome_profile: Path = ROVER_DEFAULT_CHROME_PROFILE,
    login_wait: float = ROVER_DEFAULT_LOGIN_WAIT,
    show_browser: bool = False,
    login_file: Path = ROVER_DEFAULT_LOGIN_FILE,
) -> requests.Session:
    """Open Chrome, reuse/sign in to OLA, and return an authenticated session."""
    try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
    except ImportError as exc:
        raise RoverOLAError(
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
            raise RoverOLAError(
                "Could not start Chrome automation. Close any Chrome window "
                "using the RTS automation profile, then try again. "
                f"Details: {exc}"
            ) from exc

        driver.get(f"{base_url}/pool/rover")
        deadline = time.monotonic() + login_wait
        announced = False
        credentials = rover_get_saved_login_credentials(login_file)

        while time.monotonic() < deadline:
            try:
                session = _rover_session_from_chrome(driver, base_url)
            except WebDriverException as exc:
                raise RoverOLAError(
                    "The Chrome sign-in window was closed before OLA was ready."
                ) from exc
            if _rover_is_authenticated(session, base_url):
                print("OLA sign-in is active.")
                return session
            if _rover_login_to_ola_application(session, base_url, credentials):
                print(f"OLA application login used from {login_file.name}.")
                return session
            session.close()

            if not show_browser:
                raise RoverOLAError(
                    "The saved Cloudflare sign-in is missing or expired. Run once "
                    "with --login to renew it in a visible Chrome window."
                )

            if not announced:
                print(
                    "Complete the OLA sign-in in the opened Chrome window. "
                    "Use Google or the emailed login code shown by Cloudflare."
                )
                print("This is normally needed only on the first run or after expiry.")
                announced = True
            time.sleep(2)

        raise RoverOLAError(
            f"OLA sign-in was not completed within {login_wait / 60:.0f} minutes."
        )
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass



def _rover_check_response(response: requests.Response, action: str) -> None:
    """Turn HTTP and expired-login responses into useful messages."""
    response_url = response.url.lower().rstrip("/")
    login_url = "cloudflareaccess.com" in response_url or response_url.endswith("/login")

    if response.status_code in (401, 403) or login_url:
        raise RoverOLAError(
            "OLA authentication failed or expired. Run the script again and "
            "complete sign-in in the Chrome window."
        )

    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = response.text.strip()[:500]
        if detail:
            raise RoverOLAError(f"Could not {action}: {exc}. Server response: {detail}") from exc
        raise RoverOLAError(f"Could not {action}: {exc}") from exc


def _rover_json_response(response: requests.Response, action: str) -> dict[str, Any]:
    _rover_check_response(response, action)
    try:
        data = response.json()
    except requests.JSONDecodeError as exc:
        raise RoverOLAError(f"Could not {action}: OLA returned invalid JSON.") from exc
    if not isinstance(data, dict):
        raise RoverOLAError(f"Could not {action}: OLA returned an unexpected response.")
    return data


def rover_save_redash_key(
    session: requests.Session, api_key: str, base_url: str = ROVER_DEFAULT_BASE_URL
) -> None:
    print("Saving Redash API key to OLA...")
    response = session.post(
        f"{base_url}/api/redash-key",
        json={"key": api_key},
        timeout=ROVER_REQUEST_TIMEOUT,
    )
    _rover_check_response(response, "save the Redash API key")
    print("Redash API key is active.")


def rover_start_full_process(
    session: requests.Session, base_url: str = ROVER_DEFAULT_BASE_URL
) -> str:
    print("Starting the ROVER full process...")
    response = session.post(
        f"{base_url}/pool/rover-full/run",
        timeout=ROVER_REQUEST_TIMEOUT,
    )
    data = _rover_json_response(response, "start the ROVER full process")
    job_id = data.get("job_id")
    if not isinstance(job_id, str) or not job_id.strip():
        raise RoverOLAError("OLA did not return a job_id after starting the process.")
    print(f"Job ID: {job_id}")
    return job_id


def rover_wait_for_job(
    session: requests.Session,
    job_id: str,
    poll_interval: float = ROVER_DEFAULT_POLL_INTERVAL,
    max_wait: float = ROVER_DEFAULT_MAX_WAIT,
    base_url: str = ROVER_DEFAULT_BASE_URL,
) -> None:
    """Print new log lines until the OLA job reports completion."""
    cursor = 0
    started_at = time.monotonic()

    while True:
        if time.monotonic() - started_at > max_wait:
            raise RoverOLAError(
                f"ROVER job did not finish within {max_wait / 60:.0f} minutes. "
                f"Job ID: {job_id}"
            )

        response = session.get(
            f"{base_url}/api/job/{job_id}/log",
            params={"after": cursor},
            timeout=ROVER_REQUEST_TIMEOUT,
        )
        data = _rover_json_response(response, "read the ROVER job log")

        lines = data.get("lines", [])
        if isinstance(lines, list):
            for line in lines:
                print(str(line), flush=True)

        next_cursor = data.get("next", cursor)
        if isinstance(next_cursor, int) and next_cursor >= cursor:
            cursor = next_cursor

        status = str(data.get("status", "")).lower()
        if status == "done":
            print("ROVER job finished.")
            return

        if status in {"error", "failed", "cancelled", "canceled"}:
            message = (
                data.get("special_error_message")
                or data.get("special_error")
                or f"ROVER job ended with status '{status}'."
            )
            raise RoverOLAError(str(message))

        time.sleep(poll_interval)


def rover_download_result(
    session: requests.Session,
    job_id: str,
    output_file: Path,
    base_url: str = ROVER_DEFAULT_BASE_URL,
) -> Path:
    print("Downloading result_rover.zip...")
    response = session.get(
        f"{base_url}/api/job/{job_id}/download",
        stream=True,
        timeout=ROVER_REQUEST_TIMEOUT,
    )
    _rover_check_response(response, "download the ROVER result")

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
                raise RoverOLAError("OLA's download was not a valid ZIP file.")

        os.replace(partial_file, output_file)
    finally:
        if partial_file.exists():
            partial_file.unlink()

    print(f"Downloaded: {output_file}")
    return output_file


def rover_full_run_rts_av(
    output_file: Path | str = ROVER_DEFAULT_OUTPUT_FILE,
    *,
    api_key_file: Path | str = ROVER_DEFAULT_API_KEY_FILE,
    login_file: Path | str = ROVER_DEFAULT_LOGIN_FILE,
    chrome_profile: Path | str = ROVER_DEFAULT_CHROME_PROFILE,
    refresh_api_key: bool = False,
    show_browser: bool = False,
    base_url: str = ROVER_DEFAULT_BASE_URL,
    poll_interval: float = ROVER_DEFAULT_POLL_INTERVAL,
    max_wait: float = ROVER_DEFAULT_MAX_WAIT,
    login_wait: float = ROVER_DEFAULT_LOGIN_WAIT,
) -> bool:
    """Run the full OLA RTS ROVER process and download its result ZIP."""
    try:
        api_key = rover_get_api_key(Path(api_key_file), refresh_api_key)
        base_url = base_url.rstrip("/")
        session = rover_create_authenticated_session(
            base_url,
            Path(chrome_profile),
            login_wait,
            show_browser,
            Path(login_file),
        )
        try:
            rover_save_redash_key(session, api_key, base_url)
            job_id = rover_start_full_process(session, base_url)
            rover_wait_for_job(session, job_id, poll_interval, max_wait, base_url)
            rover_download_result(session, job_id, Path(output_file), base_url)
        finally:
            session.close()
        return True
    except (RoverOLAError, OSError, requests.RequestException) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return False


def run_rover_full_pipeline():
    success = rover_full_run_rts_av()
    if not success:
        return False

    zip_file = os.path.join(script_directory, "Temp", "result_rover.zip")
    output_folder = os.path.join(script_directory, "Output")

    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Extract the ZIP file
    with zipfile.ZipFile(zip_file, "r") as zip_ref:
        zip_ref.extractall(output_folder)

    print(f"Successfully extracted to:\n{output_folder}")
    return True


def run_rpu_av_pipeline():
    os.makedirs(os.path.join(script_directory, "Temp"), exist_ok=True)
    os.makedirs(os.path.join(script_directory, "Output"), exist_ok=True)

    query_normal(534,os.path.join(script_directory, "Temp/1_raw_rpu.csv"))
    query_normal(336,os.path.join(script_directory, "Temp/0_raw_rpu_pull_out.csv"))

    df = pd.read_csv(os.path.join(script_directory, "Temp/0_raw_rpu_pull_out.csv"))
    filtered_df = df[df['Pull_Out_Check'] == 'Pull out']
    selected_columns = ['tracking_id']
    final_df = filtered_df[selected_columns]
    final_df.to_csv(os.path.join(script_directory, "Output/1_pull_out_rpu.csv"), index=False)
    print("Data pull RPU route cleaning done")

    df = pd.read_csv(os.path.join(script_directory, "Temp/1_raw_rpu.csv"))
    filtered_df = df[df['av_check'] == 'AV']
    selected_columns = ['tracking_number','shipper_order_ref_no' ,'address1','postcode','address', 'waypoint_id']
    final_df = filtered_df[selected_columns]
    final_df.to_csv(os.path.join(script_directory, "Temp/2_raw_av_rpu.csv"), index=False)
    print("Data pull raw_rpu done")



    query_with_parameter(os.path.join(script_directory, "Temp/2_raw_av_rpu.csv"),
                         1235,
                         "shipper_order_ref_no",
                         os.path.join(script_directory, "Temp/3_data_rdo_pso_grn.csv"))

    
    
    
  
    print("")
    print('Matching Method - 2 reference')
    # Direct Match Multiple Address
    direct_match_multiple_address(
        os.path.join(script_directory, "Temp/2_raw_av_rpu.csv"),
        os.path.join(script_directory, "Temp/3_data_rdo_pso_grn.csv"),
        os.path.join(script_directory, "Temp/4_upload_1st_check_point.csv"),
        os.path.join(script_directory, "Temp/5_unmatch_next.csv"),
        match_columns=('shipper_order_ref_no', 'address1'),
        lookup_column=["latitude",'longitude'])


    print("")
    print('Matching Method - 1 reference')
    # Direct Match Multiple Address
    direct_match_multiple_address(
        os.path.join(script_directory, "Temp/5_unmatch_next.csv"),
        os.path.join(script_directory, "Temp/3_data_rdo_pso_grn.csv"),
        os.path.join(script_directory, "Temp/6_upload_2nd_check_point.csv"),
        os.path.join(script_directory, "Temp/7_unmatch_next.csv"),
        match_columns='address1',
        lookup_column=["latitude",'longitude'])


    df = pd.read_csv(os.path.join(script_directory, "Temp/7_unmatch_next.csv"))
    selected_columns = ['tracking_number','address' ,'postcode', 'waypoint_id']
    df[selected_columns].to_csv(os.path.join(script_directory, "Temp/8_to_avos_csgo.csv"), index=False)
  
    csgo_pipeline()
    papercut_pipeline()


def main():
    remove_files_in_folder([os.path.join(script_directory, "Temp"),os.path.join(script_directory, "Output")])
    query_normal(602,os.path.join(script_directory, "Output/1_upload_rts_shipper_requested_no_3pl.csv"))
    query_normal(1462,os.path.join(script_directory, "Output/1_upload_rts_spx_di.csv"))
    query_normal(1273,os.path.join(script_directory, "Output/1_upload_rts_kv_em.csv"))
    run_rpu_av_pipeline()
    run_rover_full_pipeline()
    open_work_environment()


if __name__ == "__main__":
    main()
