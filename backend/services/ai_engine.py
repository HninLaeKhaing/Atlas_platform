
import google.generativeai as genai
import os, json, time
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
API_KEYS = [
    os.getenv("GEMINI_API_KEY"),
    "AIzaSyDWWUqWH-mQoS6kkZyxNayIR5xKbakeDiY",
    "AIzaSyCMzAvRNZtreMXTwfJfXMs6mdIMyZ1w5S"
]
VALID_KEYS = [k for k in API_KEYS if k and "YOUR_" not in k]
if not VALID_KEYS: VALID_KEYS = [os.getenv("GEMINI_API_KEY")]

current_key_index = 0
MODEL_NAME = 'gemini-2.5-flash'
model = None # Global variable

def configure_genai():
    """Configures Google AI with the current active key."""
    global current_key_index, model
    try:
        current_key = VALID_KEYS[current_key_index]
        genai.configure(api_key=current_key)
        model = genai.GenerativeModel(MODEL_NAME)
        # print(f"🔑 Switched to Key Index: {current_key_index}")
    except Exception as e:
        print(f"❌ Configuration Error: {e}")

def rotate_key():
    """Switches to the next API Key in the list."""
    global current_key_index
    current_key_index = (current_key_index + 1) % len(VALID_KEYS)
    configure_genai()

# Initialize first time
configure_genai()

# --- HELPERS ---
def format_history(history):
    transcript = ""
    try:
        for msg in history:
            if isinstance(msg, dict):
                role = msg.get('role', 'unknown')
                content = msg.get('content', '')
            else:
                role = getattr(msg, 'role', 'unknown')
                content = getattr(msg, 'content', '')
            sender = "INTERVIEWER" if role == "ai" else "CANDIDATE"
            transcript += f"{sender}: {content}\n"
    except: pass
    return transcript

def safe_generate(prompt):
    global model
    if not model: configure_genai()
    
    max_retries = len(VALID_KEYS) * 2
    for _ in range(max_retries):
        try:
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e) or "403" in str(e): 
                rotate_key()
            elif "404" in str(e):
                # Fallback to Pro if Flash fails
                model = genai.GenerativeModel('gemini-pro')
            else:
                print(f"AI Error: {e}")
                return None
    return "I am having trouble connecting. Let's move on."

# --- EXPORTS ---
def generate_greeting(role, rules, candidate_name, language, resume_text):
    prompt = f"ROLE: {role}\nCONTEXT: {rules}\nLANG: {language}\nCANDIDATE: {candidate_name}\nRESUME: {resume_text}\nTASK: Introduce yourself in {language}. If resume provided, mention a detail. Ask first question."
    return safe_generate(prompt) or f"Hello {candidate_name}, I am ready."

def generate_response(role, rules, history, q_count, language, resume_text):
    chat_log = format_history(history)
    instr = "Ask next question." if q_count < 7 else f"Conclude interview in {language}."
    prompt = f"ACT AS: {role}\nRULES: {rules}\nLANG: {language}\nRESUME: {resume_text}\nHISTORY: {chat_log}\nINSTRUCTION: {instr}\nCONSTRAINT: Short spoken response (max 30 words)."
    return safe_generate(prompt) or "Moving on."

def generate_final_report(history, rules, emotion_log):
    transcript = format_history(history)
    prompt = f"Evaluator.\nRULES: {rules}\nTRANSCRIPT: {transcript}\nBODY LANG: {emotion_log}\nTASK: Evaluate.\nJSON ONLY: {{ 'score': 85, 'recommendation': 'Strongly Recommend', 'summary': '...' }}"
    for _ in range(3):
        try:
            raw = safe_generate(prompt)
            if not raw: continue
            clean = raw.replace("```json", "").replace("```", "").strip()
            return json.loads(clean[clean.find('{'):clean.rfind('}')+1])
        except: pass
    return {"score": 0, "recommendation": "Error", "summary": "Processing failed."}