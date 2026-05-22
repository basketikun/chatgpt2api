
import os, glob

files = glob.glob('/app/web_dist/**/*.js', recursive=True)
patched = 0

for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
            
        if '172.16.10.38:8005' in content:
            new_content = content.replace('"http://172.16.10.38:8005"', '""')
            with open(f, 'w', encoding='utf-8') as file:
                file.write(new_content)
            patched += 1
            print(f"Patched {f}")
    except Exception as e:
        pass

print(f"Total patched: {patched}")
