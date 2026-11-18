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

// Default range: the last 7 days (times blank = start / end of day).
function rfid_default_from() {
	return frappe.datetime.add_days(frappe.datetime.get_today(), -6);
}
function rfid_default_to() {
	return frappe.datetime.get_today();
}

function rfid_pct_colour(pct) {
	if (pct >= 75) return "#1d7347";
	if (pct >= 50) return "#9a5b00";
	return "#8b1a1a";
}

const RFID_REPORT_API = "slcm.slcm.report.rfid_attendance_report.rfid_attendance_report";
const RFID_MULTISELECTS = ["academic_year", "programme", "terminal_alias", "venue", "student", "class_name", "course"];
const RFID_CLASS_NUMBERS = ["enrolled", "swiped", "marked_present"];

frappe.query_reports["RFID Attendance Report"] = {

	onload: function (report) {
		// ── Download menu: Excel (all sheets) / CSV (this report) / CSV (all sheets, .zip) ──
		const rfid_download = function (method, extra) {
			let filters;
			try {
				filters = report.get_filter_values(true);
			} catch (e) {
				return; // a required filter is missing; Frappe already shows "Please set filters"
			}
			if (!filters) return;
			open_url_post(`/api/method/${RFID_REPORT_API}.${method}`, Object.assign({ filters: filters }, extra || {}));
			frappe.show_alert({ message: __("Preparing the file — the download starts in a moment."), indicator: "blue" });
		};
		report.page.add_inner_button(__("Excel (.xlsx)"), () => rfid_download("download_excel"), __("Download"));
		report.page.add_inner_button(__("CSV – this report"), () => rfid_download("download_csv", { scope: "report" }), __("Download"));
		report.page.add_inner_button(__("CSV – all sheets (.zip)"), () => rfid_download("download_csv", { scope: "all" }), __("Download"));

		report.page.add_inner_button(__("Reset Filters"), function () {

			// Clear every MultiSelectList to an empty array
			RFID_MULTISELECTS.forEach(function (fn) {
				const f = report.get_filter(fn);
				if (f && f.set_value) f.set_value([]);
			});

			// Reset scalar filters to defaults
			report.get_filter("report_type").set_input("Terminal-wise");
			report.get_filter("view_by").set_input("Daily");
			report.get_filter("from_date").set_input(rfid_default_from());
			report.get_filter("to_date").set_input(rfid_default_to());
			report.get_filter("from_time").set_input("");
			report.get_filter("to_time").set_input("");
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
			fieldname: "report_type",
			label: __("Report"),
			fieldtype: "Select",
			options: "Terminal-wise\nClass-wise",
			default: "Terminal-wise",
			reqd: 1,
			on_change: function () { frappe.query_report.refresh(); }
		},
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
			label: __("From Date"),
			fieldtype: "Date",
			default: rfid_default_from(),
			reqd: 1
		},
		{
			fieldname: "from_time",
			label: __("From Time"),
			fieldtype: "Time",
			description: __("Blank = 00:00")
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: rfid_default_to(),
			reqd: 1
		},
		{
			fieldname: "to_time",
			label: __("To Time"),
			fieldtype: "Time",
			description: __("Blank = end of day")
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
			fieldname: "class_name",
			label: __("Class"),
			fieldtype: "MultiSelectList",
			get_data: rfid_multiselect_get_data("class_name")
		},
		{
			fieldname: "course",
			label: __("Course"),
			fieldtype: "MultiSelectList",
			get_data: rfid_multiselect_get_data("course")
		},
		{
			fieldname: "known_only",
			label: __("Known Students Only"),
			fieldtype: "Check",
			default: 0,
			depends_on: "eval:doc.report_type !== 'Class-wise'"
		},
		{
			fieldname: "include_most_swiped",
			label: __("Include Most Swiped Sheets"),
			fieldtype: "Check",
			default: 0,
			description: __("Adds the Most Swiped - Daily / Weekly / Monthly sheets to the Excel and all-sheets CSV downloads."),
			depends_on: "eval:doc.report_type !== 'Class-wise'",
			// Download-only option: the on-screen table doesn't use it, so don't re-run the report.
			on_change: function () {}
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
			if (column.fieldname === "terminal_alias" || column.fieldname === "course") {
				return `<span style="color:#2b2e4a;font-style:italic;font-size:.85em">${esc(data[column.fieldname] || "")}</span>`;
			}
			if (column.fieldname === "at_venue" && data.at_venue == null) {
				return `<span style="color:#9ca3af">—</span>`;
			}
			if (column.fieldname === "swipe_pct") {
				return `<b style="color:${rfid_pct_colour(data.swipe_pct)}">${data.swipe_pct}%</b>`;
			}
			if (column.fieldname === "not_swiped" && data.not_swiped > 0) {
				return `<b style="color:#8b1a1a">${data.not_swiped}</b>`;
			}
			if (["total_swipes", "unique_students", ...RFID_CLASS_NUMBERS, "at_venue"].includes(column.fieldname)) {
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

		// ── Class row (Class-wise) ─────────────────────────────────────────
		if (column.fieldname === "swipe_pct" && data.enrolled) {
			return `<span style="color:${rfid_pct_colour(data.swipe_pct)};font-weight:600">${data.swipe_pct}%</span>`;
		}
		if (column.fieldname === "not_swiped" && data.not_swiped > 0) {
			return `<span style="color:#8b1a1a;font-weight:600">${data.not_swiped}</span>`;
		}
		if (column.fieldname === "at_venue" && data.at_venue == null && data.time_table) {
			return `<span style="color:#9ca3af" title="${esc(__("No reader is mapped to this venue on this date"))}">—</span>`;
		}
		if (column.fieldname === "rfid_activated" && data.rfid_activated) {
			const yes = data.rfid_activated === __("Yes");
			return `<span style="color:${yes ? "#1d7347" : "#9a5b00"};font-weight:600">${esc(data.rfid_activated)}</span>`;
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
