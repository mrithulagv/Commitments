
# main.py
import os
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from starlette.middleware.sessions import SessionMiddleware
from starlette.status import HTTP_303_SEE_OTHER

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, create_engine, Text
)
from sqlalchemy.orm import sessionmaker, declarative_base, relationship, Session as DBSession

# Load .env if exists
from dotenv import load_dotenv
load_dotenv()

# Config
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set. Please export it before running the app.")

print("Using DB:", DATABASE_URL)

SECRET_KEY = os.getenv("SECRET_KEY")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# SQLAlchemy setup
engine = create_engine(DATABASE_URL, echo=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

# Models
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(150), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    commitments = relationship("Commitment", back_populates="user", cascade="all, delete-orphan")

class Commitment(Base):
    __tablename__ = "commitments"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    commitment_text = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="commitments")

# Create tables
print("🔥 Running create_all() now!")
Base.metadata.create_all(bind=engine)
print("🔥 Finished create_all()!")


# FastAPI app
app = FastAPI()
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# Templates & static
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# Dependency: DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Auth helpers
def hash_password(password: str) -> str:
    return pwd_context.hash(password[:72])  # bcrypt safe

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain[:72], hashed)

def get_current_user(request: Request, db: DBSession) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(User).filter(User.id == user_id).first()


# Routes --------------------------------------------------------------------

@app.get("/")
def home(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/dashboard")
    return RedirectResponse(url="/login")

# Signup
@app.get("/signup")
def signup_get(request: Request):
    return templates.TemplateResponse("signup.html", {"request": request, "error": None})

@app.post("/signup")
def signup_post(request: Request, username: str = Form(...), password: str = Form(...)):
    username = username.strip()
    if not username or not password:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Username and password required."})

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return templates.TemplateResponse("signup.html", {"request": request, "error": "Username already exists."})

    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)

# Login
@app.get("/login")
def login_get(request: Request):
    return templates.Templateresponse("login.html", {"request": request, "error": None})

@app.post("/login")
def login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials."})

    request.session["user_id"] = user.id
    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)

# Logout
@app.get("/logout")
def logout(request: Request):
    request.clear()
    return RedirectResponse(url="/login", status_code=HTTP_303_SEE_OTHER)

# Dashboard
@app.get("/dashboard")
def dashboard(request: Request, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    commitments = db.query(Commitment).filter(user_id == user.id).order_by(Commitment.deadline.asc()).all()
    return templates.TemplateResponse("dashboard.html", {"request": request, "user": user, "commitments": commitments})

# Create Commitment
@app.get("/commitments/new")
def commitment_new_get(request: Request, db = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("commitment_new.html", {"request": request, "error": None})

@app.post("/commitments/new")
def commitment_new_post(
    request: Request,
    commitment_text: str = Form(...),
    db: DBSession = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    if not commitment_text.strip():
        return templates.TemplateResponse("commitment_new.html", {"request": request, "error": "Commitment text required."})

    try:
        dt = datetime.fromisoformat(deadline)
    except Exception:
        return templates.TemplateResponse("commitment_new.html", {"request": request, "error": "Invalid deadline format."})

    pct = max(0, min(100, int(declared_confidence_pct)))

    commit = Commitment(
        user_id=user.id,
        commitment_text=commitment_text.strip(),
        declared_confidence_pct=pct,
        deadline=dt,
    )
    db.add(commit)
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)

# Resolve Commitment
@app.get("/commitments/{commitment_id}/resolve")
def commitment_resolve_get(request: Request, commitment_id: int, db: DBSession = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    commit = db.query(Commitment).filter(Commitment.id, Commitment.user_id == user.id).first()
    if not commit:
        return RedirectResponse(url="/dashboard")

    return templates.TemplateResponse("commitment_resolve.html", {"request": request, "commitment": commit, "error": None})

@app.post("/commitments/{commitment_id}/resolve")
def commitment_resolve_post(
    request: Request,
    commitment_id: int,
    status: str = Form(...),
    outcome_notes: Optional[str] = Form(None),
    db: DBSession = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login")

    commit = db.query(Commitment).filter(Commitment.id == commitment_id, Commitment == user.id).first()
    if not commit:
        return RedirectResponse(url="/dashboard")

    if commit.status != "open":
        return templates.TemplateResponse("commitment_resolve.html", {"request": request, "commitment": commit, "error": "Only open commitments can be resolved."})

    if status not in ("completed", "failed"):
        return templates.TemplateResponse("commitment_resolve.html", {"request": request, "commitment": commit, "error": "Invalid status selected."})

    commit.status = status
    commit.outcome_notes = (outcome_notes or "").strip() or None
    db.commit()

    return RedirectResponse(url="/dashboard", status_code=HTTP_303_SEE_OTHER)
