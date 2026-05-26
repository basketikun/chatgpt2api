import subprocess
import base64
import sys

def upload_file(local_path, remote_path):
    print(f"Uploading {local_path} to {remote_path}...")
    with open(local_path, "rb") as f:
        data = f.read()
    b64_data = base64.b64encode(data).decode("ascii")
    
    # Run plink command, feeding base64 data and decoding it on the server
    cmd = [
        "plink",
        "-ssh",
        "root@172.16.10.38",
        "-pw",
        "AnhNhi@0610",
        f"base64 -d > {remote_path}"
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = proc.communicate(input=b64_data)
    
    if proc.returncode != 0:
        print(f"Error uploading {local_path}: {stderr}")
        sys.exit(1)
    print("Upload successful.")

if __name__ == "__main__":
    upload_file(
        "D:\\Chatgpt\\chatgpt2api\\captcha-solver\\src\\auto_login.py",
        "/root/auto_login.py"
    )
    upload_file(
        "D:\\Chatgpt\\chatgpt2api\\captcha-solver\\src\\chatgpt_login.py",
        "/root/chatgpt_login.py"
    )
