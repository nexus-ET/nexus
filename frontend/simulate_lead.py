#!/usr/bin/env python3
import os
import json
import time
import sys
import urllib.request

# ⚙️ Flexible Endpoint Discovery
# If you pass a specific full URL path via the terminal, it takes absolute precedence!
CLI_INPUT = sys.argv[1] if len(sys.argv) > 1 else ""

if CLI_INPUT and (CLI_INPUT.startswith("http://") or CLI_INPUT.startswith("https://")):
    # 🎯 Direct path override bypass
    TARGET_ENDPOINT = CLI_INPUT
else:
    # Environment config fallback layer
    ENV_TARGET_URL = os.environ.get("VITE_API_URL") or os.environ.get("NEXUS_API_URL") or "http://api-service/api/v1"
    TARGET_ENDPOINT = f"{ENV_TARGET_URL.rstrip('/')}/leads"

# 📦 Production payload data blueprint
mock_live_lead = {
    "full_name": "Arun Jai Prasad",
    "email": "Arun.jai@edutrust.in",
    "institution": "Alpha Institute of Technology",
    "program_interest": "Quantum Machine Learning",
    "status": "PROCESSING",
    "score": 94,
    "agent_execution_state": "THINKING",
    "summary": "User submitted form confirmation targeting deep tier computing research matrices.",
    "next_action": "Compile localized academic outreach packet and execute semantic email drop sequences."
}

def dispatch_payload():
    print("🚀 Initializing transmission payload pipeline connection...")
    print(f"📡 Target Route Address: {TARGET_ENDPOINT}\n")
    
    json_data = json.dumps(mock_live_lead).encode('utf-8')
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
        "ngrok-skip-browser-warning": "true"  # 👈 ADD THIS LINE
    }
    
    req = urllib.request.Request(TARGET_ENDPOINT, data=json_data, headers=headers, method='POST')
    
    try:
        start_time = time.time()
        with urllib.request.urlopen(req) as response:
            status_code = response.getcode()
            response_body = response.read().decode('utf-8')
            latency = (time.time() - start_time) * 1000
            
            print("✅ CONNECTION STATE: SUCCESS")
            print(f"📊 HTTP Status Return Code: {status_code}")
            print(f"⏱️ Network Latency: {latency:.2f}ms")
            print(f"📥 Server Response:\n{response_body}\n")
            print("✨ Payload cleanly intercepted by the backend router matrix!")
            
    except urllib.error.HTTPError as e:
        print("❌ CONNECTION STATE: REJECTED BY BACKEND SERVER")
        print(f"🚨 Status Code: {e.code}")
        print(f"📜 Response Error Log Readout: {e.read().decode('utf-8')}")
    except urllib.error.URLError as e:
        print("❌ CONNECTION STATE: HARD NETWORK FAILURE")
        print(f"🚨 Reason: {e.reason}")

if __name__ == "__main__":
    dispatch_payload()