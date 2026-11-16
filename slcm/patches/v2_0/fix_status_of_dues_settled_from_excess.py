import frappe
from frappe.utils import getdate, today


def execute():
	"""Dues settled wholly or partly from excess (credit_adjusted) kept showing Pending / Overdue, because the
	status counted only cash paid. Recompute their status the way Fee Demand now does (paid + adjusted)."""
	rows = frappe.db.sql(
		"""SELECT name, due_date, outstanding_amount, status FROM `tabFee Demand`
		WHERE IFNULL(credit_adjusted, 0) > 0 AND status IN ('Pending', 'Overdue', 'Partially Paid')""",
		as_dict=True,
	)
	for d in rows:
		if (d.outstanding_amount or 0) <= 0:
			status = "Paid"
		elif d.due_date and getdate(d.due_date) < getdate(today()):
			status = "Overdue"
		else:
			status = "Partially Paid"
		if status != d.status:
			frappe.db.set_value("Fee Demand", d.name, "status", status, update_modified=False)
