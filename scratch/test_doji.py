import httpx
from bs4 import BeautifulSoup
import sys

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
        
    urls = [
        "https://giavang.doji.vn/",
        "https://bieudovang.com/gia-vang/doji/"
    ]
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    for url in urls:
        print(f"\n--- Fetching {url} ---")
        try:
            r = httpx.get(url, headers=headers, timeout=15, follow_redirects=True)
            print(f"Status: {r.status_code}")
            soup = BeautifulSoup(r.text, "html.parser")
            
            # Print title
            print(f"Title: {soup.title.string if soup.title else 'None'}")
            
            # Look for tables or price text
            tables = soup.find_all("table")
            print(f"Found {len(tables)} tables")
            
            # Let's print first 5 tables' headers and some content
            for idx, table in enumerate(tables[:5]):
                print(f"\nTable {idx+1}:")
                rows = table.find_all("tr")
                for r_idx, row in enumerate(rows[:10]):
                    cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                    print(f"  Row {r_idx}: {cols}")
                    
        except Exception as e:
            print(f"Error fetching {url}: {e}")

if __name__ == "__main__":
    main()
