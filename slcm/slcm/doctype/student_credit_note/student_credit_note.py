import frappe
from frappe.model.document import Document
from frappe.utils import flt, today

# Credit types that stand for money the student paid; the others (e.g. Scholarship Credit) carry no cash.
CASH_CREDIT_TYPES = ("Overpayment", "Advance Deposit")

def resolve_student_from_registration_id(doc):
	"""Bulk-upload rows may give the student by Registration ID (or Application Number) instead of the system ID.
	Fill Student from it, or check the two agree when both are given; then set Registration ID / Student Name from
	the student. New records only. (Registration ID is fetched only when empty, so a typed value reaches here.)"""
	if doc.docstatus != 0:
		return
	reg = (doc.registration_id or "").strip()
	if reg and not doc.student:
		doc.student = frappe.db.get_value("Student Master", {"registration_id": reg}, "name") or frappe.db.get_value(
			"Student Master", {"application_number": reg}, "name"
		)
		if not doc.student:
			frappe.throw(f"No student has Registration ID {reg}.")
	if not doc.student:
		return
	sm = frappe.db.get_value(
		"Student Master", doc.student, ["registration_id", "application_number", "first_name"], as_dict=True
	) or frappe._dict()
	if reg and reg not in (sm.registration_id, sm.application_number):
		frappe.throw(f"Registration ID {reg} does not belong to student {doc.student}.")
	doc.registration_id = sm.registration_id or None
	doc.student_name = sm.first_name or doc.student_name


class StudentCreditNote(Document):

	def validate(self):
		resolve_student_from_registration_id(self)
		if flt(self.credit_amount) <= 0:
			frappe.throw("Credit Amount must be greater than zero.")
		self.validate_money_received()

	def validate_money_received(self):
		"""Excess entered by hand for money the student actually paid (a duplicate NEFT, an advance) must say how
		it came in, so it can be accounted for. Excess moved from a paid due already has that on its payment."""
		if self.source_fee_demand:
			return
		if self.credit_type in CASH_CREDIT_TYPES and not self.received_via:
			frappe.throw(
				f"Received Via is required for a {self.credit_type} credit note: record how the money reached the university."
			)
		if self.received_via and not self.received_date:
			frappe.throw("Received Date is required when Received Via is set.")

	def before_update_after_submit(self):
		self.validate_money_received()

	def on_submit(self):
		self.db_set("available_credit", flt(self.credit_amount))
		self.db_set("used_credit", 0)
		self.db_set("status", "Active")

	def on_cancel(self):
		if flt(self.used_credit) > 0:
			frappe.throw(
				f"Cannot cancel — ₹{self.used_credit:,.2f} of this credit has already been applied. "
				"Reverse the adjustments first."
			)
		self.db_set("status", "Cancelled")
		self.db_set("available_credit", 0)

	@frappe.whitelist()
	def apply_credit_to_demand(self, fee_demand, amount):
		"""Apply credit from this note to a fee demand (desk button)."""
		# run_doc_method only checks read; applying credit changes both documents
		self.check_permission("write")
		frappe.has_permission("Fee Demand", "write", doc=fee_demand, throw=True)
		return self.apply_credit(fee_demand, amount)

	def apply_credit(self, fee_demand, amount):
		"""Apply credit from this note to a fee demand. Callers check access
		(the desk button above, or Student Fee Management's role check)."""
		amount = flt(amount)
		available = flt(self.available_credit)

		if amount <= 0:
			frappe.throw("Amount to adjust must be greater than zero.")
		if amount > available:
			frappe.throw(
				f"Amount (₹{amount:,.2f}) exceeds available credit (₹{available:,.2f})."
			)

		demand = frappe.get_doc("Fee Demand", fee_demand)
		if demand.student != self.student:
			frappe.throw("This credit note belongs to a different student.")

		if demand.status in ("Paid", "Cancelled", "Waived"):
			frappe.throw(f"Fee Demand {fee_demand} is {demand.status} and cannot take an adjustment.")
		if amount > flt(demand.outstanding_amount) + 0.005:
			frappe.throw(
				f"Amount (₹{amount:,.2f}) exceeds the due's outstanding amount (₹{flt(demand.outstanding_amount):,.2f})."
			)

		demand.credit_adjusted = flt(demand.credit_adjusted) + amount
		# Fee Demand.validate recalculates outstanding and status (Paid / Partially Paid) from paid + adjusted
		demand.flags.payment_update = True
		# money is being applied: a stale Source Document link (e.g. a deleted re-exam) must not block it,
		# the same as Fee Demand.update_payment_status
		demand.flags.ignore_links = True
		demand.save(ignore_permissions=True)
		demand.flags.payment_update = False

		new_available = available - amount
		new_used = flt(self.used_credit) + amount

		# Insert child row directly — avoids "cannot update after submit" error
		frappe.get_doc({
			"doctype": "Credit Adjustment Row",
			"parent": self.name,
			"parenttype": "Student Credit Note",
			"parentfield": "adjustments",
			"idx": len(self.adjustments) + 1,
			"fee_demand": fee_demand,
			"fee_component": demand.fee_component,
			"amount_adjusted": amount,
			"adjusted_on": today(),
			"adjusted_by": frappe.session.user,
		}).insert(ignore_permissions=True)

		self.db_set("available_credit", new_available)
		self.db_set("used_credit", new_used)
		if new_available == 0:
			self.db_set("status", "Exhausted")

		return {"available_credit": new_available, "used_credit": new_used}
