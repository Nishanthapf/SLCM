# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
RFID Attendance Report
======================
Swipe activity per period, broken down by terminal and venue.

On screen (two levels):
  Period row  : totals across all terminals for the Hour / Day / Week / Month
  Detail rows : one per terminal (reader) + venue in that period

Filters: View By, From / To (datetime; a date alone means start of day for
From and end of day for To), academic year, programme, terminal, venue,
student, known students only.

Venue comes from RFID Device Room Mapping (device -> Venue Master on the
swipe date), falling back to the log's own location text.

Excel download (same filters) — student-level detail lives here, not on screen:
  Report                  the on-screen table
  Student-wise (Daily)    one row per student per day
  Student Totals          one row per student for the whole range
  Most Swiped - Daily / Weekly / Monthly
                          top student per period, overall and per terminal
"""

import calendar as _calendar
import datetime as _dt
import io
import json as _json
from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, getdate

from slcm.permissions import AAD_ROLES

REPORT_NAME = "RFID Attendance Report"
VIEWS = ("Hourly", "Daily", "Weekly", "Monthly")
MULTISELECT_FILTERS = ("academic_year", "programme", "terminal_alias", "venue", "student")
NOT_MAPPED = "Not mapped"
MAX_EXCEL_ROWS = 300000

# Venue of the reader on the swipe date (Venue Master via RFID Device Room
# Mapping); falls back to the log's location text, then NOT_MAPPED.
VENUE_EXPR = f"""COALESCE(
    (SELECT m.room FROM `tabRFID Device Room Mapping` m
     WHERE m.device = al.device_id AND m.is_active = 1
       AND m.effective_from <= DATE(al.swipe_time)
       AND (m.effective_to IS NULL OR m.effective_to >= DATE(al.swipe_time))
     ORDER BY m.effective_from DESC LIMIT 1),
    NULLIF(al.location, ''),
    '{NOT_MAPPED}')"""

TERMINAL_EXPR = "COALESCE(NULLIF(al.terminal_alias, ''), NULLIF(al.device_id, ''), 'Unknown Terminal')"
KNOWN = "(b.student IS NOT NULL AND b.student != '')"


# ── Filter options API ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_filter_options(filter_name, txt=""):
	frappe.only_for(("System Manager", *AAD_ROLES))
	txt = (txt or "").strip()
	like = f"%{txt}%"

	if filter_name == "student":
		rows = frappe.db.sql("""
			SELECT sm.name, sm.first_name
			FROM `tabStudent Master` sm
			WHERE EXISTS (SELECT 1 FROM `tabAttendance Log` al WHERE al.student = sm.name)
			AND (sm.name LIKE %(like)s OR sm.first_name LIKE %(like)s)
			ORDER BY sm.first_name ASC
			LIMIT 50
		""", {"like": like}, as_dict=True)
		return [{"label": f"{r.first_name or r.name}  ({r.name})", "value": r.name, "description": ""} for r in rows]

	if filter_name == "academic_year":
		sql = """SELECT DISTINCT academic_year FROM `tabStudent Master`
			WHERE IFNULL(academic_year, '') != '' AND academic_year LIKE %(like)s ORDER BY academic_year DESC"""
	elif filter_name == "programme":
		sql = """SELECT DISTINCT programme_of_study FROM `tabStudent Master`
			WHERE IFNULL(programme_of_study, '') != '' AND programme_of_study LIKE %(like)s ORDER BY programme_of_study"""
	elif filter_name == "terminal_alias":
		sql = """SELECT DISTINCT terminal_alias FROM `tabAttendance Log`
			WHERE IFNULL(terminal_alias, '') != '' AND terminal_alias LIKE %(like)s ORDER BY terminal_alias"""
	elif filter_name == "venue":
		sql = """SELECT v FROM (
				SELECT DISTINCT room AS v FROM `tabRFID Device Room Mapping` WHERE is_active = 1
				UNION SELECT DISTINCT location FROM `tabAttendance Log` WHERE IFNULL(location, '') != ''
			) x WHERE v LIKE %(like)s ORDER BY v"""
	else:
		return []

	values = [r[0] for r in frappe.db.sql(sql, {"like": like})]
	if filter_name == "venue" and txt.lower() in NOT_MAPPED.lower():
		values.append(NOT_MAPPED)
	return [{"label": v, "value": v, "description": ""} for v in values]


# ── Entry point ────────────────────────────────────────────────────────────────

def execute(filters=None):
	filters = frappe._dict(filters or {})
	_validate(filters)
	base, params = _base_query(filters)

	columns = _get_columns(filters)
	data = _get_data(filters, base, params)
	summary = _get_summary(base, params)
	chart = _get_chart(data, filters)
	return columns, data, None, chart, summary


# ── Validation ─────────────────────────────────────────────────────────────────

def _validate(filters):
	"""Normalise From / To into filters.from_dt (inclusive) and filters.to_dt
	(exclusive). A To value with no time part covers that whole day; a To
	with a time includes that whole second."""
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From and To are required."))
	try:
		from_dt = get_datetime(filters.from_date)
		to_dt = get_datetime(filters.to_date)
	except Exception:
		frappe.throw(_("From and To must be valid dates/times."))
	if not from_dt or not to_dt:
		frappe.throw(_("From and To must be valid dates/times."))

	from_dt = from_dt.replace(microsecond=0)
	to_dt = to_dt.replace(microsecond=0)
	if _has_no_time(filters.to_date):
		to_dt = add_to_date(to_dt, days=1)
	else:
		to_dt = add_to_date(to_dt, seconds=1)

	if from_dt >= to_dt:
		frappe.throw(_("From must be before To."))
	if (filters.get("view_by") or "Daily") not in VIEWS:
		frappe.throw(_("View By must be one of: {0}").format(", ".join(VIEWS)))

	filters.from_dt, filters.to_dt = from_dt, to_dt


def _has_no_time(value):
	return isinstance(value, _dt.date) and not isinstance(value, _dt.datetime) or (
		isinstance(value, str) and len(value.strip()) <= 10
	)


# ── Columns ────────────────────────────────────────────────────────────────────

def _get_columns(filters):
	view = filters.get("view_by") or "Daily"
	period_label = {"Hourly": _("Hour"), "Daily": _("Date"), "Weekly": _("Week"), "Monthly": _("Month")}[view]
	return [
		{"fieldname": "period_label",    "label": period_label,              "fieldtype": "Data",     "width": 230},
		{"fieldname": "terminal_alias",  "label": _("Terminal / Room"),      "fieldtype": "Data",     "width": 165},
		{"fieldname": "venue",           "label": _("Venue"),                "fieldtype": "Data",     "width": 170},
		{"fieldname": "total_swipes",    "label": _("Total Swipes"),         "fieldtype": "Int",      "width": 115},
		{"fieldname": "unique_students", "label": _("Unique Students"),      "fieldtype": "Int",      "width": 130},
		{"fieldname": "unknown_swipes",  "label": _("Unknown Swipes"),       "fieldtype": "Int",      "width": 130},
		{"fieldname": "first_swipe",     "label": _("First Swipe"),          "fieldtype": "Datetime", "width": 175},
		{"fieldname": "last_swipe",      "label": _("Last Swipe"),           "fieldtype": "Datetime", "width": 175},
	]


# ── Base query: every filtered swipe, with terminal + venue resolved ──────────

def _parse_multiselect(raw):
	if not raw:
		return []
	if isinstance(raw, (list, tuple)):
		return [v for v in raw if v]
	if isinstance(raw, str):
		raw = raw.strip()
		if raw.startswith("["):
			try:
				return [v for v in _json.loads(raw) if v]
			except ValueError:
				pass
		return [v.strip() for v in raw.split(",") if v.strip()]
	return []


def _base_query(filters):
	"""(sql, params): a derived table `b` of the filtered swipes with columns
	swipe_time, student, terminal, venue. Every query in this report reads it,
	so the screen, the cards, the chart and the Excel all agree."""
	conditions = ["al.swipe_time >= %(from_dt)s", "al.swipe_time < %(to_dt)s"]
	params = {"from_dt": filters.from_dt, "to_dt": filters.to_dt}

	def add_in(expr, values, prefix):
		keys = []
		for i, v in enumerate(values):
			params[f"{prefix}_{i}"] = v
			keys.append(f"%({prefix}_{i})s")
		conditions.append(f"{expr} IN ({', '.join(keys)})")

	for fieldname, expr, prefix in (
		("terminal_alias", TERMINAL_EXPR, "t"),
		("venue", VENUE_EXPR, "v"),
		("student", "al.student", "s"),
		("academic_year", "sm.academic_year", "y"),
		("programme", "sm.programme_of_study", "p"),
	):
		values = _parse_multiselect(filters.get(fieldname))
		if values:
			add_in(expr, values, prefix)

	if filters.get("known_only"):
		conditions.append("(al.student IS NOT NULL AND al.student != '')")

	sql = f"""
		SELECT al.swipe_time AS swipe_time, al.student AS student,
			{TERMINAL_EXPR} AS terminal, {VENUE_EXPR} AS venue
		FROM `tabAttendance Log` al
		LEFT JOIN `tabStudent Master` sm ON sm.name = al.student
		WHERE {' AND '.join(conditions)}
	"""
	return sql, params


def _period_expr(view):
	return {
		"Hourly": "DATE_FORMAT(b.swipe_time, '%%Y-%%m-%%d %%H:00')",
		"Daily": "DATE(b.swipe_time)",
		"Weekly": "YEARWEEK(b.swipe_time, 3)",
		"Monthly": "DATE_FORMAT(b.swipe_time, '%%Y-%%m')",
	}[view]


# ── On-screen data ─────────────────────────────────────────────────────────────

def _get_data(filters, base, params):
	view = filters.get("view_by") or "Daily"
	period = _period_expr(view)

	detail_rows = frappe.db.sql(f"""
		SELECT {period} AS period_key, b.terminal, b.venue,
			COUNT(*) AS total_swipes,
			COUNT(DISTINCT CASE WHEN {KNOWN} THEN b.student END) AS unique_students,
			SUM(CASE WHEN {KNOWN} THEN 0 ELSE 1 END) AS unknown_swipes,
			MIN(b.swipe_time) AS first_swipe,
			MAX(b.swipe_time) AS last_swipe
		FROM ({base}) b
		GROUP BY period_key, b.terminal, b.venue
		ORDER BY period_key ASC, total_swipes DESC, b.terminal ASC
	""", params, as_dict=True)

	# Students who swiped at several terminals count once per period.
	unique_by_period = {
		str(r.period_key): int(r.unique_students or 0)
		for r in frappe.db.sql(f"""
			SELECT {period} AS period_key,
				COUNT(DISTINCT CASE WHEN {KNOWN} THEN b.student END) AS unique_students
			FROM ({base}) b
			GROUP BY period_key
		""", params, as_dict=True)
	}

	groups = OrderedDict()
	for r in detail_rows:
		groups.setdefault(str(r.period_key), []).append(r)

	data = []
	for period_key, rows in groups.items():
		data.append({
			"period_label": _period_label(period_key, view),
			"period_key": period_key,
			"terminal_alias": _("All terminals ({0})").format(len(rows)),
			"venue": "",
			"total_swipes": sum(int(r.total_swipes or 0) for r in rows),
			"unique_students": unique_by_period.get(period_key, 0),
			"unknown_swipes": sum(int(r.unknown_swipes or 0) for r in rows),
			"first_swipe": min((r.first_swipe for r in rows if r.first_swipe), default=None),
			"last_swipe": max((r.last_swipe for r in rows if r.last_swipe), default=None),
			"bold": 1,
			"is_period_row": 1,
		})
		for r in rows:
			data.append({
				"period_label": "",
				"period_key": period_key,
				"terminal_alias": r.terminal,
				"venue": r.venue,
				"total_swipes": int(r.total_swipes or 0),
				"unique_students": int(r.unique_students or 0),
				"unknown_swipes": int(r.unknown_swipes or 0),
				"first_swipe": r.first_swipe,
				"last_swipe": r.last_swipe,
			})
	return data


# ── Summary cards ──────────────────────────────────────────────────────────────

def _get_summary(base, params):
	agg = frappe.db.sql(f"""
		SELECT COUNT(*) AS total_swipes,
			COUNT(DISTINCT CASE WHEN {KNOWN} THEN b.student END) AS unique_known,
			COUNT(DISTINCT b.terminal) AS terminals,
			SUM(CASE WHEN {KNOWN} THEN 0 ELSE 1 END) AS unknown_swipes
		FROM ({base}) b
	""", params, as_dict=True)[0]

	total_students = frappe.db.count("Student Master")
	cards_assigned = frappe.db.count("Student Master", {"rfid_uid": ["is", "set"]})

	return [
		{"label": _("Total Swipes"),         "value": int(agg.total_swipes or 0),   "datatype": "Int", "indicator": "blue"},
		{"label": _("Unique Students"),      "value": int(agg.unique_known or 0),   "datatype": "Int", "indicator": "green"},
		{"label": _("Terminals Active"),     "value": int(agg.terminals or 0),      "datatype": "Int", "indicator": "blue"},
		{"label": _("Unknown Swipes"),       "value": int(agg.unknown_swipes or 0), "datatype": "Int", "indicator": "red"},
		{"label": _("Cards Assigned"),       "value": int(cards_assigned),          "datatype": "Int", "indicator": "green"},
		{"label": _("No Card Assigned Yet"), "value": max(int(total_students) - int(cards_assigned), 0),
		 "datatype": "Int", "indicator": "orange"},
	]


# ── Chart ──────────────────────────────────────────────────────────────────────

def _get_chart(data, filters):
	period_rows = [r for r in data if r.get("is_period_row")]
	if not period_rows:
		return None
	cap = 72 if (filters.get("view_by") == "Hourly") else 31
	period_rows = period_rows[-cap:]

	return {
		"data": {
			"labels": [r["period_label"] for r in period_rows],
			"datasets": [
				{"name": _("Known Students"), "values": [r["unique_students"] for r in period_rows], "chartType": "bar"},
				{"name": _("Unknown Swipes"), "values": [r["unknown_swipes"] for r in period_rows], "chartType": "bar"},
			],
		},
		"type": "bar",
		"colors": ["#2b2e4a", "#8b1a1a"],
		"barOptions": {"stacked": True},
		"title": _("Swipe Activity — {0}").format(filters.get("view_by") or "Daily"),
		"height": 280,
	}


# ── Excel download ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def download_excel(filters):
	"""Multi-sheet workbook for the current filters (see module docstring)."""
	if not frappe.get_doc("Report", REPORT_NAME).is_permitted():
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else (filters or {}))
	filters.setdefault("view_by", "Daily")
	_validate(filters)
	base, params = _base_query(filters)

	student_daily = _student_daily_rows(base, params)
	if len(student_daily) > MAX_EXCEL_ROWS:
		frappe.throw(_("Too many rows ({0}) for one download. Narrow the date range or filters.").format(len(student_daily)))

	report_rows = _get_data(filters, base, params)
	totals = _student_total_rows(base, params)
	top = {view: _most_swiped_rows(view, base, params) for view in ("Daily", "Weekly", "Monthly")}

	info = _student_info({r.student for r in student_daily})

	from openpyxl import Workbook
	from openpyxl.cell import WriteOnlyCell
	from openpyxl.styles import Alignment, Font, PatternFill

	wb = Workbook(write_only=True)
	header_font = Font(bold=True, color="FFFFFF")
	header_fill = PatternFill("solid", fgColor="2B2E4A")
	bold = Font(bold=True)

	def sheet(title, headers, widths, rows, note=None, bold_rows=None):
		ws = wb.create_sheet(title=title)
		for idx, width in enumerate(widths, start=1):
			ws.column_dimensions[_col_letter(idx)].width = width
		ws.freeze_panes = "A3" if note else "A2"
		if note:
			cell = WriteOnlyCell(ws, value=note)
			cell.font = Font(italic=True, color="555555")
			ws.append([cell])
		head = []
		for h in headers:
			c = WriteOnlyCell(ws, value=h)
			c.font, c.fill = header_font, header_fill
			c.alignment = Alignment(vertical="center")
			head.append(c)
		ws.append(head)
		for i, row in enumerate(rows):
			if bold_rows and bold_rows(i):
				cells = []
				for v in row:
					c = WriteOnlyCell(ws, value=v)
					c.font = bold
					cells.append(c)
				ws.append(cells)
			else:
				ws.append(row)

	scope = _scope_note(filters)

	# 1. Report (as on screen)
	sheet(
		_("Report"),
		[_("Period"), _("Terminal / Room"), _("Venue"), _("Total Swipes"), _("Unique Students"),
		 _("Unknown Swipes"), _("First Swipe"), _("Last Swipe")],
		[30, 22, 26, 13, 15, 15, 20, 20],
		[[_period_label(r["period_key"], filters.view_by) if r.get("is_period_row") else "",
		  r["terminal_alias"], r["venue"], r["total_swipes"], r["unique_students"], r["unknown_swipes"],
		  _naive(r["first_swipe"]), _naive(r["last_swipe"])] for r in report_rows],
		note=scope,
		bold_rows=lambda i: bool(report_rows[i].get("is_period_row")),
	)

	# 2. Student-wise (Daily)
	sheet(
		_("Student-wise (Daily)"),
		[_("Date"), _("Day"), _("Student ID"), _("Student Name"), _("Programme"), _("Academic Year"),
		 _("Swipes"), _("First Swipe"), _("Last Swipe"), _("Terminals"), _("Venues")],
		[12, 11, 22, 28, 34, 14, 9, 12, 12, 40, 40],
		[[r.day, _WEEKDAYS[r.day.weekday()], r.student, *_student_cols(info, r.student),
		  int(r.swipes), _time_only(r.first_swipe), _time_only(r.last_swipe), r.terminals, r.venues]
		 for r in student_daily],
		note=scope,
	)

	# 3. Student Totals
	info.update(_student_info({r.student for r in totals} - set(info)))
	sheet(
		_("Student Totals"),
		[_("Student ID"), _("Student Name"), _("Programme"), _("Academic Year"), _("Total Swipes"),
		 _("Days With Swipes"), _("Terminals Used"), _("First Swipe"), _("Last Swipe")],
		[22, 28, 34, 14, 13, 16, 15, 20, 20],
		[[r.student, *_student_cols(info, r.student), int(r.swipes), int(r.days), int(r.terminals),
		  _naive(r.first_swipe), _naive(r.last_swipe)] for r in totals],
		note=scope,
	)

	# 4-6. Most swiped per period
	for view, rows in top.items():
		info.update(_student_info({r["student"] for r in rows} - set(info)))
		sheet(
			_("Most Swiped - {0}").format(view),
			[_("Period"), _("Terminal / Room"), _("Venue"), _("Student ID"), _("Student Name"), _("Programme"),
			 _("Academic Year"), _("Their Swipes"), _("Known-Student Swipes There"), _("Share %"), _("Students Tied")],
			[30, 22, 26, 22, 28, 34, 14, 13, 24, 9, 13],
			[[_period_label(r["period_key"], view), r["terminal"], r["venue"], r["student"],
			  *_student_cols(info, r["student"]), r["swipes"], r["group_swipes"],
			  round(100.0 * r["swipes"] / r["group_swipes"], 1) if r["group_swipes"] else 0, r["ties"]]
			 for r in rows],
			note=scope + " · " + _("Top known student per period: first the period overall, then each terminal. "
			                       "Ties go to the lower Student ID; 'Students Tied' shows how many share the top count."),
			bold_rows=lambda i, rows=rows: rows[i]["terminal"] == _("All terminals"),
		)

	buf = io.BytesIO()
	wb.save(buf)
	frappe.response.filename = "RFID_Swipes_{0}_to_{1}.xlsx".format(
		filters.from_dt.strftime("%Y-%m-%d_%H%M"), _last_second(filters).strftime("%Y-%m-%d_%H%M"))
	frappe.response.filecontent = buf.getvalue()
	frappe.response.type = "binary"


def _student_daily_rows(base, params):
	return frappe.db.sql(f"""
		SELECT DATE(b.swipe_time) AS day, b.student,
			COUNT(*) AS swipes, MIN(b.swipe_time) AS first_swipe, MAX(b.swipe_time) AS last_swipe,
			GROUP_CONCAT(DISTINCT b.terminal ORDER BY b.terminal SEPARATOR ', ') AS terminals,
			GROUP_CONCAT(DISTINCT b.venue ORDER BY b.venue SEPARATOR ', ') AS venues
		FROM ({base}) b
		WHERE {KNOWN}
		GROUP BY day, b.student
		ORDER BY day ASC, swipes DESC, b.student ASC
	""", params, as_dict=True)


def _student_total_rows(base, params):
	return frappe.db.sql(f"""
		SELECT b.student, COUNT(*) AS swipes, COUNT(DISTINCT DATE(b.swipe_time)) AS days,
			COUNT(DISTINCT b.terminal) AS terminals,
			MIN(b.swipe_time) AS first_swipe, MAX(b.swipe_time) AS last_swipe
		FROM ({base}) b
		WHERE {KNOWN}
		GROUP BY b.student
		ORDER BY swipes DESC, b.student ASC
	""", params, as_dict=True)


def _most_swiped_rows(view, base, params):
	"""Per period: the overall top student, then the top student at each
	terminal + venue (terminals ordered by known-student swipes)."""
	period = _period_expr(view)

	def ranked(partition_cols, select_cols):
		part = ", ".join(["period_key", *partition_cols])
		return frappe.db.sql(f"""
			SELECT * FROM (
				SELECT r2.*,
					SUM(CASE WHEN r2.cnt = r2.mx THEN 1 ELSE 0 END) OVER (PARTITION BY {part}) AS ties
				FROM (
					SELECT r1.*,
						MAX(r1.cnt) OVER (PARTITION BY {part}) AS mx,
						SUM(r1.cnt) OVER (PARTITION BY {part}) AS group_swipes,
						ROW_NUMBER() OVER (PARTITION BY {part} ORDER BY r1.cnt DESC, r1.student ASC) AS rn
					FROM (
						SELECT {period} AS period_key, {select_cols} b.student, COUNT(*) AS cnt
						FROM ({base}) b
						WHERE {KNOWN}
						GROUP BY {part}, b.student
					) r1
				) r2
			) r3
			WHERE r3.rn = 1
			ORDER BY period_key ASC, group_swipes DESC
		""", params, as_dict=True)

	overall = ranked([], "")
	per_terminal = ranked(["terminal", "venue"], "b.terminal AS terminal, b.venue AS venue,")

	by_period = OrderedDict()
	for r in overall:
		by_period.setdefault(str(r.period_key), []).append({
			"period_key": str(r.period_key), "terminal": _("All terminals"), "venue": "",
			"student": r.student, "swipes": int(r.cnt), "group_swipes": int(r.group_swipes), "ties": int(r.ties),
		})
	for r in per_terminal:
		by_period.setdefault(str(r.period_key), []).append({
			"period_key": str(r.period_key), "terminal": r.terminal, "venue": r.venue,
			"student": r.student, "swipes": int(r.cnt), "group_swipes": int(r.group_swipes), "ties": int(r.ties),
		})
	return [row for rows in by_period.values() for row in rows]


def _student_info(student_ids):
	info = {}
	ids = [s for s in student_ids if s]
	for i in range(0, len(ids), 1000):
		for s in frappe.get_all(
			"Student Master",
			filters={"name": ["in", ids[i:i + 1000]]},
			fields=["name", "first_name", "programme_of_study", "academic_year"],
		):
			info[s.name] = s
	return info


def _student_cols(info, student):
	s = info.get(student) or frappe._dict()
	return [s.first_name or "", s.programme_of_study or "", s.academic_year or ""]


def _scope_note(filters):
	parts = [_("{0} to {1}").format(
		filters.from_dt.strftime("%Y-%m-%d %H:%M:%S"), _last_second(filters).strftime("%Y-%m-%d %H:%M:%S"))]
	for key, label in (("programme", _("Programme")), ("academic_year", _("Academic Year")),
	                   ("terminal_alias", _("Terminal")), ("venue", _("Venue")), ("student", _("Student"))):
		values = _parse_multiselect(filters.get(key))
		if values:
			parts.append(f"{label}: {', '.join(values)}")
	if filters.get("known_only"):
		parts.append(_("known students only"))
	return _("RFID swipes") + " · " + " · ".join(parts)


def _last_second(filters):
	"""Inclusive end of the range, for labels (to_dt itself is exclusive)."""
	return add_to_date(filters.to_dt, seconds=-1)


def _naive(value):
	"""openpyxl can't write tz-aware datetimes; DB values are naive already."""
	if isinstance(value, _dt.datetime) and value.tzinfo:
		return value.replace(tzinfo=None)
	return value


def _time_only(value):
	return value.time().replace(microsecond=0) if isinstance(value, _dt.datetime) else value


def _col_letter(idx):
	from openpyxl.utils import get_column_letter
	return get_column_letter(idx)


# ── Labels ─────────────────────────────────────────────────────────────────────

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _period_label(key, view):
	key = str(key)
	try:
		if view == "Hourly":
			day, hour = key.split(" ")
			start = int(hour[:2])
			return f"{day} {start:02d}:00–{(start + 1) % 24:02d}:00  ({_WEEKDAYS[getdate(day).weekday()]})"
		if view == "Daily":
			return f"{key}  ({_WEEKDAYS[getdate(key).weekday()]})"
		if view == "Weekly":
			year, week = int(key[:4]), int(key[4:])
			monday = _dt.datetime.strptime(f"{year}-W{week:02d}-1", "%G-W%V-%u").date()
			sunday = monday + _dt.timedelta(days=6)
			return f"Wk {week}, {year}  ({monday.strftime('%d %b')}–{sunday.strftime('%d %b')})"
		year, month = key.split("-")
		return f"{_calendar.month_name[int(month)]} {year}"
	except (ValueError, IndexError):
		return key
