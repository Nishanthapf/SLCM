frappe.ui.form.on("Fee Refund", {
	refresh(frm) {
		_show_available_excess(frm);
	},

	refund_source(frm) {
		if (frm.doc.refund_source === "Excess Amount") {
			frm.set_value("fee_demand", "");
			if (!frm.doc.refund_type) frm.set_value("refund_type", "Excess Refund");
		}
		_show_available_excess(frm);
	},

	student(frm) {
		frm.set_value("fee_demand", "");
		_show_available_excess(frm);
		_fill_bank_details(frm);
		if (frm.doc.student) {
			frm.set_query("fee_demand", () => ({
				filters: {
					student: frm.doc.student,
					status: ["in", ["Pending", "Partially Paid", "Overdue", "Paid"]],
				},
			}));
		}
	},

	fee_demand(frm) {
		if (!frm.doc.fee_demand) return;
		frappe.db.get_value("Fee Demand", frm.doc.fee_demand, [
			"fee_component", "original_amount", "paid_amount"
		], (r) => {
			if (!r) return;
			frm.set_value("fee_component", r.fee_component);
			frm.set_value("original_amount", r.original_amount);
			frm.set_value("paid_amount", r.paid_amount);

			if (r.paid_amount === 0) {
				frappe.msgprint({
					title: "No Payment Found",
					message: `This demand has nothing paid. A refund can only be issued for paid amounts.`,
					indicator: "orange",
				});
			}
		});
	},

	refund_amount(frm) {
		_show_refund_preview(frm);
	},

	refund_mode(frm) {
		// bank details are mandatory for these modes through mandatory_depends_on; the UTR is asked for here
		frm.toggle_reqd("utr_number", ["NEFT", "Cheque", "Online"].includes(frm.doc.refund_mode));
	},
});

function _show_refund_preview(frm) {
	const refund = flt(frm.doc.refund_amount);
	const paid = flt(frm.doc.paid_amount);
	if (!refund || !paid) return;

	const remaining_paid = paid - refund;
	if (remaining_paid < 0) {
		frappe.msgprint({
			title: "Invalid Refund Amount",
			message: `Refund (${_fr_money(refund)}) exceeds amount paid (${_fr_money(paid)}).`,
			indicator: "red",
		});
		return;
	}

	frm.dashboard.set_headline(
		`<b>Refund:</b> ${_fr_money(refund)} &nbsp;|&nbsp; ` +
		`<b>Remaining Paid Balance:</b> ${_fr_money(remaining_paid)}`
	);
}

// Own name: form scripts run in the global scope, so a function called format_currency here replaced Frappe's
// global format_currency(value, currency) for the whole session once a Fee Refund was opened.
function _fr_money(val) {
	return frappe.format(val, { fieldtype: "Currency", options: "INR" });
}

// The student's savings account, for NEFT / Cheque / Online refunds. Fills only empty fields.
function _fill_bank_details(frm) {
	if (!frm.doc.student || frm.doc.docstatus !== 0) return;
	frappe.db
		.get_value("Student Master", frm.doc.student, [
			"savings_account_holder_name",
			"savings_bank_name",
			"savings_account_number",
			"savings_ifsc_code",
		])
		.then(({ message: r }) => {
			if (!r) return;
			const map = {
				account_holder_name: r.savings_account_holder_name,
				bank_name: r.savings_bank_name,
				account_number: r.savings_account_number,
				ifsc_code: r.savings_ifsc_code,
			};
			Object.entries(map).forEach(([f, v]) => {
				if (v && !frm.doc[f]) frm.set_value(f, v);
			});
		});
}

// Excess refunds: show what the student can be refunded (unused active credit notes).
function _show_available_excess(frm) {
	if (frm.doc.docstatus !== 0 || frm.doc.refund_source !== "Excess Amount" || !frm.doc.student) return;
	frappe.db
		.get_list("Student Credit Note", {
			filters: { student: frm.doc.student, docstatus: 1, status: "Active" },
			fields: ["available_credit"],
			limit: 0,
		})
		.then((rows) => {
			const available = rows.reduce((sum, r) => sum + flt(r.available_credit), 0);
			frm.set_value("available_excess", available);
			if (!frm.doc.refund_amount && available) frm.set_value("refund_amount", available);
		});
}
