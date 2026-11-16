# Copyright (c) 2025, Nishanth and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class AttendanceLog(Document):
	# Logs are converted into Student Attendance by the scheduled processor
	# (attendance_log.process_attendance_logs.process_pending_logs), which
	# matches each tap against the session's Time Table venue.
	pass
