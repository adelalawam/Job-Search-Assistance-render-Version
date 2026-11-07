import os, re, uuid, shutil, secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from passlib.context import CryptContext
from jose import jwt, JWTError
from dotenv import load_dotenv

load_dotenv()
BASE = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE / "data"))
UPLOAD_DIR = DATA_DIR / "private_uploads"
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'jobs.db'}")
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
SECRET = os.getenv("SECRET_KEY", "CHANGE_THIS_SECRET_BEFORE_DEPLOYMENT")
ALGORITHM = "HS256"
TOKEN_HOURS = int(os.getenv("TOKEN_HOURS", "72"))

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(160), default="")
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")

class Profile(Base):
    __tablename__ = "profiles"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    headline = Column(String(240), default="")
    skills = Column(Text, default="")
    experience = Column(Text, default="")
    education = Column(Text, default="")
    languages = Column(Text, default="")
    industries = Column(Text, default="")
    preferred_roles = Column(Text, default="")
    countries = Column(Text, default="Germany")
    locations = Column(Text, default="")
    work_mode = Column(String(40), default="Any")
    employment_type = Column(String(40), default="Full-time")
    salary_min = Column(Integer, nullable=True)
    min_match = Column(Integer, default=80)
    cv_filename = Column(String(255), default="")
    cv_text = Column(Text, default="")
    user = relationship("User", back_populates="profile")

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    title = Column(String(300), nullable=False)
    company = Column(String(250), default="Unknown employer")
    location = Column(String(250), default="")
    country = Column(String(120), default="")
    work_mode = Column(String(40), default="Unknown")
    employment_type = Column(String(80), default="")
    description = Column(Text, default="")
    requirements = Column(Text, default="")
    url = Column(Text, default="")
    source = Column(String(100), default="Manual")
    external_id = Column(String(300), nullable=True)
    salary_min = Column(Integer, nullable=True)
    salary_max = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = ()

class Application(Base):
    __tablename__ = "applications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), index=True, nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    status = Column(String(40), default="Saved")
    cover_letter = Column(Text, default="")
    notes = Column(Text, default="")
    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    job = relationship("Job")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Job Search Assistance API", version="1.0.0")
app.mount("/static", StaticFiles(directory=BASE / "app" / "static"), name="static")

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def token_for(user):
    payload = {"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)

def current_user(token: str = Depends(oauth2), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
        uid = int(payload.get("sub"))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    user = db.query(User).filter(User.id == uid).first()
    if not user: raise HTTPException(status_code=401, detail="Account not found")
    return user

def profile_for(db, user):
    p = db.query(Profile).filter(Profile.user_id == user.id).first()
    if not p:
        p = Profile(user_id=user.id)
        db.add(p); db.commit(); db.refresh(p)
    return p

def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".txt": return path.read_text(encoding="utf-8", errors="ignore")[:100000]
        if suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            return "\n".join((page.extract_text() or "") for page in reader.pages)[:100000]
        if suffix in (".docx", ".doc"):
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs)[:100000]
    except Exception:
        return ""
    return ""

def tokens(s):
    return set(re.findall(r"[a-zA-Z0-9+#.]{2,}", (s or "").lower()))

def score_job(profile, job):
    # Transparent heuristic score, not a claim of guaranteed qualification.
    cv = " ".join([profile.headline or "", profile.skills or "", profile.experience or "",
                   profile.education or "", profile.languages or "", profile.industries or "",
                   profile.preferred_roles or "", profile.cv_text or ""])
    jobtxt = " ".join([job.title or "", job.description or "", job.requirements or ""])
    a, b = tokens(cv), tokens(jobtxt)
    overlap = len(a & b) / max(1, len(b))
    title_terms = tokens((profile.preferred_roles or "") + " " + (profile.headline or ""))
    job_terms = tokens(job.title)
    title_fit = len(title_terms & job_terms) / max(1, len(job_terms)) if title_terms else 0.35
    skill_terms = tokens(profile.skills or "")
    skill_fit = len(skill_terms & b) / max(1, len(skill_terms)) if skill_terms else overlap
    exp_terms = tokens(profile.experience or "")
    exp_fit = len(exp_terms & b) / max(1, len(exp_terms)) if exp_terms else overlap
    # weighted blend; cap avoids overstating confidence from sparse profiles
    raw = 100 * (0.40 * skill_fit + 0.25 * title_fit + 0.20 * overlap + 0.15 * exp_fit)
    if len(a) < 12: raw = min(raw, 65)
    return round(max(0, min(99, raw)), 1)

class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=100)
    name: str = Field(default="", max_length=160)

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class ProfileIn(BaseModel):
    headline: str = ""; skills: str = ""; experience: str = ""; education: str = ""
    languages: str = ""; industries: str = ""; preferred_roles: str = ""
    countries: str = "Germany"; locations: str = ""; work_mode: str = "Any"
    employment_type: str = "Full-time"; salary_min: Optional[int] = None; min_match: int = 80

class JobIn(BaseModel):
    title: str; company: str = "Unknown employer"; location: str = ""; country: str = ""
    work_mode: str = "Unknown"; employment_type: str = ""; description: str = ""
    requirements: str = ""; url: str = ""; source: str = "Manual"
    salary_min: Optional[int] = None; salary_max: Optional[int] = None

class ApplicationIn(BaseModel):
    job_id: int
    status: str = "Saved"

@app.get("/")
def index():
    return FileResponse(BASE / "app" / "static" / "index.html")

@app.get("/health")
def health(): return {"status": "ok", "service": "Job Search Assistance"}

@app.post("/api/auth/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    email = data.email.lower()
    if db.query(User).filter(User.email == email).first(): raise HTTPException(409, "An account with this email already exists")
    user = User(email=email, name=data.name.strip(), password_hash=pwd.hash(data.password))
    db.add(user); db.commit(); db.refresh(user)
    profile_for(db, user)
    return {"access_token": token_for(user), "token_type": "bearer", "name": user.name, "email": user.email}

@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email.lower()).first()
    if not user or not pwd.verify(data.password, user.password_hash): raise HTTPException(401, "Email or password is incorrect")
    return {"access_token": token_for(user), "token_type": "bearer", "name": user.name, "email": user.email}

@app.get("/api/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.name, "email": user.email}

@app.get("/api/profile")
def get_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = profile_for(db, user)
    return {k: getattr(p,k) for k in ["headline","skills","experience","education","languages","industries","preferred_roles","countries","locations","work_mode","employment_type","salary_min","min_match","cv_filename"]}

@app.put("/api/profile")
def put_profile(data: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = profile_for(db, user)
    for k,v in data.model_dump().items(): setattr(p,k,v)
    p.min_match = max(0, min(100, p.min_match))
    db.commit()
    return {"ok": True}

@app.post("/api/profile/cv")
async def upload_cv(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in [".pdf",".docx",".doc",".txt"]: raise HTTPException(400, "Upload a PDF, DOCX, DOC or TXT file")
    if file.content_type and file.content_type not in ["application/pdf","application/vnd.openxmlformats-officedocument.wordprocessingml.document","application/msword","text/plain","application/octet-stream"]:
        raise HTTPException(400, "Unsupported file type")
    content = await file.read()
    if len(content) > 8 * 1024 * 1024: raise HTTPException(413, "Maximum CV size is 8 MB")
    safe_name = f"user_{user.id}_{uuid.uuid4().hex}{ext}"
    path = UPLOAD_DIR / safe_name
    path.write_bytes(content)
    text = extract_text(path)
    p = profile_for(db,user)
    if p.cv_filename:
        old = UPLOAD_DIR / p.cv_filename
        if old.exists(): old.unlink()
    p.cv_filename = safe_name
    p.cv_text = text
    db.commit()
    return {"ok": True, "filename": file.filename, "text_extracted": bool(text), "characters": len(text), "message": "CV stored in your private account area."}

@app.delete("/api/profile/cv")
def delete_cv(user: User = Depends(current_user), db: Session = Depends(get_db)):
    p=profile_for(db,user)
    if p.cv_filename:
        f=UPLOAD_DIR/p.cv_filename
        if f.exists(): f.unlink()
    p.cv_filename=""; p.cv_text=""; db.commit()
    return {"ok":True}

@app.post("/api/jobs")
def add_job(data: JobIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    # Users can add a vacancy URL/details manually. Shared job catalog is deduplicated by URL/title/company.
    if data.url:
        existing=db.query(Job).filter(Job.url==data.url).first()
        if existing: return {"id":existing.id,"duplicate":True}
    job=Job(**data.model_dump())
    db.add(job); db.commit(); db.refresh(job)
    return {"id":job.id,"duplicate":False}

@app.get("/api/jobs")
def list_jobs(q: str = "", limit: int = 100, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p=profile_for(db,user)
    jobs=db.query(Job).order_by(Job.created_at.desc()).limit(min(limit,250)).all()
    out=[]
    for j in jobs:
        if q and q.lower() not in (j.title+" "+j.company+" "+j.location+" "+j.description).lower(): continue
        score=score_job(p,j)
        out.append({"id":j.id,"title":j.title,"company":j.company,"location":j.location,"country":j.country,"work_mode":j.work_mode,"employment_type":j.employment_type,"description":j.description[:500],"requirements":j.requirements[:500],"url":j.url,"source":j.source,"match":score,"meets_threshold":score >= (p.min_match or 80)})
    out.sort(key=lambda x:x["match"], reverse=True)
    return {"jobs":out,"threshold":p.min_match or 80}

@app.post("/api/applications")
def create_application(data: ApplicationIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    job=db.query(Job).filter(Job.id==data.job_id).first()
    if not job: raise HTTPException(404,"Job not found")
    old=db.query(Application).filter(Application.user_id==user.id,Application.job_id==job.id).first()
    if old: raise HTTPException(409,"You already saved this job")
    a=Application(user_id=user.id,job_id=job.id,status=data.status)
    db.add(a);db.commit();db.refresh(a)
    return {"id":a.id,"status":a.status}

@app.get("/api/applications")
def applications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows=db.query(Application).filter(Application.user_id==user.id).order_by(Application.created_at.desc()).all()
    return [{"id":a.id,"job_id":a.job_id,"title":a.job.title,"company":a.job.company,"location":a.job.location,"url":a.job.url,"status":a.status,"cover_letter":a.cover_letter,"notes":a.notes,"created_at":a.created_at.isoformat()} for a in rows]

@app.patch("/api/applications/{app_id}")
def update_application(app_id:int, status_value:str=Form(...), notes:str=Form(""), user:User=Depends(current_user), db:Session=Depends(get_db)):
    a=db.query(Application).filter(Application.id==app_id,Application.user_id==user.id).first()
    if not a: raise HTTPException(404,"Application not found")
    allowed={"Saved","Preparing","Applied","Interview","Rejected","Offer","Withdrawn"}
    if status_value not in allowed: raise HTTPException(400,"Invalid application status")
    a.status=status_value;a.notes=notes
    if status_value=="Applied" and not a.applied_at:a.applied_at=datetime.utcnow()
    db.commit();return {"ok":True}

@app.post("/api/applications/{app_id}/cover-letter")
def cover_letter(app_id:int, user:User=Depends(current_user), db:Session=Depends(get_db)):
    a=db.query(Application).filter(Application.id==app_id,Application.user_id==user.id).first()
    if not a: raise HTTPException(404,"Application not found")
    p=profile_for(db,user); j=a.job
    # Safe local draft from profile; AI-provider integration can be added with server-side credentials.
    name=user.name or "Candidate"
    skills=p.skills or "relevant professional skills"
    exp=p.experience or "my professional experience"
    a.cover_letter=f"""Dear Hiring Team,\n\nI am writing to express my interest in the {j.title} position at {j.company}. My background includes {exp}. I can bring strengths in {skills}, and I am interested in applying these capabilities to the responsibilities described in your vacancy.\n\nI would welcome the opportunity to discuss how my experience and approach could contribute to your team. Thank you for your time and consideration.\n\nKind regards,\n{name}"""
    db.commit()
    return {"cover_letter":a.cover_letter}

@app.get("/api/dashboard")
def dashboard(user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=profile_for(db,user)
    apps=db.query(Application).filter(Application.user_id==user.id).all()
    jobs=db.query(Job).all()
    scores=[score_job(p,j) for j in jobs]
    threshold=p.min_match or 80
    return {"jobs_found":len(jobs),"strong_matches":sum(1 for s in scores if s>=threshold),"applications":len(apps),"profile_readiness":min(100, sum(bool(getattr(p,k)) for k in ["headline","skills","experience","education","languages","cv_text"])*100//6),"threshold":threshold}

@app.delete("/api/account")
def delete_account(user:User=Depends(current_user),db:Session=Depends(get_db)):
    p=profile_for(db,user)
    if p.cv_filename:
        f=UPLOAD_DIR/p.cv_filename
        if f.exists():f.unlink()
    db.query(Application).filter(Application.user_id==user.id).delete()
    db.delete(p);db.delete(user);db.commit()
    return {"ok":True}

@app.get("/api/connectors/status")
def connector_status():
    return {"greenhouse":"Public job-board API adapter can be configured in a future connector module","lever":"Public postings API adapter can be configured in a future connector module","automatic_submission":"Not enabled: employer workflows differ and require authorized integrations and user confirmation."}
