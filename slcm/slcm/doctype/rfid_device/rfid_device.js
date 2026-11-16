// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

frappe.ui.form.on("RFID Device", {
	refresh(frm) {
		if (frm.is_new()) return;

		if (frm.doc.device_type === "Classroom" && !frm.doc.current_venue) {
			frm.set_intro(
				__("This classroom reader is not mapped to a venue for today, so its taps cannot be checked against the Time Table venue."),
				"orange"
			);
		}

		frm.add_custom_button(__("Map to Venue"), () => {
			frappe.new_doc("RFID Device Room Mapping", { device: frm.doc.name });
		});
		frm.add_custom_button(__("Venue Mappings"), () => {
			frappe.set_route("List", "RFID Device Room Mapping", { device: frm.doc.name });
		});
	},
});
