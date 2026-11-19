"""Admission Dashboard (desk page `admission-dashboard`).

The page is a Vue 3 + frappe-ui app built from `frontend/src/admission_dashboard`
into `slcm/public/frontend`. These whitelisted methods feed it.

Everything is read for one Admission Cycle:

* Programme cards are the active rows of the cycle's Admission Cycle Program
  table, filtered by `admission_open_for` the way the applicant portal does
  (blank or "Domestic & International" lists a programme under both tabs).
* Applicants are the ones whose `admission_cycle` is the selected cycle, split
  the way the portal splits them: `foriegn_national` "Yes" is International,
  anything else is Domestic.
* Application-fee figures follow the "NLSAT Fee Collection Report": SLCM Payment
  Requests raised against those Applicants. A payment is dated by its payment
  date and a settlement by its settlement date.
* Portal registrations follow the "Applicant Registration Status" report and are
  not tied to a programme or to Domestic / International.
"""

import json
from collections import Counter, OrderedDict
from datetime import timedelta

import frappe
from frappe import _
from frappe.query_builder import DocType
from frappe.query_builder.functions import Coalesce
from frappe.utils import add_days, cint, flt, get_datetime, getdate, nowdate

from slcm.admission.report.applicant_registration_status.applicant_registration_status import (
	get_registration_counts,
)
from slcm.utils.vite_assets import get_entry_assets

DOMESTIC = "Domestic"
INTERNATIONAL = "International"
APPLICANT_TYPES = (DOMESTIC, INTERNATIONAL)

SETTINGS_DOCTYPE = "Admission Dashboard Settings"
# Bumped when the card/chart set changes shape; an older saved layout is ignored.
LAYOUT_VERSION = 3
SETTINGS_EDITOR_ROLES = ("System Manager", "Admission Admin")
BUNDLE_ENTRY = "src/admission_dashboard/main.js"  # key in slcm/public/frontend/manifest.json

SETTLED_STATES = ("Settled", "processed")  # some records carry Razorpay's raw "processed"
NOT_SET = "Not set"

# --------------------------------------------------------------------------- #
# Admission pipeline
# --------------------------------------------------------------------------- #

STAGES = (
	"Started",
	"Submitted",
	"Fee Paid",
	"Under Evaluation",
	"Selected / Offered",
	"Offer Accepted",
	"Enrolled",
)
DRAFT, SUBMITTED, FEE_PAID, EVALUATION, SELECTED, ACCEPTED, ENROLLED = range(len(STAGES))

# Applicant Status -> furthest stage it means the application reached.
STATUS_STAGE = {
	"Draft": DRAFT,
	"Submitted": SUBMITTED,
	"Submitted and Paid": FEE_PAID,
	"Entrance Test Allocated": EVALUATION,
	"Entrance Test Scheduled": EVALUATION,
	"Entrance Test Completed": EVALUATION,
	"Entrance Test Exempted": EVALUATION,
	"Entrance Test Excempted": EVALUATION,
	"Interview Scheduled": EVALUATION,
	"Interview Sheduled": EVALUATION,
	"Interview Completed": EVALUATION,
	"Interview Exempted": EVALUATION,
	"Interview Excempted": EVALUATION,
	"Exempted Entrance Test And Interview": EVALUATION,
	"Merit Published": EVALUATION,
	"Waitlisted": EVALUATION,
	"Merit Waitlisted": EVALUATION,
	"Seat Waitlisted": EVALUATION,
	"Selected": SELECTED,
	"Merit Selected": SELECTED,
	"Seat Selected": SELECTED,
	"Offer Issued": SELECTED,
	"Accepted": ACCEPTED,
	"Offer Accepted": ACCEPTED,
	"Fee Paid": ACCEPTED,
	"Confirmation Fee Paid": ACCEPTED,
	"Full Fee Paid": ACCEPTED,
	"Enrolled": ENROLLED,
}

# Statuses that end an application, with the stage it had reached before it ended.
EXITED_STAGE = {
	"Withdrawn": DRAFT,
	"Rejected": SUBMITTED,
	"Entrance Test Rejected": EVALUATION,
	"Interview Rejected": EVALUATION,
	"Merit Rejected": EVALUATION,
	"Seat Rejected": EVALUATION,
	"Offer Declined": SELECTED,
	"Offer Expired": SELECTED,
}


def status_stage(status):
	"""(stage reached, exited) for an Applicant Status. Unknown names are read by their words."""
	status = (status or "").strip()
	if not status:
		return DRAFT, False
	if status in STATUS_STAGE:
		return STATUS_STAGE[status], False
	if status in EXITED_STAGE:
		return EXITED_STAGE[status], True

	s = status.lower()
	if any(w in s for w in ("reject", "declin", "expire", "withdraw", "cancel")):
		return SUBMITTED, True
	if "enrol" in s:
		return ENROLLED, False
	if "fee paid" in s or "accept" in s:
		return ACCEPTED, False
	if "select" in s or "offer" in s:
		return SELECTED, False
	if any(w in s for w in ("test", "interview", "merit", "waitlist", "seat", "exempt", "excempt")):
		return EVALUATION, False
	if "paid" in s:
		return FEE_PAID, False
	if "draft" in s:
		return DRAFT, False
	return SUBMITTED, False


# --------------------------------------------------------------------------- #
# Layout (Settings dialog)
# --------------------------------------------------------------------------- #

# Number cards on the programme overview: each counts applicants whose Application Status is
# *currently* one of these values (exact match, not "reached at least"), so they add up to Total.
STATUS_CARDS = OrderedDict(
	[
		("draft", ("Draft Applications", ("Draft",))),
		("submitted", ("Submitted Applications", ("Submitted",))),
		("fee_paid", ("Application Fee Paid", ("Submitted and Paid",))),
		("selected", ("Selected Applications", ("Seat Selected",))),
		("waitlisted", ("Waitlisted Applications", ("Seat Waitlisted",))),
		(
			"rejected",
			(
				"Rejected Applications",
				("Rejected", "Seat Rejected", "Interview Rejected", "Entrance Test Rejected", "Merit Rejected"),
			),
		),
		("offer_issued", ("Offer Issued Applications", ("Offer Issued",))),
		("offer_accepted", ("Offer Accepted Applications", ("Offer Accepted",))),
		("offer_expired", ("Offer Expired Applications", ("Offer Expired",))),
		("offer_declined", ("Offer Declined Applications", ("Offer Declined",))),
		("confirmation_fee_paid", ("Confirmation Fee Paid", ("Confirmation Fee Paid",))),
		("full_fee_paid", ("Full Fee Paid", ("Full Fee Paid",))),
		("enrolled", ("Enrolled Applications", ("Enrolled",))),
		("withdrawn", ("Withdrawn Applications", ("Withdrawn",))),
	]
)
CARD_OF_STATUS = {status: key for key, (_label, statuses) in STATUS_CARDS.items() for status in statuses}

CARDS = OrderedDict([("total", "Total Applications")] + [(k, label) for k, (label, _s) in STATUS_CARDS.items()])

CHARTS = OrderedDict(
	[
		("compare", "Programme comparison (2 or more programmes)"),
		("funnel", "Admission Funnel"),
		("trend", "Applications over time"),
		("status", "Status breakdown"),
		("fee", "Application fee status"),
		("category", "Category"),
		("gender", "Gender"),
		("geo", "State / Country"),
		("city", "Entrance test city"),
		("kapwd", "Karnataka Category & PWD"),
	]
)

CATEGORY_ORDER = ("General", "OBC-NCL", "SC", "ST", "EWS", NOT_SET)
GENDER_ORDER = ("Female", "Male", "Others", "Prefer not to say", NOT_SET)
FEE_ORDER = ("Paid", "Waived", "Requested", "Pending")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def get_bootstrap():
	"""Everything the page needs before the first render: built assets, cycles, layout."""
	_check_access()
	return {
		"assets": _get_bundle_assets(),
		"cycles": get_admission_cycles(),
		"settings": get_settings(),
		"can_edit_settings": _can_edit_settings(),
		"today": nowdate(),
	}


def _get_bundle_assets():
	"""Resolve the hashed JS/CSS file names from the Vite manifest."""
	assets = get_entry_assets(BUNDLE_ENTRY)
	if not assets:
		frappe.throw(
			_("Admission Dashboard assets are not built. Run `bench build --app slcm`."),
			title=_("Assets missing"),
		)
	return assets


@frappe.whitelist()
def get_admission_cycles():
	"""Admission Cycles, newest first, with the Active one as default."""
	_check_access()
	rows = frappe.get_all(
		"Admission Cycle",
		filters={"docstatus": ["<", 2]},
		fields=["name", "cycle_name", "academic_year", "status"],
		order_by="creation desc",
	)
	options = [
		{
			"value": r.name,
			"label": r.cycle_name or r.name,
			"academic_year": r.academic_year,
			"status": r.status,
		}
		for r in rows
	]
	active = next((r.name for r in rows if r.status == "Active"), None)
	return {"options": options, "default": active or (rows[0].name if rows else None)}


# --------------------------------------------------------------------------- #
# Programme list page
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def get_cycle_overview(admission_cycle, applicant_type=DOMESTIC, from_date=None, to_date=None):
	"""Summary cards, programme cards with their numbers, and the two cross-programme charts."""
	_check_access()
	applicant_type = _validate_applicant_type(applicant_type)
	cycle = _get_cycle(admission_cycle)
	window = _Window(from_date, to_date)

	programmes = _cycle_programmes(cycle.name, applicant_type)
	names = {p["name"] for p in programmes}

	# Applications: one light row per applicant of the cycle (both types, for the comparison chart).
	A = DocType("Applicant")
	applicants = (
		frappe.qb.from_(A)
		.select(A.program, A.status, A.creation, A.foriegn_national)
		.where(A.admission_cycle == cycle.name)
		.run(as_dict=True)
	)

	stats = {name: _empty_programme_stats() for name in names}
	by_programme = OrderedDict()
	for row in applicants:
		if not window.contains(row.creation):
			continue
		row_type = INTERNATIONAL if row.foriegn_national == "Yes" else DOMESTIC
		if row.program:
			split = by_programme.setdefault(row.program, {DOMESTIC: 0, INTERNATIONAL: 0})
			split[row_type] += 1
		if row_type != applicant_type or row.program not in stats:
			continue
		stage, exited = status_stage(row.status)
		s = stats[row.program]
		s["total"] += 1
		if stage == DRAFT and not exited:
			s["draft"] += 1
		if stage >= SUBMITTED:
			s["submitted"] += 1
		if stage == ENROLLED and not exited:
			s["enrolled"] += 1

	# Application fee: paid by payment date, settled by settlement date.
	fee_daily = OrderedDict()
	for pay in _fee_payments(cycle.name, applicant_type):
		s = stats.get(pay.program)
		amount = flt(pay.amount)
		settled = pay.settlement_status in SETTLED_STATES
		if window.contains(pay.paid_on):
			day = _day(pay.paid_on, fee_daily)
			day["collected"] += amount
			day["collected_count"] += 1
			if s:
				s["paid_count"] += 1
				s["collected"] += amount
				if not settled:
					s["awaiting_count"] += 1
					s["awaiting_amount"] += amount
		if settled and pay.settlement_date and window.contains(pay.settlement_date):
			day = _day(pay.settlement_date, fee_daily)
			day["settled"] += amount
			day["settled_count"] += 1
			if s:
				s["settled_count"] += 1
				s["settled_amount"] += amount

	for p in programmes:
		p["stats"] = stats[p["name"]]

	labels = {p["name"]: p["label"] for p in _cycle_programmes(cycle.name, None)}
	registration_from = window.from_date or _cycle_start(cycle)
	return {
		"programmes": programmes,
		"registrations": {
			**get_registration_counts(registration_from, window.to_date),
			"from_date": registration_from,
			"to_date": window.to_date,
		},
		"by_programme": [
			{
				"programme": labels.get(name, name),
				"name": name,
				"domestic": split[DOMESTIC],
				"international": split[INTERNATIONAL],
			}
			for name, split in by_programme.items()
			if name in labels
		],
		"fee_daily": _fill_days(fee_daily, window, ("collected", "collected_count", "settled", "settled_count")),
	}


def _empty_programme_stats():
	return {
		"total": 0,
		"draft": 0,
		"submitted": 0,
		"enrolled": 0,
		"paid_count": 0,
		"collected": 0,
		"settled_count": 0,
		"settled_amount": 0,
		"awaiting_count": 0,
		"awaiting_amount": 0,
	}


def _fee_payments(cycle, applicant_type, programs=None):
	"""Paid application-fee Payment Requests of the cycle (same rows as the NLSAT Fee Collection Report)."""
	PR = DocType("SLCM Payment Request")
	A = DocType("Applicant")
	query = (
		frappe.qb.from_(PR)
		.join(A)
		.on(A.name == PR.reference_name)
		.select(
			A.program,
			PR.amount,
			Coalesce(PR.paid_on, PR.creation).as_("paid_on"),
			PR.settlement_date,
			PR.settlement_status,
		)
		.where(PR.reference_doctype == "Applicant")
		.where(PR.docstatus < 2)
		.where(PR.status == "Paid")
		.where(A.admission_cycle == cycle)
	)
	query = query.where(_type_condition(A, applicant_type))
	if programs:
		query = query.where(A.program.isin(programs))
	return query.run(as_dict=True)


def _day(value, days):
	key = getdate(value).isoformat()
	if key not in days:
		days[key] = {"collected": 0, "collected_count": 0, "settled": 0, "settled_count": 0}
	return days[key]


# --------------------------------------------------------------------------- #
# Programme overview
# --------------------------------------------------------------------------- #

OVERVIEW_FIELDS = (
	"name",
	"program",
	"status",
	"creation",
	"application_fee_status",
	"application_fee_amount",
	"whether_scstobc_ncl",
	"gender",
	"state",
	"country",
	"first_preference",
	"karnataka_category",
	"pwd",
)


@frappe.whitelist()
def get_programme_overview(
	admission_cycle,
	programs,
	applicant_type=DOMESTIC,
	from_date=None,
	to_date=None,
	category=None,
	gender=None,
	fee_status=None,
):
	"""Cards and charts for one or more programmes of a cycle."""
	_check_access()
	applicant_type = _validate_applicant_type(applicant_type)
	cycle = _get_cycle(admission_cycle)
	programs = _as_list(programs)
	if not programs:
		frappe.throw(_("Select at least one programme."))
	window = _Window(from_date, to_date)

	A = DocType("Applicant")
	query = (
		frappe.qb.from_(A)
		.select(*[A[f] for f in OVERVIEW_FIELDS])
		.where(A.admission_cycle == cycle.name)
		.where(A.program.isin(programs))
		.where(_type_condition(A, applicant_type))
	)
	if window.start:
		query = query.where(A.creation >= window.start)
	if window.end:
		query = query.where(A.creation < window.end)

	rows = []
	for row in query.run(as_dict=True):
		row.category = (row.whether_scstobc_ncl or "").strip() or NOT_SET
		row.gender = (row.gender or "").strip() or NOT_SET
		row.fee = (row.application_fee_status or "").strip() or "Pending"
		if category and row.category != category:
			continue
		if gender and row.gender != gender:
			continue
		if fee_status and row.fee != fee_status:
			continue
		row.stage, row.exited = status_stage(row.status)
		# A paid (or waived) fee proves the Fee Paid stage even when the status doesn't, e.g. "Rejected".
		if row.stage == SUBMITTED and row.fee in ("Paid", "Waived"):
			row.stage = FEE_PAID
		rows.append(row)

	labels = {p["name"]: p["label"] for p in _cycle_programmes(cycle.name, None)}
	return {
		"cards": _overview_cards(rows),
		"sparkline": _last_days(rows, 30, window),
		"funnel": [{"stage": stage, "count": sum(1 for r in rows if r.stage >= i)} for i, stage in enumerate(STAGES)],
		"trend": _trend(rows, window, cycle),
		"status": _counts(rows, "status", blank=_("Not Set")),
		"fee": _fee_split(rows),
		"category": _ordered_counts(rows, "category", CATEGORY_ORDER),
		"gender": _ordered_counts(rows, "gender", GENDER_ORDER),
		"geo": _top(rows, "state" if applicant_type == DOMESTIC else "country"),
		"city": _top([r for r in rows if r.stage >= SUBMITTED], "first_preference"),
		"kapwd": _yes_no(rows, applicant_type),
		"compare": [
			{"name": p, "label": labels.get(p, p), **_overview_cards([r for r in rows if r.program == p])}
			for p in programs
		],
		"status_groups": _status_groups(),
	}


def _overview_cards(rows):
	"""Total, plus one count per status card by the applicant's current Application Status."""
	c = Counter()
	for r in rows:
		c["total"] += 1
		key = CARD_OF_STATUS.get((r.status or "Draft").strip())
		if key:
			c[key] += 1
	return {k: c[k] for k in CARDS}


def _trend(rows, window, cycle):
	"""Applications per day, empty days included, with the running total."""
	if not rows and not window.start:
		return []
	first = window.from_date or _cycle_start(cycle) or min(getdate(r.creation) for r in rows).isoformat()
	last = min(getdate(window.to_date or nowdate()), getdate(nowdate()))
	per_day = Counter(getdate(r.creation).isoformat() for r in rows)
	out, running, day = [], 0, getdate(first)
	if rows:
		day = min(day, min(getdate(r.creation) for r in rows))
	while day <= last:
		key = day.isoformat()
		running += per_day.get(key, 0)
		out.append({"date": key, "applications": per_day.get(key, 0), "running_total": running})
		day += timedelta(days=1)
	return out


def _last_days(rows, days, window):
	end = getdate(window.to_date or nowdate())
	per_day = Counter(getdate(r.creation) for r in rows)
	return [per_day.get(end - timedelta(days=i), 0) for i in range(days - 1, -1, -1)]


def _counts(rows, field, blank):
	c = Counter((r.get(field) or blank) for r in rows)
	return [{"label": k, "count": v} for k, v in c.most_common()]


def _ordered_counts(rows, field, order):
	c = Counter(r.get(field) for r in rows)
	known = [{"label": k, "count": c.get(k, 0)} for k in order]
	extra = [{"label": k, "count": v} for k, v in c.items() if k not in order]
	return [x for x in known + extra if x["count"] or x["label"] != NOT_SET]


def _top(rows, field, limit=10):
	c = Counter((r.get(field) or "").strip() for r in rows)
	c.pop("", None)
	return [{"label": k, "count": v} for k, v in c.most_common(limit)]


def _fee_split(rows):
	c = Counter(r.fee for r in rows)
	split = [{"label": k, "count": c.get(k, 0)} for k in FEE_ORDER]
	split += [{"label": k, "count": v} for k, v in c.items() if k not in FEE_ORDER]
	return {
		"split": [x for x in split if x["count"]],
		"collected": sum(flt(r.application_fee_amount) for r in rows if r.fee == "Paid"),
	}


def _yes_no(rows, applicant_type):
	def split(field, label):
		yes = sum(1 for r in rows if r.get(field) == "Yes")
		return {"label": label, "field": field, "yes": yes, "no": len(rows) - yes}

	out = [split("karnataka_category", _("Karnataka Category"))] if applicant_type == DOMESTIC else []
	return out + [split("pwd", _("PWD"))]


def _status_groups():
	"""Applicant Status names behind each card and funnel stage, for the list-view drill-down."""
	statuses = set(frappe.get_all("Applicant Status", pluck="name")) | set(STATUS_STAGE) | set(EXITED_STAGE)
	read = {s: status_stage(s) for s in statuses}
	pick = lambda fn: sorted(s for s, (stage, exited) in read.items() if fn(stage, exited))  # noqa: E731
	return {
		"cards": {key: list(statuses) for key, (_label, statuses) in STATUS_CARDS.items()},
		"submitted": pick(lambda st, ex: st >= SUBMITTED),
		"stages": [pick(lambda st, ex, i=i: st >= i) for i in range(len(STAGES))],
	}


# --------------------------------------------------------------------------- #
# Dashboard settings (global)
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def get_settings():
	"""Saved layout merged with the cards and charts the page knows."""
	_check_access()
	saved = _load_saved_layout()
	return {
		"cards": _merge_items(saved.get("cards"), CARDS),
		"charts": _merge_items(saved.get("charts"), CHARTS),
	}


@frappe.whitelist(methods=["POST"])
def save_settings(layout):
	"""Store the layout for everyone. Only System Manager / Admission Admin may do this."""
	if not _can_edit_settings():
		frappe.throw(_("Not permitted to change the Admission Dashboard settings."), frappe.PermissionError)

	if isinstance(layout, str):
		layout = json.loads(layout)

	clean = {"version": LAYOUT_VERSION}
	for section, allowed in (("cards", CARDS), ("charts", CHARTS)):
		items = []
		for item in layout.get(section) or []:
			key = (item or {}).get("key")
			if key in allowed and key not in {i["key"] for i in items}:
				items.append({"key": key, "enabled": 1 if item.get("enabled") else 0})
		clean[section] = items

	frappe.db.set_single_value(SETTINGS_DOCTYPE, "layout", json.dumps(clean))
	return get_settings()


@frappe.whitelist(methods=["POST"])
def reset_settings():
	if not _can_edit_settings():
		frappe.throw(_("Not permitted to change the Admission Dashboard settings."), frappe.PermissionError)
	frappe.db.set_single_value(SETTINGS_DOCTYPE, "layout", None)
	return get_settings()


def _load_saved_layout():
	raw = frappe.db.get_single_value(SETTINGS_DOCTYPE, "layout")
	if not raw:
		return {}
	try:
		data = json.loads(raw) if isinstance(raw, str) else raw
		return data if isinstance(data, dict) and data.get("version") == LAYOUT_VERSION else {}
	except ValueError:
		return {}


def _merge_items(saved_items, available):
	"""Saved order first (dropping keys that no longer exist), then any keys added since.

	Keys added after a layout was saved start hidden; with no usable saved layout
	(none yet, or one from an older version of the page) everything is shown.
	"""
	valid = [i for i in (saved_items or []) if isinstance(i, dict) and i.get("key") in available]
	items, seen = [], set()
	for item in valid:
		if item["key"] not in seen:
			items.append({"key": item["key"], "label": available[item["key"]], "enabled": cint(item.get("enabled"))})
			seen.add(item["key"])
	for key, label in available.items():
		if key not in seen:
			items.append({"key": key, "label": label, "enabled": 0 if valid else 1})
	return items


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class _Window:
	"""An inclusive date range from the page; either end may be open."""

	def __init__(self, from_date=None, to_date=None):
		self.from_date = getdate(from_date).isoformat() if from_date else None
		self.to_date = getdate(to_date).isoformat() if to_date else None
		if self.from_date and self.to_date and self.from_date > self.to_date:
			self.from_date, self.to_date = self.to_date, self.from_date
		self.start = get_datetime(self.from_date) if self.from_date else None
		self.end = get_datetime(add_days(self.to_date, 1)) if self.to_date else None  # exclusive

	def contains(self, value):
		if not value:
			return False
		value = get_datetime(value)
		return (not self.start or value >= self.start) and (not self.end or value < self.end)


def _fill_days(days, window, keys):
	"""Rows for every day of the window (or of the data, when the window is open)."""
	if not days and not (window.from_date and window.to_date):
		return []
	first = getdate(window.from_date or min(days))
	last = getdate(window.to_date or max(max(days), nowdate()))
	last = min(last, getdate(nowdate()))
	out, day = [], first
	while day <= last:
		key = day.isoformat()
		out.append({"date": key, **(days.get(key) or {k: 0 for k in keys})})
		day += timedelta(days=1)
	return out


def _cycle_programmes(cycle, applicant_type):
	"""Programme cards for a cycle and tab (all of the cycle's programmes when `applicant_type` is None)."""
	rows = frappe.get_all(
		"Admission Cycle Program",
		filters={"parent": cycle, "parenttype": "Admission Cycle", "is_active": 1},
		fields=["program", "program_name", "program_level", "admission_open_for", "idx"],
		order_by="idx asc",
	)
	fields = ["name", "program_name", "level_of_study"]
	if frappe.get_meta("Programme").has_field("dashboard_icon"):
		fields.append("dashboard_icon")
	meta = {
		p.name: p
		for p in frappe.get_all(
			"Programme", filters={"name": ["in", list({r.program for r in rows if r.program})]}, fields=fields
		)
	}

	programmes = OrderedDict()
	for row in rows:
		if not row.program or row.program in programmes:
			continue
		if applicant_type and not _open_for(row.admission_open_for, applicant_type):
			continue
		m = meta.get(row.program) or frappe._dict()
		level = m.level_of_study or row.program_level or ""
		programmes[row.program] = {
			"name": row.program,
			"label": row.program_name or m.program_name or row.program,
			"level": level,
			"level_label": _level_label(level),
			"level_key": _level_key(level),
			"icon": m.get("dashboard_icon") or None,
		}
	return list(programmes.values())


def _open_for(admission_open_for, applicant_type):
	"""Same rule as the portal: blank lists everywhere, otherwise substring match."""
	open_for = (admission_open_for or "").strip()
	return not open_for or applicant_type in open_for


def _level_key(level):
	lv = (level or "").strip().lower()
	if lv.startswith("under") or lv == "ug":
		return "undergraduate"
	if lv.startswith("post") or lv == "pg":
		return "postgraduate"
	if "research" in lv or "phd" in lv or "ph.d" in lv:
		return "research"
	return "other"


def _level_label(level):
	return {
		"undergraduate": _("Undergraduate Programme"),
		"postgraduate": _("Postgraduate Programme"),
		"research": _("Research Programme"),
	}.get(_level_key(level), level or _("Programme"))


def _type_condition(A, applicant_type):
	if applicant_type == INTERNATIONAL:
		return A.foriegn_national == "Yes"
	return Coalesce(A.foriegn_national, "") != "Yes"


def _get_cycle(name):
	if not name or not frappe.db.exists("Admission Cycle", name):
		frappe.throw(_("Select an Admission Cycle."))
	return frappe.db.get_value(
		"Admission Cycle",
		name,
		["name", "application_start_date", "cycle_start_date"],
		as_dict=True,
	)


def _cycle_start(cycle):
	start = cycle.application_start_date or cycle.cycle_start_date
	return getdate(start).isoformat() if start else None


def _as_list(value):
	if isinstance(value, str):
		value = json.loads(value) if value.strip().startswith("[") else [value]
	return [v for v in (value or []) if v]


def _check_access():
	if not frappe.has_permission("Applicant", "read"):
		frappe.throw(_("Not permitted to view the Admission Dashboard."), frappe.PermissionError)


def _can_edit_settings():
	return bool(set(SETTINGS_EDITOR_ROLES) & set(frappe.get_roles()))


def _validate_applicant_type(applicant_type):
	if applicant_type not in APPLICANT_TYPES:
		frappe.throw(_("Invalid applicant type: {0}").format(applicant_type))
	return applicant_type
