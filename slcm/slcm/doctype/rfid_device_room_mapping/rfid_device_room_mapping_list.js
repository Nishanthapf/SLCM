// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

const RDRM_API = "slcm.slcm.doctype.rfid_device_room_mapping.rfid_device_room_mapping";

frappe.listview_settings["RFID Device Room Mapping"] = {
	onload(listview) {
		if (!frappe.user.has_role("System Manager")) return;
		listview.page.add_inner_button(__("Suggest from Reader Labels"), () => rdrm_suggest(listview));
	},
};

function rdrm_suggest(listview) {
	frappe.call({ method: `${RDRM_API}.suggest_venue_mappings`, freeze: true }).then((r) => {
		const rows = r.message || [];
		const esc = frappe.utils.escape_html;
		const suggested = rows.filter((x) => x.code === "suggested");
		const body = rows
			.map(
				(x) => `<tr>
					<td>${x.code === "suggested" ? `<input type="checkbox" class="rdrm-pick" data-device="${esc(x.device)}" checked>` : ""}</td>
					<td>${esc(x.device)}</td><td>${esc(x.label)}</td>
					<td>${esc(x.venue || "")}</td><td>${esc(x.status)}</td></tr>`
			)
			.join("");
		const d = new frappe.ui.Dialog({
			title: __("Suggested Venue Mappings"),
			size: "extra-large",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "table",
					options: `<p class="text-muted">${__(
						"Matched from each reader's label (e.g. NAB-103-1 → NAB 103). Review before creating; mappings start today. Unmatched or ambiguous readers must be mapped by hand."
					)}</p>
					<div style="max-height:60vh;overflow:auto"><table class="table table-bordered table-sm">
					<thead><tr><th></th><th>${__("Device")}</th><th>${__("Reader Label")}</th><th>${__("Venue")}</th><th>${__("Status")}</th></tr></thead>
					<tbody>${body}</tbody></table></div>`,
				},
			],
			primary_action_label: __("Create {0} Mapping(s)", [suggested.length]),
			primary_action() {
				const devices = [...d.$wrapper.find(".rdrm-pick:checked")].map((el) => el.dataset.device);
				if (!devices.length) {
					frappe.msgprint(__("Select at least one device."));
					return;
				}
				frappe
					.call({ method: `${RDRM_API}.create_suggested_mappings`, args: { devices }, freeze: true })
					.then((res) => {
						d.hide();
						frappe.show_alert({ message: __("{0} mapping(s) created", [(res.message || []).length]), indicator: "green" });
						listview.refresh();
					});
			},
		});
		if (!suggested.length) d.get_primary_btn().prop("disabled", true);
		d.show();
	});
}
