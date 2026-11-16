# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

from frappe.model.document import Document
from frappe.utils import get_datetime


class RFIDSQLPunchLog(Document):
	def validate(self):
		self.set_punch_date_and_clock()

	def set_punch_date_and_clock(self):
		"""Split punch_time into separate Date and Time (with seconds) columns."""
		if not self.punch_time:
			self.punch_date = None
			self.punch_clock = None
			return
		dt = get_datetime(self.punch_time)
		self.punch_date = dt.date()
		self.punch_clock = dt.strftime("%H:%M:%S")
