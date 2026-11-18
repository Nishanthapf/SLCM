# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""Where each RFID reader is installed, over time.

The `room` field links to **Venue Master** — the same master the Time Table
uses for `venue` — so a tap can be checked against the class's venue. The
fieldname stays `room` for backward compatibility; its label is "Venue".
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, today


class RFIDDeviceRoomMapping(Document):
	def validate(self):
		if not self.effective_from:
			# A blank start date would never satisfy `effective_from <= date`,
			# leaving the mapping silently inactive.
			self.effective_from = today()
		self.validate_date_range()
		self.validate_overlap()

	def validate_date_range(self):
		if self.effective_to and getdate(self.effective_to) < getdate(self.effective_from):
			frappe.throw(_("Effective To date cannot be before Effective From date."))

	def validate_overlap(self):
		"""A reader is physically in one venue at a time: no two active
		mappings of the same device may have overlapping date ranges."""
		if not self.is_active:
			return

		existing = frappe.get_all(
			"RFID Device Room Mapping",
			filters={"device": self.device, "is_active": 1, "name": ["!=", self.name or ""]},
			fields=["name", "room", "effective_from", "effective_to"],
		)

		new_start = getdate(self.effective_from)
		new_end = getdate(self.effective_to) if self.effective_to else None

		for row in existing:
			existing_start = getdate(row.effective_from) if row.effective_from else None
			existing_end = getdate(row.effective_to) if row.effective_to else None

			starts_before_existing_ends = existing_end is None or new_start <= existing_end
			ends_after_existing_starts = new_end is None or existing_start is None or new_end >= existing_start

			if starts_before_existing_ends and ends_after_existing_starts:
				frappe.throw(_(
					"Device {0} is already mapped to venue {1} for an overlapping period ({2}). "
					"Set an Effective To date on that mapping (or deactivate it) first."
				).format(
					frappe.bold(self.device),
					frappe.bold(row.room),
					frappe.utils.get_link_to_form("RFID Device Room Mapping", row.name),
				))


def get_active_rooms_for_device(device_id, on_date=None):
	"""Venue Master names the device is mapped to on `on_date` (default today).
	Normally zero or one entry; kept as a list for the existing callers."""
	if not device_id:
		return []
	on_date = getdate(on_date) if on_date else getdate()

	return frappe.db.sql_list("""
		SELECT room
		FROM `tabRFID Device Room Mapping`
		WHERE device = %(device)s
		AND is_active = 1
		AND effective_from <= %(on_date)s
		AND (effective_to IS NULL OR effective_to >= %(on_date)s)
	""", {"device": device_id, "on_date": on_date})


def get_devices_for_venue(venue, on_date=None):
	"""RFID Device names mapped to `venue`; all active mappings when no date."""
	if not venue:
		return []
	conditions = ""
	values = {"venue": venue}
	if on_date:
		values["on_date"] = getdate(on_date)
		conditions = "AND effective_from <= %(on_date)s AND (effective_to IS NULL OR effective_to >= %(on_date)s)"
	return frappe.db.sql_list(f"""
		SELECT DISTINCT device
		FROM `tabRFID Device Room Mapping`
		WHERE room = %(venue)s AND is_active = 1 {conditions}
	""", values)


# ---------------------------------------------------------------------------
# Seeding: suggest venue mappings from RFID Device reader labels
# ---------------------------------------------------------------------------

def _norm(text):
	return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def _reader_token(label):
	"""'NAB-103-1' -> 'NAB103'; strips a trailing reader number."""
	parts = [p for p in (label or "").replace(" ", "-").split("-") if p]
	if len(parts) > 1 and parts[-1].isdigit() and len(parts[-1]) == 1:
		parts = parts[:-1]
	return _norm("".join(parts))


def _suggest_rows():
	venues = frappe.get_all("Venue Master", filters={"is_active": 1}, fields=["name", "venue_code"])
	devices = frappe.get_all(
		"RFID Device",
		filters={"is_active": 1},
		fields=["name", "device_name", "location", "device_type"],
		order_by="location asc",
	)
	rows = []
	for d in devices:
		row = {"device": d.name, "label": d.location or d.device_name or "", "venue": None, "code": "", "status": ""}
		rows.append(row)
		if (d.device_type or "Classroom") != "Classroom":
			row["code"] = "skipped"
			row["status"] = _("Skipped: {0} reader").format(d.device_type)
			continue
		current = get_active_rooms_for_device(d.name)
		if current:
			row["venue"] = current[0]
			row["code"] = "mapped"
			row["status"] = _("Already mapped")
			continue
		if "OLD" in _norm(row["label"]):
			row["code"] = "skipped"
			row["status"] = _("Skipped: label marked old")
			continue
		token = _reader_token(row["label"])
		if not token:
			row["code"] = "unmatched"
			row["status"] = _("No reader label")
			continue
		exact = [v.name for v in venues if token in (_norm(v.name), _norm(v.venue_code))]
		matches = exact or [v.name for v in venues if _norm(v.name).endswith(token)]
		matches = sorted(set(matches))
		if len(matches) == 1:
			row["venue"] = matches[0]
			row["code"] = "suggested"
			row["status"] = _("Suggested")
		elif matches:
			row["code"] = "ambiguous"
			row["status"] = _("Ambiguous: {0}").format(", ".join(matches))
		else:
			row["code"] = "unmatched"
			row["status"] = _("No matching venue")
	return rows


@frappe.whitelist()
def suggest_venue_mappings():
	"""Dry run: what each active reader would be mapped to."""
	frappe.only_for("System Manager")
	return _suggest_rows()


@frappe.whitelist()
def create_suggested_mappings(devices=None, manual=None):
	"""Create mappings (effective today).

	`devices`: devices whose current 'Suggested' venue should be used.
	`manual`: {device: venue} picked by hand for unmatched/ambiguous/skipped readers.
	All-or-nothing: any error rolls back the whole request."""
	frappe.only_for("System Manager")
	wanted = set(frappe.parse_json(devices) or [])
	manual = frappe.parse_json(manual) or {}
	if not isinstance(manual, dict):
		frappe.throw(_("Invalid manual mappings."))
	manual = {d: v for d, v in manual.items() if d and v}

	rows = {row["device"]: row for row in _suggest_rows()}
	for device, venue in manual.items():
		row = rows.get(device)
		if not row:
			frappe.throw(_("RFID Device {0} is not an active reader.").format(frappe.bold(device)))
		if row["code"] not in ("unmatched", "ambiguous", "skipped"):
			frappe.throw(_("Device {0} ({1}) can no longer be mapped by hand: {2}. Reopen the dialog.").format(
				frappe.bold(device), row["label"], row["status"]))
		if not frappe.db.get_value("Venue Master", {"name": venue, "is_active": 1}):
			frappe.throw(_("Venue {0} does not exist or is inactive.").format(frappe.bold(venue)))

	created = []
	for row in rows.values():
		if row["device"] in manual:
			venue = manual[row["device"]]
			remarks = _("Mapped by hand from reader label '{0}'").format(row["label"])
		elif row["device"] in wanted and row["code"] == "suggested":
			venue = row["venue"]
			remarks = _("Created from reader label '{0}'").format(row["label"])
		else:
			continue
		doc = frappe.get_doc({
			"doctype": "RFID Device Room Mapping",
			"device": row["device"],
			"room": venue,
			"effective_from": today(),
			"is_active": 1,
			"remarks": remarks,
		}).insert()
		created.append(doc.name)
	return created
