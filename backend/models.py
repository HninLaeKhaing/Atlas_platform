from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    
    # SAAS / PROFILE FIELDS
    full_name = Column(String, default="")
    company_name = Column(String, default="")
    plan_type = Column(String, default="free") # "free" or "premium"
    interview_usage = Column(Integer, default=0) 
    company_logo = Column(String, default="") # URL to custom logo
    
    agents = relationship("Agent", back_populates="owner")

class Agent(Base):
    __tablename__ = "agents"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    name = Column(String)
    role = Column(String)
    rules_context = Column(Text)
    voice_id = Column(String, default="en-US-AriaNeural")
    
    owner = relationship("User", back_populates="agents")
    sessions = relationship("InterviewSession", back_populates="agent")

class InterviewSession(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(Integer, ForeignKey("agents.id"))
    
    # Candidate Data
    candidate_name = Column(String)
    candidate_email = Column(String, default="")
    language = Column(String, default="English")
    resume_text = Column(Text, default="")
    resume_path = Column(String, default="")
    
    start_time = Column(DateTime, default=datetime.datetime.utcnow)
    
    # Results
    final_score = Column(Integer, default=0)
    recommendation = Column(String, default="Pending")
    feedback = Column(Text, default="")
    recording_url = Column(String, default="")
    cheat_count = Column(Integer, default=0) # Tracks violations
    
    agent = relationship("Agent", back_populates="sessions")
    messages = relationship("Message", back_populates="session")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("sessions.id"))
    role = Column(String)
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    session = relationship("InterviewSession", back_populates="messages")