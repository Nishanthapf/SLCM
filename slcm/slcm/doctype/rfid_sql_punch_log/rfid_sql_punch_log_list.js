// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

frappe.listview_settings["RFID SQL Punch Log"] = {
	onload(listview) {
		// Runs in both List and Report view: Excel of the rows matching the current filters.
		listview.page.add_inner_button(__("Download Excel"), () => {
			open_url_post(
				"/api/method/slcm.slcm.doctype.rfid_sql_punch_log.rfid_sql_punch_log.download_excel",
				{ filters: JSON.stringify(listview.get_filters_for_args() || []) }
			);
			frappe.show_alert({ message: __("Preparing the file — the download starts in a moment."), indicator: "blue" });
		});
	},
};
