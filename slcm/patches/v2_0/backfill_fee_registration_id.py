import frappe

# Fee DocTypes that gained a read-only Registration ID (fetched from the student) beside their Student link.
DOCTYPES = (
	"Fee Refund",
	"Student Credit Note",
	"Stipend Payment",
	"University Financial Aid",
	"Fee Invoice",
	"Hostel Fine",
)


def execute():
	"""Fill Registration ID on existing records; new ones get it from the student on save."""
	for doctype in DOCTYPES:
		if not frappe.db.table_exists(doctype) or not frappe.db.has_column(doctype, "registration_id"):
			continue
		frappe.db.sql(
			f"""UPDATE `tab{doctype}` t JOIN `tabStudent Master` sm ON sm.name = t.student
			SET t.registration_id = sm.registration_id
			WHERE IFNULL(t.registration_id, '') != IFNULL(sm.registration_id, '')"""
		)
