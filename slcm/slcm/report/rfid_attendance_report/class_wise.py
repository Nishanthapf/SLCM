# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""Class-wise view of the RFID Attendance Report.

One row per class (Time Table entry) that starts inside the From/To range,
grouped by period (Hour / Day / Week / Month of the class start):

  Enrolled       students currently Enrolled in the class (Classes roster)
  Swiped         of those, students with a tap between 20 min before the class
                 starts and the class end, at any reader
  At Venue       of those, students who tapped on a reader mapped to the class's
                 Time Table venue that day (blank when no reader is mapped there)
  Marked Present Student Attendance Present / Late for the class
  RFID Activated faculty pressed Activate RFID for the class

Cancelled classes and Office Hours entries are left out.
"""

import datetime as _dt
from collections import OrderedDict, defaultdict

import frappe
from frappe import _

SWIPE_GRACE_MINUTES = 20  # same early grace the RFID processor uses
PRESENT_STATUSES = ("Present", "Late")
MAX_SESSIONS = 5000


# ── Queries ─────────────────────────────────────────────────────────────────

def _sessions_sql(filters, params, parse):
	"""Class sessions in range; reused as a derived table by later queries."""
	conds = [
		"tt.docstatus < 2",
		"IFNULL(tt.is_cancelled, 0) = 0",
		"IFNULL(tt.session_status, '') != 'Cancelled'",
		"IFNULL(tt.based_on, '') != 'Office Hours'",
		"IFNULL(tt.class_name, '') != ''",
		"tt.from_time IS NOT NULL AND tt.to_time IS NOT NULL",
		"tt.schedule_date BETWEEN %(cw_from_day)s AND %(cw_to_day)s",
		"TIMESTAMP(tt.schedule_date, tt.from_time) >= %(from_dt)s",
		"TIMESTAMP(tt.schedule_date, tt.from_time) < %(to_dt)s",
	]
	params["cw_from_day"] = filters.from_dt.date()
	params["cw_to_day"] = filters.to_dt.date()

	def add_in(expr, key, prefix):
		values = parse(filters.get(key))
		if values:
			names = []
			for i, v in enumerate(values):
				params[f"{prefix}_{i}"] = v
				names.append(f"%({prefix}_{i})s")
			conds.append(f"{expr} IN ({', '.join(names)})")

	add_in("tt.programme", "programme", "cwp")
	add_in("tt.academic_year", "academic_year", "cwy")
	add_in("tt.venue", "venue", "cwv")
	add_in("tt.class_name", "class_name", "cwc")
	add_in("tt.course", "course", "cwo")

	return f"""
		SELECT tt.name, tt.class_name, tt.venue,
			TIMESTAMP(tt.schedule_date, tt.from_time) AS start_dt,
			TIMESTAMP(tt.schedule_date, tt.to_time) AS end_dt,
			TIMESTAMP(tt.schedule_date, tt.from_time) - INTERVAL {SWIPE_GRACE_MINUTES} MINUTE AS win_start
		FROM `tabTime Table` tt
		WHERE {' AND '.join(conds)}
	"""


def _roster_sql(filters, params, parse):
	cond = ""
	students = parse(filters.get("student"))
	if students:
		names = []
		for i, v in enumerate(students):
			params[f"cws_{i}"] = v
			names.append(f"%(cws_{i})s")
		cond = f"AND se.student IN ({', '.join(names)})"
	return f"""
		SELECT DISTINCT ces.parent AS class_name, se.student AS student
		FROM `tabClass Enrolled Student` ces
		JOIN `tabStudent Enrollment` se ON se.name = ces.student_enrollment
		WHERE ces.parenttype = 'Classes' AND ces.status = 'Enrolled' AND se.status = 'Enrolled'
		AND IFNULL(se.student, '') != '' {cond}
	"""


def collect(filters, parse, venue_expr, terminal_expr):
	"""Everything the class-wise screen and Excel need, from one set of queries."""
	params = {"from_dt": filters.from_dt, "to_dt": filters.to_dt}
	sessions_sql = _sessions_sql(filters, params, parse)
	roster_sql = _roster_sql(filters, params, parse)

	sessions = frappe.db.sql(f"""
		SELECT tt.name, tt.schedule_date, tt.from_time, tt.to_time, tt.course, tt.class_name, tt.section,
			tt.programme, tt.instructor, tt.instructor_name, tt.venue,
			c.course_name, s.start_dt, s.end_dt
		FROM ({sessions_sql}) s
		JOIN `tabTime Table` tt ON tt.name = s.name
		LEFT JOIN `tabClasses` c ON c.name = tt.class_name
		ORDER BY s.start_dt ASC, tt.course ASC, tt.class_name ASC
	""", params, as_dict=True)
	if len(sessions) > MAX_SESSIONS:
		frappe.throw(_("{0} classes in this range — too many to show. Narrow the dates or filters.").format(len(sessions)))
	if not sessions:
		return frappe._dict(sessions=[], roster={}, matched={}, attendance={}, activated=set(), info={}, mapped=[])

	class_names = sorted({s.class_name for s in sessions})
	params["cw_classes"] = tuple(class_names)
	roster = defaultdict(set)
	for r in frappe.db.sql(f"SELECT * FROM ({roster_sql}) r WHERE r.class_name IN %(cw_classes)s", params, as_dict=True):
		roster[r.class_name].add(r.student)

	terminal_cond = ""
	terminals = parse(filters.get("terminal_alias"))
	if terminals:
		names = []
		for i, v in enumerate(terminals):
			params[f"cwt_{i}"] = v
			names.append(f"%(cwt_{i})s")
		terminal_cond = f"AND {terminal_expr} IN ({', '.join(names)})"

	# Taps by each enrolled student inside each class's window.
	matched = {}
	for r in frappe.db.sql(f"""
		SELECT s.name AS session, al.student,
			COUNT(*) AS swipes, MIN(al.swipe_time) AS first_swipe, MAX(al.swipe_time) AS last_swipe,
			GROUP_CONCAT(DISTINCT {terminal_expr} ORDER BY {terminal_expr} SEPARATOR ', ') AS terminals,
			MAX(CASE WHEN IFNULL(s.venue, '') != '' AND {venue_expr} = s.venue THEN 1 ELSE 0 END) AS at_venue
		FROM ({sessions_sql}) s
		JOIN ({roster_sql}) r ON r.class_name = s.class_name
		JOIN `tabAttendance Log` al ON al.student = r.student
			AND al.swipe_time >= s.win_start AND al.swipe_time <= s.end_dt
		WHERE 1 = 1 {terminal_cond}
		GROUP BY s.name, al.student
	""", params, as_dict=True):
		matched[(r.session, r.student)] = r

	attendance = {}
	activated = set()
	for r in frappe.db.sql(f"""
		SELECT ats.class_schedule, sa.student, sa.status
		FROM `tabStudent Attendance` sa
		JOIN `tabAttendance Session` ats ON ats.name = sa.attendance_session
		WHERE ats.class_schedule IN (SELECT s.name FROM ({sessions_sql}) s)
		AND sa.docstatus < 2 AND ats.docstatus < 2
	""", params, as_dict=True):
		attendance[(r.class_schedule, r.student)] = r.status
	for r in frappe.db.sql(f"""
		SELECT DISTINCT ats.class_schedule
		FROM `tabAttendance Session` ats
		WHERE ats.class_schedule IN (SELECT s.name FROM ({sessions_sql}) s)
		AND ats.docstatus < 2 AND ats.rfid_activation_time IS NOT NULL
	""", params, as_dict=True):
		activated.add(r.class_schedule)

	students = set().union(*roster.values()) if roster else set()
	info = {}
	ids = sorted(students)
	for i in range(0, len(ids), 1000):
		for s in frappe.get_all("Student Master", filters={"name": ["in", ids[i:i + 1000]]},
		                        fields=["name", "registration_id", "first_name", "programme_of_study", "academic_year"]):
			info[s.name] = s

	mapped = frappe.get_all(
		"RFID Device Room Mapping", filters={"is_active": 1},
		fields=["room", "effective_from", "effective_to"],
	)
	return frappe._dict(sessions=sessions, roster=roster, matched=matched, attendance=attendance,
	                    activated=activated, info=info, mapped=mapped)


def _venue_has_reader(mapped, venue, day):
	if not venue:
		return False
	for m in mapped:
		if m.room == venue and m.effective_from and m.effective_from <= day and (
			not m.effective_to or m.effective_to >= day
		):
			return True
	return False


# ── Rows ────────────────────────────────────────────────────────────────────

def period_key(start_dt, view):
	if view == "Hourly":
		return start_dt.strftime("%Y-%m-%d %H:00")
	if view == "Daily":
		return start_dt.strftime("%Y-%m-%d")
	if view == "Weekly":
		iso = start_dt.isocalendar()
		return f"{iso[0]}{iso[1]:02d}"
	return start_dt.strftime("%Y-%m")


def _hhmm(value):
	if isinstance(value, _dt.timedelta):
		total = int(value.total_seconds())
		return f"{total // 3600:02d}:{(total % 3600) // 60:02d}"
	if isinstance(value, (_dt.time, _dt.datetime)):
		return value.strftime("%H:%M")
	return str(value or "")[:5]


def session_rows(ctx):
	"""One dict per class with its counts, in start order."""
	out = []
	for s in ctx.sessions:
		enrolled = ctx.roster.get(s.class_name, set())
		swiped = {st for st in enrolled if (s.name, st) in ctx.matched}
		has_reader = _venue_has_reader(ctx.mapped, s.venue, s.schedule_date)
		at_venue = sum(1 for st in swiped if ctx.matched[(s.name, st)].at_venue) if has_reader else None
		present = sum(1 for st in enrolled if ctx.attendance.get((s.name, st)) in PRESENT_STATUSES)
		out.append(frappe._dict(
			session=s, enrolled=enrolled, swiped=swiped, has_reader=has_reader,
			row={
				"class_time": f"{_hhmm(s.from_time)}–{_hhmm(s.to_time)}",
				"course": s.course_name or s.course or "",
				"class_name": s.class_name,
				"section": s.section or "",
				"faculty": s.instructor_name or s.instructor or "",
				"venue": s.venue or "",
				"enrolled": len(enrolled),
				"swiped": len(swiped),
				"swipe_pct": round(100.0 * len(swiped) / len(enrolled), 1) if enrolled else 0.0,
				"not_swiped": len(enrolled) - len(swiped),
				"at_venue": at_venue,
				"marked_present": present,
				"rfid_activated": _("Yes") if s.name in ctx.activated else _("No"),
				"time_table": s.name,
			},
		))
	return out


def get_columns(filters):
	view = filters.get("view_by") or "Daily"
	period_label = {"Hourly": _("Hour"), "Daily": _("Date"), "Weekly": _("Week"), "Monthly": _("Month")}[view]
	return [
		{"fieldname": "period_label",   "label": period_label,           "fieldtype": "Data",    "width": 230},
		{"fieldname": "class_time",     "label": _("Time"),              "fieldtype": "Data",    "width": 105},
		{"fieldname": "course",         "label": _("Course"),            "fieldtype": "Data",    "width": 220},
		{"fieldname": "class_name",     "label": _("Class"),             "fieldtype": "Link",    "options": "Classes", "width": 170},
		{"fieldname": "section",        "label": _("Section"),           "fieldtype": "Data",    "width": 90},
		{"fieldname": "faculty",        "label": _("Faculty"),           "fieldtype": "Data",    "width": 150},
		{"fieldname": "venue",          "label": _("Venue"),             "fieldtype": "Data",    "width": 140},
		{"fieldname": "enrolled",       "label": _("Enrolled"),          "fieldtype": "Int",     "width": 90},
		{"fieldname": "swiped",         "label": _("Swiped"),            "fieldtype": "Int",     "width": 85},
		{"fieldname": "swipe_pct",      "label": _("Swiped %"),          "fieldtype": "Percent", "width": 95},
		{"fieldname": "not_swiped",     "label": _("Not Swiped"),        "fieldtype": "Int",     "width": 100},
		{"fieldname": "at_venue",       "label": _("At Venue"),          "fieldtype": "Int",     "width": 90},
		{"fieldname": "marked_present", "label": _("Marked Present"),    "fieldtype": "Int",     "width": 125},
		{"fieldname": "rfid_activated", "label": _("RFID Activated"),    "fieldtype": "Data",    "width": 120},
		{"fieldname": "time_table",     "label": _("Time Table"),        "fieldtype": "Link",    "options": "Time Table", "width": 150},
	]


def get_data(filters, ctx, period_label):
	view = filters.get("view_by") or "Daily"
	groups = OrderedDict()
	for item in session_rows(ctx):
		groups.setdefault(period_key(item.session.start_dt, view), []).append(item)

	data = []
	for key, items in groups.items():
		enrolled = sum(i.row["enrolled"] for i in items)
		swiped = sum(i.row["swiped"] for i in items)
		venue_counts = [i.row["at_venue"] for i in items if i.row["at_venue"] is not None]
		data.append({
			"period_label": period_label(key, view),
			"period_key": key,
			"class_time": "",
			"course": _("{0} classes").format(len(items)) if len(items) != 1 else _("1 class"),
			"class_name": "", "section": "", "faculty": "", "venue": "",
			"enrolled": enrolled,
			"swiped": swiped,
			"swipe_pct": round(100.0 * swiped / enrolled, 1) if enrolled else 0.0,
			"not_swiped": enrolled - swiped,
			"at_venue": sum(venue_counts) if venue_counts else None,
			"marked_present": sum(i.row["marked_present"] for i in items),
			"rfid_activated": f"{sum(1 for i in items if i.session.name in ctx.activated)}/{len(items)}",
			"time_table": "",
			"bold": 1,
			"is_period_row": 1,
		})
		for i in items:
			data.append({"period_label": "", "period_key": key, **i.row})
	return data


def get_summary(data):
	sessions = [r for r in data if not r.get("is_period_row")]
	enrolled = sum(r["enrolled"] for r in sessions)
	swiped = sum(r["swiped"] for r in sessions)
	return [
		{"label": _("Classes"),               "value": len(sessions),                       "datatype": "Int",     "indicator": "blue"},
		{"label": _("Enrolled Seats"),        "value": enrolled,                            "datatype": "Int",     "indicator": "blue"},
		{"label": _("Swiped"),                "value": swiped,                              "datatype": "Int",     "indicator": "green"},
		{"label": _("Swipe Rate"),            "value": round(100.0 * swiped / enrolled, 1) if enrolled else 0,
		 "datatype": "Percent", "indicator": "green"},
		{"label": _("Not Swiped"),            "value": enrolled - swiped,                   "datatype": "Int",     "indicator": "red"},
		{"label": _("Classes With No Swipes"),"value": sum(1 for r in sessions if r["enrolled"] and not r["swiped"]),
		 "datatype": "Int", "indicator": "orange"},
	]


def get_chart(data, filters):
	periods = [r for r in data if r.get("is_period_row")]
	if not periods:
		return None
	periods = periods[-(72 if filters.get("view_by") == "Hourly" else 31):]
	return {
		"data": {
			"labels": [r["period_label"] for r in periods],
			"datasets": [
				{"name": _("Swiped"), "values": [r["swiped"] for r in periods], "chartType": "bar"},
				{"name": _("Not Swiped"), "values": [r["not_swiped"] for r in periods], "chartType": "bar"},
			],
		},
		"type": "bar",
		"colors": ["#2b2e4a", "#c0841a"],
		"barOptions": {"stacked": True},
		"title": _("Class-wise Swipes — {0}").format(filters.get("view_by") or "Daily"),
		"height": 280,
	}


# ── Excel ───────────────────────────────────────────────────────────────────

def student_rows(ctx):
	"""One row per class per enrolled student."""
	rows = []
	for item in session_rows(ctx):
		s = item.session
		for st in sorted(item.enrolled):
			m = ctx.matched.get((s.name, st))
			sm = ctx.info.get(st) or frappe._dict()
			if not item.has_reader:
				at_venue = "—"
			else:
				at_venue = _("Yes") if (m and m.at_venue) else _("No")
			rows.append(frappe._dict(
				date=s.schedule_date, time=item.row["class_time"], course=item.row["course"],
				class_name=s.class_name, section=s.section or "", faculty=item.row["faculty"], venue=s.venue or "",
				student=st, registration_id=sm.registration_id or "", student_name=sm.first_name or "", programme=sm.programme_of_study or "",
				academic_year=sm.academic_year or "",
				swiped=bool(m), swipes=int(m.swipes) if m else 0,
				first_swipe=m.first_swipe if m else None, last_swipe=m.last_swipe if m else None,
				terminals=(m.terminals or "") if m else "", at_venue=at_venue,
				attendance=ctx.attendance.get((s.name, st)) or _("Not marked"),
				time_table=s.name,
			))
	return rows


def student_summary(rows):
	agg = OrderedDict()
	for r in rows:
		a = agg.setdefault(r.student, frappe._dict(
			student=r.student, registration_id=r.registration_id, student_name=r.student_name, programme=r.programme,
			academic_year=r.academic_year, classes=0, swiped=0, present=0,
		))
		a.classes += 1
		a.swiped += 1 if r.swiped else 0
		a.present += 1 if r.attendance in PRESENT_STATUSES else 0
	out = list(agg.values())
	for a in out:
		a.not_swiped = a.classes - a.swiped
		a.swipe_pct = round(100.0 * a.swiped / a.classes, 1) if a.classes else 0.0
	out.sort(key=lambda a: (a.swipe_pct, a.student))
	return out
