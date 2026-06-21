import os
import subprocess
import sys

PROXMOX_HOST = "10.1.1.6"
LXC_ID = "150"
SSH_KEY = "C:/Users/John/.ssh/id_rsa"
LOCAL_DIR = os.path.dirname(os.path.abspath(__file__))
REMOTE_TMP_DIR = "/tmp/osint-hub-deploy"
CONTAINER_DEST = "/opt/osint-hub"

def run_local(cmd, check=True):
    print(f"[LOCAL] Running: {cmd}")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"[ERROR] Local command failed: {res.stderr}")
        sys.exit(1)
    return res.stdout, res.stderr

def run_ssh(cmd, check=True):
    ssh_cmd = f'ssh -i {SSH_KEY} -o StrictHostKeyChecking=no root@{PROXMOX_HOST} "{cmd}"'
    print(f"[SSH] Running on Proxmox: {cmd}")
    res = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)
    if check and res.returncode != 0:
        print(f"[ERROR] SSH command failed:\nSTDOUT: {res.stdout}\nSTDERR: {res.stderr}")
        sys.exit(1)
    return res.stdout, res.stderr

def main():
    print("=== STARTING DEPLOYMENT ===")

    # 1. Clean remote temporary directory on Proxmox Host
    run_ssh(f"rm -rf {REMOTE_TMP_DIR} && mkdir -p {REMOTE_TMP_DIR}")

    # 2. Upload files via SCP
    # We want to copy main.py, requirements.txt, templates.py, templates/, static/
    # Exclude venv, __pycache__, database.json to preserve active data
    files_to_copy = ["main.py", "requirements.txt", "templates.py"]
    dirs_to_copy = ["templates", "static"]

    for file in files_to_copy:
        local_path = os.path.join(LOCAL_DIR, file)
        if os.path.exists(local_path):
            print(f"Uploading file: {file}")
            run_local(f'scp -i {SSH_KEY} -o StrictHostKeyChecking=no "{local_path}" root@{PROXMOX_HOST}:{REMOTE_TMP_DIR}/{file}')

    for folder in dirs_to_copy:
        local_path = os.path.join(LOCAL_DIR, folder)
        if os.path.exists(local_path):
            print(f"Uploading directory: {folder}")
            # Ensure the directory exists on remote first
            run_ssh(f"mkdir -p {REMOTE_TMP_DIR}/{folder}")
            # Run SCP recursively
            run_local(f'scp -i {SSH_KEY} -o StrictHostKeyChecking=no -r "{local_path}/*" root@{PROXMOX_HOST}:{REMOTE_TMP_DIR}/{folder}/')

    # 3. Push files inside container
    print("Pushing files into LXC container...")
    run_ssh(f"pct exec {LXC_ID} -- mkdir -p {CONTAINER_DEST}")
    run_ssh(f"pct exec {LXC_ID} -- mkdir -p {CONTAINER_DEST}/static")
    run_ssh(f"pct exec {LXC_ID} -- mkdir -p {CONTAINER_DEST}/templates")
    
    # Push individual files and directories from host temp directory
    for file in files_to_copy:
        run_ssh(f"pct push {LXC_ID} {REMOTE_TMP_DIR}/{file} {CONTAINER_DEST}/{file}")
        
    run_ssh(f"pct push {LXC_ID} {REMOTE_TMP_DIR}/templates {CONTAINER_DEST}/templates")
    run_ssh(f"pct push {LXC_ID} {REMOTE_TMP_DIR}/static {CONTAINER_DEST}/static")

    # 4. Configure Virtual Environment & dependencies inside the container
    print("Configuring virtualenv and installing python requirements in LXC container...")
    setup_env_cmds = (
        f"cd {CONTAINER_DEST} && "
        "if [ ! -d venv ]; then python3 -m venv venv; fi && "
        "./venv/bin/pip install --upgrade pip && "
        "./venv/bin/pip install -r requirements.txt"
    )
    run_ssh(f"pct exec {LXC_ID} -- bash -c '{setup_env_cmds}'")

    # 5. Set up systemd service inside the LXC container
    print("Ensuring systemd service is configured...")
    service_content = f"""[Unit]
Description=OSINT Hub Service
After=network.target

[Service]
Type=simple
WorkingDirectory={CONTAINER_DEST}
ExecStart={CONTAINER_DEST}/venv/bin/python main.py
Restart=always
RestartSec=5
Environment=PATH={CONTAINER_DEST}/venv/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
"""
    # Write to a temporary file locally, upload, and push to container systemd
    local_service_path = os.path.join(LOCAL_DIR, "osinthub.service")
    with open(local_service_path, "w") as f:
        f.write(service_content)
    
    run_local(f'scp -i {SSH_KEY} -o StrictHostKeyChecking=no "{local_service_path}" root@{PROXMOX_HOST}:{REMOTE_TMP_DIR}/osinthub.service')
    run_ssh(f"pct push {LXC_ID} {REMOTE_TMP_DIR}/osinthub.service /etc/systemd/system/osinthub.service")
    
    try:
        os.remove(local_service_path)
    except Exception:
        pass
    
    # Reload daemon and restart service
    print("Restarting OSINT Hub service...")
    run_ssh(f"pct exec {LXC_ID} -- systemctl daemon-reload")
    run_ssh(f"pct exec {LXC_ID} -- systemctl enable osinthub.service")
    run_ssh(f"pct exec {LXC_ID} -- systemctl restart osinthub.service")

    # Clean up temp files on Host
    run_ssh(f"rm -rf {REMOTE_TMP_DIR}")

    print("\n=== DEPLOYMENT COMPLETED SUCCESSFULLY ===")
    print("You can access your OSINT Hub dashboard at: http://10.1.1.250:8000")

if __name__ == "__main__":
    main()
