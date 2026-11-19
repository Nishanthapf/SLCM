import frappe
from frappe import _
from frappe.utils import cint, flt, fmt_money, formatdate, getdate, today

ALLOWED_ROLES = ("System Manager", "Campus Admin", "Accounts Manager", "Accounts User")

# Demand-level aggregate per student. Cancelled demands never count toward dues.
_DEMAND_AGG = """
	SELECT
		student,
		COUNT(*)                                                         AS demand_count,
		SUM(net_payable)                                                 AS total_payable,
		SUM(paid_amount)                                                 AS paid_amount,
		SUM(waiver_amount)                                               AS waiver_amount,
		SUM(outstanding_amount)                                          AS outstanding_amount,
		SUM(CASE WHEN status = 'Overdue' THEN outstanding_amount ELSE 0 END) AS overdue_amount
	FROM `tabFee Demand`
	WHERE status != 'Cancelled' {component_condition}
	GROUP BY student
"""

# Excess = unused balance on active (submitted) credit notes.
_CREDIT_AGG = """
	SELECT student, SUM(available_credit) AS excess_amount
	FROM `tabStudent Credit Note`
	WHERE docstatus = 1 AND status = 'Active'
	GROUP BY student
"""


def _check_access():
	frappe.only_for(ALLOWED_ROLES)


REMARKS_MIN_LENGTH = 15


def _require_remarks(remarks, label=None):
	"""Remarks / reasons on every Student Due Details action: mandatory, at least REMARKS_MIN_LENGTH characters."""
	remarks = (remarks or "").strip()
	if len(remarks) < REMARKS_MIN_LENGTH:
		frappe.throw(
			_("{0} must be at least {1} characters (currently {2}).").format(
				label or _("Remarks"), REMARKS_MIN_LENGTH, len(remarks)
			)
		)
	return remarks


def _as_list(value):
	"""Accept a list, a JSON-encoded list, or a single plain value; drop blanks."""
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.lstrip().startswith("[") else [value]
	return [v for v in value if v not in (None, "")]


@frappe.whitelist()
def get_filter_options():
	"""Academic years, terms (with their year, for dependent filtering) and programmes present on students."""
	_check_access()

	years = frappe.db.sql_list(
		"""SELECT DISTINCT academic_year FROM `tabStudent Master`
		WHERE IFNULL(academic_year, '') != '' ORDER BY academic_year DESC"""
	)
	# Terms set up in Academic Term (a student no longer stores a term).
	terms = frappe.db.sql(
		"""SELECT academic_year, name AS academic_term FROM `tabAcademic Term`
		WHERE IFNULL(status, '') != 'Inactive'
		ORDER BY academic_term""",
		as_dict=True,
	)
	programmes = frappe.db.sql(
		"""SELECT DISTINCT sm.programme_of_study AS name, p.program_name
		FROM `tabStudent Master` sm
		LEFT JOIN `tabProgramme` p ON p.name = sm.programme_of_study
		WHERE IFNULL(sm.programme_of_study, '') != ''
		ORDER BY sm.programme_of_study""",
		as_dict=True,
	)
	fee_components = frappe.db.sql_list(
		"""SELECT DISTINCT fee_component FROM `tabFee Demand`
		WHERE status != 'Cancelled' AND IFNULL(fee_component, '') != '' ORDER BY fee_component"""
	)
	return {"academic_years": years, "terms": terms, "programmes": programmes, "fee_components": fee_components}


@frappe.whitelist()
def get_students(
	academic_year=None,
	academic_term=None,
	programme=None,
	dues_status=None,
	fee_component=None,
	search=None,
	start=0,
	page_length=50,
	sort_by=None,
	sort_order=None,
):
	"""Paginated student list with per-student fee totals, plus totals across the whole filtered set."""
	_check_access()

	base, values = _student_base(academic_year, academic_term, programme, dues_status, fee_component, search)

	totals = frappe.db.sql(
		f"""SELECT
			COUNT(*)                              AS student_count,
			SUM(IFNULL(fd.total_payable, 0))      AS total_payable,
			SUM(IFNULL(fd.paid_amount, 0))        AS paid_amount,
			SUM(IFNULL(fd.outstanding_amount, 0)) AS outstanding_amount,
			SUM(IFNULL(fd.overdue_amount, 0))     AS overdue_amount,
			SUM(IFNULL(cn.excess_amount, 0))      AS excess_amount
		{base}""",
		values,
		as_dict=True,
	)[0]

	values.update(start=cint(start), page_length=min(cint(page_length) or 50, 500))
	rows = frappe.db.sql(
		f"""SELECT
			sm.name AS student, sm.first_name AS student_name, sm.registration_id,
			sm.official_email_id, sm.email, sm.programme_of_study, sm.batch,
			sm.academic_year, NULL AS academic_term, sm.section, sm.student_status,
			IFNULL(fd.demand_count, 0)       AS demand_count,
			IFNULL(fd.total_payable, 0)      AS total_payable,
			IFNULL(fd.paid_amount, 0)        AS paid_amount,
			IFNULL(fd.waiver_amount, 0)      AS waiver_amount,
			IFNULL(fd.outstanding_amount, 0) AS outstanding_amount,
			IFNULL(fd.overdue_amount, 0)     AS overdue_amount,
			IFNULL(cn.excess_amount, 0)      AS excess_amount
		{base}
		ORDER BY {_order_by(sort_by, sort_order)}
		LIMIT %(start)s, %(page_length)s""",
		values,
		as_dict=True,
	)
	_attach_receipt_info(rows)

	return {"rows": rows, "totals": totals}


def _student_base(academic_year=None, academic_term=None, programme=None, dues_status=None, fee_component=None, search=None):
	"""FROM/WHERE clause (aliases sm, fd, cn) selecting the students the list filters match,
	plus its bind values. Shared by the student list and the reports so they always agree."""
	conditions = ["1=1"]
	values = {}
	# Each filter takes one or more values (multi-select); empty means "no filter".
	for param, column, key in (
		(academic_year, "sm.academic_year", "academic_year"),
		(programme, "sm.programme_of_study", "programme"),
	):
		selected = _as_list(param)
		if selected:
			conditions.append(f"{column} IN %({key})s")
			values[key] = tuple(selected)
	# A student no longer stores a term: a Term filter matches students in the term's academic year.
	selected_terms = _as_list(academic_term)
	if selected_terms:
		conditions.append(
			"sm.academic_year IN (SELECT at.academic_year FROM `tabAcademic Term` at"
			" WHERE at.name IN %(academic_term)s)"
		)
		values["academic_term"] = tuple(selected_terms)
	if search:
		conditions.append(
			"(sm.name LIKE %(search)s OR sm.first_name LIKE %(search)s "
			"OR sm.registration_id LIKE %(search)s OR sm.application_number LIKE %(search)s "
			# a student's address may be in any of the three email fields
			"OR sm.official_email_id LIKE %(search)s OR sm.email LIKE %(search)s OR sm.personal_email LIKE %(search)s)"
		)
		values["search"] = f"%{search.strip()}%"

	status_conditions = {
		"pending": "IFNULL(fd.outstanding_amount, 0) > 0",
		"overdue": "IFNULL(fd.overdue_amount, 0) > 0",
		"cleared": "IFNULL(fd.demand_count, 0) > 0 AND IFNULL(fd.outstanding_amount, 0) = 0",
		"excess": "IFNULL(cn.excess_amount, 0) > 0",
		"no_demands": "IFNULL(fd.demand_count, 0) = 0",
	}
	# Several statuses → a student matching any of them is included.
	chosen = [status_conditions[k] for k in _as_list(dues_status) if k in status_conditions]
	if chosen:
		conditions.append("(" + " OR ".join(f"({c})" for c in chosen) + ")")

	# Fee Component: only students with dues for these components, and every amount counts only them
	components = _as_list(fee_component)
	component_condition = ""
	if components:
		component_condition = "AND fee_component IN %(fee_component)s"
		values["fee_component"] = tuple(components)
		conditions.append("IFNULL(fd.demand_count, 0) > 0")
	demand_agg = _DEMAND_AGG.format(component_condition=component_condition)

	base = f"""
		FROM `tabStudent Master` sm
		LEFT JOIN ({demand_agg}) fd ON fd.student = sm.name
		LEFT JOIN ({_CREDIT_AGG}) cn ON cn.student = sm.name
		WHERE {" AND ".join(conditions)}
	"""
	return base, values


# Sortable columns → SQL expressions. Only these keys are accepted, so sort input never reaches SQL raw.
_SORT_COLUMNS = {
	"student": ["sm.first_name"],
	"programme": ["sm.programme_of_study"],
	"year_term": ["sm.academic_year"],
	"batch": ["sm.batch"],
	"demand_count": ["IFNULL(fd.demand_count, 0)"],
	"total_payable": ["IFNULL(fd.total_payable, 0)"],
	"paid_amount": ["IFNULL(fd.paid_amount, 0)"],
	"outstanding_amount": ["IFNULL(fd.outstanding_amount, 0)"],
	"excess_amount": ["IFNULL(cn.excess_amount, 0)"],
	# Same precedence as the list's status badge: Overdue > Pending > Cleared > No Demands
	"status": [
		"""CASE WHEN IFNULL(fd.demand_count, 0) = 0 THEN 0
			WHEN IFNULL(fd.overdue_amount, 0) > 0 THEN 3
			WHEN IFNULL(fd.outstanding_amount, 0) > 0 THEN 2
			ELSE 1 END"""
	],
}


def _order_by(sort_by, sort_order):
	if sort_by not in _SORT_COLUMNS:
		return "IFNULL(fd.outstanding_amount, 0) DESC, sm.first_name ASC, sm.name ASC"
	direction = "ASC" if (sort_order or "").lower() == "asc" else "DESC"
	return ", ".join(f"{col} {direction}" for col in _SORT_COLUMNS[sort_by]) + ", sm.name ASC"


def _attach_receipt_info(rows):
	"""Add receipt_count and latest_receipt (active Fee Receipts) to each student row on the page."""
	if not rows:
		return
	receipts = frappe.get_all(
		"Fee Receipt",
		filters={"student": ["in", [r.student for r in rows]], "status": ["!=", "Cancelled"]},
		fields=["name", "student"],
		order_by="receipt_date desc, creation desc",
	)
	by_student = {}
	for rc in receipts:
		by_student.setdefault(rc.student, []).append(rc.name)
	for r in rows:
		names = by_student.get(r.student, [])
		r["receipt_count"] = len(names)
		r["latest_receipt"] = names[0] if names else None


@frappe.whitelist()
def get_student_receipts(student):
	"""Active Fee Receipts for one student, newest first, with the demands each one settled."""
	_check_access()

	receipts = frappe.get_all(
		"Fee Receipt",
		filters={"student": student, "status": ["!=", "Cancelled"]},
		fields=["name", "receipt_date", "amount", "payment_mode", "reference_number", "fee_payment"],
		order_by="receipt_date desc, creation desc",
	)
	if receipts:
		paid = frappe.get_all(
			"Fee Receipt Demands Paid",
			filters={"parent": ["in", [r.name for r in receipts]], "parenttype": "Fee Receipt"},
			fields=["parent", "fee_demand", "description"],
			order_by="idx asc",
		)
		by_parent = {}
		for row in paid:
			by_parent.setdefault(row.parent, []).append(row.description or row.fee_demand)
		for r in receipts:
			r["demands"] = by_parent.get(r.name, [])
	return receipts


@frappe.whitelist()
def download_receipt(receipt):
	"""
	PDF for a Fee Receipt, rendered exactly as staff print it today: the linked Fee Payment in the
	"Fee Payment Receipt - Admin Copy" format (the Fee Payment form's Print Receipt → Admin Copy).
	Receipts with no linked Fee Payment fall back to the student portal's orphan-receipt layout.
	Access is gated by this page's roles, since Accounts roles lack read on Fee Receipt / Fee Payment.
	"""
	_check_access()
	pdf = _receipt_pdf(receipt)
	frappe.local.response.filename = "{0}.pdf".format(receipt.replace(" ", "-").replace("/", "-"))
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"


def _receipt_pdf(receipt):
	"""The Fee Receipt PDF that download_receipt serves (callers check access)."""
	row = frappe.db.get_value("Fee Receipt", receipt, ["status", "fee_payment"], as_dict=True)
	if not row:
		frappe.throw(_("Receipt {0} not found.").format(receipt))
	if row.status == "Cancelled":
		frappe.throw(_("Receipt {0} has been cancelled.").format(receipt))

	fee_payment = row.fee_payment or frappe.db.get_value("Fee Payment", {"receipt": receipt}, "name")
	if fee_payment:
		frappe.flags.ignore_print_permissions = True
		try:
			pdf = frappe.get_print(
				"Fee Payment", fee_payment, "Fee Payment Receipt - Admin Copy", as_pdf=True, no_letterhead=0
			)
		finally:
			frappe.flags.ignore_print_permissions = False
	else:
		from slcm.api.student_portal import _generate_orphan_receipt_pdf

		pdf = _generate_orphan_receipt_pdf(receipt)
	return pdf


@frappe.whitelist()
def download_receipts_zip(student, receipts):
	"""One ZIP of the student's receipts (the selected dues' receipts on Manage Dues).
	receipts: JSON list of Fee Receipt names; each must belong to the student. Cancelled
	receipts are skipped; a receipt that fails to render is listed in errors.txt."""
	import io
	import json
	import zipfile

	_check_access()
	names = list(dict.fromkeys(json.loads(receipts) if isinstance(receipts, str) else receipts or []))
	if not names:
		frappe.throw(_("No receipts to download."))
	rows = {
		r.name: r
		for r in frappe.get_all(
			"Fee Receipt", filters={"name": ["in", names]}, fields=["name", "student", "status"]
		)
	}
	buffer, errors, added = io.BytesIO(), [], 0
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
		for name in names:
			row = rows.get(name)
			if not row or row.student != student:
				errors.append(f"{name}: not a receipt of this student")
				continue
			if row.status == "Cancelled":
				continue
			try:
				zf.writestr("{0}.pdf".format(name.replace(" ", "-").replace("/", "-")), _receipt_pdf(name))
				added += 1
			except Exception as e:
				frappe.clear_messages()
				errors.append(f"{name}: {frappe.utils.strip_html(str(e))}")
		if errors:
			zf.writestr("errors.txt", "\n".join(errors))
	if not added:
		frappe.throw(_("None of the selected receipts could be downloaded.") + ("<br>" + "<br>".join(errors) if errors else ""))
	reg = frappe.db.get_value("Student Master", student, "registration_id") or student
	frappe.local.response.filename = f"Receipts-{reg}.zip".replace(" ", "-").replace("/", "-")
	frappe.local.response.filecontent = buffer.getvalue()
	frappe.local.response.type = "download"


@frappe.whitelist()
def export_student_dues(student, demands, view=None):
	"""Excel (.xlsx) of the student's dues as shown on Manage Dues (the current filter, or the selected rows).
	demands: JSON list of Fee Demand names in on-screen order; each must belong to the student.
	view: short text describing what was exported (e.g. "Pending · Tuition Fee"), printed above the table."""
	import io
	import json

	from openpyxl import Workbook
	from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
	from openpyxl.utils import get_column_letter

	_check_access()
	if not frappe.db.exists("Student Master", student):
		frappe.throw(_("Student {0} not found.").format(student))
	names = list(dict.fromkeys(json.loads(demands) if isinstance(demands, str) else demands or []))
	if not names:
		frappe.throw(_("There are no dues to export."))

	rows = {
		d.name: d
		for d in frappe.get_all(
			"Fee Demand",
			filters={"name": ["in", names], "student": student},
			fields=[
				"name", "demand_type", "fee_component", "description", "status", "demand_date", "due_date",
				"creation", "academic_year", "original_amount", "penalty_amount", "waiver_amount", "net_payable",
				"paid_amount", "credit_adjusted", "outstanding_amount", "moved_to_excess_amount", "remarks",
			],
		)
	}
	ordered = [rows[n] for n in names if n in rows]  # names of another student are dropped
	if not ordered:
		frappe.throw(_("None of the selected dues belong to this student."))

	receipts = {}
	for r in frappe.db.sql(
		"""SELECT rdp.fee_demand, fr.name
		FROM `tabFee Receipt Demands Paid` rdp
		JOIN `tabFee Receipt` fr ON fr.name = rdp.parent AND rdp.parenttype = 'Fee Receipt'
		WHERE fr.student = %s AND IFNULL(fr.status, '') != 'Cancelled'
		ORDER BY fr.receipt_date, fr.creation""",
		student,
		as_dict=True,
	):
		receipts.setdefault(r.fee_demand, [])
		if r.name not in receipts[r.fee_demand]:
			receipts[r.fee_demand].append(r.name)

	sm = frappe.db.get_value(
		"Student Master", student, ["first_name", "registration_id", "programme_of_study"], as_dict=True
	)
	programme = (
		frappe.db.get_value("Programme", sm.programme_of_study, "program_name") or sm.programme_of_study
		if sm.programme_of_study
		else ""
	)

	def status_of(d):
		# Same rule as sfm_demand_status on the page
		if d.status == "Cancelled" and flt(d.moved_to_excess_amount) > 0:
			return "Cancelled & Moved to Excess"
		return d.status or ""

	columns = [
		# (header, width, value, is_amount)
		("Sl No.", 7, None, False),
		("Fee Component", 28, lambda d: d.fee_component or "", False),
		("Demand Type", 16, lambda d: d.demand_type or "", False),
		("Academic Year", 15, lambda d: d.academic_year or "", False),
		("Voucher No.", 17, lambda d: d.name, False),
		("Due Status", 18, status_of, False),
		("Date of Creation", 15, lambda d: getdate(d.demand_date or d.creation), False),
		("Due Date", 12, lambda d: getdate(d.due_date) if d.due_date else None, False),
		("Total Fee Payable", 16, lambda d: flt(d.original_amount, 2), True),
		("Penalty", 12, lambda d: flt(d.penalty_amount, 2), True),
		("Scholarship / Waiver", 18, lambda d: flt(d.waiver_amount, 2), True),
		("Net Fee Payable", 16, lambda d: flt(d.net_payable, 2), True),
		("Paid Amount", 15, lambda d: flt(flt(d.paid_amount) + flt(d.credit_adjusted), 2), True),
		("Pending Amount", 15, lambda d: flt(d.outstanding_amount, 2), True),
		("Remark", 40, lambda d: d.remarks or d.description or "", False),
		("Receipt No(s).", 24, lambda d: ", ".join(receipts.get(d.name, [])), False),
	]
	n_cols = len(columns)
	money_fmt = "#,##0.00"
	bold = Font(bold=True)
	thin = Side(style="thin", color="BFBFBF")
	border = Border(left=thin, right=thin, top=thin, bottom=thin)
	head_fill = PatternFill("solid", fgColor="920C24")

	wb = Workbook()
	ws = wb.active
	ws.title = "Dues"

	ws.append(["Student Due Details"])
	ws["A1"].font = Font(bold=True, size=14, color="920C24")
	info = [
		("Student", f"{sm.first_name or ''} ({student})".strip()),
		("Registration ID", sm.registration_id or "—"),
		("Programme", programme or "—"),
		("Showing", (view or "All dues").strip()[:140]),
		("Exported on", frappe.utils.format_datetime(frappe.utils.now_datetime(), "dd-MM-yyyy hh:mm a")),
	]
	# One cell per line ("Label: value"), so it spills over the empty cells beside it instead of being cut off
	# by the narrow Sl No. column.
	for label, value in info:
		ws.append([f"{label}: {value}"])
	ws.append([])

	ws.append([c[0] for c in columns])
	header_row = ws.max_row  # read after appending: an empty append() above does not move max_row
	for i in range(1, n_cols + 1):
		cell = ws.cell(row=header_row, column=i)
		cell.font = Font(bold=True, color="FFFFFF")
		cell.fill = head_fill
		cell.border = border
		cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
	ws.row_dimensions[header_row].height = 30

	for idx, d in enumerate(ordered, 1):
		ws.append([idx] + [c[2](d) for c in columns[1:]])
		r = ws.max_row
		for i, c in enumerate(columns, 1):
			cell = ws.cell(row=r, column=i)
			cell.border = border
			cell.alignment = Alignment(vertical="top", wrap_text=(c[0] == "Remark"))
			if c[3]:
				cell.number_format = money_fmt
			elif c[0] in ("Due Date", "Date of Creation"):
				cell.number_format = "DD-MM-YYYY"

	first, last = header_row + 1, ws.max_row
	total = ["Total"] + [""] * (n_cols - 1)
	ws.append(total)
	tr = ws.max_row
	for i, c in enumerate(columns, 1):
		cell = ws.cell(row=tr, column=i)
		cell.font = bold
		cell.border = Border(top=Side(style="medium"), bottom=Side(style="double"))
		if c[3]:
			col = get_column_letter(i)
			cell.value = f"=SUM({col}{first}:{col}{last})"
			cell.number_format = money_fmt

	for i, c in enumerate(columns, 1):
		ws.column_dimensions[get_column_letter(i)].width = c[1]
	ws.freeze_panes = ws.cell(row=header_row + 1, column=3)
	ws.auto_filter.ref = f"A{header_row}:{get_column_letter(n_cols)}{last}"
	ws.page_setup.orientation = "landscape"
	ws.page_setup.fitToWidth = 1
	ws.page_setup.fitToHeight = 0
	ws.sheet_properties.pageSetUpPr.fitToPage = True
	ws.print_title_rows = f"{header_row}:{header_row}"

	buffer = io.BytesIO()
	wb.save(buffer)
	reg = sm.registration_id or student
	frappe.local.response.filename = f"Dues-{reg}-{frappe.utils.today()}.xlsx".replace(" ", "-").replace("/", "-")
	frappe.local.response.filecontent = buffer.getvalue()
	frappe.local.response.type = "download"


@frappe.whitelist()
def get_student_dues(student):
	"""Everything the student detail view needs: profile, summary, demands, payments, credits, refunds."""
	_check_access()

	if not frappe.db.exists("Student Master", student):
		frappe.throw(_("Student {0} not found.").format(student))

	profile = frappe.db.get_value(
		"Student Master",
		student,
		[
			"name", "first_name", "registration_id", "official_email_id", "email", "phone",
			"programme_of_study", "batch", "academic_year", "section",
			"student_status", "passport_size_photo",
			"applying_scholarship", "scholarship_type", "scholarship_amount", "scholarship_percentage",
			"scholarship_approval_date", "fee_waiver_remarks",
		],
		as_dict=True,
	)
	if profile.programme_of_study:
		profile.update(
			frappe.db.get_value(
				"Programme", profile.programme_of_study, ["program_name"], as_dict=True
			)
			or {}
		)

	demands = frappe.get_all(
		"Fee Demand",
		filters={"student": student},
		fields=[
			"name", "demand_type", "fee_component", "description", "status",
			"demand_date", "due_date", "creation", "academic_year",
			"original_amount", "penalty_amount", "waiver_amount", "net_payable",
			"paid_amount", "credit_adjusted", "outstanding_amount", "refunded_amount", "moved_to_excess_amount",
			"is_refundable", "last_payment_date", "remarks",
		],
		order_by="demand_date desc, creation desc",
	)

	# Receipts that settled each demand (a receipt can cover several demands, a demand several receipts)
	receipt_rows = frappe.db.sql(
		"""SELECT rdp.fee_demand, fr.name, fr.receipt_date, fr.payment_mode, rdp.amount
		FROM `tabFee Receipt Demands Paid` rdp
		JOIN `tabFee Receipt` fr ON fr.name = rdp.parent AND rdp.parenttype = 'Fee Receipt'
		WHERE fr.student = %s AND IFNULL(fr.status, '') != 'Cancelled'
		ORDER BY fr.receipt_date DESC, fr.creation DESC""",
		student,
		as_dict=True,
	)
	by_demand = {}
	for r in receipt_rows:
		by_demand.setdefault(r.pop("fee_demand"), []).append(r)
	for d in demands:
		d["receipts"] = by_demand.get(d.name, [])

	payments = frappe.get_all(
		"Fee Payment",
		filters={"student": student},
		fields=[
			"name", "payment_date", "payment_mode", "amount", "reference_number", "payment_gateway",
			"settlement_date", "status", "docstatus", "receipt", "remarks", "university_bank_account",
		],
		order_by="payment_date desc, creation desc",
	)
	if payments:
		rows = frappe.get_all(
			"Fee Payment Demand Row",
			filters={"parent": ["in", [p.name for p in payments]], "parenttype": "Fee Payment"},
			fields=["parent", "fee_demand", "demand_description", "amount_allocated"],
			order_by="idx asc",
		)
		by_parent = {}
		for r in rows:
			by_parent.setdefault(r.parent, []).append(r)
		for p in payments:
			p["allocations"] = by_parent.get(p.name, [])

	credit_notes = frappe.get_all(
		"Student Credit Note",
		filters={"student": student, "docstatus": 1},
		fields=[
			"name", "credit_type", "academic_year", "credit_amount", "available_credit",
			"used_credit", "status", "source_receipt", "remarks", "creation",
		],
		order_by="creation desc",
	)
	if credit_notes:
		adjustments = frappe.get_all(
			"Credit Adjustment Row",
			filters={"parent": ["in", [c.name for c in credit_notes]], "parenttype": "Student Credit Note"},
			fields=["parent", "fee_demand", "fee_component", "amount_adjusted", "adjusted_on", "adjusted_by"],
			order_by="idx asc",
		)
		by_parent = {}
		for a in adjustments:
			by_parent.setdefault(a.parent, []).append(a)
		for c in credit_notes:
			c["adjustments"] = by_parent.get(c.name, [])

	refunds = frappe.get_all(
		"Fee Refund",
		filters={"student": student},
		fields=[
			"name", "refund_source", "fee_demand", "fee_component", "refund_type", "refund_amount",
			"refund_date", "refund_mode", "utr_number", "status", "docstatus", "reason",
		],
		order_by="refund_date desc, creation desc",
	)

	concessions = frappe.get_all(
		"Fee Concession",
		filters={"student": student, "docstatus": ["!=", 2]},
		fields=[
			"name", "fee_demand", "fee_component", "concession_type", "concession_date",
			"waiver_value", "waiver_amount", "status", "docstatus", "reason", "approved_on", "creation",
		],
		order_by="creation desc",
	)
	stipends = frappe.get_all(
		"Stipend Payment",
		filters={"student": student, "docstatus": ["!=", 2]},
		fields=[
			"name", "stipend_type", "academic_year", "academic_term", "payment_date", "payment_mode",
			"amount", "reference_number", "status", "docstatus", "remarks",
		],
		order_by="payment_date desc, creation desc",
	)

	active = [d for d in demands if d.status != "Cancelled"]
	summary = {
		"total_payable": sum(flt(d.net_payable) for d in active),
		"paid_amount": sum(flt(d.paid_amount) for d in active),
		"waiver_amount": sum(flt(d.waiver_amount) for d in active),
		"penalty_amount": sum(flt(d.penalty_amount) for d in active),
		"pending_amount": sum(flt(d.outstanding_amount) for d in active),
		"overdue_amount": sum(flt(d.outstanding_amount) for d in active if d.status == "Overdue"),
		"excess_amount": sum(
			flt(c.available_credit) for c in credit_notes if c.status == "Active"
		),
		"refunded_amount": sum(flt(r.refund_amount) for r in refunds if r.docstatus == 1),
		"scholarship_amount": sum(flt(c.waiver_amount) for c in concessions if c.status == "Approved"),
		"stipend_paid": sum(flt(x.amount) for x in stipends if x.docstatus == 1),
	}

	return {
		"profile": profile,
		"summary": summary,
		"demands": demands,
		"payments": payments,
		"credit_notes": credit_notes,
		"refunds": refunds,
		"concessions": concessions,
		"stipends": stipends,
	}


def _payment_details(payment_mode, payment_date, reference_number, university_bank_account, settlement_date, remarks):
	"""Validated header fields shared by Record Payment and Edit Payment."""
	remarks = _require_remarks(remarks)
	reference_number = (reference_number or "").strip()
	if not payment_mode:
		frappe.throw(_("Payment Mode is mandatory."))
	if payment_mode == "Online Payment":
		frappe.throw(_("Online payments are recorded by the payment gateway. Choose the mode the money was received in."))
	if not reference_number:
		frappe.throw(_("Reference / UTR No. is mandatory."))
	if not university_bank_account:
		frappe.throw(_("University bank account is mandatory."))
	if not payment_date:
		frappe.throw(_("Payment Date is mandatory."))
	if not settlement_date:
		frappe.throw(_("Settlement Date is mandatory."))
	if getdate(settlement_date) < getdate(payment_date):
		frappe.throw(
			_("Settlement Date ({0}) cannot be before the Payment Date ({1}).").format(
				formatdate(settlement_date), formatdate(payment_date)
			)
		)
	return frappe._dict(
		payment_mode=payment_mode,
		payment_date=payment_date,
		settlement_date=settlement_date,
		reference_number=reference_number,
		university_bank_account=university_bank_account,
		remarks=remarks,
	)


def _submit_payment(student, allocations, details, amended_from=None):
	"""Build, insert and submit one Fee Payment against the student's demands (allocations: list of
	{"fee_demand", "amount"}). Submitting runs the Fee Payment pipeline (demand status, receipt, ERPNext)."""
	allocations = frappe.parse_json(allocations) or []
	allocations = [a for a in allocations if flt(a.get("amount")) > 0]
	if not allocations:
		frappe.throw(_("Enter an amount for at least one demand."))
	if len({a["fee_demand"] for a in allocations}) != len(allocations):
		frappe.throw(_("A due appears more than once in this payment."))

	demand_names = [a["fee_demand"] for a in allocations]
	demands = {
		d.name: d
		for d in frappe.get_all(
			"Fee Demand",
			filters={"name": ["in", demand_names]},
			fields=["name", "student", "description", "fee_component", "outstanding_amount", "status"],
		)
	}
	for a in allocations:
		d = demands.get(a["fee_demand"])
		if not d or d.student != student:
			frappe.throw(_("Fee Demand {0} does not belong to this student.").format(a["fee_demand"]))
		if d.status in ("Paid", "Cancelled", "Waived"):
			frappe.throw(_("Fee Demand {0} is {1} and cannot take a payment.").format(d.name, d.status))
		if flt(a["amount"]) > flt(d.outstanding_amount) + 0.005:
			frappe.throw(
				_("Amount for {0} ({1}) exceeds its pending amount ({2}).").format(
					d.name,
					frappe.utils.fmt_money(a["amount"], currency="INR"),
					frappe.utils.fmt_money(d.outstanding_amount, currency="INR"),
				)
			)

	payment = frappe.new_doc("Fee Payment")
	payment.student = student
	payment.update(details)
	payment.amended_from = amended_from
	payment.amount = sum(flt(a["amount"]) for a in allocations)
	for a in allocations:
		d = demands[a["fee_demand"]]
		payment.append("payment_demands", {
			"fee_demand": d.name,
			"demand_description": d.description or d.fee_component,
			"outstanding_amount": d.outstanding_amount,
			"amount_allocated": flt(a["amount"]),
		})
	payment.flags.ignore_permissions = bool(amended_from)
	payment.insert()
	payment.submit()
	return payment


@frappe.whitelist()
def record_payment(
	student,
	allocations,
	payment_mode,
	payment_date=None,
	reference_number=None,
	remarks=None,
	university_bank_account=None,
	settlement_date=None,
):
	"""
	Record one offline Fee Payment against one or more of a student's demands and submit it.
	allocations: JSON list of {"fee_demand": ..., "amount": ...}.
	"""
	_check_access()
	details = _payment_details(
		payment_mode, payment_date, reference_number, university_bank_account, settlement_date, remarks
	)
	payment = _submit_payment(student, allocations, details)
	return {"payment": payment.name, "receipt": payment.receipt}


def _editable_payment(payment, student):
	"""The submitted offline Fee Payment, if it can still be edited or deleted; throws otherwise."""
	if not frappe.db.exists("Fee Payment", payment):
		frappe.throw(_("Fee Payment {0} was not found.").format(payment))
	doc = frappe.get_doc("Fee Payment", payment)
	if doc.student != student:
		frappe.throw(_("Fee Payment {0} does not belong to this student.").format(payment))
	if doc.docstatus != 1:
		frappe.throw(_("Fee Payment {0} is not active (it is {1}).").format(payment, doc.status or _("a draft")))
	if not doc.is_offline():
		frappe.throw(
			_("{0} is an online (gateway) payment. Only offline payments can be edited or deleted here.").format(payment)
		)
	for row in doc.payment_demands:
		d = frappe.db.get_value(
			"Fee Demand", row.fee_demand, ["refunded_amount", "moved_to_excess_amount"], as_dict=True
		) or {}
		if flt(d.get("refunded_amount")) > 0 or flt(d.get("moved_to_excess_amount")) > 0:
			frappe.throw(
				_("Money paid on {0} has been refunded or moved to excess, so {1} can no longer be edited or deleted.").format(
					row.fee_demand, payment
				)
			)
	if doc.receipt and frappe.db.exists("Student Credit Note", {"source_receipt": doc.receipt, "docstatus": 1}):
		frappe.throw(_("A credit note was raised from receipt {0}, so {1} can no longer be edited or deleted.").format(doc.receipt, payment))
	return doc


def _cancel_payment(doc, remarks):
	doc.add_comment("Comment", _("Cancelled from Student Due Details: {0}").format(remarks))
	doc.flags.ignore_permissions = True
	doc.cancel()


@frappe.whitelist()
def edit_payment(
	student,
	payment,
	allocations,
	payment_mode,
	payment_date=None,
	reference_number=None,
	remarks=None,
	university_bank_account=None,
	settlement_date=None,
):
	"""Correct an offline payment: it is cancelled (dues, receipt and ERPNext entry reversed) and an amended
	Fee Payment (FP-xxxx-1) is submitted in its place, all in one transaction - any error leaves the original."""
	_check_access()
	doc = _editable_payment(payment, student)
	details = _payment_details(
		payment_mode, payment_date, reference_number, university_bank_account, settlement_date, remarks
	)
	allocations = frappe.parse_json(allocations) or []
	own = {r.fee_demand: flt(r.amount_allocated) for r in doc.payment_demands}
	for a in allocations:
		name = a.get("fee_demand")
		if name not in own:
			frappe.throw(_("Fee Demand {0} is not part of {1}.").format(name, payment))
		# what the due can take once this payment is reversed
		limit = flt(frappe.db.get_value("Fee Demand", name, "outstanding_amount")) + own[name]
		if flt(a.get("amount")) < 0 or flt(a.get("amount")) > limit + 0.005:
			frappe.throw(
				_("Amount for {0} must be between 0 and {1}.").format(name, frappe.utils.fmt_money(limit, currency="INR"))
			)
	if not any(flt(a.get("amount")) > 0 for a in allocations):
		frappe.throw(_("Enter an amount for at least one demand."))

	# cancel + re-record succeed together or not at all
	frappe.db.savepoint("sfm_edit_payment")
	try:
		_cancel_payment(doc, details.remarks)
		new = _submit_payment(student, allocations, details, amended_from=doc.name)
	except Exception:
		frappe.db.rollback(save_point="sfm_edit_payment")
		raise
	return {"payment": new.name, "receipt": new.receipt, "old_payment": doc.name}


@frappe.whitelist()
def delete_payment(student, payment, remarks=None):
	"""Delete an offline payment: it is cancelled, which re-opens the dues it paid, cancels its receipt and
	reverses its ERPNext entry. The cancelled record stays for the audit trail."""
	_check_access()
	remarks = _require_remarks(remarks)
	doc = _editable_payment(payment, student)
	_cancel_payment(doc, remarks)
	return {"payment": doc.name}


@frappe.whitelist()
def apply_excess_credit(student, fee_demand, amount, remarks=None):
	"""Adjust a student's excess (active credit notes, oldest first) against one demand."""
	_check_access()
	remarks = _require_remarks(remarks)

	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero."))

	demand = frappe.db.get_value(
		"Fee Demand", fee_demand, ["student", "outstanding_amount", "status"], as_dict=True
	)
	if not demand or demand.student != student:
		frappe.throw(_("Fee Demand {0} does not belong to this student.").format(fee_demand))
	if demand.status in ("Paid", "Cancelled", "Waived"):
		frappe.throw(_("Fee Demand {0} is {1}.").format(fee_demand, demand.status))
	if amount > flt(demand.outstanding_amount):
		frappe.throw(
			_("Amount ({0}) exceeds the outstanding amount ({1}).").format(
				frappe.utils.fmt_money(amount, currency="INR"),
				frappe.utils.fmt_money(demand.outstanding_amount, currency="INR"),
			)
		)

	notes = frappe.get_all(
		"Student Credit Note",
		filters={"student": student, "docstatus": 1, "status": "Active", "available_credit": [">", 0]},
		fields=["name", "available_credit"],
		order_by="creation asc",
	)
	if amount > sum(flt(n.available_credit) for n in notes):
		frappe.throw(_("Amount exceeds the student's available excess."))

	remaining = amount
	used = []
	for n in notes:
		if remaining <= 0:
			break
		take = min(remaining, flt(n.available_credit))
		frappe.get_doc("Student Credit Note", n.name).apply_credit(fee_demand, take)
		used.append(n.name)
		remaining -= take

	frappe.get_doc("Fee Demand", fee_demand).add_comment(
		"Comment",
		_("Adjusted {0} from excess ({1}). Remarks: {2}").format(
			frappe.utils.fmt_money(amount, currency="INR"), ", ".join(used), frappe.utils.escape_html(remarks)
		),
	)
	return {"credit_notes": used}


@frappe.whitelist()
def create_due(
	student,
	fee_component,
	demand_date,
	due_date,
	original_amount,
	penalty_amount=0,
	waiver_amount=0,
	academic_year=None,
	is_refundable=0,
	remarks=None,
):
	"""Create a Fee Demand for the student from Student Due Details (normal Fee Demand permissions apply).
	The description comes from the fee component (Fee Demand fills it in)."""
	_check_access()
	remarks = _require_remarks(remarks)
	original_amount, penalty_amount, waiver_amount = flt(original_amount), flt(penalty_amount), flt(waiver_amount)
	if original_amount <= 0:
		frappe.throw(_("Amount must be greater than zero."))
	if penalty_amount < 0 or waiver_amount < 0:
		frappe.throw(_("Penalty and Scholarship / Waiver cannot be negative."))
	if waiver_amount > original_amount:
		frappe.throw(_("Scholarship / Waiver cannot exceed the amount."))
	if not (demand_date and due_date):
		frappe.throw(_("Date of Creation and Due Date are mandatory."))
	if getdate(due_date) <= getdate(demand_date):
		frappe.throw(
			_("Due Date ({0}) must be after the Date of Creation ({1}).").format(formatdate(due_date), formatdate(demand_date))
		)
	sm = frappe.db.get_value("Student Master", student, ["programme_of_study", "batch"], as_dict=True)
	if not sm:
		frappe.throw(_("Student {0} not found.").format(student))

	doc = frappe.new_doc("Fee Demand")
	doc.update({
		"student": student,
		"program": sm.programme_of_study,
		"programme": sm.batch,
		"fee_component": fee_component,
		"academic_year": academic_year,
		"demand_date": demand_date,
		"due_date": due_date,
		"original_amount": original_amount,
		"penalty_amount": penalty_amount,
		"waiver_amount": waiver_amount,
		"is_refundable": cint(is_refundable),
		"remarks": remarks,
	})
	doc.insert()
	return {"fee_demand": doc.name}


@frappe.whitelist()
def cancel_demand(fee_demand, remarks=None):
	_check_access()
	remarks = _require_remarks(remarks)
	demand = frappe.get_doc("Fee Demand", fee_demand)
	result = demand.cancel_demand()
	demand.add_comment("Comment", _("Due cancelled. Remarks: {0}").format(frappe.utils.escape_html(remarks)))
	return result


@frappe.whitelist()
def move_to_excess(student, fee_demand, amount, credit_type, remarks=None, academic_year=None, cancel_due=0):
	"""
	Move money already paid against a due into the student's excess.

	The amount comes off the due's paid amount (the due's outstanding/status recalculate through the
	standard Fee Demand logic, same as a refund) and a submitted Student Credit Note is created for it,
	so it shows under Excess and can later be adjusted against other dues or refunded.
	Optionally cancels the due when its whole paid amount has been moved.
	"""
	_check_access()
	remarks = _require_remarks(remarks)
	amount = flt(amount)
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero."))

	demand = frappe.get_doc("Fee Demand", fee_demand)
	if demand.student != student:
		frappe.throw(_("Fee Demand {0} does not belong to this student.").format(fee_demand))
	if demand.status == "Cancelled":
		frappe.throw(_("Fee Demand {0} is cancelled.").format(fee_demand))
	if amount > flt(demand.paid_amount):
		frappe.throw(
			_("Amount ({0}) exceeds the amount paid on {1} ({2}).").format(
				frappe.utils.fmt_money(amount, currency="INR"),
				fee_demand,
				frappe.utils.fmt_money(demand.paid_amount, currency="INR"),
			)
		)
	if cint(cancel_due) and amount < flt(demand.paid_amount):
		frappe.throw(_("A due can only be cancelled when its whole paid amount is moved to excess."))

	source_receipt = frappe.db.sql(
		"""SELECT fr.name FROM `tabFee Receipt Demands Paid` rdp
		JOIN `tabFee Receipt` fr ON fr.name = rdp.parent AND rdp.parenttype = 'Fee Receipt'
		WHERE rdp.fee_demand = %s AND IFNULL(fr.status, '') != 'Cancelled'
		ORDER BY fr.receipt_date DESC, fr.creation DESC LIMIT 1""",
		fee_demand,
	)

	demand.update_payment_status(paid_delta=-amount)

	note = frappe.new_doc("Student Credit Note")
	note.student = student
	note.credit_type = credit_type
	note.academic_year = academic_year or demand.academic_year
	note.credit_amount = amount
	note.source_receipt = source_receipt[0][0] if source_receipt else None
	note.source_fee_demand = fee_demand
	note.remarks = _("Moved from due {0} ({1}). {2}").format(
		fee_demand, demand.fee_component or demand.description or "", remarks
	)
	note.insert()
	note.submit()

	# Status: "Moved to Excess", or Cancelled (shown as "Cancelled & Moved to Excess" via moved_to_excess_amount)
	demand.reload()
	moved_total = flt(demand.moved_to_excess_amount) + amount
	if cint(cancel_due):
		demand.cancel_demand()
		demand.db_set("moved_to_excess_amount", moved_total)
	else:
		demand.db_set({"moved_to_excess_amount": moved_total, "status": "Moved to Excess"})

	demand.add_comment(
		"Comment",
		_("{0} moved to excess as {1}. Remarks: {2}").format(
			frappe.utils.fmt_money(amount, currency="INR"), note.name, frappe.utils.escape_html(remarks)
		),
	)
	return {"credit_note": note.name}


def _submit_stipend(student, values, amended_from=None):
	"""Create and submit a Stipend Payment from the dialog values."""
	remarks = _require_remarks(values.get("remarks"))
	amount = flt(values.get("amount"))
	if amount <= 0:
		frappe.throw(_("Amount must be greater than zero."))
	sm = frappe.db.get_value("Student Master", student, ["first_name", "programme_of_study"], as_dict=True)
	if not sm:
		frappe.throw(_("Student {0} not found.").format(student))

	doc = frappe.new_doc("Stipend Payment")
	doc.update({
		"student": student,
		"student_name": sm.first_name,
		"programme": sm.programme_of_study if frappe.db.exists("Programme", sm.programme_of_study) else None,
		"academic_year": values.get("academic_year"),
		"academic_term": values.get("academic_term"),
		"stipend_type": values.get("stipend_type"),
		"payment_date": values.get("payment_date"),
		"payment_mode": values.get("payment_mode"),
		"amount": amount,
		"reference_number": (values.get("reference_number") or "").strip() or None,
		"remarks": remarks,
		"status": "Draft",
		"amended_from": amended_from,
	})
	doc.flags.ignore_permissions = bool(amended_from)
	doc.insert()
	doc.submit()
	return doc


@frappe.whitelist()
def record_stipend(
	student,
	stipend_type,
	payment_date,
	payment_mode,
	amount,
	remarks=None,
	academic_year=None,
	academic_term=None,
	reference_number=None,
):
	"""Create and submit a Stipend Payment for the student (normal Stipend Payment permissions apply)."""
	_check_access()
	doc = _submit_stipend(student, frappe._dict(locals()))
	return {"stipend_payment": doc.name}


def _active_stipend(stipend_payment, student):
	if not frappe.db.exists("Stipend Payment", stipend_payment):
		frappe.throw(_("Stipend Payment {0} was not found.").format(stipend_payment))
	doc = frappe.get_doc("Stipend Payment", stipend_payment)
	if doc.student != student:
		frappe.throw(_("Stipend Payment {0} does not belong to this student.").format(stipend_payment))
	if doc.docstatus != 1:
		frappe.throw(_("Stipend Payment {0} is not active (it is {1}).").format(stipend_payment, doc.status or _("a draft")))
	return doc


def _cancel_stipend(doc, remarks):
	doc.add_comment("Comment", _("Cancelled from Student Due Details: {0}").format(frappe.utils.escape_html(remarks)))
	doc.flags.ignore_permissions = True
	doc.cancel()


@frappe.whitelist()
def edit_stipend(
	student,
	stipend_payment,
	stipend_type,
	payment_date,
	payment_mode,
	amount,
	remarks=None,
	academic_year=None,
	academic_term=None,
	reference_number=None,
):
	"""Correct a stipend payment: it is cancelled (its ERPNext entry reversed) and an amended Stipend Payment
	(SP-xxxx-1) is submitted in its place, in one transaction - any error leaves the original."""
	_check_access()
	values = frappe._dict(locals())
	values.remarks = _require_remarks(remarks)
	doc = _active_stipend(stipend_payment, student)
	if flt(amount) <= 0:
		frappe.throw(_("Amount must be greater than zero."))

	frappe.db.savepoint("sfm_edit_stipend")
	try:
		_cancel_stipend(doc, values.remarks)
		new = _submit_stipend(student, values, amended_from=doc.name)
	except Exception:
		frappe.db.rollback(save_point="sfm_edit_stipend")
		raise
	return {"stipend_payment": new.name, "old_stipend_payment": doc.name}


@frappe.whitelist()
def delete_stipend(student, stipend_payment, remarks=None):
	"""Delete a stipend payment: it is cancelled (its ERPNext entry reversed); the record stays for the audit trail."""
	_check_access()
	remarks = _require_remarks(remarks)
	doc = _active_stipend(stipend_payment, student)
	_cancel_stipend(doc, remarks)
	return {"stipend_payment": doc.name}


def _active_concession(concession, student):
	if not frappe.db.exists("Fee Concession", concession):
		frappe.throw(_("Fee Concession {0} was not found.").format(concession))
	doc = frappe.get_doc("Fee Concession", concession)
	if doc.student != student:
		frappe.throw(_("Fee Concession {0} does not belong to this student.").format(concession))
	if doc.docstatus != 1:
		frappe.throw(_("Fee Concession {0} is not active (it is {1}).").format(concession, doc.status or _("a draft")))
	if frappe.db.get_value("Fee Demand", doc.fee_demand, "status") == "Cancelled":
		frappe.throw(_("Due {0} is cancelled, so its concession can no longer be changed.").format(doc.fee_demand))
	return doc


def _cancel_concession(doc, remarks):
	doc.add_comment("Comment", _("Cancelled from Student Due Details: {0}").format(frappe.utils.escape_html(remarks)))
	doc.flags.ignore_permissions = True
	doc.cancel()


@frappe.whitelist()
def add_credit_note(
	student,
	credit_type,
	credit_amount,
	academic_year=None,
	received_via=None,
	received_bank_account=None,
	received_date=None,
	received_reference=None,
	remarks=None,
):
	"""Add excess / credit for the student from the page's pop-up: a Student Credit Note is
	created and submitted (it becomes Active with the full amount available)."""
	_check_access()
	if flt(credit_amount) <= 0:
		frappe.throw(_("Credit Amount must be greater than zero."))
	if not frappe.db.exists("Student Master", student):
		frappe.throw(_("Student {0} was not found.").format(student))
	doc = frappe.new_doc("Student Credit Note")
	doc.update({
		"student": student,
		"credit_type": credit_type,
		"credit_amount": flt(credit_amount),
		"academic_year": academic_year,
		"received_via": received_via,
		"received_bank_account": received_bank_account if received_via and received_via != "Cash" else None,
		"received_date": received_date,
		"received_reference": received_reference,
		"remarks": remarks,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return {"credit_note": doc.name}


@frappe.whitelist()
def apply_concession(student, fee_demand, concession_type, waiver_value, reason, concession_date=None):
	"""Apply a scholarship / waiver to one of the student's dues from the page's pop-up:
	a Fee Concession is created and submitted, which takes the waiver off the due."""
	_check_access()
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Reason is mandatory."))
	if flt(waiver_value) <= 0:
		frappe.throw(_("Waiver Value must be greater than zero."))
	demand = frappe.db.get_value(
		"Fee Demand", fee_demand, ["student", "status", "outstanding_amount"], as_dict=True
	)
	if not demand or demand.student != student:
		frappe.throw(_("Due {0} does not belong to this student.").format(fee_demand))
	if demand.status in ("Cancelled", "Paid", "Waived") or flt(demand.outstanding_amount) <= 0:
		frappe.throw(_("A scholarship can only be applied to a due with a pending amount."))
	if flt(waiver_value) > flt(demand.outstanding_amount) + 0.005:
		frappe.throw(
			_("Waiver Value {0} is more than the pending amount {1} on {2}.").format(
				fmt_money(waiver_value, currency="INR"), fmt_money(demand.outstanding_amount, currency="INR"), fee_demand
			)
		)
	doc = frappe.new_doc("Fee Concession")
	doc.update({
		"student": student,
		"fee_demand": fee_demand,
		"concession_type": concession_type,
		"waiver_value": flt(waiver_value),
		"concession_date": concession_date or frappe.utils.today(),
		"reason": reason,
	})
	doc.flags.ignore_permissions = True
	doc.insert()
	doc.submit()
	return {"concession": doc.name}


@frappe.whitelist()
def edit_concession(student, concession, concession_type, waiver_value, reason, concession_date=None, remarks=None):
	"""Correct a scholarship / waiver: the concession is cancelled (its waiver taken off the due) and an amended
	Fee Concession (CON-xxxx-1) is submitted on the same due, in one transaction - any error (for example a waiver
	larger than the unpaid balance) leaves the original as it was."""
	_check_access()
	remarks = _require_remarks(remarks)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Reason is mandatory."))
	if flt(waiver_value) <= 0:
		frappe.throw(_("Waiver Value must be greater than zero."))
	doc = _active_concession(concession, student)

	frappe.db.savepoint("sfm_edit_concession")
	try:
		_cancel_concession(doc, remarks)
		new = frappe.new_doc("Fee Concession")
		new.update({
			"student": student,
			"fee_demand": doc.fee_demand,
			"concession_type": concession_type,
			"waiver_value": flt(waiver_value),
			"concession_date": concession_date or doc.concession_date,
			"reason": reason,
			"amended_from": doc.name,
		})
		new.flags.ignore_permissions = True
		new.insert()
		new.submit()
		new.add_comment("Comment", _("Amended from {0}: {1}").format(doc.name, frappe.utils.escape_html(remarks)))
	except Exception:
		frappe.db.rollback(save_point="sfm_edit_concession")
		raise
	return {"concession": new.name, "old_concession": doc.name}


@frappe.whitelist()
def delete_concession(student, concession, remarks=None):
	"""Delete a scholarship / waiver: the concession is cancelled and its waiver taken off the due (the due's
	pending amount goes back up). The record stays as Reversed for the audit trail."""
	_check_access()
	remarks = _require_remarks(remarks)
	doc = _active_concession(concession, student)
	_cancel_concession(doc, remarks)
	return {"concession": doc.name}


@frappe.whitelist()
def get_refund_bank_details(student):
	"""The student's savings account, to prefill an excess refund."""
	_check_access()
	bank = frappe.db.get_value(
		"Student Master",
		student,
		["savings_account_holder_name", "savings_bank_name", "savings_account_number", "savings_ifsc_code"],
		as_dict=True,
	) or {}
	return {
		"account_holder_name": bank.get("savings_account_holder_name"),
		"bank_name": bank.get("savings_bank_name"),
		"account_number": bank.get("savings_account_number"),
		"ifsc_code": bank.get("savings_ifsc_code"),
	}


@frappe.whitelist()
def refund_from_excess(
	student,
	amount,
	refund_mode,
	refund_date=None,
	bank_name=None,
	account_number=None,
	ifsc_code=None,
	utr_number=None,
	transaction_date=None,
	remarks=None,
	account_holder_name=None,
	university_bank_account=None,
):
	"""Refund part or all of the student's excess: a submitted Fee Refund (source Excess Amount)
	that draws down their active Student Credit Notes, oldest first."""
	_check_access()
	remarks = _require_remarks(remarks, _("Reason for Refund"))
	if not university_bank_account:
		frappe.throw(_("University Bank Account is mandatory."))
	if flt(amount) <= 0:
		frappe.throw(_("Amount must be greater than zero."))
	if refund_mode in ("NEFT", "Cheque", "Online") and not (account_holder_name and bank_name and account_number and ifsc_code):
		frappe.throw(
			_("Account Holder Name, Bank Name, Account Number and IFSC Code are required for {0} refunds.").format(refund_mode)
		)

	doc = frappe.new_doc("Fee Refund")
	doc.update({
		"student": student,
		"student_name": frappe.db.get_value("Student Master", student, "first_name"),
		"refund_source": "Excess Amount",
		"refund_type": "Excess Refund",
		"refund_amount": flt(amount),
		"refund_date": refund_date or today(),
		"refund_mode": refund_mode,
		"university_bank_account": university_bank_account,
		"account_holder_name": account_holder_name,
		"bank_name": bank_name,
		"account_number": account_number,
		"ifsc_code": ifsc_code,
		"utr_number": utr_number,
		"transaction_date": transaction_date,
		"reason": remarks,
		"status": "Draft",
	})
	doc.insert()
	doc.submit()
	return {"fee_refund": doc.name}


@frappe.whitelist()
def download_fee_certificate(name, file_format="pdf"):
	"""Old URL for certificate downloads (links shared before the Fee Certificates page existed)."""
	from slcm.slcm.page.fee_certificates.fee_certificates import download_fee_certificate as download

	return download(name, file_format)
