"""
OBJECTIVE:
This script automates the deployment of Label Studio within Cloudera AI (CML).
It handles the following tasks:
1. Environment Setup: Creates a virtual environment and installs Label Studio if not present.
2. Data Persistence: Ensures a local directory exists to store projects and annotations.
3. Network Configuration: Bridges the CAI Application Proxy by binding Label Studio to 
   the local loopback (127.0.0.1) on a dynamic port.
4. Security: Configures CSRF trusted origins to allow the Cloudera domain to bypass 
   security blocks after login.
5. Database Readiness: Runs migrations to initialize the database for new installations.
"""

import os
import subprocess
import sys
import secrets
import time
import glob

def launch():
    # --- CONFIGURATION SECTION ---
    ######################################################################################################
    # Set your unique application subdomain here - IMPORTANT - Put the same name in the App menu!
    ######################################################################################################

    MY_SUBDOMAIN = os.getenv('MY_SUBDOMAIN', 'labelstudio-default')
    ######################################################################################################

    home_dir = os.environ.get('HOME', '/home/cdsw')
    venv_path = os.path.join(home_dir, ".ls_venv")
    data_dir = os.path.join(home_dir, "label_studio_data")
    
    # Executable paths within the virtual environment
    python_bin = os.path.join(venv_path, "bin/python3")
    pip_path = os.path.join(venv_path, "bin/pip")
    
    print(f"--- DYNAMIC DEPLOYMENT OF LABEL STUDIO ON CLOUDERA AI: {MY_SUBDOMAIN} ---", flush=True)

    # 1. AUTOMATIC INSTALLATION
    # This section runs only once. Subsequent executions will skip this.
    install_env = os.environ.copy()
    install_env["PIP_USER"] = "false"
    install_env["PYTHONPATH"] = "" 

    if not os.path.exists(venv_path):
        print("[*] Creating virtual environment...", flush=True)
        subprocess.run([sys.executable, "-m", "venv", venv_path], check=True, env=install_env)
    
    if not os.path.exists(os.path.join(venv_path, "bin/label-studio")):
        print("[*] Installing Label Studio. This may take up to 20 minutes...", flush=True)
        subprocess.run([pip_path, "install", "--upgrade", "pip", "setuptools", "wheel"], check=True, env=install_env)
        subprocess.run([pip_path, "install", "label-studio", "--ignore-installed"], check=True, env=install_env)

    # Ensure the data directory exists to persist Label Studio annotations and projects
    if not os.path.exists(data_dir):
        print(f"[*] Creating data directory at {data_dir}", flush=True)
        os.makedirs(data_dir, exist_ok=True)

    # Dynamically locate manage.py regardless of the Python version installed in venv
    try:
        manage_py = glob.glob(f"{venv_path}/lib/python*/site-packages/label_studio/manage.py")[0]
    except IndexError:
        print("[-] ERROR: manage.py not found. Installation might be corrupted.", flush=True)
        return

    # 2. DYNAMIC PORT CAPTURE
    # We use CDSW_READONLY_PORT, which is the CML standard for Applications
    PORT = os.getenv('CDSW_READONLY_PORT', '8100')
    domain = os.getenv('CDSW_DOMAIN')
    app_url = f"https://{MY_SUBDOMAIN}.{domain}"
    
    # 3. RUNTIME ENVIRONMENT SETUP
    run_env = os.environ.copy()
    run_env['PYTHONUNBUFFERED'] = "1"
    run_env['DJANGO_SETTINGS_MODULE'] = 'label_studio.core.settings.label_studio'
    run_env['LABEL_STUDIO_BASE_DATA_DIR'] = data_dir
    run_env['ALLOWED_HOSTS'] = '*'
    run_env['LABEL_STUDIO_DISABLE_TELEMETRY'] = "1"

    # --- CSRF SECURITY FIX ---
    # Informs Label Studio to trust the Cloudera domain. 
    # Without this, you will receive a 403 Forbidden error upon login.
    run_env['CSRF_TRUSTED_ORIGINS'] = f"https://*.{os.getenv('CDSW_DOMAIN')}"
    
    if 'SECRET_KEY' not in run_env:
        run_env['SECRET_KEY'] = secrets.token_hex(24)

    # 4. SYSTEM CLEANUP
    # Kill any existing instances to avoid 'Address already in use' errors.
    os.system("pkill -9 -f label-studio > /dev/null 2>&1")
    time.sleep(2)

    # 5. DATABASE INITIALIZATION
    # Necessary for first-time installs to create the SQLite schema.
    print("[*] Running database migrations...", flush=True)
    subprocess.run([python_bin, manage_py, "migrate"], env=run_env, check=True)

    # 6. LAUNCH ENGINE
    # We bind to 127.0.0.1 on the CML assigned port.
    # Note: Using the Django manage.py 'runserver' is the most reliable way 
    # to bypass CML network restrictions.
    cmd = [
        python_bin, 
        manage_py, 
        "runserver", 
        f"127.0.0.1:{PORT}", 
        "--noreload"
    ]

    print("-" * 50, flush=True)
    print(f"[*] Port detected (CAI): {PORT}", flush=True)
    print(f"[*] Access URL: {app_url}", flush=True)
    print(f"[*] Command executed: {' '.join(cmd)}", flush=True)
    print("-" * 50, flush=True)
    
    try:
        # Start the subprocess and keep it running
        process = subprocess.Popen(
            cmd,
            stdout=sys.stdout, 
            stderr=sys.stderr, 
            env=run_env
        )
        process.wait()
    except KeyboardInterrupt:
        print("[*] Stopping Label Studio...", flush=True)
        process.terminate()

if __name__ == "__main__":
    launch()