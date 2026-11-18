// Drill-downs from the dashboard into desk list views and reports.
// The page runs inside desk, so `frappe.set_route` is available.

// `undefined` / `null` leave a filter alone; "" clears it (e.g. a report's default dates).
function go(route, options) {
	const clean = Object.fromEntries(
		Object.entries(options || {}).filter(([, v]) => v !== undefined && v !== null)
	);
	window.frappe.route_options = clean;
	window.frappe.set_route(...route);
}

/**
 * Applicant list for the dashboard's current scope, plus `extra` filters.
 * Values follow route_options: a plain value means "=", an array is [operator, value].
 */
export function openApplicants(scope, extra = {}) {
	const options = {
		admission_cycle: scope.cycle,
		foriegn_national: scope.applicantType === "International" ? "Yes" : ["!=", "Yes"],
	};
	if (scope.programs?.length) {
		options.program = scope.programs.length === 1 ? scope.programs[0] : ["in", scope.programs];
	}
	if (scope.range?.length === 2) {
		options.creation = ["between", [scope.range[0], scope.range[1]]];
	}
	if (scope.category) options.whether_scstobc_ncl = categoryFilter(scope.category);
	if (scope.gender) options.gender = scope.gender === "Not set" ? ["is", "not set"] : scope.gender;
	if (scope.feeStatus) options.application_fee_status = scope.feeStatus;
	go(["List", "Applicant", "List"], { ...options, ...extra });
}

function categoryFilter(category) {
	return category === "Not set" ? ["is", "not set"] : category;
}

export function openReport(name, filters) {
	go(["query-report", name], filters);
}

export const statusIn = (statuses) => ["in", statuses];
