# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

import io

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

MAX_EXCEL_ROWS = 500000


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


@frappe.whitelist()
def download_excel(filters=None):
	"""Excel of the punches matching the list / report view filters, newest first:
	Student Id, Student, Student Name, Punch Date, Punch Time (HH:MM:SS), Terminal / Location."""
	from openpyxl import Workbook
	from openpyxl.cell import WriteOnlyCell
	from openpyxl.styles import Alignment, Font, PatternFill

	filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or [])
	# get_list applies the user's read permission.
	rows = frappe.get_list(
		"RFID SQL Punch Log",
		filters=filters,
		fields=["emp_code", "student", "punch_time", "terminal_alias", "terminal_id"],
		order_by="punch_time desc, source_log_id desc",
		limit_page_length=MAX_EXCEL_ROWS + 1,
	)
	if len(rows) > MAX_EXCEL_ROWS:
		frappe.throw(_("More than {0} punches match these filters. Narrow the filters and try again.").format(MAX_EXCEL_ROWS))

	names = {}
	ids = sorted({r.student for r in rows if r.student})
	for i in range(0, len(ids), 1000):
		for s in frappe.get_all("Student Master", filters={"name": ["in", ids[i:i + 1000]]}, fields=["name", "first_name"]):
			names[s.name] = s.first_name or ""

	wb = Workbook(write_only=True)
	ws = wb.create_sheet(title="RFID SQL Punch Log")
	headers = [_("Student Id"), _("Student"), _("Student Name"), _("Punch Date"), _("Punch Time (HH:MM:SS)"),
	           _("Terminal / Location")]
	for idx, width in enumerate([18, 20, 30, 14, 22, 20], start=1):
		ws.column_dimensions[chr(64 + idx)].width = width
	ws.freeze_panes = "A2"

	center = Alignment(horizontal="center", vertical="center")
	head = []
	for h in headers:
		c = WriteOnlyCell(ws, value=h)
		c.font = Font(bold=True, color="FFFFFF")
		c.fill = PatternFill("solid", fgColor="2B2E4A")
		c.alignment = center
		head.append(c)
	ws.append(head)

	def cell(value, fmt=None, align=center):
		c = WriteOnlyCell(ws, value=value)
		if fmt:
			c.number_format = fmt
		c.alignment = align
		return c

	left = Alignment(horizontal="left", vertical="center")
	for r in rows:
		dt = get_datetime(r.punch_time) if r.punch_time else None
		ws.append([
			cell(r.emp_code or ""),
			cell(r.student or ""),
			cell(names.get(r.student, ""), align=left),
			cell(dt.date() if dt else None, "dd-mm-yyyy"),
			cell(dt.time().replace(microsecond=0) if dt else None, "hh:mm:ss"),
			cell(r.terminal_alias or r.terminal_id or ""),
		])

	buf = io.BytesIO()
	wb.save(buf)
	frappe.response.filename = "RFID_SQL_Punch_Log_{0}.xlsx".format(now_datetime().strftime("%Y-%m-%d_%H%M"))
	frappe.response.filecontent = buf.getvalue()
	frappe.response.type = "binary"
