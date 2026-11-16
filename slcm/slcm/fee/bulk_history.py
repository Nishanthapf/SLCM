"""History and delete for the fee bulk uploads (Data Import, Insert New Records).

History lists every Data Import of a fee doctype with what it created and how much of it is still active.
Delete reverses everything one import created, through each doctype's own cancel logic, so the dues, receipts,
excess and ERPNext entries reverse exactly as when a single record is cancelled. It is all-or-nothing: if any
record cannot be reversed (for example a payment that has since been refunded) nothing changes and the reason
is shown. Reversed records stay as Cancelled / Reversed for the audit trail.
"""

import frappe
from frappe import _
from frappe.utils import cint, flt

from slcm.slcm.fee.bulk_upload import BULK_DOCTYPES

ALLOWED_ROLES = ("System Manager", "Campus Admin", "Accounts Manager", "Accounts User")


def _check_access():
	frappe.only_for(ALLOWED_ROLES)


def _created_records(data_import):
	"""Names of the records an import created, in creation order."""
	rows = frappe.get_all(
		"Data Import Log",
		filters={"data_import": data_import, "success": 1},
		fields=["docname"],
		order_by="log_index asc, creation asc",
	)
	seen, names = set(), []
	for r in rows:
		if r.docname and r.docname not in seen:
			seen.add(r.docname)
			names.append(r.docname)
	return names


def _is_active(doctype, row):
	"""Still in effect (not cancelled / reversed / deleted)."""
	if not row:
		return False
	if doctype == "Fee Demand":
		return row.status != "Cancelled"
	return cint(row.docstatus) == 1


def _record_rows(doctype, names):
	if not names:
		return {}
	fields = {
		"Fee Demand": ["name", "status", "docstatus", "student", "registration_id", "fee_component", "net_payable AS amount"],
		"Fee Payment": ["name", "status", "docstatus", "student", "registration_id", "amount", "reference_number AS reference"],
		"Fee Concession": ["name", "status", "docstatus", "student", "registration_id", "waiver_amount AS amount", "fee_demand AS reference"],
		"Fee Refund": ["name", "status", "docstatus", "student", "registration_id", "refund_amount AS amount", "refund_source AS reference"],
		"Student Credit Note": ["name", "status", "docstatus", "student", "registration_id", "credit_amount AS amount", "received_reference AS reference"],
	}[doctype]
	return {r.name: r for r in frappe.get_all(doctype, filters={"name": ["in", names]}, fields=fields)}


@frappe.whitelist()
def get_history(limit=50):
	"""Fee bulk uploads, newest first, with created / still-active counts."""
	_check_access()
	imports = frappe.get_all(
		"Data Import",
		filters={"reference_doctype": ["in", BULK_DOCTYPES], "import_type": "Insert New Records"},
		fields=["name", "reference_doctype", "status", "owner", "creation", "import_file", "submit_after_import"],
		order_by="creation desc",
		limit_page_length=cint(limit) or 50,
	)
	for imp in imports:
		names = _created_records(imp.name)
		rows = _record_rows(imp.reference_doctype, names)
		imp.created = len(names)
		imp.active = sum(1 for n in names if _is_active(imp.reference_doctype, rows.get(n)))
		imp.failed = frappe.db.count("Data Import Log", {"data_import": imp.name, "success": 0})
		imp.owner_name = frappe.utils.get_fullname(imp.owner)
		imp.file_name = (imp.import_file or "").rsplit("/", 1)[-1]
	return imports


@frappe.whitelist()
def get_records(data_import):
	"""What one import created and the current state of each record."""
	_check_access()
	doctype = frappe.db.get_value("Data Import", data_import, "reference_doctype")
	if doctype not in BULK_DOCTYPES:
		frappe.throw(_("{0} is not a fee bulk upload.").format(data_import))
	names = _created_records(data_import)
	rows = _record_rows(doctype, names)
	out = []
	for n in names:
		r = rows.get(n)
		out.append({
			"name": n,
			"exists": bool(r),
			"active": _is_active(doctype, r),
			"status": (r.status if r else _("Deleted")) or "",
			"registration_id": r.registration_id if r else "",
			"amount": flt(r.amount) if r else 0,
			"reference": (r.get("reference") if r else "") or "",
		})
	return {"doctype": doctype, "records": out}


# ── Delete (reverse) ─────────────────────────────────────────────────────────
def _reverse(doctype, name, remarks):
	doc = frappe.get_doc(doctype, name)
	note = _("Reversed with its bulk upload: {0}").format(remarks)
	if doctype == "Fee Payment":
		from slcm.slcm.page.student_fee_management.student_fee_management import _cancel_payment, _editable_payment

		_cancel_payment(_editable_payment(name, doc.student), note)
		return
	if doctype == "Fee Demand":
		if flt(doc.paid_amount) > 0 or flt(doc.credit_adjusted) > 0:
			frappe.throw(_("{0} has money paid or adjusted against it; reverse that first.").format(name))
		concession = frappe.db.get_value("Fee Concession", {"fee_demand": name, "docstatus": 1}, "name")
		if concession:
			frappe.throw(_("{0} has concession {1}; reverse it first.").format(name, concession))
		doc.status = "Cancelled"
		doc.flags.ignore_links = True
		doc.save(ignore_permissions=True)
		doc.add_comment("Comment", note)
		return
	# submittable: Fee Concession, Fee Refund, Student Credit Note — their on_cancel reverses the effect
	doc.add_comment("Comment", note)
	doc.flags.ignore_permissions = True
	doc.cancel()


@frappe.whitelist()
def delete_import(data_import, remarks=None):
	"""Reverse every record a fee bulk upload created that is still active. All or nothing."""
	_check_access()
	remarks = (remarks or "").strip()
	if not remarks:
		frappe.throw(_("Remarks are mandatory."))
	doctype = frappe.db.get_value("Data Import", data_import, "reference_doctype")
	if doctype not in BULK_DOCTYPES:
		frappe.throw(_("{0} is not a fee bulk upload.").format(data_import))

	names = _created_records(data_import)
	rows = _record_rows(doctype, names)
	todo = [n for n in reversed(names) if _is_active(doctype, rows.get(n))]  # newest first
	if not todo:
		frappe.throw(_("Nothing to delete: every record of this upload is already reversed."))

	frappe.db.savepoint("sfm_delete_import")
	try:
		for name in todo:
			try:
				_reverse(doctype, name, remarks)
			except Exception as e:
				frappe.clear_last_message()
				msg = getattr(e, "message", None) or str(e) or e.__class__.__name__
				frappe.throw(
					_("Could not delete {0} {1}: {2}. Nothing in this upload was changed.").format(
						_(doctype), name, frappe.utils.strip_html(str(msg))
					),
					title=_("Upload not deleted"),
				)
	except Exception:
		frappe.db.rollback(save_point="sfm_delete_import")
		raise

	frappe.get_doc("Data Import", data_import).add_comment(
		"Comment", _("{0} record(s) reversed from Student Fee Management. Remarks: {1}").format(len(todo), frappe.utils.escape_html(remarks))
	)
	return {"reversed": len(todo)}
