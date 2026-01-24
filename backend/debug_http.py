import requests
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

print(f"🔑 Testing Key: {API_KEY[:10]}...")

# 1. Try Flash Model
url_flash = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={API_KEY}"
# 2. Try Pro Model (Fallback)
url_pro = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={API_KEY}"

headers = {"Content-Type": "application/json"}
data = {"contents": [{"parts": [{"text": "Hello, are you working?"}]}]}

print("\n--- ATTEMPT 1: Gemini 1.5 Flash ---")
try:
    response = requests.post(url_flash, headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("✅ SUCCESS! Response:", response.json()['candidates'][0]['content']['parts'][0]['text'])
    else:
        print("❌ ERROR:", response.text)
except Exception as e:
    print("CRASH:", e)

print("\n--- ATTEMPT 2: Gemini Pro ---")
try:
    response = requests.post(url_pro, headers=headers, json=data)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 200:
        print("✅ SUCCESS! Response:", response.json()['candidates'][0]['content']['parts'][0]['text'])
    else:
        print("❌ ERROR:", response.text)
except Exception as e:
    print("CRASH:", e)