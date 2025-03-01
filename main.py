from fastapi import FastAPI, Request, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlalchemy import create_engine, Column, Integer, String, Date, Text, and_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from sqlalchemy import text

# === DATABASE SETUP ===
# MySQL 접속정보를 본인 환경에 맞게 수정하세요.
DATABASE_URL = "mysql+mysqlconnector://root:Tmdrnjs159!@localhost/emr_db"

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# EMR 기록 모델
class EMR(Base):
    __tablename__ = 'emrs'
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    birth_date = Column(Date, nullable=False)      # 생년월일
    visit_date = Column(Date, nullable=False)        # 방문날짜
    symptoms = Column(Text, nullable=False)          # 증상
    treatment = Column(Text, nullable=False)         # 치료

# 환자 접수표 모델
class Registration(Base):
    __tablename__ = 'registrations'
    id = Column(Integer, primary_key=True, index=True)  # 순번 (Auto Increment)
    patient_name = Column(String(100), nullable=False)
    status = Column(String(100), nullable=False)

# 모든 테이블 생성 (이미 생성되어 있다면 무시됨)
Base.metadata.create_all(bind=engine)

# === FASTAPI SETUP ===
app = FastAPI()

# 정적파일 경로 설정
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# 데이터베이스 세션 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# === 1. 로그인 화면 ===
@app.get("/", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    # 예제에서는 "admin" 사용자만 허용합니다.
    if username == "admin" and password == "admin":
        response = RedirectResponse(url="/dashboard", status_code=302)
        return response
    else:
        return templates.TemplateResponse("login.html", {"request": request, "error": "아이디 또는 비밀번호가 올바르지 않습니다."})

# === 2. 대시보드 화면 (카테고리 선택 및 검색 기능) ===
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    category: str = "진료부",  # 기본값은 진료부
    query: str = "",
    db: Session = Depends(get_db)
):
    patients = []
    if query:
        # 모든 EMR 기록에서 이름 검색 (필요시 카테고리별 추가 필터링 가능)
        patients = (
            db.query(EMR.name, EMR.birth_date)
            .filter(EMR.name.like(f"%{query}%"))
            .group_by(EMR.name, EMR.birth_date)
            .all()
        )
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "category": category,
        "patients": patients,
        "query": query
    })

# === 3. EMR 신규 작성 (진료부 전용) ===
@app.get("/emr/new", response_class=HTMLResponse)
async def new_emr(request: Request):
    return templates.TemplateResponse("new_emr.html", {"request": request})

@app.post("/emr/new")
async def create_emr(
    request: Request,
    name: str = Form(...),
    birth_date: str = Form(...),
    visit_date: str = Form(...),
    symptoms: str = Form(...),
    treatment: str = Form(...),
    db: Session = Depends(get_db)
):
    try:
        birth_date_obj = datetime.strptime(birth_date, "%Y-%m-%d").date()
        visit_date_obj = datetime.strptime(visit_date, "%Y-%m-%d").date()
    except ValueError:
        return templates.TemplateResponse("new_emr.html", {"request": request, "error": "날짜 형식이 올바르지 않습니다."})
    
    new_record = EMR(
        name=name,
        birth_date=birth_date_obj,
        visit_date=visit_date_obj,
        symptoms=symptoms,
        treatment=treatment
    )
    db.add(new_record)
    db.commit()
    db.refresh(new_record)
    return RedirectResponse(url="/dashboard", status_code=302)

# === 4. 특정 환자의 EMR 조회 및 날짜별 내비게이션 ===
@app.get("/patient", response_class=HTMLResponse)
async def view_patient(
    request: Request,
    name: str,
    birth_date: str,
    index: int = 0,
    db: Session = Depends(get_db)
):
    try:
        birth_date_obj = datetime.strptime(birth_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 생년월일 형식입니다.")

    records = (
        db.query(EMR)
        .filter(and_(EMR.name == name, EMR.birth_date == birth_date_obj))
        .order_by(EMR.visit_date.desc())
        .all()
    )
    if not records:
        raise HTTPException(status_code=404, detail="해당 환자의 EMR이 없습니다.")
    
    if index < 0 or index >= len(records):
        index = 0
    current_record = records[index]
    
    record_data = {
        "id": current_record.id,
        "name": current_record.name,
        "birth_date": current_record.birth_date.strftime("%Y-%m-%d"),
        "visit_date": current_record.visit_date.strftime("%Y-%m-%d"),
        "symptoms": current_record.symptoms,
        "treatment": current_record.treatment
    }
    
    return templates.TemplateResponse(
        "view_emr.html",
        {
            "request": request,
            "record": record_data,
            "index": index,
            "total": len(records),
            "name": name,
            "birth_date": current_record.birth_date.strftime("%Y-%m-%d")
        }
    )

# === 5. 환자 접수표 관련 기능 ===

# 접수표 페이지: 등록된 모든 접수 목록 표시
@app.get("/registration", response_class=HTMLResponse)
async def registration_page(request: Request, db: Session = Depends(get_db)):
    regs = db.query(Registration).order_by(Registration.id).all()
    return templates.TemplateResponse("registration.html", {"request": request, "registrations": regs})

# 새 접수 추가 (환자이름만 입력받고 상태는 기본값 "대기"로 설정)
@app.post("/registration/add")
async def registration_add(
    request: Request,
    patient_name: str = Form(...),
    db: Session = Depends(get_db)
):
    new_reg = Registration(patient_name=patient_name, status="대기")
    db.add(new_reg)
    db.commit()
    db.refresh(new_reg)
    return RedirectResponse(url="/registration", status_code=302)

# 접수 내용 수정 (환자이름과 상태 모두 수정 가능)
@app.post("/registration/update")
async def registration_update(
    request: Request,
    id: int = Form(...),
    patient_name: str = Form(...),
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    reg = db.query(Registration).filter(Registration.id == id).first()
    if reg:
        reg.patient_name = patient_name
        reg.status = status
        db.commit()
    return RedirectResponse(url="/registration", status_code=302)

# 접수 삭제
@app.post("/registration/delete")
async def registration_delete(
    request: Request,
    id: int = Form(...),
    db: Session = Depends(get_db)
):
    reg = db.query(Registration).filter(Registration.id == id).first()
    if reg:
        db.delete(reg)
        db.commit()
    return RedirectResponse(url="/registration", status_code=302)

# **환자 접수표 초기화: 모든 데이터 삭제 및 순번 리셋**
@app.post("/registration/reset")
async def registration_reset(request: Request, db: Session = Depends(get_db)):
    # 모든 등록 데이터 삭제
    db.query(Registration).delete()
    db.commit()
    # MySQL의 경우 AUTO_INCREMENT를 1로 재설정 (다른 DBMS는 방법이 다를 수 있음)
    db.execute(text("ALTER TABLE registrations AUTO_INCREMENT = 1"))
    db.commit()
    return RedirectResponse(url="/registration", status_code=302)

# 실행: uvicorn main:app --reload