import frappe


def execute():
	"""Fill RFID SQL Punch Log.punch_date / punch_clock from punch_time for existing rows."""
	frappe.db.sql(
		"""UPDATE `tabRFID SQL Punch Log`
		SET punch_date = DATE(punch_time), punch_clock = TIME(punch_time)
		WHERE punch_time IS NOT NULL
		  AND (punch_date IS NULL OR punch_clock IS NULL)"""
	)
