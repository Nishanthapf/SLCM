import frappe


def execute():
	"""Add User Activity Log (365 days) to Log Settings > Logs to Clear."""
	if frappe.db.exists("DocType", "User Activity Log"):
		frappe.get_doc("Log Settings").save(ignore_permissions=True)
