"""Deploy codext-inspired integration to chatgpt2api server.

Pushes all new services + modified files to the Docker container
on 172.16.10.38 and restarts the container.
"""

import os
import paramiko

HOST = "172.16.10.38"
USER = "root"
PASSWORD = "AnhNhi@0610"
CONTAINER = "chatgpt2api"
BASE = r"d:\Chatgpt\chatgpt2api"

# Files to deploy: (local_path, container_path)
FILES = [
    # New services (codext-inspired)
    ("services/account_switch_resume.py", "/app/services/account_switch_resume.py"),
    ("services/usage_snapshot_poller.py", "/app/services/usage_snapshot_poller.py"),
    ("services/project_docs_watcher.py", "/app/services/project_docs_watcher.py"),
    # Modified files
    ("api/app.py", "/app/api/app.py"),
    ("api/accounts.py", "/app/api/accounts.py"),
    ("services/config.py", "/app/services/config.py"),
    ("services/model_cooldown.py", "/app/services/model_cooldown.py"),
    ("services/protocol/openai_v1_chat_complete.py", "/app/services/protocol/openai_v1_chat_complete.py"),
]


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"Connecting to {HOST} as {USER}...")
        ssh.connect(HOST, username=USER, password=PASSWORD, timeout=10)
        print("Connected.")

        sftp = ssh.open_sftp()

        for local_rel, container_path in FILES:
            local_path = os.path.join(BASE, local_rel)
            if not os.path.exists(local_path):
                print(f"  SKIP (not found): {local_rel}")
                continue

            tmp_remote = f"/tmp/{os.path.basename(local_rel)}"
            print(f"  Upload: {local_rel} -> {tmp_remote}")
            sftp.put(local_path, tmp_remote)

            print(f"  Copy:   {tmp_remote} -> {CONTAINER}:{container_path}")
            stdin, stdout, stderr = ssh.exec_command(
                f"docker cp {tmp_remote} {CONTAINER}:{container_path}"
            )
            err = stderr.read().decode("utf-8", errors="ignore")
            if err:
                print(f"  WARN: {err.strip()}")

        sftp.close()

        print("\nRestarting container...")
        stdin, stdout, stderr = ssh.exec_command(f"docker restart {CONTAINER}")
        out = stdout.read().decode("utf-8", errors="ignore")
        print(f"  Status: {out.strip() or 'OK'}")

        print("\nDeployment complete!")

    except Exception as exc:
        print(f"ERROR: {exc}")
    finally:
        ssh.close()


if __name__ == "__main__":
    main()
