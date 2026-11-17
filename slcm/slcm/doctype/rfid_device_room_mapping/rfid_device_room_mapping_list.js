// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

const RDRM_API = "slcm.slcm.doctype.rfid_device_room_mapping.rfid_device_room_mapping";

frappe.listview_settings["RFID Device Room Mapping"] = {
	onload(listview) {
		if (!frappe.user.has_role("System Manager")) return;
		listview.page.add_inner_button(__("Suggest from Reader Labels"), () => rdrm_suggest(listview), null, "primary");
	},
};

function rdrm_suggest(listview) {
	frappe.call({ method: `${RDRM_API}.suggest_venue_mappings`, freeze: true }).then((r) => {
		const rows = r.message || [];
		const esc = frappe.utils.escape_html;
		const tabs = [
			{ key: "matched", label: __("Matched"), codes: ["suggested", "mapped"] },
			{ key: "unmatched", label: __("Not Matched"), codes: ["unmatched", "ambiguous"] },
			{ key: "skipped", label: __("Skipped"), codes: ["skipped"] },
		];
		const can_pick = (x) => ["unmatched", "ambiguous", "skipped"].includes(x.code);
		const row_html = (x) => `<tr>
					<td>${x.code === "suggested" ? `<input type="checkbox" class="rdrm-pick" data-device="${esc(x.device)}" checked>` : ""}</td>
					<td>${esc(x.device)}</td><td>${esc(x.label)}</td>
					<td class="${can_pick(x) ? "rdrm-venue-cell" : ""}" data-device="${esc(x.device)}">${can_pick(x) ? "" : esc(x.venue || "")}</td>
					<td>${esc(x.status)}</td></tr>`;
		const empty = `<tr><td colspan="5" class="text-muted text-center">${__("No readers")}</td></tr>`;
		const nav = tabs
			.map((t, i) => {
				const n = rows.filter((x) => t.codes.includes(x.code)).length;
				return `<li><a href="#" class="rdrm-tab ${i ? "" : "active"}" data-tab="${t.key}">${t.label}
					<span class="rdrm-count">${n}</span></a></li>`;
			})
			.join("");
		const panes = tabs
			.map((t, i) => {
				const list = rows.filter((x) => t.codes.includes(x.code));
				return `<div class="rdrm-pane" data-tab="${t.key}" style="${i ? "display:none;" : ""}${t.key === "matched" ? "max-height:55vh;overflow:auto" : ""}">
					<table class="table table-bordered table-sm">
					<thead><tr><th></th><th>${__("Device")}</th><th>${__("Reader Label")}</th><th>${__("Venue")}</th><th>${__("Status")}</th></tr></thead>
					<tbody>${list.length ? list.map(row_html).join("") : empty}</tbody></table></div>`;
			})
			.join("");
		const d = new frappe.ui.Dialog({
			title: __("Suggested Venue Mappings"),
			size: "extra-large",
			fields: [
				{
					fieldtype: "HTML",
					fieldname: "table",
					options: `<p class="text-muted">${__(
						"Matched from each reader's label (e.g. NAB-103-1 → NAB 103). Review before creating; mappings start today. For unmatched or ambiguous readers, pick a venue in the Not Matched or Skipped tab. Gate readers never count for class attendance."
					)}</p>
					<style>
						.rdrm-tabs { display: flex; gap: 6px; list-style: none; padding: 0; margin: 0 0 12px; }
						.rdrm-tab { display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px; border: none !important;
							border-radius: 6px; color: var(--text-muted); font-weight: 500; text-decoration: none !important; }
						.rdrm-tab:hover { background: #F7E9EC; color: #920C24; }
						.rdrm-tab.active { background: #920C24; color: #fff; }
						.rdrm-count { font-size: 11px; padding: 1px 8px; border-radius: 10px; background: #F7E9EC; color: #920C24; font-weight: 600; }
						.rdrm-tab.active .rdrm-count { background: rgba(255,255,255,0.2); color: #fff; }
						.rdrm-venue-cell { min-width: 240px; padding: 4px 8px !important; }
						.rdrm-venue-cell .form-group, .rdrm-venue-cell .frappe-control { margin: 0; }
						.rdrm-venue-cell .awesomplete > ul { z-index: 1050; max-height: 240px; overflow-y: auto; }
					</style>
					<ul class="rdrm-tabs">${nav}</ul>${panes}`,
				},
			],
			primary_action_label: __("Create Mapping(s)"),
			primary_action() {
				const devices = [...d.$wrapper.find(".rdrm-pick:checked")].map((el) => el.dataset.device);
				const manual = picked();
				if (!devices.length && !Object.keys(manual).length) {
					frappe.msgprint(__("Tick a suggested reader or pick a venue for an unmatched one."));
					return;
				}
				const by_device = Object.fromEntries(rows.map((x) => [x.device, x]));
				const plan = [
					...devices.map((dev) => ({ ...by_device[dev], venue: by_device[dev].venue, source: __("Suggested") })),
					...Object.entries(manual).map(([dev, venue]) => ({ ...by_device[dev], venue, source: __("Manual") })),
				];
				const list = plan
					.map(
						(x) => `<tr><td>${esc(x.device)}</td><td>${esc(x.label)}</td>
							<td><b>${esc(x.venue)}</b></td><td>${x.source}</td></tr>`
					)
					.join("");
				frappe.confirm(
					`<p>${__("Create {0} venue mapping(s), effective from today ({1})?", [
						plan.length,
						frappe.datetime.str_to_user(frappe.datetime.get_today()),
					])}</p>
					<div style="max-height:45vh;overflow:auto"><table class="table table-bordered table-sm mb-0">
					<thead><tr><th>${__("Device")}</th><th>${__("Reader Label")}</th><th>${__("Venue")}</th><th>${__("Source")}</th></tr></thead>
					<tbody>${list}</tbody></table></div>`,
					() => {
						frappe
							.call({ method: `${RDRM_API}.create_suggested_mappings`, args: { devices, manual }, freeze: true })
							.then((res) => {
								d.hide();
								frappe.show_alert({ message: __("{0} mapping(s) created", [(res.message || []).length]), indicator: "green" });
								listview.refresh();
							});
					}
				);
			},
		});
		const venue_controls = {};
		const picked = () => {
			const out = {};
			for (const [device, ctrl] of Object.entries(venue_controls)) {
				const v = ctrl.get_value();
				if (v) out[device] = v;
			}
			return out;
		};
		const update_count = () => {
			const n = d.$wrapper.find(".rdrm-pick:checked").length + Object.keys(picked()).length;
			d.get_primary_btn().html(__("Create {0} Mapping(s)", [n]));
			d.get_primary_btn().prop("disabled", !n);
		};
		d.$wrapper.find(".rdrm-venue-cell").each(function () {
			const device = this.dataset.device;
			venue_controls[device] = frappe.ui.form.make_control({
				parent: $(this),
				df: {
					fieldtype: "Link",
					fieldname: `venue_${device}`,
					options: "Venue Master",
					placeholder: __("Select venue"),
					get_query: () => ({ filters: { is_active: 1 } }),
					change: update_count,
				},
				only_input: true,
				render_input: true,
			});
		});
		d.$wrapper.on("change", ".rdrm-pick", update_count);
		d.$wrapper.on("click", ".rdrm-tab", function (e) {
			e.preventDefault();
			d.$wrapper.find(".rdrm-tab").removeClass("active");
			$(this).addClass("active");
			d.$wrapper.find(".rdrm-pane").hide();
			d.$wrapper.find(`.rdrm-pane[data-tab="${this.dataset.tab}"]`).show();
		});
		update_count();
		d.show();
	});
}
