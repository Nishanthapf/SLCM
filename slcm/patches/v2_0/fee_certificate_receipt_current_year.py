import frappe

from slcm.slcm.doctype.fee_certificate_settings.fee_certificate_settings import SINGLE_YEAR_RECEIPT

OLD = (
	"studying in {{ current_year }} year {{ programme }} programme for the Academic Year (AY) {{ academic_year }}"
)
NEW = (
	"studying in {{ studying_year }} year {{ programme }} programme for the Academic Year (AY) "
	"{{ current_academic_year }}"
)


def execute():
	"""Fee Receipt: the opening ("studying in __ year ... for the Academic Year (AY) __")
	now states the student's current year of study and the current Academic Year; the
	closing still names the year the receipt is for. Only the first occurrence is
	replaced, and rows whose text no longer has the default opening are left alone."""
	frappe.reload_doc("slcm", "doctype", "fee_certificate_purpose_template")
	for row in frappe.get_all(
		"Fee Certificate Purpose Template",
		filters={"parent": "Fee Certificate Settings", "certificate_type": SINGLE_YEAR_RECEIPT},
		fields=["name", "body_text"],
	):
		if OLD in (row.body_text or ""):
			frappe.db.set_value(
				"Fee Certificate Purpose Template",
				row.name,
				"body_text",
				row.body_text.replace(OLD, NEW, 1),
				update_modified=False,
			)
	frappe.clear_document_cache("Fee Certificate Settings", "Fee Certificate Settings")
