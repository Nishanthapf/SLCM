import frappe


def execute():
	"""Fee Demand list shows the student's Registration ID (registration_id) instead of the system ID."""
	if not frappe.db.has_column("Fee Demand", "registration_id"):
		return
	frappe.db.sql(
		"""UPDATE `tabFee Demand` fd JOIN `tabStudent Master` sm ON sm.name = fd.student
		SET fd.registration_id = sm.registration_id
		WHERE IFNULL(fd.registration_id, '') != IFNULL(sm.registration_id, '')"""
	)
