from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import edge_tts
import os, uuid, shutil
from pypdf import PdfReader 

from database import engine, Base, get_db
from models import User, Agent, InterviewSession, Message
from services.ai_engine import generate_response, generate_final_report, generate_greeting

# 1. Initialize Database & Create All Necessary Folders
Base.metadata.create_all(bind=engine)
folders = [
    "generated_audio", 
    "user_recordings", 
    "user_resumes", 
    "company_logos", 
    "user_photos"  # New folder for profile pictures
]
for folder in folders:
    os.makedirs(folder, exist_ok=True)

app = FastAPI()

app = FastAPI()

# --- ADD THIS BLOCK HERE ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins (Netlify, Vercel, Localhost)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# ---------------------------


# 2. CORS & Static Mounts
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.mount("/audio", StaticFiles(directory="generated_audio"), name="audio")
app.mount("/videos", StaticFiles(directory="user_recordings"), name="videos")
app.mount("/user_resumes", StaticFiles(directory="user_resumes"), name="user_resumes")
app.mount("/logos", StaticFiles(directory="company_logos"), name="logos")
app.mount("/photos", StaticFiles(directory="user_photos"), name="photos")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# --- HELPER: MOCK MARKETING ---
def sync_to_mailchimp(email, name):
    print(f"\n[Marketing API] 🔌 Connecting to Mailchimp...")
    print(f"[Marketing API] 📤 Subscribing: {email} ({name})")
    print(f"[Marketing API] ✅ Success.\n")

# ==========================================
# 1. AUTH & PROFILE ROUTES
# ==========================================

@app.post("/register")
def register(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    # Check existing
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(400, "Email already registered")
    
    try: hashed_pw = pwd_context.hash(password)
    except: hashed_pw = password # Fallback
    
    db.add(User(email=email, password_hash=hashed_pw))
    db.commit()
    return {"status": "ok"}

@app.post("/login")
def login(email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == email).first()
    if not user: raise HTTPException(400, "User not found")
    
    valid = False
    try: valid = pwd_context.verify(password, user.password_hash)
    except: valid = (password == user.password_hash)
    
    if not valid: raise HTTPException(400, "Invalid password")
    return {"status": "ok", "user_id": user.id}

@app.post("/update_profile")
def update_profile(user_id: int = Form(...), full_name: str = Form(""), company_name: str = Form(""), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if user:
        user.full_name = full_name
        user.company_name = company_name
        db.commit()
        return {"status": "updated"}
    return {"status": "error"}

@app.get("/get_user/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    return {
        "email": u.email, 
        "full_name": u.full_name, 
        "company": u.company_name, 
        "plan": u.plan_type, 
        "logo": u.company_logo, 
        "usage": u.interview_usage,
        "pf_photo": getattr(u, "pf_photo", "") # Safely get photo if column exists
    }

@app.post("/upgrade_plan")
def upgrade_plan(user_id: int = Form(...), db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    u.plan_type = "premium"
    db.commit()
    return {"status": "upgraded"}

@app.get("/user_history/{user_id}")
def user_history(user_id: int, db: Session = Depends(get_db)):
    # Returns a list of agents created as "History"
    agents = db.query(Agent).filter(Agent.user_id == user_id).all()
    # Mocking a created_at date since we didn't add it to Agent model
    return [{"name": a.name, "created_at": "Recent"} for a in agents]

# ==========================================
# 2. UPLOAD ROUTES (Logos & Photos)
# ==========================================

@app.post("/upload_logo")
async def upload_logo(user_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = f"logo_{user_id}_{uuid.uuid4()}.png"
    with open(f"company_logos/{filename}", "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    user = db.query(User).filter(User.id == user_id).first()
    user.company_logo = f"http://127.0.0.1:8000/logos/{filename}"
    db.commit()
    return {"status": "ok", "url": user.company_logo}

@app.post("/upload_pf")
async def upload_pf(user_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    filename = f"pf_{user_id}_{uuid.uuid4()}.png"
    with open(f"user_photos/{filename}", "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    user = db.query(User).filter(User.id == user_id).first()
    # Ensure your User model has 'pf_photo' column. 
    # If using SQLite and you added it recently, delete atlas.db to regenerate schema.
    user.pf_photo = f"http://127.0.0.1:8000/photos/{filename}"
    db.commit()
    return {"status": "ok", "url": user.pf_photo}

# ==========================================
# 3. AGENT MANAGEMENT
# ==========================================

@app.post("/create_agent")
async def create_agent(
    user_id: int = Form(...), name: str = Form(...), role: str = Form(...), 
    voice_id: str = Form("en-US-AriaNeural"), manual_rules: str = Form(None),
    file: UploadFile = File(None), db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    
    # SAAS LIMIT: Free = 1 Agent
    if user.plan_type == "free" and len(user.agents) >= 1:
        raise HTTPException(403, "Limit Reached")

    rules_text = manual_rules if manual_rules else "Standard Interview."
    if file:
        content = await file.read()
        try: rules_text = content.decode("utf-8")
        except: pass
        
    db.add(Agent(user_id=user_id, name=name, role=role, rules_context=rules_text, voice_id=voice_id))
    db.commit()
    return {"status": "ok"}

@app.get("/my_agents/{user_id}")
def get_agents(user_id: int, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    return {"agents": u.agents, "plan": u.plan_type, "usage": u.interview_usage, "logo": u.company_logo}

@app.get("/get_agent/{agent_id}")
def get_agent(agent_id: int, db: Session = Depends(get_db)):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    return {"name": a.name, "role": a.role, "logo": a.owner.company_logo}

@app.get("/agent_sessions/{agent_id}")
def get_sessions(agent_id: int, db: Session = Depends(get_db)):
    return db.query(InterviewSession).filter(InterviewSession.agent_id == agent_id).order_by(InterviewSession.start_time.desc()).all()

# ==========================================
# 4. INTERVIEW LOGIC
# ==========================================

def get_voice_for_language(lang, default_voice):
    voices = {
        "English": default_voice,
        "Burmese": "my-MM-ThihaNeural",
        "Spanish": "es-ES-ElviraNeural",
        "French": "fr-FR-DeniseNeural",
        "German": "de-DE-KatjaNeural",
        "Hindi": "hi-IN-SwaraNeural",
        "Japanese": "ja-JP-NanamiNeural"
    }
    return voices.get(lang, default_voice)

async def generate_voice(text, filename, voice_id):
    communicate = edge_tts.Communicate(text, voice_id)
    await communicate.save(f"generated_audio/{filename}")

@app.post("/start_interview")
async def start_interview(
    agent_id: int = Form(...), candidate_name: str = Form(...),
    candidate_email: str = Form(""), language: str = Form("English"),
    newsletter_optin: str = Form("false"), resume: UploadFile = File(None), 
    db: Session = Depends(get_db)
):
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    
    # SAAS LIMIT: Free = 5 Interviews
    if a.owner.plan_type == "free" and a.owner.interview_usage >= 5:
        raise HTTPException(403, "Interview Limit Reached")
    a.owner.interview_usage += 1
    
    r_text, r_url = "", ""
    if resume:
        fname = f"{uuid.uuid4()}_{resume.filename}"
        with open(f"user_resumes/{fname}", "wb") as b: shutil.copyfileobj(resume.file, b)
        r_url = f"http://127.0.0.1:8000/user_resumes/{fname}"
        try: 
            reader = PdfReader(f"user_resumes/{fname}")
            for p in reader.pages: r_text += p.extract_text()
        except: pass

    s = InterviewSession(
        agent_id=agent_id, candidate_name=candidate_name, candidate_email=candidate_email,
        language=language, resume_text=r_text[:3000], resume_path=r_url
    )
    db.add(s); db.commit(); db.refresh(s)
    
    if newsletter_optin == "true": sync_to_mailchimp(candidate_email, candidate_name)
    
    text = generate_greeting(a.role, a.rules_context, candidate_name, language, r_text)
    db.add(Message(session_id=s.id, role="ai", content=text)); db.commit()
    
    voice = get_voice_for_language(language, a.voice_id)
    fname = f"{uuid.uuid4()}.mp3"
    await generate_voice(text, fname, voice)
    
    return {"session_id": s.id, "text": text, "audio_url": f"http://127.0.0.1:8000/audio/{fname}", "logo": a.owner.company_logo}

@app.post("/chat")
async def chat(session_id: int = Form(...), agent_id: int = Form(...), user_input: str = Form(...), db: Session = Depends(get_db)):
    db.add(Message(session_id=session_id, role="user", content=user_input)); db.commit()
    
    s = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    a = db.query(Agent).filter(Agent.id == agent_id).first()
    hist = db.query(Message).filter(Message.session_id == session_id).order_by(Message.timestamp).all()
    q_count = sum(1 for m in hist if m.role == "ai")
    
    text = generate_response(a.role, a.rules_context, hist, q_count, s.language, s.resume_text)
    db.add(Message(session_id=session_id, role="ai", content=text)); db.commit()
    
    voice = get_voice_for_language(s.language, a.voice_id)
    fname = f"{uuid.uuid4()}.mp3"
    await generate_voice(text, fname, voice)
    
    return {"text": text, "audio_url": f"http://127.0.0.1:8000/audio/{fname}"}

@app.post("/upload_video")
async def upload_video(session_id: int = Form(...), file: UploadFile = File(...), db: Session = Depends(get_db)):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    fname = f"rec_{session_id}_{uuid.uuid4()}.webm"
    with open(f"user_recordings/{fname}", "wb") as b: shutil.copyfileobj(file.file, b)
    session.recording_url = f"http://127.0.0.1:8000/videos/{fname}"
    db.commit()
    return {"status": "ok"}

@app.post("/end_interview")
def end_interview(session_id: int = Form(...), emotion_log: str = Form(""), cheat_log: int = Form(0), db: Session = Depends(get_db)):
    session = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    
    # 3 Strikes Rule
    if cheat_log >= 3:
        session.final_score = 0
        session.recommendation = "REJECT (Cheating)"
        session.feedback = "Terminated due to multiple cheating violations."
        session.cheat_count = cheat_log
        db.commit()
        return {"report": {"score": 0, "recommendation": "REJECT (Cheating)", "summary": session.feedback}}

    agent = db.query(Agent).filter(Agent.id == session.agent_id).first()
    messages = db.query(Message).filter(Message.session_id == session_id).all()
    history = [{"role": m.role, "content": m.content} for m in messages]
    
    report = generate_final_report(history, agent.rules_context, emotion_log)
    
    session.final_score = report.get("score", 0)
    session.recommendation = report.get("recommendation", "Pending")
    session.feedback = report.get("summary", "")
    session.cheat_count = cheat_log
    db.commit()
    return {"report": report}

@app.post("/log_cheat")
def log_cheat(session_id: int = Form(...), db: Session = Depends(get_db)):
    s = db.query(InterviewSession).filter(InterviewSession.id == session_id).first()
    if s: 
        s.cheat_count = (s.cheat_count or 0) + 1
        db.commit()
    return {"status": "logged"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)