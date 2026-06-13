from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr
from datetime import datetime
from db import get_db
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth")

class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

@router.post("/signup")
async def signup(data: SignupRequest):
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    conn = get_db()
    c = conn.cursor()

    existing = c.execute("SELECT id FROM users WHERE email = ?", (data.email,)).fetchone()
    if existing:
        conn.close()
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    hashed = hash_password(data.password)
    c.execute(
        "INSERT INTO users (email, hashed_password, name, created_at) VALUES (?, ?, ?, ?)",
        (data.email, hashed, data.name, datetime.utcnow().isoformat())
    )
    conn.commit()
    user_id = c.lastrowid
    conn.close()

    token = create_access_token(user_id, data.email)
    return {"token": token, "user": {"id": user_id, "name": data.name, "email": data.email}}

@router.post("/login")
async def login(data: LoginRequest):
    conn = get_db()
    c = conn.cursor()

    user = c.execute("SELECT * FROM users WHERE email = ?", (data.email,)).fetchone()
    conn.close()

    if not user or not verify_password(data.password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(user["id"], user["email"])
    return {"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}

@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    user = c.execute(
        "SELECT id, name, email, created_at FROM users WHERE id = ?",
        (current_user["user_id"],)
    ).fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"id": user["id"], "name": user["name"], "email": user["email"], "created_at": user["created_at"]}

@router.get("/history")
async def get_history(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    c = conn.cursor()
    rows = c.execute(
        "SELECT id, filename, score, verdict, created_at FROM analysis_history WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
        (current_user["user_id"],)
    ).fetchall()
    conn.close()
    return {"history": [dict(r) for r in rows]}
