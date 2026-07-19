import urllib.request
import json
import sys

# Default repo URL
github_url = sys.argv[1] if len(sys.argv) > 1 else "https://github.com/facebook/react"

url = "http://127.0.0.1:8000/workspaces/index"
data = json.dumps({"githubUrl": github_url}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')

try:
    print(f"Sending request to clone and index {github_url}...")
    with urllib.request.urlopen(req, timeout=300) as response:
        resp_data = json.loads(response.read().decode())
        print("Success!")
        print(json.dumps(resp_data, indent=2))
except Exception as e:
    print(f"Failed: {e}")
