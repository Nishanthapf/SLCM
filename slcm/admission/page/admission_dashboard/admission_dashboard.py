"""Admission Dashboard (desk page `admission-dashboard`).

The page is a Vue 3 + frappe-ui app built from `frontend/src/admission_dashboard`
into `slcm/public/frontend`. These whitelisted methods feed it.

Programme cards follow the admission portal (`get_active_programs` in
`slcm.admission.utils.portal`): the active rows of the Admission Cycle Program
table, filtered by `admission_open_for` (blank or "Domestic & International"
lists a programme under both tabs). The Academic Year filter selects the
Admission Cycles whose `academic_year` matches.

Applicants are split the same way the portal splits them: `foriegn_national`
"Yes" is International, anything else is Domestic.
"""

import json
from collections import OrderedDict

import frappe
from frappe import _
from frappe.utils import cint, get_datetime

from slcm.utils.vite_assets import get_entry_assets

DOMESTIC = "Domestic"
INTERNATIONAL = "International"
APPLICANT_TYPES = (DOMESTIC, INTERNATIONAL)

TOTAL_CARD = "total"
STATUS_CARD_PREFIX = "status:"

# Cards shown when nothing has been saved yet (the rest are listed, switched off).
DEFAULT_STATUS_CARDS = ("Draft", "Submitted", "Submitted and Paid", "Selected", "Rejected")

CHARTS = OrderedDict(
	[
		("status_donut", "Application Status"),
		("trend", "Application Trend"),
	]
)

SETTINGS_DOCTYPE = "Admission Dashboard Settings"
SETTINGS_EDITOR_ROLES = ("System Manager", "Admission Admin")
BUNDLE_ENTRY = "src/admission_dashboard/main.js"  # key in slcm/public/frontend/manifest.json


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def get_bootstrap():
	"""Everything the page needs before the first render: built assets, filters, layout."""
	_check_access()
	return {
		"assets": _get_bundle_assets(),
		"academic_years": get_academic_years(),
		"settings": get_settings(),
		"can_edit_settings": _can_edit_settings(),
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


# --------------------------------------------------------------------------- #
# Filters and programme cards
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def get_academic_years():
	"""Academic Years that have an Admission Cycle, newest first, with the active one as default."""
	_check_access()
	cycles = frappe.get_all(
		"Admission Cycle",
		filters={"docstatus": ["<", 2], "academic_year": ["is", "set"]},
		fields=["academic_year", "status"],
		order_by="academic_year desc",
	)

	years = list(OrderedDict.fromkeys(c.academic_year for c in cycles))
	active = next((c.academic_year for c in cycles if c.status == "Active"), None)
	return {"options": years, "default": active or (years[0] if years else None)}


@frappe.whitelist()
def get_programmes(academic_year, applicant_type=DOMESTIC):
	"""Programme cards for the selected Academic Year and Domestic/International tab."""
	_check_access()
	applicant_type = _validate_applicant_type(applicant_type)
	cycles = _get_cycles(academic_year)
	if not cycles:
		return []

	rows = frappe.get_all(
		"Admission Cycle Program",
		filters={"parent": ["in", cycles], "parenttype": "Admission Cycle", "is_active": 1},
		fields=["program", "program_name", "program_level", "admission_open_for", "idx"],
		order_by="idx asc",
	)

	programme_meta = {
		p.name: p
		for p in frappe.get_all(
			"Programme",
			filters={"name": ["in", list({r.program for r in rows if r.program})]},
			fields=["name", "program_name", "level_of_study"],
		)
	}

	programmes = OrderedDict()
	for row in rows:
		if not row.program or row.program in programmes:
			continue
		if not _open_for(row.admission_open_for, applicant_type):
			continue

		meta = programme_meta.get(row.program) or frappe._dict()
		level = meta.level_of_study or row.program_level or ""
		programmes[row.program] = {
			"name": row.program,
			"label": row.program_name or meta.program_name or row.program,
			"level": level,
			"level_label": _level_label(level),
			"level_key": _level_key(level),
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


# --------------------------------------------------------------------------- #
# Programme overview
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def get_programme_overview(academic_year, program, applicant_type=DOMESTIC):
	"""Number cards, status split and monthly trend for one programme."""
	_check_access()
	applicant_type = _validate_applicant_type(applicant_type)
	cycles = _get_cycles(academic_year)

	filters = [["Applicant", "program", "=", program]]
	if cycles:
		filters.append(["Applicant", "admission_cycle", "in", cycles])
	else:
		# No cycle in this year means no applications to show.
		filters.append(["Applicant", "name", "is", "not set"])

	if applicant_type == INTERNATIONAL:
		filters.append(["Applicant", "foriegn_national", "=", "Yes"])
	else:
		filters.append(["Applicant", "foriegn_national", "!=", "Yes"])

	status_rows = frappe.get_list(
		"Applicant",
		filters=filters,
		fields=["status", {"COUNT": "*", "as": "count"}],
		group_by="status",
		order_by=None,
	)
	by_status = {(r.status or _("Not Set")): cint(r.count) for r in status_rows}
	total = sum(by_status.values())

	created = frappe.get_list(
		"Applicant",
		filters=filters,
		pluck="creation",
		order_by="creation asc",
		limit_page_length=0,
	)

	return {
		"total": total,
		"by_status": by_status,
		"trend": _monthly_trend(created),
	}


def _monthly_trend(creation_dates):
	"""Applications per month and the running total, with empty months filled in."""
	if not creation_dates:
		return []

	months = OrderedDict()
	for value in creation_dates:
		key = get_datetime(value).strftime("%Y-%m-01")
		months[key] = months.get(key, 0) + 1

	first, last = next(iter(months)), next(reversed(months))
	year, month = int(first[:4]), int(first[5:7])
	trend, running = [], 0
	while True:
		key = f"{year:04d}-{month:02d}-01"
		new = months.get(key, 0)
		running += new
		trend.append({"month": key, "applications": running, "new": new})
		if key == last:
			break
		month += 1
		if month > 12:
			year, month = year + 1, 1
	return trend


# --------------------------------------------------------------------------- #
# Dashboard settings (global)
# --------------------------------------------------------------------------- #


@frappe.whitelist()
def get_settings():
	"""Saved layout merged with the current Applicant Status list."""
	_check_access()
	saved = _load_saved_layout()
	return {
		"cards": _merge_items(saved.get("cards"), _available_cards(), _default_card_keys()),
		"charts": _merge_items(saved.get("charts"), CHARTS, set(CHARTS)),
	}


@frappe.whitelist(methods=["POST"])
def save_settings(layout):
	"""Store the layout for everyone. Only System Manager / Admission Admin may do this."""
	if not _can_edit_settings():
		frappe.throw(_("Not permitted to change the Admission Dashboard settings."), frappe.PermissionError)

	if isinstance(layout, str):
		layout = json.loads(layout)

	clean = {}
	for section, allowed in (("cards", _available_cards()), ("charts", CHARTS)):
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
		return data if isinstance(data, dict) else {}
	except ValueError:
		return {}


def _available_cards():
	cards = OrderedDict([(TOTAL_CARD, _("Total Applications"))])
	for status in frappe.get_all("Applicant Status", pluck="name", order_by="creation asc"):
		cards[STATUS_CARD_PREFIX + status] = status
	return cards


def _default_card_keys():
	return {TOTAL_CARD} | {STATUS_CARD_PREFIX + s for s in DEFAULT_STATUS_CARDS}


def _merge_items(saved_items, available, default_enabled):
	"""Saved order first (dropping keys that no longer exist), then any new keys."""
	items, seen = [], set()
	if saved_items:
		for item in saved_items:
			key = item.get("key")
			if key in available and key not in seen:
				items.append({"key": key, "label": available[key], "enabled": cint(item.get("enabled"))})
				seen.add(key)
		new_enabled = set()  # anything added after the layout was saved starts hidden
	else:
		new_enabled = default_enabled

	# Without a saved layout, put the default cards first in their default order.
	if not saved_items:
		ordered = [k for k in available if k == TOTAL_CARD]
		ordered += [STATUS_CARD_PREFIX + s for s in DEFAULT_STATUS_CARDS if STATUS_CARD_PREFIX + s in available]
		ordered += [k for k in available if k not in ordered]
	else:
		ordered = list(available)

	for key in ordered:
		if key not in seen:
			items.append({"key": key, "label": available[key], "enabled": 1 if key in new_enabled else 0})
			seen.add(key)
	return items


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _check_access():
	if not frappe.has_permission("Applicant", "read"):
		frappe.throw(_("Not permitted to view the Admission Dashboard."), frappe.PermissionError)


def _can_edit_settings():
	return bool(set(SETTINGS_EDITOR_ROLES) & set(frappe.get_roles()))


def _validate_applicant_type(applicant_type):
	if applicant_type not in APPLICANT_TYPES:
		frappe.throw(_("Invalid applicant type: {0}").format(applicant_type))
	return applicant_type


def _get_cycles(academic_year):
	if not academic_year:
		return []
	return frappe.get_all(
		"Admission Cycle",
		filters={"academic_year": academic_year, "docstatus": ["<", 2]},
		pluck="name",
	)
