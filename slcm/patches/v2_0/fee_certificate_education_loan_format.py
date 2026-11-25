import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import (
	_BANK_DETAILS,
	_LOAN_BODY,
	_LOAN_NOTE,
	MULTI_YEAR,
)

_INTRO = "<p>This is to certify that <strong>{{ student_name }}</strong> (student ID: <strong>{{ student_id }}</strong>) "
_TAIL = (
	"in this University is now required to pay the course fee for {{ due_year }} year i.e. "
	"<strong>AY {{ due_academic_year }}</strong>.</p><p>The fee structure for {{ programme }} is shown below.</p>"
)
# Earlier default bodies (before / after patch fee_certificate_opening_current_year).
OLD_BODIES = {
	_INTRO
	+ "studying in {{ current_year }} year {{ programme }} programme for the Academic Year (AY) {{ academic_year }} "
	+ _TAIL,
	_INTRO
	+ "studying in {{ studying_year }} year {{ programme }} programme for the Academic Year (AY) "
	+ "{{ current_academic_year }} "
	+ _TAIL,
}


def execute():
	"""Education Loan certificate in the office's "FEE CERTIFICATE" format: heading, wording,
	"Amount paid" / "Balance payable" rows and the provisional-fees note before the bank
	details. Only fields still on an earlier default are changed."""
	frappe.reload_doc("slcm", "doctype", "fee_certificate_purpose_template")
	for row in frappe.get_all(
		"Fee Certificate Purpose Template",
		filters={"parent": "Fee Certificate Settings", "certificate_type": MULTI_YEAR},
		fields=["name", "heading", "body_text", "bank_details_text", "paid_row_label", "outstanding_row_label"],
	):
		values = {}
		if (row.heading or "").strip() in ("", "Fee Demand Letter"):
			values["heading"] = "FEE CERTIFICATE"
		if (row.body_text or "").strip() in OLD_BODIES:
			values["body_text"] = _LOAN_BODY
		if (row.bank_details_text or "").strip() == _BANK_DETAILS:
			values["bank_details_text"] = _LOAN_NOTE + _BANK_DETAILS
		if (row.paid_row_label or "").strip() in ("", "Total Fee paid"):
			values["paid_row_label"] = "Amount paid"
		if (row.outstanding_row_label or "").strip() in ("", "Outstanding fee"):
			values["outstanding_row_label"] = "Balance payable"
		if values:
			frappe.db.set_value("Fee Certificate Purpose Template", row.name, values, update_modified=False)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
