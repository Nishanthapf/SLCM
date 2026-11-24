// Shared helpers for the examination screens in this folder.
frappe.provide('slcm.exam_ui');

// Default picture for a student without a photo, or whose photo file is missing
slcm.exam_ui.USER_ICON =
	'<svg class="slcm-user-icon" viewBox="0 0 24 24" width="62%" height="62%" fill="none" stroke="currentColor"' +
	' stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
	'<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-7 8-7s8 2.6 8 7"/></svg>';

// <img> that falls back to the user icon, or the icon alone when there is no photo
slcm.exam_ui.avatar = function (url, attrs) {
	if (!url) return slcm.exam_ui.USER_ICON;
	return '<img src="' + frappe.utils.escape_html(url) + '" alt="" ' + (attrs || '') +
		' onerror="this.outerHTML = slcm.exam_ui.USER_ICON">';
};

// Consolidated Report: one Excel of results across plans / programmes / terms.
// Opened from the Examination workspace, the Exam Planner and the result pages.
slcm.exam_ui.consolidated_report = function (exam_plan) {
	var URL_ = '/api/method/slcm.slcm.page.term_result.term_result.download_consolidated_report';
	var FILTERS = [
		['exam_plan', __('Exam plan')], ['academic_year', __('Academic year')], ['programme', __('Programme')],
		['trimester', __('Trimester')], ['batch', __('Batch')],
	];
	var busy = false;

	var d = new frappe.ui.Dialog({
		title: __('Consolidated report'),
		size: 'large',
		fields: [
			{ fieldname: 'intro', fieldtype: 'HTML', options:
				'<p class="slcm-cr-intro">' + __('One Excel of student results: a sheet for everyone, plus one sheet per course. Pick at least one filter below.') + '</p>' },

			{ fieldtype: 'Section Break', label: __('What to include') },
			{ label: __('Report covers'), fieldname: 'report_type', fieldtype: 'Select', default: 'Bulk',
				options: [{ value: 'Bulk', label: __('All courses') }, { value: 'Course Based', label: __('One course') }],
				onchange: function () { refresh(); } },
			{ fieldtype: 'Column Break' },
			{ label: __('Course'), fieldname: 'course', fieldtype: 'Link', options: 'Course',
				depends_on: 'eval:doc.report_type=="Course Based"',
				mandatory_depends_on: 'eval:doc.report_type=="Course Based"',
				description: __('Only courses that match the filters below are listed.'),
				get_query: function () {
					return {
						query: 'slcm.slcm.page.examination_result.examination_result.course_link_query',
						filters: { exam_plan: d.get_value('exam_plan'), programme: d.get_value('programme'), trimester: d.get_value('trimester') },
					};
				},
				onchange: function () { refresh(); } },

			{ fieldtype: 'Section Break', label: __('Filters') },
			{ label: __('Exam plan'), fieldname: 'exam_plan', fieldtype: 'Link', options: 'Exam Plan', default: exam_plan || '',
				onchange: function () { clear_course(); refresh(); } },
			{ label: __('Programme'), fieldname: 'programme', fieldtype: 'Link', options: 'Programme',
				onchange: function () { if (d.get_value('trimester')) d.set_value('trimester', ''); clear_course(); refresh(); } },
			{ label: __('Batch'), fieldname: 'batch', fieldtype: 'Link', options: 'SLCM Batch',
				onchange: function () { refresh(); } },
			{ fieldtype: 'Column Break' },
			{ label: __('Academic year'), fieldname: 'academic_year', fieldtype: 'Link', options: 'Academic Year',
				onchange: function () { refresh(); } },
			{ label: __('Trimester'), fieldname: 'trimester', fieldtype: 'Link', options: 'Academic Term',
				description: __('Pick a Programme first to see only its trimesters.'),
				get_query: function () {
					return {
						query: 'slcm.slcm.page.examination_result.examination_result.trimester_link_query',
						filters: { programme: d.get_value('programme') },
					};
				},
				onchange: function () { clear_course(); refresh(); } },

			{ fieldtype: 'Section Break' },
			{ fieldname: 'summary', fieldtype: 'HTML' },
		],
		primary_action_label: __('Download Excel'),
		primary_action: function () { download(); },
		secondary_action_label: __('Clear filters'),
		secondary_action: function () {
			if (busy) return;
			FILTERS.forEach(function (f) { d.set_value(f[0], ''); });
			d.set_value('course', '');
			d.set_value('report_type', 'Bulk');
			refresh();
		},
	});
	d.$wrapper.addClass('slcm-cr-dialog er-theme');

	function clear_course() { if (d.get_value('course')) d.set_value('course', ''); }

	function chosen() {
		var v = d.get_values(true) || {};
		var args = {};
		FILTERS.forEach(function (f) { if (v[f[0]]) args[f[0]] = v[f[0]]; });
		if (v.report_type === 'Course Based' && v.course) args.course = v.course;
		return { v: v, args: args };
	}

	// The summary under the form says exactly what the file will hold, or what is missing
	function problem(c) {
		if (c.v.report_type === 'Course Based' && !c.v.course) return __('Pick the course, or set "Report covers" to All courses.');
		if (!Object.keys(c.args).filter(function (k) { return k !== 'course'; }).length && !c.args.course) return __('Pick at least one filter.');
		return null;
	}

	function refresh() {
		var c = chosen(), err = problem(c), e = frappe.utils.escape_html;
		var chips = FILTERS.filter(function (f) { return c.args[f[0]]; }).map(function (f) {
			return '<span class="slcm-cr-chip"><small>' + e(f[1]) + '</small>' + e(c.args[f[0]]) + '</span>';
		});
		chips.unshift('<span class="slcm-cr-chip on"><small>' + __('Courses') + '</small>' +
			e(c.v.report_type === 'Course Based' ? (c.v.course || '—') : __('All courses')) + '</span>');
		d.fields_dict.summary.$wrapper.html(
			'<div class="slcm-cr-summary ' + (err ? 'warn' : '') + '">' +
				'<div class="slcm-cr-summary-h">' + (err ? e(err) : __('The report will include')) + '</div>' +
				(err ? '' : '<div class="slcm-cr-chips">' + chips.join('') + '</div>') +
			'</div>'
		);
		d.get_primary_btn().prop('disabled', !!err || busy);
	}

	function set_busy(on) {
		busy = on;
		var $b = d.get_primary_btn();
		$b.prop('disabled', on).html(on
			? '<span class="slcm-cr-spin"></span>' + __('Preparing…')
			: __('Download Excel'));
		d.get_secondary_btn().prop('disabled', on);
		if (!on) refresh();
	}

	function show_error(msg) {
		d.fields_dict.summary.$wrapper.find('.slcm-cr-error').remove();
		d.fields_dict.summary.$wrapper.append('<div class="slcm-cr-error">' + frappe.utils.escape_html(msg) + '</div>');
	}

	function file_name(res, args) {
		var cd = res.headers.get('Content-Disposition') || '';
		var m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
		if (m) return decodeURIComponent(m[1]);
		var tag = (args.course || args.exam_plan || args.programme || 'Report').replace(/[^\w\-]+/g, '_');
		return 'Consolidated_' + tag + '_' + frappe.datetime.now_date() + '.xlsx';
	}

	function download() {
		if (busy) return;
		var c = chosen(), err = problem(c);
		if (err) { refresh(); return; }
		set_busy(true);
		d.fields_dict.summary.$wrapper.find('.slcm-cr-error').remove();
		var name;
		fetch(URL_ + '?' + $.param(c.args), {
			credentials: 'same-origin',
			headers: { 'X-Frappe-CSRF-Token': frappe.csrf_token || '' },
		})
			.then(function (res) {
				if (!res.ok) {
					return res.json().catch(function () { return {}; }).then(function (body) {
						var msg = __('The server could not build the report ({0}).', [res.status]);
						try {
							if (body && body._server_messages) {
								var first = JSON.parse(JSON.parse(body._server_messages)[0]);
								msg = $('<div>').html(first.message || msg).text();
							} else if (body && body.exception) {
								msg = body.exception.split(': ').pop();
							}
						} catch (e) { /* keep the generic message */ }
						throw new Error(msg);
					});
				}
				name = file_name(res, c.args);
				return res.blob();
			})
			.then(function (blob) {
				var a = document.createElement('a');
				a.href = URL.createObjectURL(blob);
				a.download = name;
				document.body.appendChild(a);
				a.click();
				a.remove();
				setTimeout(function () { URL.revokeObjectURL(a.href); }, 1000);
				set_busy(false);
				d.hide();
				frappe.show_alert({ message: __('Report downloaded: {0}', [frappe.utils.escape_html(name)]), indicator: 'green' });
			})
			.catch(function (e) {
				set_busy(false);
				// stay open with the filters kept, so the user can widen them and retry
				show_error(e && e.message ? e.message : __('Could not download the report. Please try again.'));
			});
	}

	if (!document.getElementById('slcm-cr-style')) {
		$('head').append('<style id="slcm-cr-style">' +
			'.slcm-cr-dialog .modal-body{padding-top:6px}' +
			'.slcm-cr-dialog .form-section{padding-top:4px!important;padding-bottom:4px!important}' +
			'.slcm-cr-dialog .form-section .section-head{font-size:11px;font-weight:700;letter-spacing:.5px;text-transform:uppercase;color:#920C24;margin:6px 0 2px;padding:0}' +
			'.slcm-cr-dialog .form-section + .form-section{border-top:1px solid var(--border-color,#eee)}' +
			'.slcm-cr-dialog .frappe-control{margin-bottom:10px}' +
			'.slcm-cr-dialog .help-box{font-size:11.5px}' +
			'.slcm-cr-intro{margin:0 0 4px;color:var(--text-muted);font-size:13px}' +
			'.slcm-cr-summary{border:1px solid #E8B4BE;background:#FBEEF0;border-radius:8px;padding:10px 12px}' +
			'.slcm-cr-summary.warn{border-color:#f3d19e;background:#fff8eb}' +
			'.slcm-cr-summary-h{font-size:12.5px;font-weight:600;color:#6E091B}' +
			'.slcm-cr-summary.warn .slcm-cr-summary-h{color:#8a5a00}' +
			'.slcm-cr-chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}' +
			'.slcm-cr-chip{display:inline-flex;align-items:baseline;gap:6px;background:#fff;border:1px solid #E8B4BE;border-radius:999px;padding:3px 10px;font-size:12px;font-weight:600;color:#1e293b;max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
			'.slcm-cr-chip small{font-size:10.5px;font-weight:600;color:#920C24;text-transform:uppercase;letter-spacing:.3px}' +
			'.slcm-cr-error{margin-top:8px;border:1px solid #fecaca;background:#fef2f2;color:#b91c1c;border-radius:8px;padding:9px 12px;font-size:12.5px;font-weight:500}' +
			'.slcm-cr-dialog .btn-primary{background:#920C24;border-color:#920C24;color:#fff}' +
			'.slcm-cr-dialog .btn-primary:hover:not(:disabled){background:#6E091B;border-color:#6E091B}' +
			'.slcm-cr-dialog .btn-primary:disabled{opacity:.55;cursor:not-allowed}' +
			'.slcm-cr-dialog .btn-secondary:hover:not(:disabled){color:#920C24;border-color:#920C24}' +
			'.slcm-cr-spin{display:inline-block;width:12px;height:12px;margin-right:7px;vertical-align:-1px;border:2px solid rgba(255,255,255,.45);border-top-color:#fff;border-radius:50%;animation:slcm-cr-spin .7s linear infinite}' +
			'@keyframes slcm-cr-spin{to{transform:rotate(360deg)}}' +
			'</style>');
	}

	d.show();
	refresh();
};
