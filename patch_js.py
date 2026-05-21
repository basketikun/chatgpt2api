
import os, glob

# Find all JS files in web_dist
files = glob.glob('/app/web_dist/**/*.js', recursive=True)
patched = 0

for f in files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Look for the buggy logic. In minified JS it might be `if(!m.url)continue;` or `if(!e.url)continue;`
        # We can just look for `.url)continue`
        if ')continue' in content and 'url' in content:
            # A bit dangerous, let's be more specific
            # In page.tsx: `if (!m.url) continue;`
            import re
            # Matches: if(!a.url)continue;
            new_content, count = re.subn(r'if\(![a-zA-Z_]\.url\)continue;?', '', content)
            if count > 0:
                with open(f, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                patched += count
                print(f"Patched {count} occurrences in {f}")
    except Exception as e:
        pass

print(f"Total patched: {patched}")
