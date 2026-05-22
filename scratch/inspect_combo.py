import json
import paramiko

def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect("172.16.10.38", username="root", password="AnhNhi@0610")
    
    # Lấy toàn bộ config.json
    stdin, stdout, stderr = ssh.exec_command("docker exec chatgpt2api cat /app/data/config.json")
    raw = stdout.read().decode('utf-8')
    ssh.close()
    
    cfg = json.loads(raw)
    combos = cfg.get("combo_models") or {}
    print("=== COMBO MODELS ===")
    print(json.dumps(combos, indent=2, ensure_ascii=False))
    
    # Check if ha-agent exists
    ha = combos.get("ha-agent")
    if ha:
        print(f"\nha-agent models: {ha}")
    else:
        print("\n[!] ha-agent not found in config!")
        # Print all combo keys
        print("Available combos:", list(combos.keys()))

if __name__ == "__main__":
    main()
