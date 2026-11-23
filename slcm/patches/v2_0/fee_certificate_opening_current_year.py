import frappe

OLD = (
	"studying in {{ current_year }} year {{ programme }} programme for the Academic Year (AY) {{ academic_year }}"
)
NEW = (
	"studying in {{ studying_year }} year {{ programme }} programme for the Academic Year (AY) "
	"{{ current_academic_year }}"
)


def execute():
	"""Fee Demand Letter and Education Loan certificates: the opening ("studying in __ year
	... for the Academic Year (AY) __") states the student's year of study now and the
	current Academic Year, as the Fee Receipt already does; the rest of the text keeps the
	requested year. Only the default opening is replaced (first occurrence)."""
	for row in frappe.get_all(
		"Fee Certificate Purpose Template",
		filters={"parent": "Fee Certificate Settings"},
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
