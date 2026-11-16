// Read-only audit trail: no form actions, just a jump to the referenced document.
frappe.ui.form.on("User Activity Log", {
	refresh(frm) {
		frm.disable_save();
		if (frm.doc.reference_doctype && frm.doc.reference_name && frm.doc.action !== "Delete") {
			frm.add_custom_button(__("Open Document"), () =>
				frappe.set_route("Form", frm.doc.reference_doctype, frm.doc.reference_name)
			);
		}
	},
});
