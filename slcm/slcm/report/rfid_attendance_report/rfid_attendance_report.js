// Copyright (c) 2026, Nishanth and contributors
// For license information, please see license.txt

/* ── Shared helper: build a MultiSelectList get_data function ────────────────
   Calls the whitelisted Python API get_filter_options(filter_name, txt)
   and returns a Promise that resolves to [{label, value, description}].
──────────────────────────────────────────────────────────────────────────── */
function rfid_multiselect_get_data(filter_name) {
	return function (txt) {
		return frappe.call({
			method: "slcm.slcm.report.rfid_attendance_report.rfid_attendance_report.get_filter_options",
			args: { filter_name: filter_name, txt: txt || "" }
		}).then(function (r) {
			return r && r.message ? r.message : [];
		});
	};
}

/* ── Inject NLSIU selection highlight styles once ────────────────────────── */
(function inject_rfid_styles() {
	if (document.getElementById("rfid-report-styles")) return;
	const style = document.createElement("style");
	style.id = "rfid-report-styles";
	style.textContent = `
		/* Summary rows (bold=1) — light navy background, stronger bottom border */
		.dt-row.dt-row--bold .dt-cell {
			background: #eef0f8 !important;
			border-bottom: 2px solid #b8bcd8 !important;
		}
		/* Indent detail rows visually */
		.dt-row:not(.dt-row--bold) .dt-cell--col-0 {
			padding-left: 28px !important;
		}
		/* Horizontal scroll — force the datatable wrapper to scroll */
		.report-wrapper .dt-scrollable {
			overflow-x: auto !important;
		}
		/* Selected item in MultiSelectList dropdown — navy highlight */
		.rfid-filter .selectable-item.selected,
		.rfid-filter .selectable-item.selected:hover {
			background: #2b2e4a !important;
			color: #fff !important;
		}
		/* Tick icon inside selected item */
		.rfid-filter .selectable-item.selected .multiselect-check {
			color: #fff !important;
		}
		/* Hover on unselected items — light navy tint */
		.rfid-filter .selectable-item:hover {
			background: #e8e9f0 !important;
			color: #2b2e4a !important;
		}
		/* Clear All button — maroon */
		.rfid-filter .clear-selections {
			background: #8b1a1a !important;
			border-color: #8b1a1a !important;
			color: #fff !important;
		}
		/* Select All button — navy */
		.rfid-filter .select-all-options {
			background: #2b2e4a !important;
			border-color: #2b2e4a !important;
			color: #fff !important;
		}
		/* Status text when values selected — navy bold */
		.rfid-filter .multiselect-list .status-text {
			color: #2b2e4a;
			font-weight: 600;
		}
	`;
	document.head.appendChild(style);
})();

// Default range: the last 7 days, start of the first day to end of today.
function rfid_default_from() {
	return frappe.datetime.add_days(frappe.datetime.get_today(), -6) + " 00:00:00";
}
function rfid_default_to() {
	return frappe.datetime.get_today() + " 23:59:59";
}

const RFID_REPORT_API = "slcm.slcm.report.rfid_attendance_report.rfid_attendance_report";
const RFID_MULTISELECTS = ["academic_year", "programme", "terminal_alias", "venue", "student"];

frappe.query_reports["RFID Attendance Report"] = {

	onload: function (report) {
		// ── Reset Filters button ─────────────────────────────────────────────
		// ── Excel download: report + student-wise + most-swiped sheets ──────
		report.page.add_inner_button(__("Download Excel"), function () {
			let filters;
			try {
				filters = report.get_filter_values(true);
			} catch (e) {
				return; // a required filter is missing; Frappe already shows "Please set filters"
			}
			if (!filters) return;
			open_url_post(`/api/method/${RFID_REPORT_API}.download_excel`, { filters: filters });
			frappe.show_alert({ message: __("Preparing Excel — the download starts in a moment."), indicator: "blue" });
		}).css({ "font-weight": "600" });

		report.page.add_inner_button(__("Reset Filters"), function () {

			// Clear every MultiSelectList to an empty array
			RFID_MULTISELECTS.forEach(function (fn) {
				const f = report.get_filter(fn);
				if (f && f.set_value) f.set_value([]);
			});

			// Reset scalar filters to defaults
			report.get_filter("view_by").set_input("Daily");
			report.get_filter("from_date").set_input(rfid_default_from());
			report.get_filter("to_date").set_input(rfid_default_to());
			report.get_filter("known_only").set_input(0);

			// Clear the URL params so stale values don't re-apply on refresh
			frappe.route_options = {};

			report.refresh();
		}).css({
			"color":        "#8b1a1a",
			"font-weight":  "600",
			"border-color": "#8b1a1a"
		});

		// ── Apply .rfid-filter CSS class to MultiSelectList controls ─────────
		setTimeout(function () {
			report.page.page_form.find(".frappe-control").each(function () {
				const fn = $(this).attr("data-fieldname");
				if (RFID_MULTISELECTS.includes(fn)) {
					$(this).addClass("rfid-filter");
				}
			});
		}, 600);
	},

	filters: [
		{
			fieldname: "view_by",
			label: __("View By"),
			fieldtype: "Select",
			options: "Hourly\nDaily\nWeekly\nMonthly",
			default: "Daily",
			reqd: 1,
			on_change: function () { frappe.query_report.refresh(); }
		},
		{
			fieldname: "from_date",
			label: __("From"),
			fieldtype: "Datetime",
			default: rfid_default_from(),
			reqd: 1
		},
		{
			fieldname: "to_date",
			label: __("To"),
			fieldtype: "Datetime",
			default: rfid_default_to(),
			reqd: 1
		},
		{
			fieldname: "academic_year",
			label: __("Academic Year"),
			fieldtype: "MultiSelectList",
			get_data: rfid_multiselect_get_data("academic_year")
		},
		{
			fieldname: "programme",
			label: __("Programme(s)"),
			fieldtype: "MultiSelectList",
			get_data: rfid_multiselect_get_data("programme")
		},
		{
			fieldname: "terminal_alias",
			label: __("Terminal / Room"),
			fieldtype: "MultiSelectList",
			get_data: rfid_multiselect_get_data("terminal_alias")
		},
		{
			fieldname: "venue",
			label: __("Venue"),
			fieldtype: "MultiSelectList",
			get_data: rfid_multiselect_get_data("venue")
		},
		{
			fieldname: "student",
			label: __("Student"),
			fieldtype: "MultiSelectList",
			get_data: rfid_multiselect_get_data("student")
		},
		{
			fieldname: "known_only",
			label: __("Known Students Only"),
			fieldtype: "Check",
			default: 0
		}
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const esc = frappe.utils.escape_html;

		// ── Period (summary) row ───────────────────────────────────────────
		if (data.is_period_row) {
			if (column.fieldname === "period_label") {
				const raw = data.period_label || "";
				const m = raw.match(/^(.+?)\s+\((.+?)\)$/);
				return m
					? `<span style="color:#2b2e4a;font-weight:700">${esc(m[1])}</span><span style="color:#6b7280;font-size:.85em;margin-left:6px">(${esc(m[2])})</span>`
					: `<span style="color:#2b2e4a;font-weight:700">${esc(raw)}</span>`;
			}
			if (column.fieldname === "terminal_alias") {
				return `<span style="color:#2b2e4a;font-style:italic;font-size:.85em">${esc(data.terminal_alias || "")}</span>`;
			}
			if (["total_swipes", "unique_students"].includes(column.fieldname)) {
				return `<b style="color:#2b2e4a">${data[column.fieldname] || 0}</b>`;
			}
			if (column.fieldname === "unknown_swipes" && data.unknown_swipes > 0) {
				return `<b style="color:#8b1a1a">${data.unknown_swipes}</b>`;
			}
			return value;
		}

		// ── Terminal row ───────────────────────────────────────────────────
		if (column.fieldname === "terminal_alias" && data.terminal_alias) {
			return `<code style="background:#dde0f0;color:#2b2e4a;padding:2px 8px;border-radius:4px;font-size:.82em;font-weight:600">${esc(data.terminal_alias)}</code>`;
		}
		if (column.fieldname === "venue" && data.venue) {
			const unmapped = data.venue === "Not mapped";
			return `<span style="color:${unmapped ? "#8b1a1a" : "#555"};${unmapped ? "font-style:italic" : ""}">${esc(data.venue)}</span>`;
		}
		if (column.fieldname === "unknown_swipes" && data.unknown_swipes > 0) {
			return `<span style="color:#8b1a1a;font-weight:600">${data.unknown_swipes}</span>`;
		}
		return value;
	},

	get_datatable_options: function (options) {
		return Object.assign(options, {
			checkboxColumn:    false,
			cellHeight:        40,
			/* treeView adds "Set Level / Collapse All" controls — keep off.
			   We use indent purely for visual indentation via the formatter. */
			treeView:          false,
			/* "fixed" keeps column widths as defined and enables the
			   horizontal scrollbar properly. "fluid" stretches columns
			   and breaks overflow scroll. */
			layout:            "fixed",
			/* Freeze the first column (Date) so it stays visible while
			   scrolling horizontally across the wide table. */
			freezeColumns:     1,
		});
	}
};
