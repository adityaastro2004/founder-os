import urllib.request, json
req = urllib.request.Request(
    "http://localhost:8000/api/test/plan",
    data=json.dumps({"message": "Plan my week!"}).encode('utf-8'),
    headers={"Content-Type": "application/json"}
)
try:
    with urllib.request.urlopen(req) as response:
        data = json.loads(response.read().decode('utf-8'))
        print("Model:", data['model'])
        print("\nRAW MARKDOWN:\n=====\n" + data['raw_markdown'] + "\n=====\n")
        print("Success Criteria:", data['plan']['success_criteria'])
except Exception as e:
    print("Error:", e)
