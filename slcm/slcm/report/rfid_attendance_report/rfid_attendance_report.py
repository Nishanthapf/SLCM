# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
RFID Attendance Report
======================
Two report types, picked with the "Report" filter:

Terminal-wise (default) — swipe activity per period by terminal and venue.
  Period row  : totals across all terminals for the Hour / Day / Week / Month
  Detail rows : one per terminal (reader) + venue in that period

Class-wise — one row per class (Time Table entry) in the range: enrolled vs
  swiped, at the class venue, marked present, RFID activated. See class_wise.py.

Filters: Report, View By, From Date + From Time, To Date + To Time (one
continuous range; blank times mean start / end of day), academic year,
programme, terminal, venue, student, class, course, known students only.
In Terminal-wise, Class / Course keep the swipes of students enrolled there.

Venue comes from RFID Device Room Mapping (device -> Venue Master on the
swipe date), falling back to the log's own location text.

Excel download (same filters) — student-level detail lives here, not on screen.
Terminal-wise:
  Report                  the on-screen table
  Student-wise (Daily)    one row per student per day
  Student Totals          one row per student for the whole range
  Most Swiped - Daily / Weekly / Monthly
                          top student per period, overall and per terminal
Class-wise:
  Class-wise              the on-screen table
  Class Students          one row per class per enrolled student
  Not Swiped              the Class Students rows with no swipe
  Student Summary         one row per student: classes, swiped, present
"""

import calendar as _calendar
import datetime as _dt
import io
import json as _json
from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, get_time, getdate

from slcm.permissions import AAD_ROLES
from slcm.slcm.report.rfid_attendance_report import class_wise

REPORT_NAME = "RFID Attendance Report"
VIEWS = ("Hourly", "Daily", "Weekly", "Monthly")
REPORT_TYPES = ("Terminal-wise", "Class-wise")
MULTISELECT_FILTERS = ("academic_year", "programme", "terminal_alias", "venue", "student", "class_name", "course")
NOT_MAPPED = "Not mapped"
MAX_EXCEL_ROWS = 300000
MAX_SPLIT_SHEETS = 40
# Filters whose selected values each get their own sheet in the Excel, in this order.
SPLIT_FILTERS = (
	("class_name", "Class"), ("course", "Course"), ("programme", "Programme"),
	("academic_year", "Academic Year"), ("venue", "Venue"), ("terminal_alias", "Terminal"),
	("student", "Student"),
)

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

	if filter_name == "class_name":
		rows = frappe.db.sql("""
			SELECT name, course_name, section FROM `tabClasses`
			WHERE name LIKE %(like)s OR course_name LIKE %(like)s OR course LIKE %(like)s
			ORDER BY modified DESC LIMIT 50
		""", {"like": like}, as_dict=True)
		return [{"label": r.name, "value": r.name,
		         "description": " · ".join(x for x in (r.course_name, r.section) if x)} for r in rows]

	if filter_name == "course":
		rows = frappe.db.sql("""
			SELECT DISTINCT c.course, c.course_name FROM `tabClasses` c
			WHERE IFNULL(c.course, '') != '' AND (c.course LIKE %(like)s OR c.course_name LIKE %(like)s)
			ORDER BY c.course_name LIMIT 50
		""", {"like": like}, as_dict=True)
		return [{"label": r.course_name or r.course, "value": r.course, "description": r.course} for r in rows]

	if filter_name == "academic_year":
		sql = """SELECT v FROM (
				SELECT DISTINCT academic_year AS v FROM `tabStudent Master` WHERE IFNULL(academic_year, '') != ''
				UNION SELECT DISTINCT academic_year FROM `tabTime Table` WHERE IFNULL(academic_year, '') != ''
			) x WHERE v LIKE %(like)s ORDER BY v DESC"""
	elif filter_name == "programme":
		sql = """SELECT v FROM (
				SELECT DISTINCT programme_of_study AS v FROM `tabStudent Master` WHERE IFNULL(programme_of_study, '') != ''
				UNION SELECT DISTINCT programme FROM `tabTime Table` WHERE IFNULL(programme, '') != ''
			) x WHERE v LIKE %(like)s ORDER BY v"""
	elif filter_name == "terminal_alias":
		sql = """SELECT DISTINCT terminal_alias FROM `tabAttendance Log`
			WHERE IFNULL(terminal_alias, '') != '' AND terminal_alias LIKE %(like)s ORDER BY terminal_alias"""
	elif filter_name == "venue":
		sql = """SELECT v FROM (
				SELECT DISTINCT room AS v FROM `tabRFID Device Room Mapping` WHERE is_active = 1
				UNION SELECT name FROM `tabVenue Master` WHERE is_active = 1
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

	if _is_class_wise(filters):
		ctx = class_wise.collect(filters, _parse_multiselect, VENUE_EXPR, TERMINAL_EXPR)
		data = class_wise.get_data(filters, ctx, _period_label)
		return (class_wise.get_columns(filters), data, None,
		        class_wise.get_chart(data, filters), class_wise.get_summary(data))

	base, params = _base_query(filters)
	columns = _get_columns(filters)
	data = _get_data(filters, base, params)
	summary = _get_summary(base, params)
	chart = _get_chart(data, filters)
	return columns, data, None, chart, summary


# ── Validation ─────────────────────────────────────────────────────────────────

def _validate(filters):
	"""Combine From Date + From Time and To Date + To Time into one continuous
	range: filters.from_dt (inclusive) and filters.to_dt (exclusive).

	A blank From Time means 00:00:00; a blank To Time means the end of To Date;
	a To Time includes that whole second. A date filter that already carries a
	time (older links from the datetime version) keeps it unless a separate
	time is given."""
	if not filters.get("from_date") or not filters.get("to_date"):
		frappe.throw(_("From Date and To Date are required."))

	from_dt = _combine(filters.from_date, filters.get("from_time"), _("From"))
	to_dt = _combine(filters.to_date, filters.get("to_time"), _("To"))

	if filters.get("to_time") or not _has_no_time(filters.to_date):
		to_dt = add_to_date(to_dt, seconds=1)
	else:
		to_dt = add_to_date(to_dt, days=1)

	if from_dt >= to_dt:
		frappe.throw(_("From Date / Time must be before To Date / Time."))
	if (filters.get("view_by") or "Daily") not in VIEWS:
		frappe.throw(_("View By must be one of: {0}").format(", ".join(VIEWS)))
	if (filters.get("report_type") or REPORT_TYPES[0]) not in REPORT_TYPES:
		frappe.throw(_("Report must be one of: {0}").format(", ".join(REPORT_TYPES)))

	filters.from_dt, filters.to_dt = from_dt, to_dt


def _is_class_wise(filters):
	return filters.get("report_type") == "Class-wise"


def _combine(date_value, time_value, label):
	try:
		value = get_datetime(date_value)
		if value and time_value:
			value = _dt.datetime.combine(value.date(), get_time(time_value))
	except Exception:
		value = None
	if not value:
		frappe.throw(_("{0} Date / Time is not valid.").format(label))
	return value.replace(microsecond=0)


def _has_no_time(value):
	if isinstance(value, _dt.datetime):
		return False
	if isinstance(value, _dt.date):
		return True
	return isinstance(value, str) and len(value.strip()) <= 10


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

	# Class / Course: keep swipes of students currently enrolled in those classes.
	class_conds = []
	for fieldname, expr, prefix in (("class_name", "c.name", "c"), ("course", "c.course", "o")):
		values = _parse_multiselect(filters.get(fieldname))
		if values:
			keys = []
			for i, v in enumerate(values):
				params[f"{prefix}_{i}"] = v
				keys.append(f"%({prefix}_{i})s")
			class_conds.append(f"{expr} IN ({', '.join(keys)})")
	if class_conds:
		conditions.append(f"""al.student IN (
			SELECT se.student FROM `tabClasses` c
			JOIN `tabClass Enrolled Student` ces ON ces.parent = c.name AND ces.parenttype = 'Classes'
			JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
			WHERE ces.status = 'Enrolled' AND se.status = 'Enrolled' AND {' AND '.join(class_conds)})""")

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
	filters = _download_filters(filters)

	from openpyxl import Workbook
	from openpyxl.cell import WriteOnlyCell
	from openpyxl.styles import Alignment, Font, PatternFill

	wb = Workbook(write_only=True)
	header_font = Font(bold=True, color="FFFFFF")
	header_fill = PatternFill("solid", fgColor="2B2E4A")
	bold = Font(bold=True)

	used_titles = set()

	def sheet(title, headers, widths, rows, note=None, bold_rows=None):
		ws = wb.create_sheet(title=_sheet_title(title, used_titles))
		for idx, width in enumerate(widths, start=1):
			ws.column_dimensions[_col_letter(idx)].width = width
		first_data = "A3" if note else "A2"
		ws.freeze_panes = first_data
		# Put the cursor on the first data row; a cursor inside the frozen header
		# makes some spreadsheet apps open the sheet scrolled past the data.
		ws.sheet_view.selection[-1].activeCell = first_data
		ws.sheet_view.selection[-1].sqref = first_data
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

	_write_sheets(filters, sheet)

	buf = io.BytesIO()
	wb.save(buf)
	_send_file(_download_name(filters, "xlsx"), buf.getvalue())


@frappe.whitelist()
def download_csv(filters, scope="report"):
	"""CSV export. scope="report": one .csv of the on-screen table (the overall
	sheet). scope="all": a .zip with one .csv per Excel sheet + README.txt
	listing the filters behind each file. UTF-8 with BOM so Excel opens it."""
	import csv
	import zipfile

	if scope not in ("report", "all"):
		frappe.throw(_("Unknown CSV scope."))
	filters = _download_filters(filters)

	tables = []  # (title, note, headers, rows)
	used_titles = set()

	def sheet(title, headers, widths, rows, note=None, bold_rows=None):
		tables.append((_sheet_title(title, used_titles), note or "", headers, rows))

	_write_sheets(filters, sheet, main_only=(scope == "report"))

	def to_csv(headers, rows):
		out = io.StringIO()
		writer = csv.writer(out)
		writer.writerow(headers)
		for row in rows:
			writer.writerow([_csv_value(v) for v in row])
		return ("\ufeff" + out.getvalue()).encode("utf-8")

	if scope == "report":
		title, note, headers, rows = tables[0]
		_send_file(_download_name(filters, "csv"), to_csv(headers, rows))
		return

	buf = io.BytesIO()
	readme = [_("RFID Attendance Report — CSV export"), ""]
	with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
		for i, (title, note, headers, rows) in enumerate(tables, start=1):
			name = f"{i:02d} {_file_safe(title)}.csv"
			zf.writestr(name, to_csv(headers, rows))
			readme.append(f"{name}  ({len(rows)} rows)")
			readme.append(f"    {note}")
		zf.writestr("README.txt", "\n".join(readme) + "\n")
	_send_file(_download_name(filters, "zip"), buf.getvalue())


def _download_filters(filters):
	if not frappe.get_doc("Report", REPORT_NAME).is_permitted():
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	filters = frappe._dict(frappe.parse_json(filters) if isinstance(filters, str) else (filters or {}))
	filters.setdefault("view_by", "Daily")
	_validate(filters)
	return filters


def _write_sheets(filters, sheet, main_only=False):
	"""Feed every table of the download to `sheet` (Excel or CSV writer)."""
	scope = _scope_note(filters)
	if _is_class_wise(filters):
		_class_wise_sheets(filters, sheet, scope, main_only)
	else:
		_terminal_sheets(filters, sheet, scope, main_only)


def _download_name(filters, ext):
	kind = "Class" if _is_class_wise(filters) else "Swipes"
	return "RFID_{0}_{1}_to_{2}.{3}".format(
		kind, filters.from_dt.strftime("%Y-%m-%d_%H%M"), _last_second(filters).strftime("%Y-%m-%d_%H%M"), ext)


def _send_file(filename, content):
	frappe.response.filename = filename
	frappe.response.filecontent = content
	frappe.response.type = "binary"


def _csv_value(value):
	if value is None:
		return ""
	if isinstance(value, _dt.datetime):
		return value.strftime("%Y-%m-%d %H:%M:%S")
	if isinstance(value, _dt.date):
		return value.isoformat()
	if isinstance(value, _dt.time):
		return value.strftime("%H:%M:%S")
	return value


def _file_safe(name):
	return "".join("-" if ch in '<>:"/\\|?*' else ch for ch in name).strip() or "sheet"


def _class_wise_sheets(filters, sheet, scope, main_only=False):
	ctx = class_wise.collect(filters, _parse_multiselect, VENUE_EXPR, TERMINAL_EXPR)
	rows = class_wise.get_data(filters, ctx, _period_label)
	if main_only:
		_class_table(sheet, _("Class-wise"), filters, rows, scope)
		return
	students = class_wise.student_rows(ctx)
	if len(students) > MAX_EXCEL_ROWS:
		frappe.throw(_("Too many rows ({0}) for one download. Narrow the date range or filters.").format(len(students)))
	note = scope + " · " + _("Swiped = a tap from {0} min before the class start to its end; "
	                         "Enrolled = students currently enrolled in the class.").format(class_wise.SWIPE_GRACE_MINUTES)

	splits = _split_values(filters)
	class_note = " · " + _("Swiped = a tap from {0} min before the class start to its end; "
	                       "Enrolled = students currently enrolled in the class.").format(class_wise.SWIPE_GRACE_MINUTES)
	_class_table(sheet, _("Overall Class-wise") if splits else _("Class-wise"), filters, rows,
	             note + _split_note(splits))
	for fieldname, label, value in splits:
		sub = _single_value_filters(filters, fieldname, value)
		sub_ctx = class_wise.collect(sub, _parse_multiselect, VENUE_EXPR, TERMINAL_EXPR)
		_class_table(sheet, value, sub, class_wise.get_data(sub, sub_ctx, _period_label),
		             _scope_note(sub) + class_note)

	headers = [_("Date"), _("Day"), _("Time"), _("Course"), _("Class"), _("Section"), _("Faculty"), _("Venue"),
	           _("Student ID"), _("Student Name"), _("Programme"), _("Academic Year"), _("Swiped"), _("Swipes"),
	           _("First Swipe"), _("Last Swipe"), _("Terminals"), _("At Venue"), _("Attendance"), _("Time Table")]
	widths = [12, 11, 13, 34, 26, 10, 24, 20, 22, 28, 34, 14, 9, 9, 12, 12, 30, 10, 14, 20]

	def as_row(r):
		return [r.date, _WEEKDAYS[r.date.weekday()], r.time, r.course, r.class_name, r.section, r.faculty, r.venue,
		        r.student, r.student_name, r.programme, r.academic_year, _("Yes") if r.swiped else _("No"),
		        r.swipes, _time_only(r.first_swipe), _time_only(r.last_swipe), r.terminals, r.at_venue,
		        r.attendance, r.time_table]

	sheet(_("Class Students"), headers, widths, [as_row(r) for r in students], note=note)
	sheet(_("Not Swiped"), headers, widths, [as_row(r) for r in students if not r.swiped], note=note)

	summary = class_wise.student_summary(students)
	sheet(
		_("Student Summary"),
		[_("Student ID"), _("Student Name"), _("Programme"), _("Academic Year"), _("Classes"), _("Swiped"),
		 _("Not Swiped"), _("Swiped %"), _("Marked Present")],
		[22, 28, 34, 14, 10, 10, 11, 10, 15],
		[[a.student, a.student_name, a.programme, a.academic_year, a.classes, a.swiped, a.not_swiped,
		  a.swipe_pct, a.present] for a in summary],
		note=note + " · " + _("Lowest swipe rate first."),
	)


def _terminal_sheets(filters, sheet, scope, main_only=False):
	base, params = _base_query(filters)
	if main_only:
		_terminal_table(sheet, _("Report"), filters, _get_data(filters, base, params), scope)
		return

	student_daily = _student_daily_rows(base, params)
	if len(student_daily) > MAX_EXCEL_ROWS:
		frappe.throw(_("Too many rows ({0}) for one download. Narrow the date range or filters.").format(len(student_daily)))

	report_rows = _get_data(filters, base, params)
	totals = _student_total_rows(base, params)
	top = {view: _most_swiped_rows(view, base, params) for view in ("Daily", "Weekly", "Monthly")}
	info = _student_info({r.student for r in student_daily})

	# 1. Overall report (as on screen), then one sheet per selected filter value
	splits = _split_values(filters)
	_terminal_table(sheet, _("Overall Report") if splits else _("Report"), filters, report_rows,
	                scope + _split_note(splits))
	for fieldname, label, value in splits:
		sub = _single_value_filters(filters, fieldname, value)
		sub_base, sub_params = _base_query(sub)
		_terminal_table(sheet, value, sub, _get_data(sub, sub_base, sub_params), _scope_note(sub))

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


def _terminal_table(sheet, title, filters, rows, note):
	sheet(
		title,
		[_("Period"), _("Terminal / Room"), _("Venue"), _("Total Swipes"), _("Unique Students"),
		 _("Unknown Swipes"), _("First Swipe"), _("Last Swipe")],
		[30, 22, 26, 13, 15, 15, 20, 20],
		[[_period_label(r["period_key"], filters.view_by) if r.get("is_period_row") else "",
		  r["terminal_alias"], r["venue"], r["total_swipes"], r["unique_students"], r["unknown_swipes"],
		  _naive(r["first_swipe"]), _naive(r["last_swipe"])] for r in rows],
		note=note,
		bold_rows=lambda i: bool(rows[i].get("is_period_row")),
	)


def _class_table(sheet, title, filters, rows, note):
	sheet(
		title,
		[_("Period"), _("Time"), _("Course"), _("Class"), _("Section"), _("Faculty"), _("Venue"), _("Enrolled"),
		 _("Swiped"), _("Swiped %"), _("Not Swiped"), _("At Venue"), _("Marked Present"), _("RFID Activated"),
		 _("Time Table")],
		[30, 13, 34, 26, 10, 24, 20, 10, 9, 10, 11, 10, 15, 14, 20],
		[[_period_label(r["period_key"], filters.view_by) if r.get("is_period_row") else "", r["class_time"],
		  r["course"], r["class_name"], r["section"], r["faculty"], r["venue"], r["enrolled"], r["swiped"],
		  r["swipe_pct"], r["not_swiped"], "—" if r["at_venue"] is None else r["at_venue"], r["marked_present"],
		  r["rfid_activated"], r["time_table"]] for r in rows],
		note=note,
		bold_rows=lambda i: bool(rows[i].get("is_period_row")),
	)


def _split_values(filters):
	"""[(fieldname, label, value)] for every filter with 2+ values selected —
	each value gets its own sheet after the overall one. Capped so a huge
	selection doesn't produce hundreds of sheets."""
	out = []
	for fieldname, label in SPLIT_FILTERS:
		values = _parse_multiselect(filters.get(fieldname))
		if len(values) >= 2:
			out.extend((fieldname, label, v) for v in values)
	return out[:MAX_SPLIT_SHEETS]


def _split_note(splits):
	if not splits:
		return ""
	labels = OrderedDict((label, None) for _f, label, _v in splits)
	return " · " + _("Separate sheet per {0} follows").format(" / ".join(_(lbl) for lbl in labels))


def _single_value_filters(filters, fieldname, value):
	sub = frappe._dict(filters)
	sub[fieldname] = [value]
	return sub


_INVALID_TITLE_CHARS = set('[]:*?/\\')


def _sheet_title(title, used):
	"""Excel sheet names: max 31 chars, no []:*?/\\, no edge apostrophes, unique (case-insensitive)."""
	clean = "".join("-" if ch in _INVALID_TITLE_CHARS else ch for ch in str(title or "")).strip().strip("'") or "Sheet"
	base = clean[:31]
	candidate, n = base, 2
	while candidate.lower() in used or candidate.lower() == "history":
		suffix = f" ({n})"
		candidate = base[:31 - len(suffix)] + suffix
		n += 1
	used.add(candidate.lower())
	return candidate


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
	parts = [filters.get("report_type") or REPORT_TYPES[0], _("{0} to {1}").format(
		filters.from_dt.strftime("%Y-%m-%d %H:%M:%S"), _last_second(filters).strftime("%Y-%m-%d %H:%M:%S"))]
	for key, label in (("programme", _("Programme")), ("academic_year", _("Academic Year")),
	                   ("terminal_alias", _("Terminal")), ("venue", _("Venue")), ("student", _("Student")),
	                   ("class_name", _("Class")), ("course", _("Course"))):
		values = _parse_multiselect(filters.get(key))
		if values:
			parts.append(f"{label}: {', '.join(values)}")
	if filters.get("known_only") and not _is_class_wise(filters):
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
