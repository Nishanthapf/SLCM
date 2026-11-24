# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""The examination office's two Excel sheets, downloaded and imported as they are.

Exam timetable = "classroom allocation sheet": a title, one header row, then a
day header ("Saturday, 19th September 2026") followed by that day's rooms,
Forenoon on the left (Sl. No., Date, Venue, Year, paper, ID Nos. From / To,
Invigilator) and Afternoon on the right. Each line is one Exam Plan › Course
Schedule row; a course split over rooms has a row per room with its ID range.

Continuing Evaluation Schedule: a sheet per programme, title row, then
Course Faculty | Subject | Component | Marks | Due Date for Submission |
Date for activities/ Mid-Term Exam/Class Test | Extension Applicable | extra
columns of the plan; Faculty and Subject merged down the subject's components.
Each component is an Exam Assessment Schedule Item (of every programme teaching
the course); a typed faculty is its Course Note. The older one-row-per-subject
sheet (Evaluation n/Assessment n, Marks, Date ×n | SGD | remarks) still imports.

Text the masters don't know is kept as written (Paper, Room, Invigilator, Marks,
Date), so a sheet imported and downloaded again comes back the same.
"""

import math
import re
from collections import Counter
from datetime import date, datetime, timedelta
from io import BytesIO

import frappe
from frappe import _
from frappe.utils import cstr, flt, getdate, to_timedelta
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from slcm.slcm.utils.exam_timetable import _faculty_label, check_exam_schedule

THIN = Side(style="thin")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
GREY = PatternFill("solid", fgColor="D8D8D8")
HEAD_GREY = PatternFill("solid", fgColor="BFBFBF")
CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
TOP = Alignment(horizontal="center", vertical="top", wrap_text=True)
LEFT = Alignment(vertical="center", wrap_text=True)

SESSIONS = ("Forenoon", "Afternoon")
SESSION_TIMES = {"Forenoon": "10:00", "Afternoon": "14:30"}
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}

# Timetable columns: A Sl. No., B Date, C–H Forenoon, I Date, J–O Afternoon
TT_WIDTHS = {"A": 7, "B": 17.6, "C": 13, "D": 19.6, "E": 43.4, "F": 17.7, "G": 18.3, "H": 18,
             "I": 15.3, "J": 15, "K": 20.4, "L": 40.4, "M": 14.4, "N": 17.3, "O": 18}
SIDE_COL = {"Forenoon": 3, "Afternoon": 10}   # first column (Venue) of each side
CE_WIDTHS = {"A": 19.4, "B": 31.3, "C": 10, "D": 18.7, "E": 22.4, "F": 10, "G": 18, "H": 17.6, "I": 10,
             "J": 23.9, "K": 17.6, "L": 10, "M": 18, "N": 43.3, "O": 23.4}


# ── small helpers ──────────────────────────────────────────────────────────────

def _text(v):
	if v is None:
		return ""
	if isinstance(v, float) and v.is_integer():
		v = int(v)
	return cstr(v).replace("\xa0", " ").strip()


def _key(text):
	"""Room / name key: letters and digits only (OAB - 101 = OAB-101 = oab101)."""
	return re.sub(r"[^A-Z0-9]", "", _text(text).upper())


def _norm(text):
	return " ".join(re.sub(r"[^a-z0-9]+", " ", _text(text).lower()).split())


def _words(text):
	return {w for w in _norm(text).split() if len(w) > 2 and w not in ("the", "and", "for", "with")}


_END_TERM = re.compile(r"\b(end[\s-]*term|end[\s-]*sem\w*|final\s+exam\w*)\b", re.I)


def _is_end_term(*texts):
	"""End-term papers pair only with end-term assessments, internals with internals."""
	return any(_END_TERM.search(_text(t)) for t in texts)


def _ordinal(n):
	return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _long_date(d):
	"""Saturday, 19th September 2026"""
	return f"{d.strftime('%A')}, {_ordinal(d.day)} {d.strftime('%B %Y')}"


def _ampm(t):
	"""10:00 -> 10.00 AM, 14:30 -> 2.30 PM"""
	td = to_timedelta(t)
	h, m = int(td.total_seconds() // 3600), int(td.total_seconds() % 3600 // 60)
	return f"{(h % 12) or 12}.{m:02d} {'AM' if h < 12 else 'PM'}"


def _hhmm(t):
	return str(t or "")[:5].rjust(5, "0") if t else ""


def _session_of(row):
	if row.get("session") in SESSIONS:
		return row.get("session")
	if row.get("start_time"):
		return "Forenoon" if to_timedelta(row.get("start_time")) < timedelta(hours=12) else "Afternoon"
	return "Forenoon"


def _cell(ws, r, c, value=None, bold=False, fill=None, align=CENTER, size=12, font="Bookman Old Style"):
	cell = ws.cell(r, c)
	if value not in (None, ""):
		cell.value = value
	cell.font = Font(name=font, size=size, bold=bold)
	cell.alignment = align
	cell.border = BOX
	if fill:
		cell.fill = fill
	return cell


def _merge(ws, r1, c1, r2, c2):
	if (r1, c1) != (r2, c2):
		ws.merge_cells(start_row=r1, start_column=c1, end_row=r2, end_column=c2)


def _fit_heights(ws, first, last, widths, minimum=21, line=15.5):
	"""Excel doesn't grow rows for wrapped text written by openpyxl; estimate it."""
	merged = set()
	for rng in ws.merged_cells.ranges:
		if rng.max_row > rng.min_row:
			merged |= {(r, c) for r in range(rng.min_row, rng.max_row + 1) for c in range(rng.min_col, rng.max_col + 1)}
	for r in range(first, last + 1):
		lines = 1
		for c in range(1, ws.max_column + 1):
			v = ws.cell(r, c).value
			if v is None or (r, c) in merged:
				continue
			width = widths.get(ws.cell(r, c).column_letter, 10)
			per_line = max(4, int(width * 0.95))
			lines = max(lines, sum(max(1, math.ceil(len(part) / per_line)) for part in str(v).split("\n")))
		ws.row_dimensions[r].height = max(minimum, lines * line + 6)


def _send(wb, filename):
	buf = BytesIO()
	wb.save(buf)
	frappe.response["filename"] = filename
	frappe.response["filecontent"] = buf.getvalue()
	frappe.response["type"] = "binary"


def _safe_filename(text):
	return re.sub(r"[^A-Za-z0-9 _.-]+", "", text).strip() or "sheet"


def file_content(file_url):
	if not file_url:
		frappe.throw(_("Attach the Excel sheet first."))
	return frappe.get_doc("File", {"file_url": file_url}).get_content()


def _grid(content):
	"""Cell values as a list of rows (15+ columns); a cell merged down a column
	(Sl. No., Date, Venue, Year…) carries its value into every row it covers."""
	try:
		wb = load_workbook(BytesIO(content), data_only=True)
	except Exception:
		frappe.throw(_("This is not an Excel (.xlsx) file."))
	ws = wb.active
	width = max(ws.max_column, 15)
	grid = [list(r) + [None] * (width - len(r)) for r in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=width, values_only=True)]
	for rng in ws.merged_cells.ranges:
		if rng.min_col == rng.max_col and rng.max_row > rng.min_row:
			v = grid[rng.min_row - 1][rng.min_col - 1]
			for r in range(rng.min_row, rng.max_row):
				grid[r][rng.min_col - 1] = v
	return grid


def _parse_date(value, ref=None):
	"""19.09.2026 / a date cell / Monday, 21st September 2026 / 8th Sept 2026."""
	if isinstance(value, datetime):
		return value.date()
	if isinstance(value, date):
		return value
	text = _text(value)
	if not text or not re.search(r"\d", text):
		return None
	m = re.search(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\b", text)
	if m:
		d, mth, y = (int(x) for x in m.groups())
		try:
			return date(y + 2000 if y < 100 else y, mth, d)
		except ValueError:
			return None
	if not re.search(r"jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", text, re.I):
		return None
	from dateutil import parser

	ref = getdate(ref) if ref else getdate()
	try:
		return parser.parse(text, fuzzy=True, dayfirst=True, default=datetime(ref.year, ref.month, 1)).date()
	except (ValueError, OverflowError):
		return None


def _course_index(term):
	"""Normalized course name / code / ID -> Course; courses taught in the term win."""
	index = {}
	taught = set(frappe.get_all("Classes", filters={"academic_term": term}, pluck="course", distinct=True)) if term else set()
	courses = frappe.get_all("Course", fields=["name", "course_name", "course_code"])
	for c in sorted(courses, key=lambda c: c.name in taught):
		for k in (c.course_name, c.course_code, c.name):
			if _norm(k):
				index[_norm(k)] = c.name
	return index


def _faculty_index():
	index = {}
	for f in frappe.get_all("Faculty", fields=["name", "first_name", "last_name", "faculty_id"]):
		for k in (" ".join(filter(None, [f.first_name, f.last_name])), f.faculty_id, str(f.name)):
			if _norm(k):
				index[_norm(k)] = f.name
	return index


def _year_labels(term):
	"""Course -> "<Programme> <year> Year" from its Classes, for rows without a Year."""
	out = {}
	if term:
		for c in frappe.get_all("Classes", filters={"academic_term": term}, fields=["course", "programme", "year_no"], order_by="programme"):
			if c.course not in out and c.programme:
				year = ROMAN.get(c.year_no) or (str(c.year_no) if c.year_no else "")
				out[c.course] = f"{c.programme} {year} Year" if year else c.programme
	return out


# ── Exam timetable (classroom allocation sheet) ───────────────────────────────

def _table(reexam):
	"""Exam Plan child table of the exam (course_schedules) or re-exam (reexam_schedules) timetable."""
	return "reexam_schedules" if reexam else "course_schedules"


def timetable_entries(plan, reexam=False):
	"""The plan's (re-)exam timetable rows as sheet lines, by date and session."""
	term = plan.term
	sittings = plan.get(_table(reexam)) or []
	names = dict(frappe.get_all("Course", filters={"name": ["in", [r.course for r in sittings if r.course] or [""]]},
	                            fields=["name", "course_name"], as_list=True))
	years = _year_labels(term)
	out = []
	for r in sittings:
		if not r.exam_date:
			continue
		out.append(frappe._dict(
			exam_date=getdate(r.exam_date), session=_session_of(r), start_time=r.start_time, idx=r.idx,
			venue=r.venue or r.hall or "", year=r.programme_year or years.get(r.course, ""),
			paper=r.paper or names.get(r.course) or r.course or "",
			id_from=r.id_from or "", id_to=r.id_to or "",
			invigilator=_faculty_label(r.invigilator) if r.invigilator else (r.invigilator_name or ""),
		))
	out.sort(key=lambda e: (e.exam_date, SESSIONS.index(e.session), e.idx))
	return out


def _date_span(days):
	a, b = days[0], days[-1]
	if a == b:
		return f"{_ordinal(a.day)} {a.strftime('%B %Y')}"
	if (a.year, a.month) == (b.year, b.month):
		return f"{_ordinal(a.day)} to {_ordinal(b.day)} {b.strftime('%B %Y')}"
	return f"{_ordinal(a.day)} {a.strftime('%B')} to {_ordinal(b.day)} {b.strftime('%B %Y')}"


def timetable_workbook(exam_plan, reexam=False):
	plan = frappe.get_doc("Exam Plan", exam_plan)
	entries = timetable_entries(plan, reexam)
	days = sorted({e.exam_date for e in entries})

	wb = Workbook()
	ws = wb.active
	ws.title = "Sheet1"
	for col, w in TT_WIDTHS.items():
		ws.column_dimensions[col].width = w
	last_col = 15

	# 1 blank band, 2 title, 3 header
	for c in range(1, last_col + 1):
		_cell(ws, 1, c)
	_merge(ws, 1, 1, 1, last_col)
	ws.row_dimensions[1].height = 22.5
	title = (_("{0} Re-Examination classroom allocation sheet") if reexam
	         else _("{0} End-Term Examination classroom allocation sheet")).format(plan.term or plan.exam_name)
	if days:
		title += f" ({_date_span(days)})"
	for c in range(1, last_col + 1):
		_cell(ws, 2, c, bold=True, fill=GREY)
	ws.cell(2, 1).value = title
	_merge(ws, 2, 1, 2, last_col)
	ws.row_dimensions[2].height = 21

	starts = {s: Counter(_hhmm(e.start_time) for e in entries if e.session == s and e.start_time).most_common(1) for s in SESSIONS}
	start = {s: (starts[s][0][0] if starts[s] else SESSION_TIMES[s]) for s in SESSIONS}
	header = ["Sl. No.", "Date", "Venue", "Year", f"Forenoon Session ({_ampm(start['Forenoon'])})", "ID Nos. \nFrom", "ID Nos.\nTo", "Invigilator",
	          "Date", "Venue", "Year", f"Afternoon Session \n({_ampm(start['Afternoon'])})", "ID Nos. \nFrom", "ID Nos.\nTo", "Invigilator"]
	for c, h in enumerate(header, 1):
		_cell(ws, 3, c, h, bold=True, fill=HEAD_GREY)
	ws.row_dimensions[3].height = 38.25
	ws.freeze_panes = "A4"

	r = 4
	for n, day in enumerate(days, 1):
		for c in range(1, last_col + 1):
			_cell(ws, r, c, bold=True, fill=GREY)
		ws.cell(r, 1).value = _long_date(day)
		_merge(ws, r, 1, r, last_col)
		ws.row_dimensions[r].height = 18.75
		r += 1

		sides = {s: [e for e in entries if e.exam_date == day and e.session == s] for s in SESSIONS}
		k = max(1, *(len(v) for v in sides.values()))
		for i in range(k):
			for c in range(1, last_col + 1):
				_cell(ws, r + i, c)
		day_text = f"{day.strftime('%d.%m.%Y')}\n{day.strftime('%A')}"
		for c, v in ((1, n), (2, day_text), (9, day_text)):
			_cell(ws, r, c, v, bold=True, align=TOP)
			_merge(ws, r, c, r + k - 1, c)
		for session, lines in sides.items():
			_write_side(ws, r, k, lines, SIDE_COL[session])
		_fit_heights(ws, r, r + k - 1, TT_WIDTHS)
		r += k

	return wb


def _write_side(ws, r, k, lines, c0):
	"""Venue, Year, paper, From, To, Invigilator of one session; a room spanning
	several lines is one merged Venue cell, "All students" spans From and To."""
	for i, e in enumerate(lines):
		row = r + i
		for j, v in enumerate((e.venue, e.year, e.paper, e.id_from, e.id_to, e.invigilator)):
			if v:
				ws.cell(row, c0 + j).value = v
		if e.id_from and not e.id_to:
			_merge(ws, row, c0 + 3, row, c0 + 4)
	i = 0
	while i < len(lines):
		j = i
		while j + 1 < len(lines) and lines[j + 1].venue and lines[j + 1].venue == lines[i].venue:
			j += 1
		if lines[i].venue:
			_merge(ws, r + i, c0, r + j, c0)
		i = j + 1
	if len(lines) < k:
		_merge(ws, r + len(lines), c0, r + k - 1, c0 + 5)


def parse_timetable(content):
	"""Lines of a classroom allocation sheet: [{sheet_row, exam_date, session,
	start_time, venue, year, paper, id_from, id_to, invigilator}], issues."""
	grid = _grid(content)
	issues, lines = [], []
	head = next((i for i, row in enumerate(grid)
	             if _norm(row[0]).startswith("sl") and any("session" in _norm(v) for v in row)), None)
	if head is None:
		frappe.throw(_("No header row found. The sheet needs the header: Sl. No. | Date | Venue | Year | Forenoon Session (10.00 AM) | ID Nos. From | ID Nos. To | Invigilator | Date | Venue | Year | Afternoon Session (2.30 PM) | …"))

	def header_time(text, default):
		m = re.search(r"(\d{1,2})(?:[.:](\d{2}))?\s*([AaPp])\.?\s*[Mm]", _text(text))
		if not m:
			return default
		h, mi = int(m.group(1)) % 12, int(m.group(2) or 0)
		return f"{h + (12 if m.group(3).lower() == 'p' else 0):02d}:{mi:02d}"

	start = {"Forenoon": header_time(grid[head][4], SESSION_TIMES["Forenoon"]),
	         "Afternoon": header_time(grid[head][11], SESSION_TIMES["Afternoon"])}

	day = None
	last_venue = {}
	previous = {}
	for i in range(head + 1, len(grid)):
		row = [_text(v) if not isinstance(v, (date, datetime)) else v for v in grid[i][:15]]
		if not any(row):
			continue
		if row[0] and not isinstance(grid[i][0], (int, float)) and not any(row[1:]):
			day = _parse_date(row[0]) or day        # "Saturday, 19th September 2026"
			last_venue, previous = {}, {}
			continue
		for session, c0 in SIDE_COL.items():
			venue, year, paper, id_from, id_to, invig = row[c0 - 1:c0 + 5]
			when = _parse_date(row[c0 - 2]) or _parse_date(row[1]) or day
			if not paper:
				if venue:
					last_venue[session] = venue
				continue
			venue = venue or last_venue.get(session, "")
			last_venue[session] = venue
			line = frappe._dict(sheet_row=i + 1, exam_date=when, session=session, start_time=start[session],
			                    venue=venue, year=year, paper=paper, id_from=id_from,
			                    id_to=id_to if id_to != id_from else "", invigilator=invig)
			sig = (when, venue, year, paper, id_from, id_to)
			if previous.get(session) == sig:      # a paper merged down several rows
				continue
			previous[session] = sig
			if not when:
				issues.append({"sheet_row": i + 1, "level": "error", "message": _("{0}: no date for this line, skipped.").format(paper)})
				continue
			lines.append(line)
	return lines, issues


def resolve_timetable(plan, lines, duration_hours=3):
	"""Sheet lines -> Exam Course Schedule rows, matching rooms (Venue Master),
	papers (Course) and invigilators (Faculty); unknown text is kept as written."""
	venues = {_key(v): v for v in frappe.get_all("Venue Master", pluck="name")}
	capacity = dict(frappe.get_all("Venue Master", fields=["name", "capacity"], as_list=True))
	courses = _course_index(plan.term)
	faculty = _faculty_index()
	rows, issues = [], []
	for ln in lines:
		venue_text, year = ln.venue, ln.year
		if _key(venue_text) not in venues and _key(year) in venues:   # Venue and Year typed the other way round
			venue_text, year = year, venue_text
		venue = venues.get(_key(venue_text))
		course = courses.get(_norm(ln.paper))
		invigilator = faculty.get(_norm(ln.invigilator)) if ln.invigilator else None
		end = (datetime.combine(date.today(), datetime.strptime(ln.start_time, "%H:%M").time())
		       + timedelta(hours=flt(duration_hours) or 3)).strftime("%H:%M")
		if venue_text and not venue:
			issues.append({"sheet_row": ln.sheet_row, "level": "warning",
			               "message": _("Room {0} is not in Venue Master: kept as written, not checked for clashes or seats.").format(venue_text)})
		if not course:
			issues.append({"sheet_row": ln.sheet_row, "level": "info",
			               "message": _("{0} is not a Course name: kept as the paper text.").format(ln.paper.replace("\n", " "))})
		if ln.invigilator and not invigilator:
			issues.append({"sheet_row": ln.sheet_row, "level": "info",
			               "message": _("Invigilator {0} is not a Faculty record: kept as written.").format(ln.invigilator)})
		rows.append({
			"course": course, "paper": ln.paper, "programme_year": year, "exam_date": ln.exam_date,
			"session": ln.session, "start_time": ln.start_time, "end_time": end,
			"venue": venue, "hall": None if venue else (venue_text or None),
			"seat_capacity": capacity.get(venue) if venue else None,
			"id_from": ln.id_from or None, "id_to": ln.id_to or None,
			"invigilator": invigilator, "invigilator_name": None if invigilator else (ln.invigilator or None),
			"sheet_row": ln.sheet_row,
		})
	return rows, issues


def _check_rows(plan, rows, reexam=False):
	plan.set(_table(reexam), [{k: v for k, v in r.items() if k != "sheet_row"} for r in rows])
	for i, r in enumerate(plan.get(_table(reexam)), 1):
		r.idx = i
	return check_exam_schedule(plan, reexam=reexam)


def _line_text(r):
	"""24.09.2026 Forenoon · NAB-001 · Legal Methods · L26002–L26085"""
	when = " ".join(filter(None, [getdate(r["exam_date"]).strftime("%d.%m.%Y") if r.get("exam_date") else "", r.get("session") or ""]))
	ids = "–".join(filter(None, [r.get("id_from"), r.get("id_to")]))
	return " · ".join(filter(None, [when, r.get("venue") or r.get("hall"), (r.get("paper") or r.get("course") or "").replace("\n", " "), ids]))


def _group(issues):
	"""One note per message, with every sheet row it applies to (for the preview)."""
	grouped = {}
	for x in issues:
		grouped.setdefault((x["level"], x["message"]), []).append(x["sheet_row"])
	order = {"error": 0, "warning": 1, "info": 2}
	return sorted(({"level": lv, "message": msg, "sheet_rows": sorted(set(r)), "sheet_row": min(r)}
	               for (lv, msg), r in grouped.items()), key=lambda x: (order[x["level"]], x["sheet_row"]))


def timetable_issues(exam_plan, content, duration_hours=3, reexam=False):
	"""Sheet lines -> rows and every issue per sheet row (with its line)."""
	plan = frappe.get_doc("Exam Plan", exam_plan)
	lines, issues = parse_timetable(content)
	rows, more = resolve_timetable(plan, lines, duration_hours)
	text = {r["sheet_row"]: _line_text(r) for r in rows}
	issues += more
	check = _check_rows(plan, rows, reexam)
	for bucket, level in (("errors", "error"), ("warnings", "warning")):
		for x in check[bucket]:
			issues.append({"sheet_row": rows[x["row"] - 1]["sheet_row"], "level": level, "message": x["message"]})
	for x in issues:
		x.setdefault("line", text.get(x["sheet_row"], ""))
	return plan, rows, issues


def import_timetable(exam_plan, content, duration_hours=3, apply=False, file_url=None, reexam=False):
	"""Read a classroom allocation sheet. Without apply: what would be imported,
	with the timetable checks. With apply: replace the plan's exam timetable with
	the lines that pass the checks; lines with a problem are skipped and every
	import is written to an Exam Sheet Import Log."""
	plan, rows, issues = timetable_issues(exam_plan, content, duration_hours, reexam)
	sheet = "Re-exam Timetable" if reexam else "Exam Timetable"
	total = len(rows) + sum(1 for x in issues if x["level"] == "error" and x["sheet_row"] not in {r["sheet_row"] for r in rows})
	bad = {x["sheet_row"] for x in issues if x["level"] == "error"}
	keep = [r for r in rows if r["sheet_row"] not in bad]
	summary = {
		"lines": total, "days": len({r["exam_date"] for r in rows}),
		"courses": len({r["course"] for r in rows if r["course"]}),
		"text_only": sum(1 for r in rows if not r["course"]),
		"error_lines": total - len(keep), "valid_lines": len(keep),
		"issues": _group(issues),
	}
	if not apply:
		return summary
	# leaving lines out can't add clashes, but the rest of a shared, over-full room may still fail
	for _ in range(5):
		check = _check_rows(plan, keep, reexam)
		if not check["errors"]:
			break
		more = {keep[x["row"] - 1]["sheet_row"] for x in check["errors"]}
		issues += [{"sheet_row": keep[x["row"] - 1]["sheet_row"], "level": "error", "message": x["message"],
		            "line": _line_text(keep[x["row"] - 1])} for x in check["errors"]]
		keep = [r for r in keep if r["sheet_row"] not in more]
	if not keep:
		log = write_import_log(sheet, exam_plan, file_url, total, 0, issues)
		frappe.db.commit()
		frappe.throw(_("No line of the sheet can be imported. See {0}.").format(
			f'<a href="/desk/exam-sheet-import-log/{log}">{log}</a>'))
	plan.save()
	summary.update(imported=len(keep), skipped=total - len(keep),
	               log=write_import_log(sheet, exam_plan, file_url, total, len(keep), issues))
	frappe.db.commit()
	return summary


def _row_no(v):
	return int(v) if str(v).isdigit() else 10 ** 9


def write_import_log(sheet, exam_plan, file_url, total, imported, issues):
	log = frappe.new_doc("Exam Sheet Import Log")
	log.update({
		"sheet": sheet, "exam_plan": exam_plan, "import_file": file_url,
		"status": "Failed" if not imported else ("Imported with skipped lines" if imported < total else "Imported"),
		"imported_by": frappe.session.user, "imported_on": frappe.utils.now_datetime(),
		"total_lines": total, "imported_lines": imported, "skipped_lines": total - imported,
	})
	order = {"error": 0, "warning": 1, "info": 2}
	# errors and warnings only: "kept as text" notes would bury them
	for x in sorted((x for x in issues if x["level"] != "info"), key=lambda x: (order[x["level"]], _row_no(x["sheet_row"]))):
		log.append("issues", {"sheet_row": str(x["sheet_row"]), "level": x["level"], "line": x.get("line", ""), "message": x["message"]})
	log.insert(ignore_permissions=True)
	return log.name


def issues_workbook(issues, title):
	"""Problems of an import, one line per sheet row: Sheet row | Level | Line | Problem."""
	wb = Workbook()
	ws = wb.active
	ws.title = "Problems"
	widths = {"A": 11, "B": 10, "C": 70, "D": 80}
	for col, w in widths.items():
		ws.column_dimensions[col].width = w
	_cell(ws, 1, 1, title, bold=True, size=12, align=LEFT)
	ws.merge_cells("A1:D1")
	for c, h in enumerate(("Sheet row", "Level", "Line", "Problem"), 1):
		_cell(ws, 2, c, h, bold=True, fill=HEAD_GREY, size=11)
	order = {"error": 0, "warning": 1, "info": 2}
	rows = sorted((x for x in issues if x["level"] != "info"), key=lambda x: (order.get(x["level"], 3), _row_no(x["sheet_row"])))
	for r, x in enumerate(rows, 3):
		for c, v in enumerate((x["sheet_row"], x["level"], x.get("line", ""), x["message"]), 1):
			_cell(ws, r, c, v, size=10, align=LEFT)
		if x["level"] == "error":
			ws.cell(r, 2).fill = PatternFill("solid", fgColor="FDE6E8")
	ws.freeze_panes = "A3"
	_fit_heights(ws, 3, len(rows) + 2, widths, minimum=15, line=13)
	return wb


# ── Continuing Evaluation Schedule ────────────────────────────────────────────

def _reexam_components():
	return set(frappe.get_all("Exam Component", filters={"component_type": "Re Exam"}, pluck="name"))


def _schema_configs(course, exam_plan):
	from slcm.slcm.doctype.exam_assessment_schedule.exam_assessment_schedule import _get_mapped_schema

	schema = _get_mapped_schema(course, exam_plan)
	return frappe.get_all(
		"Schema Assessment Config", filters={"parent": schema, "parenttype": "Evaluation Schema"},
		fields=["label", "component", "assessment_type", "maximum_marks"], order_by="idx asc",
	) if schema else []


def _marks_text(value):
	return f"{flt(value):g} marks" if flt(value) else ""


def _date_text(value):
	if not value:
		return ""
	d = getdate(value)
	return f"{_ordinal(d.day)} {d.strftime('%b %Y')}"


def _plan_schedules(plan):
	"""Active Exam Assessment Schedules of the plan's term (this plan's or no plan's)."""
	return [s for s in frappe.get_all(
		"Exam Assessment Schedule", filters={"term": plan.term, "status": "Active"},
		fields=["name", "programme", "exam_plan"], order_by="programme asc, creation asc",
	) if s.exam_plan in (None, "", plan.name)] if plan.term else []


# Continuing Evaluation Schedule, laid out like the office's sheet: per subject
# its Course Faculty and one row per component (Marks, Due Date for Submission,
# Date for activities / Mid-Term Exam / Class Test, Extension Applicable), then
# any extra columns the exam plan adds (ce_extra_columns on the Exam Plan).
CE_COLUMNS = (
	("faculty", "Course Faculty", 22),
	("subject", "Subject", 18),
	("label", "Component", 36),
	("marks", "Marks", 11),
	("due", "Due Date for Submission", 30),
	("date", "Date for activities/ Mid-Term Exam/Class Test", 24),
	("extension", "Extension Applicable", 30),
)
CE_EXTRA_WIDTH = 22
CE_HEAD_FILL = PatternFill("solid", fgColor="DCE3EE")
_COL_KEY = re.compile(r"^[a-z0-9_]{1,24}$")


def plan_extra_columns(exam_plan):
	"""[{key, label}] extra columns of the plan's evaluation schedule."""
	raw = frappe.db.get_value("Exam Plan", exam_plan, "ce_extra_columns")
	try:
		cols = frappe.parse_json(raw) if raw else []
	except Exception:
		cols = []
	return [{"key": c["key"], "label": _text(c.get("label"))} for c in cols or []
	        if isinstance(c, dict) and _COL_KEY.match(cstr(c.get("key"))) and _text(c.get("label"))]


def _clean_columns(columns):
	"""Validate the extra columns sent by the planner / found in a sheet."""
	out, seen = [], set()
	for c in columns or []:
		key, label = cstr((c or {}).get("key")), _text((c or {}).get("label"))
		if not _COL_KEY.match(key):
			frappe.throw(_("Extra column {0} has an invalid key.").format(frappe.bold(label or key)))
		if not label:
			frappe.throw(_("Every extra column needs a name. Name the empty column, or remove it."), title=_("Column name missing"))
		if _norm(label) in {_norm(x[1]) for x in CE_COLUMNS} | seen:
			frappe.throw(_("There are two columns called {0}. Give each column a different name.").format(frappe.bold(label)),
			             title=_("Duplicate column name"))
		seen.add(_norm(label))
		out.append({"key": key, "label": label})
	return out


def _course_faculty(course, term):
	"""Faculty of the course's Classes this term, one name per line."""
	if not term:
		return ""
	ids = frappe.get_all("Classes", filters={"course": course, "academic_term": term, "faculty": ["is", "set"]},
	                     pluck="faculty", distinct=True, order_by="faculty")
	from slcm.slcm.utils.exam_timetable import _faculty_label

	names = []
	for f in ids:
		n = _faculty_label(f)
		if n and n not in names:
			names.append(n)
	return "\n".join(names)


def _extra(value, keys):
	try:
		data = frappe.parse_json(value) if isinstance(value, str) else (value or {})
	except Exception:
		data = {}
	return {k: _text(data.get(k)) for k in keys if isinstance(data, dict) and _text(data.get(k))}


def assessment_grid(exam_plan):
	"""{columns, lines}: one line per course with its faculty and evaluations
	(label, marks, due, date, extension, extra). A course taught in several
	programmes shows once. Mapped courses without assessments yet show their
	schema's (suggested)."""
	plan = frappe.get_doc("Exam Plan", exam_plan)
	reexam = _reexam_components()
	columns = plan_extra_columns(exam_plan)
	keys = [c["key"] for c in columns]
	lines = {}
	for s in _plan_schedules(plan):
		doc = frappe.get_doc("Exam Assessment Schedule", s.name)
		configs = {}
		for it in doc.assessments:
			if it.component in reexam:
				continue
			line = lines.setdefault(it.course, frappe._dict(course=it.course, programmes=[], evaluations=[], faculty_override="", source=doc.name))
			if s.programme not in line.programmes:
				line.programmes.append(s.programme)
			if line.source != doc.name:
				continue
			if it.course not in configs:
				configs[it.course] = {(c.component, c.assessment_type): c.maximum_marks for c in _schema_configs(it.course, exam_plan)}
			line.evaluations.append({
				"label": it.assessment_label or "",
				"marks": it.marks_text or _marks_text(configs[it.course].get((it.component, it.assessment_type))),
				"due": it.get("due_date_text") or "",
				"date": it.date_text or _date_text(it.assessment_date),
				"extension": it.get("extension_text") or "",
				"extra": _extra(it.get("extra_values"), keys),
			})
		for n in doc.get("course_notes") or []:
			if n.course in lines and lines[n.course].source == doc.name:
				lines[n.course].faculty_override = n.get("faculty_text") or ""

	mapped = frappe.get_all("Course Schema Assignment", filters={"exam_plan": exam_plan}, pluck="course")
	for course in mapped:
		if course not in lines:
			configs = [c for c in _schema_configs(course, exam_plan) if c.component not in reexam]
			names = Counter(_norm(c.label or c.assessment_type or c.component) for c in configs)
			lines[course] = frappe._dict(course=course, programmes=_term_programmes(course, plan.term) if plan.term else [],
			                             faculty_override="", suggested=1, evaluations=[
				# a label used twice in the schema (Project › Viva, Viva › Viva) is named after its component,
				# since an Assessment Schedule lists each name once per course
				{"label": (lbl if names[_norm(lbl)] == 1 else f"{c.component} – {lbl}"), "marks": _marks_text(c.maximum_marks),
				 "due": "", "date": "", "extension": "", "extra": {},
				 # the schema assessment it stands for, so the saved row counts towards the result
				 "component": c.component, "assessment_type": c.assessment_type}
				for c in configs for lbl in [c.label or c.assessment_type or c.component]
			])
	names = dict(frappe.get_all("Course", filters={"name": ["in", list(lines) or [""]]}, fields=["name", "course_name"], as_list=True))
	out = []
	for line in lines.values():
		line.course_name = names.get(line.course, line.course)
		line.faculty_default = _course_faculty(line.course, plan.term)
		line.faculty = line.pop("faculty_override") or line.faculty_default
		line.pop("source", None)
		out.append(line)
	out.sort(key=lambda x: _norm(x.course_name))
	return {"columns": columns, "lines": out}


def _term_programmes(course, term):
	return frappe.get_all("Classes", filters={"course": course, "academic_term": term, "programme": ["is", "set"]},
	                      pluck="programme", distinct=True, order_by="programme")


def save_assessment_grid(exam_plan, lines, columns=None):
	"""Write sheet lines into the Exam Assessment Schedule of every programme
	teaching each course (made when missing). Evaluations keep their schema
	assessment (component / type) by label, then by order; assessments that
	already have marks are never removed. columns (when given) replace the
	plan's extra columns."""
	plan = frappe.get_doc("Exam Plan", exam_plan)
	if not plan.term:
		frappe.throw(_("Set the Exam Plan's Academic Term first."))
	if columns is not None:
		columns = _clean_columns(columns)
		frappe.db.set_value("Exam Plan", exam_plan, "ce_extra_columns", frappe.as_json(columns), update_modified=False)
	keys = [c["key"] for c in (columns if columns is not None else plan_extra_columns(exam_plan))]
	academic_year = frappe.db.get_value("Academic Term", plan.term, "academic_year")
	term_start = frappe.db.get_value("Academic Term", plan.term, "term_start_date")
	reexam = _reexam_components()
	docs, warnings, saved = {}, [], 0

	def schedule_for(programme):
		if programme not in docs:
			name = frappe.db.get_value("Exam Assessment Schedule", {"term": plan.term, "programme": programme, "status": "Active"}, "name")
			doc = frappe.get_doc("Exam Assessment Schedule", name) if name else frappe.new_doc("Exam Assessment Schedule")
			if not name:
				doc.update({"academic_year": academic_year, "term": plan.term, "programme": programme, "status": "Active"})
			doc.exam_plan = doc.exam_plan or exam_plan
			docs[programme] = doc
		return docs[programme]

	course_names = {}
	for line in lines:
		course = line.get("course")
		if not course:
			continue
		course_names[course] = course_names.get(course) or frappe.db.get_value("Course", course, "course_name")
		programmes = _term_programmes(course, plan.term)
		if not programmes:
			warnings.append(_("{0}: no Class teaches it in {1}, not saved.").format(course_names[course] or course, plan.term))
			continue
		if "faculty" in line:
			# keep only a real override: the Classes' faculty is shown anyway
			default = _course_faculty(course, plan.term)
			typed = _text(line.get("faculty"))
			line = dict(line, faculty="" if _norm(typed) == _norm(default) else typed)
		for p in programmes:
			warnings += _apply_course(schedule_for(p), course, course_names[course], line, reexam, term_start, keys)
		saved += 1
	for doc in docs.values():
		doc.save()
	frappe.db.commit()
	return {"courses": saved, "schedules": sorted(d.name for d in docs.values()), "warnings": sorted(set(warnings))}


def _sheet_text(value):
	text = _text(value)
	return "" if text == "-" else text


def _apply_course(doc, course, course_name, line, reexam, term_start, keys=()):
	evals = [e for e in (line.get("evaluations") or []) if _text(e.get("label")) not in ("", "-")]
	mine = [it for it in doc.assessments if it.course == course and it.component not in reexam]
	used, matched, warnings = set(), {}, []
	end_term = {id(it): _is_end_term(it.component, it.assessment_type, it.assessment_label) for it in mine}
	same_kind = lambda e, it: _is_end_term(e["label"]) == end_term[id(it)]

	def take(i, it):
		matched[i] = it
		used.add(id(it))

	for i, e in enumerate(evals):                      # same label
		it = next((it for it in mine if id(it) not in used and _norm(it.assessment_label) == _norm(e["label"])), None)
		if it:
			take(i, it)
	for i, e in enumerate(evals):                      # shares 2+ words, e.g. End-term examination ~ End Term Paper
		if i in matched:
			continue
		scored = [(len(_words(e["label"]) & (_words(it.assessment_label) | _words(it.assessment_type))), it) for it in mine
		          if id(it) not in used and same_kind(e, it)]
		best = max(scored, key=lambda x: x[0], default=(0, None))
		if best[0] >= 2:
			take(i, best[1])
	for i, e in enumerate(evals):                      # then in order
		if i not in matched:
			it = next((it for it in mine if id(it) not in used and same_kind(e, it)), None)
			if it:
				take(i, it)

	ordered = []
	for i, e in enumerate(evals):
		it = matched.get(i) or doc.append("assessments", {"course": course, "course_name": course_name})
		if not it.component and e.get("component") and e.get("assessment_type"):
			taken = {(x.component, x.assessment_type) for x in doc.assessments if x.course == course and x is not it}
			if (e["component"], e["assessment_type"]) not in taken:
				it.component, it.assessment_type = e["component"], e["assessment_type"]
		date_text = _sheet_text(e.get("date"))
		if it.date_text != date_text or not it.name:
			parsed = _parse_date(date_text, term_start)
			if parsed or date_text:
				it.assessment_date = datetime.combine(parsed, datetime.min.time()) if parsed else None
		# columns an older sheet doesn't have are left as they are
		if "due" in e:
			due_text = _sheet_text(e.get("due"))
			if (it.get("due_date_text") or "") != due_text or not it.name:
				# a real date fills the First Submission Deadline (end of that day); text such as
				# "Rolling basis…" stays text, and a deadline set on the form is never cleared here
				parsed = _parse_date(due_text, term_start)
				deadline = datetime.combine(parsed, datetime.max.time().replace(microsecond=0)) if parsed else None
				if deadline and _deadline_fits(it, deadline):
					it.first_submission_deadline = deadline
			it.due_date_text = due_text
		if "extension" in e:
			it.extension_text = _sheet_text(e.get("extension"))
		if "extra" in e:
			vals = {k: _sheet_text(v) for k, v in (e.get("extra") or {}).items() if k in keys and _sheet_text(v)}
			it.extra_values = frappe.as_json(vals) if vals else None
		it.assessment_label = _text(e["label"])
		it.marks_text = _sheet_text(e.get("marks"))
		it.date_text = date_text
		if not it.component:
			warnings.append(_("{0} › {1}: no matching assessment in the Evaluation Schema, so marks entered for it are not counted in the result.").format(
				course_name or course, it.assessment_label.split("\n")[0]))
		ordered.append(it)
	for it in mine:
		if id(it) in used:
			continue
		if it.name and frappe.db.exists("Student Assessment Marks", {"schedule_item": it.name}):
			warnings.append(_("{0} › {1} has marks entered, so it was kept.").format(course_name or course, it.assessment_label))
			ordered.append(it)

	# the course's lines in sheet order where the course was; re-exam rows after them
	rows = list(doc.assessments)
	first = next((k for k, it in enumerate(rows) if it.course == course), len(rows))
	before = [it for it in rows[:first] if it.course != course]
	after = [it for it in rows[first:] if it.course != course]
	doc.set("assessments", before + ordered + [it for it in rows if it.course == course and it.component in reexam] + after)
	for k, it in enumerate(doc.assessments, 1):
		it.idx = k

	# course note: faculty override, and SGD / remarks (only when the sheet has them)
	note = next((n for n in doc.get("course_notes") or [] if n.course == course), None)
	vals = {
		"faculty_text": note.get("faculty_text") if note else "",
		"sgd": note.sgd if note else "",
		"remarks": note.remarks if note else "",
	}
	if "faculty" in line:
		vals["faculty_text"] = _sheet_text(line.get("faculty"))
	for k in ("sgd", "remarks"):
		if k in line:
			vals[k] = _sheet_text(line.get(k))
	if any(vals.values()):
		note = note or doc.append("course_notes", {"course": course})
		note.update(vals)
	elif note:
		doc.set("course_notes", [n for n in doc.course_notes if n is not note])
	return warnings


def _deadline_fits(it, first):
	"""First Submission Deadline that keeps the Assessment Schedule's date rules
	(after the assessment date, before a second deadline and the marks entry deadline)."""
	dt = frappe.utils.get_datetime
	if it.assessment_date and first < dt(it.assessment_date):
		return False
	if it.get("second_submission_deadline") and dt(it.second_submission_deadline) <= first:
		return False
	if not it.get("second_submission_deadline") and it.get("marks_entry_deadline") and dt(it.marks_entry_deadline) <= first:
		return False
	return True


def _sheet_title(text, used):
	title = re.sub(r"[\[\]\:\*\?\/\\]", " ", text).strip()[:31] or "Sheet"
	base, n = title, 2
	while title.lower() in used:
		title = f"{base[:28]} {n}"
		n += 1
	used.add(title.lower())
	return title


def assessment_workbook(exam_plan, blank=False):
	"""The office's Continuing Evaluation Schedule: a sheet per programme, a
	title row, then per subject its faculty and one row per component."""
	grid = assessment_grid(exam_plan)
	lines, extra = grid["lines"], grid["columns"]
	term = frappe.db.get_value("Exam Plan", exam_plan, "term") or exam_plan
	from openpyxl.utils import get_column_letter
	from openpyxl.worksheet.properties import PageSetupProperties

	header = [c[1] for c in CE_COLUMNS] + [c["label"] for c in extra]
	widths = {get_column_letter(i): w for i, w in enumerate([c[2] for c in CE_COLUMNS] + [CE_EXTRA_WIDTH] * len(extra), 1)}
	ncol = len(header)

	by_programme = {}
	for line in lines:
		for p in (line.programmes or [_("Other courses")]):
			by_programme.setdefault(p, []).append(line)
	if not by_programme:
		by_programme[_("Continuing Evaluation")] = []

	wb = Workbook()
	wb.remove(wb.active)
	used = set()
	for programme in sorted(by_programme, key=_norm):
		ws = wb.create_sheet(_sheet_title(programme, used))
		for col, w in widths.items():
			ws.column_dimensions[col].width = w
		# title row: "<Programme> - <Term>" left, CONTINUING EVALUATION SCHEDULE right
		split = max(2, ncol - 2)
		_merge(ws, 1, 1, 1, split)
		ws.cell(1, 1, f"{programme} - {term}").font = Font(name="Arial", size=14, bold=True)
		ws.cell(1, 1).alignment = Alignment(vertical="bottom")
		_merge(ws, 1, split + 1, 1, ncol)
		ws.cell(1, split + 1, "CONTINUING EVALUATION SCHEDULE").font = Font(name="Arial", size=11, bold=True)
		ws.cell(1, split + 1).alignment = Alignment(horizontal="right", vertical="bottom")
		ws.row_dimensions[1].height = 30
		for c, h in enumerate(header, 1):
			_cell(ws, 2, c, h, bold=True, fill=CE_HEAD_FILL, font="Arial", size=11,
			      align=Alignment(horizontal="left", vertical="center", wrap_text=True))
		ws.row_dimensions[2].height = 34
		r = 3
		for line in by_programme[programme]:
			evals = [] if blank else line.evaluations
			evals = evals or [{}] * (4 if blank else 1)
			first = r
			for e in evals:
				values = ["", "", e.get("label", ""), e.get("marks", ""), e.get("due", ""), e.get("date", ""), e.get("extension", "")]
				values += [(e.get("extra") or {}).get(c["key"], "") for c in extra]
				for c, v in enumerate(values, 1):
					_cell(ws, r, c, v, size=10, font="Arial", bold=(c == 4),
					      align=Alignment(horizontal="center" if c == 4 else "left", vertical="center", wrap_text=True))
				r += 1
			_cell(ws, first, 1, line.faculty, size=10, font="Arial", align=Alignment(vertical="center", wrap_text=True))
			_cell(ws, first, 2, line.course_name, size=10, font="Arial", bold=True,
			      align=Alignment(horizontal="center", vertical="center", wrap_text=True))
			_merge(ws, first, 1, r - 1, 1)
			_merge(ws, first, 2, r - 1, 2)
		if r > 3:
			_fit_heights(ws, 3, r - 1, widths, minimum=18, line=13)
		ws.freeze_panes = "C3"
		ws.print_title_rows = "1:2"
		ws.page_setup.orientation = "landscape"
		ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
		ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
		ws.oddFooter.left.text = f"{programme} - {term}"
		ws.oddFooter.right.text = "Page &P of &N"
	return wb


def _grid_ws(ws):
	width = max(ws.max_column, 15)
	grid = [list(r) + [None] * (width - len(r)) for r in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=width, values_only=True)]
	for rng in ws.merged_cells.ranges:
		if rng.min_col == rng.max_col and rng.max_row > rng.min_row:
			v = grid[rng.min_row - 1][rng.min_col - 1]
			for r in range(rng.min_row, rng.max_row):
				grid[r][rng.min_col - 1] = v
	return grid


def _ce_header_map(row):
	"""Column index of each field in a template header row, extras by their text; None if not one."""
	cols, extras = {}, []
	for j, v in enumerate(row):
		h = _norm(v)
		if not h:
			continue
		key = ("faculty" if "faculty" in h else
		       "subject" if h in ("subject", "course", "course name") else
		       "label" if h in ("component", "components", "assessment", "evaluation") else
		       "marks" if h in ("marks", "mark", "max marks", "maximum marks") else
		       "due" if h.startswith("due") or "submission" in h else
		       "date" if h.startswith("date") else
		       "extension" if "extension" in h else None)
		if key and key not in cols:
			cols[key] = j
		elif not key:
			extras.append((j, _text(v)))
	# the older sheet repeats "Evaluation n/Assessment n" groups: not this layout
	if sum(1 for v in row if re.match(r"^(evaluation|assessment) \d", _norm(v))) > 1:
		return None, None
	return (cols, extras) if "subject" in cols and "label" in cols else (None, None)


def parse_assessment_sheet(content):
	"""Lines of a Continuing Evaluation Schedule workbook: [{sheet_row, sheet, subject,
	faculty?, evaluations: [{label, marks, due, date, extension, extra: {label: value}}]}].
	Reads every worksheet; the older one-row-per-subject sheet is still accepted."""
	try:
		wb = load_workbook(BytesIO(content), data_only=True)
	except Exception:
		frappe.throw(_("This is not an Excel (.xlsx) file."))
	lines, found = [], False
	for ws in wb.worksheets:
		grid = _grid_ws(ws)
		head = cols = None
		for i, row in enumerate(grid[:15]):
			cols, extras = _ce_header_map(row)
			if cols:
				head = i
				break
		if head is None:
			continue
		found = True
		cell = lambda row, j: "" if j is None or j >= len(row) else (
			_date_text(row[j]) if isinstance(row[j], (date, datetime)) else _text(row[j]))
		current = None
		for i in range(head + 1, len(grid)):
			row = grid[i]
			subject, label = cell(row, cols.get("subject")), cell(row, cols["label"])
			if not subject and current and label:
				subject = current["subject"]          # subject typed only on its first row
			if not subject:
				continue
			if not current or subject != current["subject"]:
				current = {"sheet_row": i + 1, "sheet": ws.title, "subject": subject, "evaluations": []}
				if "faculty" in cols:
					current["faculty"] = cell(row, cols["faculty"])
				lines.append(current)
			if label and label != "-":
				ev = {"label": label}
				for k in ("marks", "due", "date", "extension"):
					if k in cols:
						ev[k] = cell(row, cols[k])
				ev["extra"] = {name: cell(row, j) for j, name in extras if cell(row, j)}
				current["evaluations"].append(ev)
	if found:
		return lines
	return _parse_wide_sheet(content)


def _parse_wide_sheet(content):
	"""The older sheet: Subject | Evaluation n/Assessment n, Marks, Date (×n) | SGD | remarks."""
	grid = _grid(content)
	head = next((i for i, row in enumerate(grid) if _norm(row[0]) == "subject"), None)
	if head is None:
		frappe.throw(_("No header row found. The sheet needs a row with Course Faculty | Subject | Component | Marks | "
		               "Due Date for Submission | Date for activities | Extension Applicable (download a sheet to see it)."),
		             title=_("Not an evaluation schedule"))
	header = [_norm(v) for v in grid[head]]
	groups, c = [], 1
	while c < len(header) and (header[c].startswith("evaluation") or header[c].startswith("assessment")):
		groups.append(c)
		c += 3
	sgd_col = next((j for j, h in enumerate(header) if h == "sgd"), c)
	lines = []
	for i in range(head + 1, len(grid)):
		row = grid[i]
		subject = _text(row[0])
		if not subject:
			continue
		cell = lambda j: (_date_text(row[j]) if isinstance(row[j], (date, datetime)) else _text(row[j])) if j < len(row) else ""
		evals = [{"label": cell(g), "marks": cell(g + 1), "date": cell(g + 2)} for g in groups]
		lines.append({
			"sheet_row": i + 1, "subject": subject,
			"evaluations": [e for e in evals if e["label"] not in ("", "-")],
			"sgd": cell(sgd_col), "remarks": cell(sgd_col + 1),
		})
	return lines


def assessment_issues(exam_plan, content, mapping=None):
	"""Sheet lines with their Course (name, code or ID; or the mapping
	{subject: course} picked in the preview); a subject without one is an error.
	A course on several programme sheets is taken from the first one."""
	plan = frappe.get_doc("Exam Plan", exam_plan)
	parsed = parse_assessment_sheet(content)
	index = _course_index(plan.term)
	mapping = mapping or {}
	issues, lines, seen = [], [], {}
	for line in parsed:
		line["course"] = mapping.get(line["subject"]) or index.get(_norm(line["subject"]))
		where = f"{line['sheet']} › " if line.get("sheet") else ""
		if not line["course"]:
			issues.append({"sheet_row": line["sheet_row"], "level": "error", "line": f"{where}{line['subject']}",
			               "message": _("{0} is not a Course of this term: skipped. Pick the course in the import preview.").format(line["subject"])})
			lines.append(line)
			continue
		if line["course"] in seen:
			first = seen[line["course"]]
			if frappe.as_json(first.get("evaluations")) != frappe.as_json(line.get("evaluations")) or first.get("faculty") != line.get("faculty"):
				issues.append({"sheet_row": line["sheet_row"], "level": "warning", "line": f"{where}{line['subject']}",
				               "message": _("{0} is also on sheet {1} with different details; the one on {1} is used.").format(
					               line["subject"], first.get("sheet") or "")})
			continue
		seen[line["course"]] = line
		lines.append(line)
	return plan, lines, issues


def _columns_for_import(exam_plan, lines):
	"""Plan's extra columns plus any new ones in the sheet (matched by name); values keyed by column key."""
	columns = plan_extra_columns(exam_plan)
	by_name = {_norm(c["label"]): c["key"] for c in columns}
	for line in lines:
		for e in line.get("evaluations") or []:
			if "extra" not in e:
				continue
			keyed = {}
			for name, value in (e.get("extra") or {}).items():
				if _norm(name) not in by_name:
					key = "c" + frappe.generate_hash(length=8).lower()
					columns.append({"key": key, "label": name})
					by_name[_norm(name)] = key
				keyed[by_name[_norm(name)]] = value
			e["extra"] = keyed
	return columns


def import_assessment_sheet(exam_plan, content, mapping=None, apply=False, file_url=None):
	"""Preview, or (apply) save the subjects that have a Course; the others are
	skipped and the import is written to an Exam Sheet Import Log."""
	plan, lines, issues = assessment_issues(exam_plan, content, mapping)
	unmatched = [{"sheet_row": x["sheet_row"], "subject": x["line"]} for x in issues if x["level"] == "error"]
	out = {"lines": len(lines), "matched": sum(1 for x in lines if x["course"]), "unmatched": unmatched,
	       "rows": [{k: x.get(k) for k in ("sheet_row", "subject", "course")} | {"evaluations": len(x["evaluations"])} for x in lines]}
	if apply:
		good = [x for x in lines if x["course"]]
		if not good:
			frappe.throw(_("No subject of the sheet is matched to a course. Pick the courses in the preview."))
		columns = _columns_for_import(exam_plan, good)
		out.update(save_assessment_grid(exam_plan, good, columns))
		issues += [{"sheet_row": "", "level": "warning", "line": "", "message": w} for w in out["warnings"]]
		out.update(saved=1, imported=len(good), skipped=len(lines) - len(good),
		           log=write_import_log("Continuing Evaluation Schedule", exam_plan, file_url, len(lines), len(good), issues))
		frappe.db.commit()
	else:
		taught = frappe.get_all("Classes", filters={"academic_term": plan.term}, pluck="course", distinct=True) if plan.term else []
		out["courses"] = frappe.get_all("Course", filters={"name": ["in", taught or [""]]}, fields=["name", "course_name"], order_by="course_name")
	return out
