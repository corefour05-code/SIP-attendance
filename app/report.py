import io
from datetime import datetime, timedelta

from app.attendance import IST, format_duration
from app.config import HOTEL_NAME

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

VALID_STATUSES = ("all", "present", "absent")


def get_default_date_range(conn) -> tuple[str, str]:
    today = datetime.now(IST).date().isoformat()
    # Check if we have records in daily_attendance
    row = conn.execute(
        "SELECT MIN(work_date) AS mn, MAX(work_date) AS mx FROM daily_attendance"
    ).fetchone()
    if row and row["mn"] and row["mx"]:
        return row["mn"], today
    return today, today


def parse_report_params(query_params, conn) -> tuple[str, str, str, str]:
    today = datetime.now(IST).date().isoformat()
    default_from, default_to = get_default_date_range(conn)

    # Preset handling
    preset = query_params.get("preset")
    if preset == "today":
        date_from, date_to = today, today
    elif preset == "yesterday":
        yest = (datetime.now(IST).date() - timedelta(days=1)).isoformat()
        date_from, date_to = yest, yest
    elif preset == "week":
        week_ago = (datetime.now(IST).date() - timedelta(days=6)).isoformat()
        date_from, date_to = week_ago, today
    elif preset == "month":
        month_ago = (datetime.now(IST).date() - timedelta(days=29)).isoformat()
        date_from, date_to = month_ago, today
    else:
        date_from = query_params.get("from") or default_from
        date_to = query_params.get("to") or default_to

    try:
        datetime.strptime(date_from, "%Y-%m-%d")
        datetime.strptime(date_to, "%Y-%m-%d")
    except ValueError:
        date_from, date_to = default_from, default_to

    status_filter = query_params.get("status", "all")
    if status_filter not in VALID_STATUSES:
        status_filter = "all"

    q = (query_params.get("q") or "").strip()
    return date_from, date_to, status_filter, q


def build_hotel_report(conn, date_from: str, date_to: str, status_filter: str, q: str) -> dict:
    """Build day-by-day and staff-by-staff attendance timesheets for hotel owner."""
    d0 = datetime.strptime(date_from, "%Y-%m-%d").date()
    d1 = datetime.strptime(date_to, "%Y-%m-%d").date()
    dates = []
    curr = d0
    while curr <= d1:
        dates.append(curr.isoformat())
        curr += timedelta(days=1)

    # All active staff with enrolled face embeddings
    if q:
        like = f"%{q}%"
        staff_rows = conn.execute(
            """
            SELECT s.student_id, s.name, s.mobile_number
            FROM students s
            JOIN embeddings e ON e.student_id = s.student_id
            WHERE s.name LIKE ? OR s.student_id LIKE ? OR s.mobile_number LIKE ?
            GROUP BY s.student_id
            ORDER BY s.student_id
            """,
            (like, like, like),
        ).fetchall()
    else:
        staff_rows = conn.execute(
            """
            SELECT s.student_id, s.name, s.mobile_number
            FROM students s
            JOIN embeddings e ON e.student_id = s.student_id
            GROUP BY s.student_id
            ORDER BY s.student_id
            """
        ).fetchall()

    total_enrolled = conn.execute(
        """
        SELECT COUNT(DISTINCT student_id) AS c FROM embeddings
        """
    ).fetchone()["c"]

    # Fetch daily_attendance records within the date range
    att_rows = conn.execute(
        """
        SELECT staff_id, work_date, first_in, last_out, total_hours, punch_count, status
        FROM daily_attendance
        WHERE work_date BETWEEN ? AND ?
        """,
        (date_from, date_to),
    ).fetchall()

    # Map: (staff_id, work_date) -> record
    att_map = {(r["staff_id"], r["work_date"]): r for r in att_rows}

    # Generate flat timesheet rows
    timesheet = []
    total_present_shifts = 0
    total_hours_sum = 0.0

    for d in sorted(dates, reverse=True):
        for s in staff_rows:
            sid = s["student_id"]
            name = s["name"]
            mobile = s["mobile_number"] or ""
            rec = att_map.get((sid, d))

            if rec:
                # Present on this day
                first_in_dt = rec["first_in"]
                last_out_dt = rec["last_out"]
                try:
                    first_in_disp = datetime.strptime(first_in_dt, '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')
                except Exception:
                    first_in_disp = first_in_dt[11:16] if len(first_in_dt) >= 16 else first_in_dt
                try:
                    last_out_disp = datetime.strptime(last_out_dt, '%Y-%m-%d %H:%M:%S').strftime('%I:%M %p')
                except Exception:
                    last_out_disp = last_out_dt[11:16] if len(last_out_dt) >= 16 else last_out_dt

                hours = float(rec["total_hours"])
                punches = int(rec["punch_count"])
                is_present = True
                status_str = "Present"
                total_present_shifts += 1
                total_hours_sum += hours
            else:
                first_in_disp = "—"
                last_out_disp = "—"
                hours = 0.0
                punches = 0
                is_present = False
                status_str = "Absent"

            if status_filter == "present" and not is_present:
                continue
            if status_filter == "absent" and is_present:
                continue

            timesheet.append({
                "date": d,
                "staff_id": sid,
                "name": name,
                "mobile": mobile,
                "first_in": first_in_disp,
                "last_out": last_out_disp,
                "total_hours": hours,
                "duration_str": format_duration(hours) if is_present else "0h 0m",
                "punch_count": punches,
                "is_present": is_present,
                "status": status_str,
            })

    total_possible_slots = len(dates) * len(staff_rows)
    att_rate = round((total_present_shifts / total_possible_slots * 100), 1) if total_possible_slots else 0.0
    avg_hours = round(total_hours_sum / total_present_shifts, 1) if total_present_shifts else 0.0

    return {
        "hotel_name": HOTEL_NAME,
        "date_from": date_from,
        "date_to": date_to,
        "dates_count": len(dates),
        "status_filter": status_filter,
        "q": q,
        "total_enrolled": total_enrolled,
        "total_present_shifts": total_present_shifts,
        "total_hours_sum": round(total_hours_sum, 1),
        "avg_hours": avg_hours,
        "att_rate": att_rate,
        "timesheet": timesheet,
    }


def render_hotel_pdf(data: dict) -> bytes:
    """Generate luxury hotel timesheet PDF for owner and payroll records."""
    buf = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        buf,
        pagesize=page_size,
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "HotelTitle",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#1b2733"),
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        "HotelSub",
        parent=styles["Normal"],
        textColor=colors.HexColor("#5b6675"),
        fontSize=9,
        spaceAfter=8,
    )

    elements = []
    title = f"{data['hotel_name']} — Staff Shift Attendance Timesheet"
    elements.append(Paragraph(title, title_style))

    sub = (
        f"Period: <b>{data['date_from']}</b> to <b>{data['date_to']}</b> &nbsp;|&nbsp; "
        f"Present Shifts: <b>{data['total_present_shifts']}</b> &nbsp;|&nbsp; "
        f"Total Hours: <b>{data['total_hours_sum']} hrs</b> &nbsp;|&nbsp; "
        f"Avg Duration: <b>{data['avg_hours']} hrs/shift</b> &nbsp;|&nbsp; "
        f"Generated {datetime.now(IST).strftime('%Y-%m-%d %I:%M %p')} IST"
    )
    elements.append(Paragraph(sub, sub_style))
    elements.append(Spacer(1, 6))

    header = ["Date", "Staff ID", "Name", "Mobile", "First IN", "Last OUT", "Total Hours", "Punches", "Status"]
    table_data = [header]

    for row in data["timesheet"]:
        table_data.append([
            row["date"],
            row["staff_id"],
            row["name"],
            row["mobile"] or "—",
            row["first_in"],
            row["last_out"],
            row["duration_str"],
            str(row["punch_count"]),
            row["status"],
        ])

    avail_width = page_size[0] - 20 * mm
    # 9 columns width budget
    col_widths = [
        22 * mm,  # Date
        18 * mm,  # ID
        45 * mm,  # Name
        26 * mm,  # Mobile
        22 * mm,  # First IN
        22 * mm,  # Last OUT
        26 * mm,  # Total Hours
        16 * mm,  # Punches
        remaining_w := max(20 * mm, avail_width - (22 + 18 + 45 + 26 + 22 + 22 + 26 + 16) * mm),
    ]

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1b2733")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#fef7e0")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d0d7de")),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("ALIGN", (4, 0), (7, -1), "CENTER"),
                ("ALIGN", (8, 0), (8, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ]
        )
    )
    elements.append(t)
    doc.build(elements)
    return buf.getvalue()


# Compatibility aliases
def build_report(conn, date_from, date_to, session_filter, status_filter, q):
    return build_hotel_report(conn, date_from, date_to, status_filter, q)


def render_pdf(data):
    return render_hotel_pdf(data)
