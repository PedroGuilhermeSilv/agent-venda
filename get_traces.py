import os
import requests
from dotenv import load_dotenv
import json

load_dotenv()

public_key = os.getenv("LANGFUSE_PUBLIC_KEY").strip(' "')
secret_key = os.getenv("LANGFUSE_SECRET_KEY").strip(' "')

url = "http://localhost:3000/api/public/traces?page=1&limit=5"
response = requests.get(url, auth=(public_key, secret_key))

if response.status_code == 200:
    data = response.json()
    print("Últimos Traces (Árvore de Execução):")
    for t in data.get("data", []):
        trace_id = t.get("id")
        name = t.get("name")
        session_id = t.get("sessionId")

        print(f"\n[Trace Root] ID: {trace_id} | Name: {name} | Session: {session_id}")

        # Obter os spans e gerações deste trace
        trace_url = f"http://localhost:3000/api/public/traces/{trace_id}"
        trace_resp = requests.get(trace_url, auth=(public_key, secret_key))
        if trace_resp.status_code == 200:
            trace_data = trace_resp.json()
            observations = trace_data.get("observations", [])
            for obs in observations:
                obs_name = obs.get("name")
                obs_type = obs.get("type")
                obs_parent = obs.get("parentObservationId")
                print(f"  └─ [{obs_type}] {obs_name} (Parent: {obs_parent})")
else:
    print("Error:", response.status_code, response.text)
