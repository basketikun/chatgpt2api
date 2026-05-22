
import urllib.request
try:
    print("Trying 172.16.10.38:8005...")
    r = urllib.request.urlopen("http://172.16.10.38:8005/", timeout=5)
    print("Success! " + r.read().decode('utf-8')[:50])
except Exception as e:
    print("Failed: " + str(e))

try:
    print("Trying vn-mcp-hub:8005...")
    r = urllib.request.urlopen("http://vn-mcp-hub:8005/", timeout=5)
    print("Success! " + r.read().decode('utf-8')[:50])
except Exception as e:
    print("Failed: " + str(e))
