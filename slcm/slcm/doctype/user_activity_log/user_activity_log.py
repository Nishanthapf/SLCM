# Copyright (c) 2026, SLCM and contributors
# One row per action a logged-in user performs (see slcm/utils/activity_log.py for what is captured).

import frappe
from frappe.model.document import Document
from frappe.query_builder import Interval
from frappe.query_builder.functions import Now


class UserActivityLog(Document):
	@staticmethod
	def clear_old_logs(days=365):
		"""Retention: Log Settings > User Activity Log (default 365 days)."""
		table = frappe.qb.DocType("User Activity Log")
		frappe.db.delete(table, filters=(table.creation < (Now() - Interval(days=days))))
