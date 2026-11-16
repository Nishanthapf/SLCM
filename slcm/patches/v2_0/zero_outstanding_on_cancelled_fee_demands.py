import frappe


def execute():
	"""Cancelled dues carry no pending amount."""
	frappe.db.sql(
		"""UPDATE `tabFee Demand` SET outstanding_amount = 0
		WHERE status = 'Cancelled' AND IFNULL(outstanding_amount, 0) != 0"""
	)
