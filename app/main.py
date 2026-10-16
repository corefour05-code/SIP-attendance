import csv
import io
from pathlib import Path
from datetime import datetime

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from app.db import db_session, init_schema
from app.students import (
    next_staff_id,
    next_student_id,
    student_exists,
    list_students,
    get_student,
    find_by_mobile,
    mobile_in_use,
    normalize_mobile,
    update_student_name,
    update_student_mobile,
    replace_embeddings,
    delete_student,
)
from app.face import decode_image, validate_and_embed_single, detect_and_embed_all, embedding_to_blob
from app.config import HOTEL_NAME, HOTEL_SUBTITLE
from app.matching import match_embedding, reload_gallery
from app.attendance import IST, record_staff_punch, format_duration
from app.report import parse_report_params, build_hotel_report, render_hotel_pdf

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(title=f"{HOTEL_NAME} — Attendance System")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


@app.on_event("startup")
def _startup():
    init_schema()
    reload_gallery()


@app.get("/")
def dashboard_page(request: Request):
    """Hotel Owner Command Dashboard: Real-time attendance KPIs, active shifts, and live punch log."""
    today = datetime.now(IST).date().isoformat()
    with db_session() as conn:
        total_staff = conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"]
        total_enrolled = conn.execute(
            "SELECT COUNT(DISTINCT student_id) AS c FROM embeddings"
        ).fetchone()["c"]

        # Today's daily attendance rows
        today_rows = conn.execute(
            """
            SELECT 
                da.staff_id,
                s.name,
                s.mobile_number,
                da.first_in,
                da.last_out,
                da.total_hours,
                da.punch_count,
                da.last_punch_at,
                da.status
            FROM daily_attendance da
            JOIN students s ON s.student_id = da.staff_id
            WHERE da.work_date = ?
            ORDER BY da.last_punch_at DESC
            """,
            (today,),
        ).fetchall()

        present_count = len(today_rows)
        clocked_in_now = sum(1 for r in today_rows if r["status"] == "Working")
        total_hours_today = round(sum(float(r["total_hours"]) for r in today_rows), 1)

        # Recent 8 raw punches
        recent_punches = conn.execute(
            """
            SELECT p.punch_time, p.staff_id, s.name
            FROM attendance_punches p
            JOIN students s ON s.student_id = p.staff_id
            WHERE p.work_date = ?
            ORDER BY p.punch_time DESC
            LIMIT 8
            """,
            (today,),
        ).fetchall()

        formatted_roster = []
        for r in today_rows:
            try:
                first_in_disp = datetime.strptime(r["first_in"], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')
            except Exception:
                first_in_disp = r["first_in"]
            try:
                last_out_disp = datetime.strptime(r["last_out"], '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')
            except Exception:
                last_out_disp = r["last_out"]

            formatted_roster.append({
                "staff_id": r["staff_id"],
                "name": r["name"],
                "mobile_number": r["mobile_number"],
                "first_in": first_in_disp,
                "last_out": last_out_disp,
                "total_hours": float(r["total_hours"]),
                "duration_str": format_duration(float(r["total_hours"])),
                "punch_count": r["punch_count"],
                "status": r["status"],
            })

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "hotel_name": HOTEL_NAME,
            "hotel_subtitle": HOTEL_SUBTITLE,
            "today_date": today,
            "total_staff": total_staff,
            "total_enrolled": total_enrolled,
            "present_count": present_count,
            "clocked_in_now": clocked_in_now,
            "total_hours_today": total_hours_today,
            "recent_punches": recent_punches,
            "roster": formatted_roster,
        },
    )


@app.get("/api/dashboard/stats")
def api_dashboard_stats():
    """Live JSON endpoint for real-time dashboard auto-refresh."""
    today = datetime.now(IST).date().isoformat()
    with db_session() as conn:
        total_staff = conn.execute("SELECT COUNT(*) AS c FROM students").fetchone()["c"]
        today_rows = conn.execute(
            "SELECT total_hours, status FROM daily_attendance WHERE work_date = ?", (today,)
        ).fetchall()
        present_count = len(today_rows)
        clocked_in_now = sum(1 for r in today_rows if r["status"] == "Working")
        total_hours = round(sum(float(r["total_hours"]) for r in today_rows), 1)

    return JSONResponse({
        "total_staff": total_staff,
        "present_count": present_count,
        "clocked_in_now": clocked_in_now,
        "total_hours_today": total_hours,
        "today_date": today,
    })


@app.get("/scan")
def scan_page(request: Request):
    """Hotel Biometric Terminal Scanner page."""
    return templates.TemplateResponse(
        "scan.html",
        {
            "request": request,
            "hotel_name": HOTEL_NAME,
            "hotel_subtitle": HOTEL_SUBTITLE,
        },
    )


@app.post("/api/scan")
async def scan(image: UploadFile = File(...)):
    """Live facial recognition scanner endpoint.

    Matches detected faces and computes First IN / Last OUT / Active Shift Hours.
    """
    image_bytes = await image.read()
    img = decode_image(image_bytes)
    detections = detect_and_embed_all(img)

    faces = []
    for det in detections:
        match = match_embedding(det["embedding"])
        if match is None:
            faces.append({"bbox": det["bbox"], "status": "unknown"})
            continue

        punch = record_staff_punch(match["student_id"])
        faces.append(
            {
                "bbox": det["bbox"],
                "status": "match",
                "student_id": match["student_id"],
                "name": match["name"],
                "action": punch["action"],
                "first_in": punch["first_in"],
                "last_out": punch["last_out"],
                "total_hours": punch["total_hours"],
                "duration_str": punch["duration_str"],
                "message": punch["message"],
                "speech": punch.get("speech") or f"{match['name']}, {punch['duration_str']}",
                "already_marked": punch["already"],
            }
        )

    return JSONResponse({"faces": faces})


@app.get("/enroll")
def enroll_page(request: Request):
    """1-Click Single Photo Staff Enrollment page."""
    return templates.TemplateResponse(
        "enroll.html",
        {
            "request": request,
            "hotel_name": HOTEL_NAME,
            "hotel_subtitle": HOTEL_SUBTITLE,
        },
    )


@app.get("/api/students/lookup")
@app.get("/api/staff/lookup")
def lookup_student(mobile: str = ""):
    number = normalize_mobile(mobile)
    if number is None:
        return JSONResponse({"found": False, "reason": "Enter a valid 10-digit mobile number"})

    with db_session() as conn:
        match = find_by_mobile(conn, number)

    if match is None:
        return JSONResponse({"found": False})

    return JSONResponse(
        {
            "found": True,
            "student_id": match["student_id"],
            "name": match["name"],
            "has_photos": match["photo_count"] > 0,
        }
    )


@app.post("/api/enroll/validate-photo")
async def validate_photo(image: UploadFile = File(...)):
    """Single photo validation with auto-augmented embeddings."""
    image_bytes = await image.read()
    img = decode_image(image_bytes)
    result = validate_and_embed_single(img)
    return JSONResponse(result)


class PhotoIn(BaseModel):
    angle_label: str
    embedding: list[float]


class EnrollSubmitIn(BaseModel):
    name: str
    mobile_number: str
    photos: list[PhotoIn]


@app.post("/api/enroll/submit")
def enroll_submit(payload: EnrollSubmitIn):
    name = payload.name.strip()
    mobile_number = normalize_mobile(payload.mobile_number)

    if not name:
        return JSONResponse({"ok": False, "reason": "Name is required"}, status_code=400)
    if mobile_number is None:
        return JSONResponse({"ok": False, "reason": "Enter a valid 10-digit mobile number"}, status_code=400)
    if not payload.photos:
        return JSONResponse({"ok": False, "reason": "At least one valid photo embedding is required"}, status_code=400)

    with db_session() as conn:
        if mobile_in_use(conn, mobile_number):
            return JSONResponse(
                {"ok": False, "reason": f"Phone {mobile_number} is already enrolled for another staff member."},
                status_code=409,
            )

        staff_id = next_staff_id(conn, prefix="HTL")
        conn.execute(
            "INSERT INTO students (student_id, name, mobile_number) VALUES (?, ?, ?)",
            (staff_id, name, mobile_number),
        )
        for photo in payload.photos:
            conn.execute(
                "INSERT INTO embeddings (student_id, embedding, angle_label) VALUES (?, ?, ?)",
                (staff_id, embedding_to_blob(photo.embedding), photo.angle_label),
            )

    reload_gallery()
    return JSONResponse({"ok": True, "student_id": staff_id, "staff_id": staff_id})


@app.get("/staff")
@app.get("/students")
def staff_directory_page(request: Request):
    """Hotel Staff Directory & Roster."""
    with db_session() as conn:
        staff_list = list_students(conn)
    return templates.TemplateResponse(
        "students.html",
        {
            "request": request,
            "hotel_name": HOTEL_NAME,
            "hotel_subtitle": HOTEL_SUBTITLE,
            "students": staff_list,
        },
    )


@app.get("/staff/{student_id}/edit")
@app.get("/students/{student_id}/edit")
def edit_staff_page(request: Request, student_id: str):
    student_id = student_id.strip().upper()
    with db_session() as conn:
        student = get_student(conn, student_id)
        if student is None:
            raise HTTPException(status_code=404, detail=f"Staff member {student_id} not found")
    return templates.TemplateResponse(
        "edit_student.html",
        {
            "request": request,
            "hotel_name": HOTEL_NAME,
            "hotel_subtitle": HOTEL_SUBTITLE,
            "student": student,
        },
    )


class UpdateStudentIn(BaseModel):
    name: str
    mobile_number: str = ""


@app.post("/api/students/{student_id}/update")
def update_student(student_id: str, payload: UpdateStudentIn):
    student_id = student_id.strip().upper()
    name = payload.name.strip()
    if not name:
        return JSONResponse({"ok": False, "reason": "Name is required"}, status_code=400)

    mobile_number = None
    if payload.mobile_number.strip():
        mobile_number = normalize_mobile(payload.mobile_number)
        if mobile_number is None:
            return JSONResponse({"ok": False, "reason": "Enter a valid 10-digit mobile number"}, status_code=400)

    with db_session() as conn:
        if not student_exists(conn, student_id):
            return JSONResponse({"ok": False, "reason": f"Staff {student_id} not found"}, status_code=404)
        existing = find_by_mobile(conn, mobile_number) if mobile_number else None
        if existing and existing["student_id"] != student_id:
            return JSONResponse(
                {"ok": False, "reason": f"{mobile_number} is already used by {existing['student_id']}"},
                status_code=409,
            )
        update_student_name(conn, student_id, name)
        update_student_mobile(conn, student_id, mobile_number)

    return JSONResponse({"ok": True, "student_id": student_id, "name": name, "mobile_number": mobile_number})


@app.post("/api/students/{student_id}/delete")
def delete_student_endpoint(student_id: str):
    student_id = student_id.strip().upper()
    with db_session() as conn:
        if not student_exists(conn, student_id):
            return JSONResponse({"ok": False, "reason": f"Staff {student_id} not found"}, status_code=404)
        delete_student(conn, student_id)

    reload_gallery()
    return JSONResponse({"ok": True, "student_id": student_id})


class RecaptureIn(BaseModel):
    photos: list[PhotoIn]


@app.post("/api/students/{student_id}/recapture")
def recapture_student(student_id: str, payload: RecaptureIn):
    student_id = student_id.strip().upper()
    if not payload.photos:
        return JSONResponse({"ok": False, "reason": "Valid face photo required"}, status_code=400)

    with db_session() as conn:
        if not student_exists(conn, student_id):
            return JSONResponse({"ok": False, "reason": f"Staff {student_id} not found"}, status_code=404)
        replace_embeddings(conn, student_id, [p.model_dump() for p in payload.photos])

    reload_gallery()
    return JSONResponse({"ok": True, "student_id": student_id})


@app.get("/report")
def report_page(request: Request):
    """Hotel Owner Timesheet & Shift Hours Reports."""
    with db_session() as conn:
        date_from, date_to, status_filter, q = parse_report_params(request.query_params, conn)
        data = build_hotel_report(conn, date_from, date_to, status_filter, q)
    return templates.TemplateResponse("report.html", {"request": request, **data})


@app.get("/report/export.csv")
def report_export_csv(request: Request):
    """Download hotel shift attendance timesheet in CSV."""
    with db_session() as conn:
        date_from, date_to, status_filter, q = parse_report_params(request.query_params, conn)
        data = build_hotel_report(conn, date_from, date_to, status_filter, q)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Staff ID", "Name", "Mobile Number", "First IN", "Last OUT", "Total Hours", "Punches", "Status"])
    for row in data["timesheet"]:
        writer.writerow([
            row["date"],
            row["staff_id"],
            row["name"],
            row["mobile"],
            row["first_in"],
            row["last_out"],
            f"{row['total_hours']:.2f}",
            row["punch_count"],
            row["status"],
        ])

    filename = f"hotel_attendance_{data['date_from']}_to_{data['date_to']}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/report/export.pdf")
def report_export_pdf(request: Request):
    """Download styled hotel attendance timesheet in PDF."""
    with db_session() as conn:
        date_from, date_to, status_filter, q = parse_report_params(request.query_params, conn)
        data = build_hotel_report(conn, date_from, date_to, status_filter, q)

    pdf_bytes = render_hotel_pdf(data)
    filename = f"hotel_attendance_{data['date_from']}_to_{data['date_to']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
