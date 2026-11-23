// Uniquad Overall Dashboard — /desk/uniquad-overall-dashboard
//
// Every Uniquad module in one place — Admission, Student Registration,
// Programme Management, Attendance, ID Card, Fees, Venue Booking, PACE, FLE,
// Examinations, Transcripts and Promotion — laid out like the Pathways Overall Dashboard: filters →
// headline funnel → a board of single / paired cards (one section per module)
// → Timeline tab (one person, start to end) → Admission Funnel tab.
// Uniquad look: #920C24 + Merriweather.
//
// Every card and number opens a centred drilldown (per-programme cards, then
// a server-paged, sortable, searchable table with "Export all (CSV)").
// Clicking a person opens their timeline. All numbers come from
// permission-scoped server calls; every value rendered into HTML goes
// through esc().

const UOD_API = 'slcm.slcm.page.uniquad_overall_dashboard.uniquad_overall_dashboard.';
const UOD_STORE_KEY = 'uod-filters-v1';
const UOD_MODULE_KEY = 'uod-module-v1';
const UOD_ADM_KEY = 'uod-adm-v1';
const UOD_HIDE_KEY = 'uod-hide-empty-v1';
const UOD_COLLAPSE_KEY = 'uod-collapsed-v1';
const UOD_SCOPE_KEY = 'uod-scope-v2';
// Switches inside a module tab (section "scope" from the server; no scope = 'all').
// list: a paged table shown under that view, loaded the first time it is opened.
const UOD_SCOPES = {
	programme: [
		{ key: 'all', label: __('All programmes'), hint: __('Every programme, course, batch and faculty member') },
		{ key: 'nlsat', label: __('NLSAT'), hint: __('Programmes admitted through the NLSAT entrance test') },
		{ key: 'regular', label: __('Regular'), hint: __('Programmes admitted without the entrance test') },
		{ key: 'pace', label: __('PACE'), hint: __('PACE programmes, their courses, faculty and enrolments') }
	],
	attendance: [
		{ key: 'all', label: __('Sessions & attendance'), hint: __('Class sessions, attendance marked, eligibility and condonation') },
		{ key: 'rfid', label: __('RFID swipes'), hint: __('Card swipes from the RFID devices and how they matched to classes'),
			list: { kind: 'alog', title: __('All swipes in the selected dates'), sub: __('Newest first · search by card UID, student, device or terminal · export all'), export: 'rfid-swipes' } }
	]
};
// Admission types shown inside the Admission tab. sections = board section key;
// figs = [card, label] on the picker card; kpis = the few cards kept above the
// table; hide = cards left out of the table (already shown as cards);
// base = what the share column is a share of (Regular only).
const UOD_ADM_TYPES = [
	{ key: 'regular', label: 'Regular admission', icon: 'file', sections: 'admission', funnel: true, share: 'app',
		figs: [['ov_apps', __('Applications')], ['ov_reg_enr', __('Enrolled')], ['ov_reg_money', __('Received')]],
		kpis: [['iv_today', __('Interviews today')], ['iv_next7', __('Interviews in next 7 days')], ['appfee_pending', __('Application fee pending')], ['ov_reg_money', __('Money received')]],
		hide: ['iv_today', 'iv_next7'] },
	{ key: 'pace', label: 'PACE', icon: 'award', sections: 'pace', prefix: true,
		figs: [['ov_pace_apps', __('Applications')], ['ov_pace_enr', __('Enrolled')], ['ov_pace_money', __('Received')]],
		kpis: [['ov_pace_apps', __('Applications')], ['ov_pace_enr', __('Enrolled')], ['pdv_pending', __('Documents pending')], ['ov_pace_money', __('Money received')]],
		hide: [] },
	{ key: 'fle', label: 'FLE', icon: 'pen', sections: 'fle', prefix: true,
		figs: [['ov_fle', __('Registrations')], ['ov_fle_paid', __('Paid')], ['ov_fle_money', __('Received')]],
		kpis: [['ov_fle', __('Registrations')], ['ov_fle_paid', __('Paid')], ['fle_no_lms', __('Paid, no LMS account')], ['ov_fle_money', __('Money received')]],
		hide: [] }
];
// Icon per module tab (keys match MODULES in the .py; "overview" is the first tab).
const UOD_MODULE_ICONS = {
	overview: 'grid', admission: 'file', registration: 'users', programme: 'book', attendance: 'check',
	idcard: 'idcard', fees: 'coins', venue: 'door', pace: 'award', fle: 'pen', exams: 'clipboard',
	transcripts: 'filesign', promotion: 'send'
};
const UOD_LIST_FILTERS =['programmes', 'academic_years', 'admission_cycles', 'genders', 'categories', 'stages'];

// Tone = what a colour means (same everywhere on the page).
const UOD_TONES = {
	good: '#1d6b3a', bad: '#a4161a', action: '#8a5a00', info: '#2b4f7e', neutral: '#6B6560', time: '#920c24'
};
const UOD_STAGE_COLORS = {
	'Applying': '#8A8580', 'In process': '#2b4f7e', 'Waitlisted': '#8a5a00',
	'Offer / Admitted': '#1d6b3a', 'Not admitted': '#a4161a'
};
// Categorical slots for programmes (assigned in name order, always shown with the name).
const UOD_PALETTE = ['#920c24', '#2b4f7e', '#0f6b63', '#8a5a00', '#6d3b8c', '#3d4a5c', '#b0476b', '#4f7a28', '#c2541a', '#5b6b7a'];
const UOD_KIND_COLORS = {
	application: '#920c24', status: '#6B7A8A', payment: '#2F7D4F', test: '#4F46E5', interview: '#0891B2',
	merit: '#0D9488', seat: '#16A34A', offer: '#7C3AED', log: '#8A96A3', student: '#2F7D4F', idcard: '#A16207', onboarding: '#0D9488',
	fees: '#1d6b3a', attendance: '#2b4f7e', exams: '#920c24', transcript: '#6d3b8c', promotion: '#0f6b63'
};
const UOD_DAY_RANGES = [['0-7', '0–7 days'], ['8-15', '8–15 days'], ['16-30', '16–30 days'], ['31-60', '31–60 days'],
	['61-90', '61–90 days'], ['91-', '90+ days'], ['31-', 'Over 30 days']];

const UOD_ICONS = {
	users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
	file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M16 13H8"/><path d="M16 17H8"/>',
	mic: '<path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"/><path d="M19 10v2a7 7 0 0 1-14 0v-2"/><path d="M12 19v3"/>',
	calendar: '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
	clock: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
	award: '<circle cx="12" cy="8" r="6"/><path d="M15.48 12.89 17 22l-5-3-5 3 1.52-9.11"/>',
	xcircle: '<circle cx="12" cy="12" r="10"/><path d="m15 9-6 6M9 9l6 6"/>',
	check: '<path d="M20 6 9 17l-5-5"/>',
	clipboard: '<rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/><path d="m9 14 2 2 4-4"/>',
	pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4z"/>',
	coins: '<circle cx="8" cy="8" r="6"/><path d="M18.09 10.37A6 6 0 1 1 10.34 18"/><path d="M7 6h1v4"/>',
	send: '<path d="m22 2-7 20-4-9-9-4z"/><path d="M22 2 11 13"/>',
	handshake: '<path d="m11 17 2 2a1 1 0 1 0 3-3"/><path d="m14 14 2.5 2.5a1 1 0 1 0 3-3l-3.88-3.88a3 3 0 0 0-4.24 0l-.88.88a1 1 0 1 1-3-3l2.81-2.81a5.79 5.79 0 0 1 7.06-.87l.47.28a2 2 0 0 0 1.42.25L21 4"/><path d="m21 3 1 11h-2"/><path d="M3 3 2 14l6.5 6.5a1 1 0 1 0 3-3"/><path d="M3 4h8"/>',
	filesign: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="m9 15 2 2 4-4"/>',
	door: '<path d="M13 4h3a2 2 0 0 1 2 2v14"/><path d="M2 20h3"/><path d="M13 20h9"/><path d="M10 12v.01"/><path d="M13 4.56v16.88a.5.5 0 0 1-.6.49l-6.4-1.28A1 1 0 0 1 5 19.67V5.78a2 2 0 0 1 1.6-1.96l5.2-1.04a1 1 0 0 1 1.2.98z"/>',
	idcard: '<rect x="2" y="5" width="20" height="14" rx="2"/><circle cx="8" cy="12" r="2"/><path d="M14 10h4M14 14h4"/>',
	chevron: '<path d="m6 9 6 6 6-6"/>',
	unfold: '<path d="m7 15 5 5 5-5"/><path d="m7 9 5-5 5 5"/>',
	fold: '<path d="m7 20 5-5 5 5"/><path d="m7 4 5 5 5-5"/>',
	grid: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
	book: '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>',
	alert: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/>'
};
const uod_icon = (k) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${UOD_ICONS[k] || ''}</svg>`;

frappe.pages['uniquad-overall-dashboard'].on_page_load = function (wrapper) {
	if (!document.getElementById('uod-font')) {
		$('head').append('<link id="uod-font" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Merriweather:opsz,wght@18..144,300..900&display=swap">');
	}
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __('Uniquad Overall Dashboard'),
		single_column: true
	});
	wrapper.uod = new UniquadOverallDashboard(page, wrapper);
};

class UniquadOverallDashboard {
	constructor(page, wrapper) {
		this.page = page;
		this.$root = $(wrapper).find('.page-content');
		this.meta = null;
		this.data = null;
		this.funnel = null;
		this.filters = null;
		this.ms = {};
		this.tab = 'dash';
		this.module = this.read_pref(UOD_MODULE_KEY) || 'overview';
		this.adm = this.read_pref(UOD_ADM_KEY) || 'regular';
		this.adm_pick = {};   // admission type → programmes picked in its pane
		this.hide_empty = this.read_pref(UOD_HIDE_KEY) === '1';
		// Module → selected switch value (Programme management, Attendance).
		this.scope = (() => { try { return JSON.parse(this.read_pref(UOD_SCOPE_KEY) || '{}') || {}; } catch (e) { return {}; } })();
		const old_pm = this.read_pref('uod-pm-scope-v1');
		if (old_pm && !this.scope.programme) this.scope.programme = old_pm;
		// Collapsed table sections, "<admission type>|<section title>".
		this.collapsed = new Set((() => { try { return JSON.parse(this.read_pref(UOD_COLLAPSE_KEY) || '[]'); } catch (e) { return []; } })());
		// PACE and FLE used to be top-level tabs; they now live inside Admission.
		if (this.module === 'pace' || this.module === 'fle') { this.adm = this.module; this.module = 'admission'; }
		this.tl = { people: 'app', sort: 'creation', stage: '', status: '', pipeline: '', days: '' };
		this.render_shell();
		frappe.xcall(UOD_API + 'get_meta').then((meta) => {
			this.meta = meta;
			UOD_LIST_FILTERS.forEach(k => this.ms[k].set_options(meta.options[k] || []));
			const saved = this.read_saved() || {};
			UOD_LIST_FILTERS.forEach(k => this.ms[k].set_value(saved[k] || []));
			const [from_date, to_date] = this.preset_range('year');
			this.$root.find('#uod-from').val(from_date);
			this.$root.find('#uod-to').val(to_date);
			this.load(this.current_filters());
		});
	}

	// ── helpers ────────────────────────────────────────────────────────────
	esc(v) { return frappe.utils.escape_html(v === null || v === undefined ? '' : String(v)); }
	n(v) { return v === null || v === undefined ? '—' : Number(v).toLocaleString('en-IN'); }
	pct(a, b) { return b ? Math.round((a / b) * 1000) / 10 : 0; }
	pct_txt(a, b) {
		if (!b) return '0%';
		const p = (a / b) * 100;
		return a && p < 0.1 ? '<0.1%' : `${Math.round(p * 10) / 10}%`;
	}
	fmt_date(d) { return d ? frappe.datetime.str_to_user(String(d).slice(0, 10)) : ''; }
	fmt_dt(d) { return d ? frappe.datetime.str_to_user(String(d)).replace(/(\d{1,2}:\d{2}):\d{2}(\.\d+)?$/, '$1') : ''; }
	prog_name(p) { return (this.data && this.data.programme_names[p]) || p || __('Not set'); }
	prog_color(p) {
		const names = Object.keys((this.data && this.data.programme_names) || {}).sort();
		const i = names.indexOf(p);
		return i < 0 ? '#64748B' : UOD_PALETTE[i % UOD_PALETTE.length];
	}
	prog_pill(p) { return `<span class="uod-pill" style="--c:${this.prog_color(p)}">${this.esc(this.prog_name(p))}</span>`; }
	stage_pill(s) { return s ? `<span class="uod-pill" style="--c:${UOD_STAGE_COLORS[s] || '#64748B'}">${this.esc(s)}</span>` : ''; }
	slug(dt) { return String(dt || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''); }
	desk_link(dt, name) { return `/desk/${this.slug(dt)}/${encodeURIComponent(name)}`; }

	read_saved() {
		try { return JSON.parse(localStorage.getItem(UOD_STORE_KEY) || 'null'); } catch (e) { return null; }
	}
	read_pref(k) {
		try { return localStorage.getItem(k) || null; } catch (e) { return null; }
	}
	save_pref(k, v) {
		try { localStorage.setItem(k, v); } catch (e) { /* private mode etc. */ }
	}
	// Dates are deliberately not remembered: the page always opens on "This year".
	save_filters(f) {
		try {
			const keep = {};
			UOD_LIST_FILTERS.forEach(k => { keep[k] = f[k] || []; });
			localStorage.setItem(UOD_STORE_KEY, JSON.stringify(keep));
		} catch (e) { /* private mode etc. */ }
	}

	// ── layout ─────────────────────────────────────────────────────────────
	render_shell() {
		const ms = (k, label, ph) => `<div class="uod-f"><label>${label}</label><div class="uod-ms" id="uod-ms-${k}" data-placeholder="${ph}"></div></div>`;
		const panel = (id, title, sub, tools = '', body = `<div class="uod-panel-body" id="${id}"></div>`) => `
			<div class="uod-panel">
				<div class="uod-panel-head"><div><div class="uod-panel-title">${title}</div><div class="uod-panel-sub">${sub}</div></div>${tools}</div>
				${body}
			</div>`;
		this.$root.html(`
			<style>${UOD_CSS}</style>
			<div class="uod-root">
				<div class="uod-tabs" role="tablist">
					<button class="uod-tab is-on" data-tab="dash" role="tab">${__('Dashboard')}</button>
					<button class="uod-tab" data-tab="timeline" role="tab">${__('Timeline')}</button>
					<button class="uod-tab" data-tab="funnel" role="tab">${__('Admission Funnel')}</button>
				</div>
				<div class="uod-filters">
					<div class="uod-topbar">
						<div class="uod-presets">
							${[['month', __('This month')], ['last30', __('Last 30 days')], ['last90', __('Last 90 days')],
								['year', __('This year')], ['all', __('All time')]]
								.map(([k, l]) => `<button class="uod-preset" data-p="${k}">${l}</button>`).join('')}
						</div>
						<div class="uod-topbar-right">
							<span class="uod-muted" title="${__('Ignores every filter')}">${__('All-time applications')}: <b id="uod-alltime">—</b></span>
							<span class="uod-muted" id="uod-sub"></span>
							<button class="btn btn-default btn-xs" id="uod-guide">ⓘ ${__('Card guide')}</button>
							<button class="btn btn-default btn-xs" id="uod-refresh">⟳ ${__('Refresh')}</button>
						</div>
					</div>
					<div class="uod-filter-row">
						<div class="uod-f"><label>${__('Created from')}</label><input type="date" id="uod-from"></div>
						<div class="uod-f"><label>${__('To')}</label><input type="date" id="uod-to"></div>
						${ms('programmes', __('Programme'), __('All programmes'))}
						${ms('academic_years', __('Academic year'), __('All years'))}
						${ms('admission_cycles', __('Admission cycle'), __('All cycles'))}
						${ms('genders', __('Gender'), __('All genders'))}
						${ms('categories', __('Category'), __('All categories'))}
						${ms('stages', __('Stage'), __('All stages'))}
						<div class="uod-f uod-f-btns">
							<button class="btn btn-primary btn-sm" id="uod-apply">${__('Apply')}</button>
							<button class="btn btn-default btn-sm" id="uod-reset">${__('Reset')}</button>
						</div>
					</div>
				</div>

				<div class="uod-pane" data-pane="dash">
					<div class="uod-mnav-wrap" id="uod-mnav-wrap">
						<button class="uod-mnav-arrow is-left" data-dir="-1" tabindex="-1" aria-label="${__('Scroll tabs left')}" hidden>‹</button>
						<div class="uod-mnav" id="uod-mnav" role="tablist" aria-label="${__('Modules')}"></div>
						<button class="uod-mnav-arrow is-right" data-dir="1" tabindex="-1" aria-label="${__('Scroll tabs right')}" hidden>›</button>
					</div>
					<div class="uod-mpanes" id="uod-mpanes"></div>
				</div>

				<div class="uod-pane" data-pane="timeline" hidden>
					<div class="uod-panel">
						<div class="uod-panel-head"><div>
							<div class="uod-panel-title">${__('Student journey timeline')}</div>
							<div class="uod-panel-sub">${__('Everyone matching the filters above · search, then click a name to open their timeline, start to end')}</div>
						</div></div>
						<div class="uod-tl-tools" id="uod-tl-tools"></div>
						<div id="uod-tl-list"></div>
					</div>
				</div>

				<div class="uod-pane" data-pane="funnel" hidden>
					${panel('uod-funbars', __('Admission funnel'), __('How many applicants reach each step · bar length = share of all applications · click a step for its list'))}
					${panel('uod-fununits', __('Funnel by programme'), __('The same steps for each programme · % = share of the step before · click a number for its list'), '',
						'<div class="uod-table-scroll" id="uod-fununits"></div>')}
					${panel('uod-pipe', __('Pipeline & offers'), __('How long applicants have been in the process, and where offers stand · click any number or bar for its list'))}
					${panel('uod-prog', __('Programme summary'), __('Applications → admitted → registered, per programme · every number opens its list'),
						`<div class="uod-panel-tools"><button class="btn btn-default btn-xs" id="uod-export-prog">${__('Export CSV')}</button></div>`,
						'<div class="uod-table-scroll" id="uod-prog"></div>')}
					${panel('uod-profile', __('Who is applying'), __('Category, gender, source and state of the applications in scope · click a bar or slice for its list'))}
					${panel('uod-iv', __('Interviews'), __('Every interview slot — past, upcoming and cancelled · filtered by interview date'), this.range_tools())}
					${panel('uod-apps', __('All applications'), __('Every application in scope, newest first · page, sort, search and export all of them'))}
					${panel('uod-regs', __('Student registrations'), __('Every student record in scope and where it is in the registration chain'))}
					<div id="uod-log-wrap" style="display:none">
						${panel('uod-log', __('Admission change log'), __('Every admission audit entry (what changed, from → to, who, when, why) in the selected dates'))}
					</div>
					<div class="uod-grid-2">
						${panel('uod-stages', __('Where applicants are'), __('Current stage of every application in scope · click a bar for the list'))}
						${panel('uod-trend', __('Applications per week'), __('Week starting Monday · hover for numbers · click a bar for that week'))}
					</div>
				</div>
				<div class="uod-tip" id="uod-tip"></div>
			</div>
		`);

		const $c = this.$root;
		UOD_LIST_FILTERS.forEach(k => { this.ms[k] = this.make_multiselect($c.find(`#uod-ms-${k}`)); });
		$c.find('#uod-apply').on('click', () => { this.load(this.current_filters()); });
		$c.find('#uod-refresh').on('click', () => { this.load(this.filters || this.current_filters(), true); });
		$c.find('#uod-reset').on('click', () => {
			Object.values(this.ms).forEach(m => m.clear());
			const [f, t] = this.preset_range('year');
			$c.find('#uod-from').val(f);
			$c.find('#uod-to').val(t);
			this.load(this.current_filters());
		});
		// A preset is one click = the user is done choosing → apply at once.
		$c.find('.uod-preset:not(.uod-rpreset)').on('click', (e) => {
			const [f, t] = this.preset_range($(e.currentTarget).data('p'));
			$c.find('#uod-from').val(f || '');
			$c.find('#uod-to').val(t || '');
			this.load(this.current_filters());
		});
		$c.find('#uod-guide').on('click', () => { this.open_guide(); });
		const nav = $c.find('#uod-mnav')[0];
		$c.find('.uod-mnav-arrow').on('click', (e) => {
			nav.scrollBy({ left: Number($(e.currentTarget).data('dir')) * Math.max(200, nav.clientWidth * 0.6), behavior: 'smooth' });
		});
		$(nav).on('scroll', () => { this.update_arrows(); });
		// Namespaced so it is tied to this page and cannot pile up.
		$(window).off('resize.uod').on('resize.uod', frappe.utils.debounce(() => { this.update_arrows(); }, 120));
		$c.find('.uod-tab').on('click', (e) => { this.show_tab(String($(e.currentTarget).data('tab'))); });
		$(document).on('click.uod', (e) => {
			if (!$(e.target).closest('.uod-ms').length) $('.uod-ms.open').removeClass('open');
		});
		this.bind_tip($c);
	}

	preset_range(p) {
		const today = frappe.datetime.get_today();
		const d = frappe.datetime;
		if (p === 'month') return [d.month_start(), today];
		if (p === 'last30') return [d.add_days(today, -29), today];
		if (p === 'last90') return [d.add_days(today, -89), today];
		if (p === 'year') return [today.slice(0, 4) + '-01-01', today];
		return ['', ''];
	}
	current_filters() {
		const f = { from_date: this.$root.find('#uod-from').val() || null, to_date: this.$root.find('#uod-to').val() || null };
		UOD_LIST_FILTERS.forEach(k => { f[k] = this.ms[k].get_value(); });
		return f;
	}
	mark_preset() {
		const f = this.filters || {};
		let on = null;
		['month', 'last30', 'last90', 'year', 'all'].forEach(p => {
			const [a, b] = this.preset_range(p);
			if ((a || null) === (f.from_date || null) && (b || null) === (f.to_date || null)) on = p;
		});
		this.$root.find('.uod-preset:not(.uod-rpreset)').each((_i, el) => { $(el).toggleClass('is-on', $(el).data('p') === on); });
	}

	// Searchable multi-select with chips (no Frappe control: these filter
	// values come from three different DocTypes).
	// on_change (optional) runs, debounced, after the user changes the picks.
	make_multiselect($el, on_change = null) {
		const ph = $el.data('placeholder');
		let options = [];
		let value = [];
		const emit = on_change ? frappe.utils.debounce(() => on_change(value.slice()), 350) : () => {};
		$el.html(`<div class="uod-ms-box"></div>
			<div class="uod-ms-panel">
				<div class="uod-ms-search"><input type="text" placeholder="${__('Search')}"></div>
				<div class="uod-ms-actions"><a data-a="all">${__('Select all')}</a><a data-a="none">${__('Clear')}</a></div>
				<div class="uod-ms-list"></div>
			</div>`);
		const $box = $el.find('.uod-ms-box');
		const $list = $el.find('.uod-ms-list');
		const $q = $el.find('.uod-ms-search input');
		const label_of = (v) => (options.find(o => o.value === v) || { label: v }).label;
		const draw_box = () => {
			if (!value.length) { $box.html(`<span class="uod-ms-ph">${this.esc(ph)}</span>`); return; }
			const chips = value.slice(0, 2).map(v => `<span class="uod-ms-chip"><span class="txt">${this.esc(label_of(v))}</span><span class="x" data-v="${this.esc(v)}">×</span></span>`).join('');
			$box.html(chips + (value.length > 2 ? `<span class="uod-ms-more">+${value.length - 2}</span>` : ''));
		};
		const draw_list = () => {
			const q = ($q.val() || '').toLowerCase();
			const shown = options.filter(o => !q || String(o.label).toLowerCase().includes(q) || String(o.value).toLowerCase().includes(q));
			$list.html(shown.length ? shown.map(o => `<label class="uod-ms-opt"><input type="checkbox" value="${this.esc(o.value)}" ${value.includes(o.value) ? 'checked' : ''}> ${this.esc(o.label)}</label>`).join('')
				: `<div class="uod-ms-empty">${__('No matches')}</div>`);
		};
		$box.on('click', (e) => {
			const $x = $(e.target).closest('.x');
			if ($x.length) {
				value = value.filter(v => v !== String($x.attr('data-v')));
				draw_box(); draw_list(); emit();
				e.stopPropagation();
				return;
			}
			$('.uod-ms.open').not($el).removeClass('open');
			$el.toggleClass('open');
			if ($el.hasClass('open')) { draw_list(); $q.trigger('focus'); }
		});
		$q.on('input', () => { draw_list(); });
		$list.on('change', 'input', (e) => {
			const v = e.target.value;
			value = e.target.checked ? value.concat([v]) : value.filter(x => x !== v);
			draw_box(); emit();
		});
		$el.find('.uod-ms-actions a').on('click', (e) => {
			const a = $(e.currentTarget).data('a');
			value = a === 'all' ? options.map(o => o.value) : [];
			draw_box(); draw_list(); emit();
		});
		draw_box();
		return {
			set_options: (o) => { options = o || []; value = value.filter(v => options.some(x => x.value === v)); draw_box(); },
			set_value: (v) => { value = (v || []).filter(x => options.some(o => o.value === x)); draw_box(); },
			get_value: () => value.slice(),
			clear: () => { value = []; draw_box(); }
		};
	}

	// ── data ───────────────────────────────────────────────────────────────
	load(filters, refresh = false) {
		this.filters = filters;
		this.save_filters(filters);
		this.mark_preset();
		this.funnel = null;
		const $r = this.$root.find('.uod-root').addClass('uod-loading');
		frappe.xcall(UOD_API + 'get_dashboard_data', { filters, refresh: refresh ? 1 : 0 }).then((data) => {
			this.data = data;
			$r.removeClass('uod-loading');
			this.$root.find('#uod-alltime').text(this.n(data.alltime));
			this.$root.find('#uod-sub').text(`${__('Updated')} ${data.updated}`);
			this.render_board();
			if (this.tab === 'timeline') this.render_timeline_tab();
			if (this.tab === 'funnel') this.render_funnel_tab(refresh);
		}).catch(() => { $r.removeClass('uod-loading'); });
	}

	show_tab(tab) {
		this.tab = tab;
		this.$root.find('.uod-tab').each((_i, el) => { $(el).toggleClass('is-on', $(el).data('tab') === tab); });
		this.$root.find('.uod-pane').each((_i, el) => { el.hidden = $(el).data('pane') !== tab; });
		if (!this.data) return;
		if (tab === 'timeline') this.render_timeline_tab();
		if (tab === 'funnel') this.render_funnel_tab();
	}

	// ── dashboard tab ──────────────────────────────────────────────────────
	card_data(key) { return (this.data.cards || {})[key]; }
	card_count(key) { const d = this.card_data(key); return d ? d.total : null; }
	// null = the user cannot read that DocType: the card shows "—" and is not clickable.
	allowed(key) { return this.card_data(key) !== null && this.card_data(key) !== undefined; }
	base_of(card) {
		if (!card.pct) return null;
		const t = (this.data.totals || {})[card.kind];
		return t === undefined ? null : t;
	}
	money(v) { return format_currency(v || 0, frappe.boot.sysdefaults.currency || 'INR', 0); }
	unused(c) { const d = this.card_data(c.key); return !!(d && d.unused); }
	sub_of(c) {
		const d = this.card_data(c.key);
		if (d && d.unused) return __('not recorded in Uniquad yet');
		if (c.sum && d && d.amount !== null && d.amount !== undefined) return this.money(d.amount);
		if (c.sub) return c.sub;
		if (!c.pct) return '';
		return c.kind === 'stu' ? __('of student records') : __('of total applications');
	}
	info_html(text) {
		return text ? `<span class="uod-info" data-tip="${this.esc(text)}" tabindex="0" aria-label="${this.esc(text)}">i</span>` : '';
	}
	share_html(v, base) {
		return base === null ? '' : `<span class="uod-share">${this.pct_txt(v, base)}</span>`;
	}
	dot(card) {
		return ['good', 'bad'].includes(card.tone) ? `<span class="uod-dot" style="--c:${UOD_TONES[card.tone]}"></span>` : '';
	}

	// Regular admission funnel (headline): shown on Overview and on the Admission tab.
	// Value of a card for the programmes picked in an admission pane (none = all).
	// split=false: the card's records carry no programme, so it cannot be narrowed.
	fv(key, picks) {
		const c = this.find_card(key);
		const d = this.card_data(key);
		if (!c || !d) return { total: null, amount: null, split: true };
		if (!picks || !picks.length) return { total: d.total, amount: d.amount, split: true };
		if (!(this.meta.sources[c.kind] || {}).grouped) return { total: null, amount: null, split: false };
		const by = d.by || {};
		const ba = d.by_amount;
		return {
			total: picks.reduce((a, p) => a + (by[p] || 0), 0),
			amount: ba ? picks.reduce((a, p) => a + (ba[p] || 0), 0) : null,
			split: true
		};
	}
	ps_attr(picks) { return picks && picks.length ? ` data-ps="${this.esc(JSON.stringify(picks))}"` : ''; }

	// Regular admission funnel (headline): Overview and the Admission tab (narrowed by picks there).
	funnel_html(picks = []) {
		const base = this.fv('ov_apps', picks).total;
		const html = this.meta.headline.map((c) => {
			const ok = this.allowed(c.key);
			const v = ok ? this.fv(c.key, picks).total : null;
			const aside = c.key === 'not_admitted' ? ' is-aside' : '';
			return `<div class="uod-kpi${ok ? ' is-click' : ''}${aside}" ${ok ? `data-card="${c.key}" tabindex="0" role="button"${this.ps_attr(picks)}` : ''}>
				<div class="uod-kpi-top"><span class="uod-kpi-label">${this.dot(c)}${this.esc(c.label)}</span>${this.info_html(c.guide)}</div>
				<div class="uod-kpi-value" style="${c.tone === 'action' || c.tone === 'time' ? `color:${UOD_TONES[c.tone]}` : ''}">${this.n(v)}${v === null || base === null ? '' : this.share_html(v, base)}</div>
				<div class="uod-kpi-sub">${this.esc(c.sub)}</div>
			</div>`;
		}).join('');
		return `<div class="uod-section"><div class="uod-section-title"><span>${__('Regular admission funnel')}</span></div>
			<div class="uod-headline is-funnel">${html}</div></div>`;
	}

	// Tiles of a section the user can read at least one card of.
	visible_tiles(sec) { return sec.tiles.filter(t => t.cards.some(c => this.allowed(c.key))); }

	section_html(sec, show_title, cls = '') {
		const tiles = this.visible_tiles(sec);
		if (!tiles.length) return '';
		const note = sec.key === 'registration' && show_title
			? `<span class="uod-section-note">${this.n(this.data.stu_total)} ${__('student records in scope')}</span>` : '';
		const title = show_title ? `<div class="uod-section-title"><span>${this.esc(sec.title)}</span>${note}</div>` : '';
		return `<div class="uod-section">${title}<div class="uod-tiles ${cls}">${tiles.map(t => this.tile_html(t)).join('')}</div></div>`;
	}

	module_head(key, label, sub) {
		return `<div class="uod-mhead">
			<div class="uod-mhead-ico">${uod_icon(UOD_MODULE_ICONS[key] || 'grid')}</div>
			<div><div class="uod-mhead-title">${this.esc(label)}</div><div class="uod-mhead-sub">${sub}</div></div>
		</div>`;
	}

	// Value of one figure for the small summary blocks (money cards show ₹).
	fig_value(key) {
		const c = this.find_card(key);
		const d = this.card_data(key);
		if (!c || !d) return '—';
		return c.money ? this.money(d.amount) : this.n(d.total);
	}

	// ── Overview pane ──
	overview_html() {
		const secs = this.meta.board.filter(s => s.key === 'overview');
		const parts = secs.map((s, i) => this.section_html(s, true, i === 0 ? 'is-ov' : 'is-wide'));
		parts.push(this.funnel_html());
		// One snapshot card per module: its first figures + a link to the module tab.
		const snaps = this.module_tabs().filter(m => m.key !== 'admission').map((m) => {
			const cards = [];
			this.meta.board.filter(s => s.key === m.key).forEach(s => this.visible_tiles(s).forEach(t => t.cards.forEach(c => {
				if (cards.length < 2 && this.allowed(c.key)) cards.push(c);
			})));
			const figs = cards.map(c => {
				const v = this.card_count(c.key);
				const color = c.tone === 'action' && v && !this.unused(c) ? ` style="color:${UOD_TONES.action}"` : '';
				return `<div class="uod-snap-fig is-click" data-card="${c.key}" tabindex="0" role="button">
					<b${color}>${this.unused(c) ? '—' : (c.money ? this.money((this.card_data(c.key) || {}).amount) : this.n(v))}</b>
					<span>${this.esc(c.label)}</span></div>`;
			}).join('');
			return `<div class="uod-snap">
				<button class="uod-snap-head" data-goto="${m.key}">
					<span class="uod-snap-ico">${uod_icon(UOD_MODULE_ICONS[m.key] || 'grid')}</span>
					<span class="uod-snap-name">${this.esc(m.label)}</span><span class="uod-snap-go" aria-hidden="true">›</span>
				</button>
				<div class="uod-snap-figs">${figs}</div>
			</div>`;
		}).join('');
		if (snaps) {
			parts.push(`<div class="uod-section"><div class="uod-section-title"><span>${__('Modules')}</span>
				<span class="uod-section-note">${__('click a number for its list, or a module name to open it')}</span></div>
				<div class="uod-snaps">${snaps}</div></div>`);
		}
		return parts.join('');
	}

	// ── Admission pane: pick an admission type, see its cards ──
	adm_types() {
		const visible = (k) => this.meta.board.some(s => s.key === k && this.visible_tiles(s).length);
		return UOD_ADM_TYPES.filter(t => visible(t.sections));
	}

	admission_html() {
		const types = this.adm_types();
		if (!types.some(t => t.key === this.adm)) this.adm = types.length ? types[0].key : null;
		const picker = types.map((t) => {
			const on = t.key === this.adm;
			const figs = t.figs.filter(([k]) => this.allowed(k)).map(([k, label]) =>
				`<span class="uod-adm-fig"><b>${this.fig_value(k)}</b><small>${this.esc(label)}</small></span>`).join('');
			return `<button class="uod-adm${on ? ' is-on' : ''}" role="tab" data-adm="${t.key}" aria-selected="${on}" tabindex="${on ? 0 : -1}">
				<span class="uod-adm-top"><span class="uod-adm-ico">${uod_icon(t.icon)}</span><span class="uod-adm-name">${this.esc(__(t.label))}</span></span>
				<span class="uod-adm-figs">${figs}</span>
			</button>`;
		}).join('');
		const panes = types.map((t) => `<div class="uod-adm-pane" data-adm="${t.key}" role="tabpanel" ${t.key === this.adm ? '' : 'hidden'}>
				${this.adm_toolbar(t)}<div class="uod-adm-body" data-adm="${t.key}">${this.type_body(t)}</div>
			</div>`).join('');
		return this.module_head('admission', __('Admission'), __('Choose an admission type · click any number for the list behind it'))
			+ `<div class="uod-adm-pick" role="tablist" aria-label="${__('Admission type')}">${picker}</div>` + panes;
	}

	adm_secs(t) { return this.meta.board.filter(s => s.key === t.sections); }

	// Programmes an admission type's records are split by: {key: records}.
	adm_units(t) {
		const units = {};
		// Regular admission records carry a Programme: offer every programme, even with no records yet.
		if (t.key === 'regular' && this.allowed('ov_apps')) {
			((this.meta.options || {}).programmes || []).forEach((o) => { units[o.value] = 0; });
		}
		const keys = [].concat(...this.adm_secs(t).map(s => [].concat(...s.tiles.map(x => x.cards.map(c => c.key)))))
			.concat(t.kpis.map(([k]) => k), t.funnel ? this.meta.headline.map(c => c.key) : []);
		keys.forEach((k) => {
			const c = this.find_card(k);
			if (!c || !this.allowed(k) || !(this.meta.sources[c.kind] || {}).grouped) return;
			Object.entries((this.card_data(k) || {}).by || {}).forEach(([p, v]) => { units[p] = Math.max(units[p] || 0, v); });
		});
		return units;
	}

	adm_toolbar(t) {
		const has_units = Object.keys(this.adm_units(t)).length > 0;
		return `<div class="uod-adm-tools" data-adm="${t.key}">
			${has_units ? `<div class="uod-f uod-adm-prog"><label>${__('Programme')}</label><div class="uod-ms" data-placeholder="${__('All programmes')}"></div></div>` : ''}
			<label class="uod-switch"><input type="checkbox" class="uod-hide-empty" ${this.hide_empty ? 'checked' : ''}><span class="uod-switch-track" aria-hidden="true"></span><span>${__('Hide rows with no records')}</span></label>
			<span class="uod-muted uod-adm-scope"></span>
		</div>`;
	}

	// Wire the programme pickers after the Admission pane is (re)drawn.
	init_adm_tools() {
		this.adm_types().forEach((t) => {
			const $tools = this.$root.find(`.uod-adm-tools[data-adm="${t.key}"]`);
			const $ms = $tools.find('.uod-adm-prog .uod-ms');
			if ($ms.length) {
				const units = this.adm_units(t);
				const ms = this.make_multiselect($ms, (v) => { this.adm_pick[t.key] = v; this.refresh_adm(t.key); });
				ms.set_options(Object.keys(units).sort((a, b) => this.unit_label(a).localeCompare(this.unit_label(b)))
					.map(k => ({ value: k, label: this.unit_label(k) })));
				ms.set_value(this.adm_pick[t.key] || []);
				// Picks that no longer exist after a filter change are dropped.
				this.adm_pick[t.key] = ms.get_value();
			} else {
				this.adm_pick[t.key] = [];
			}
			this.draw_adm_scope(t);
		});
		this.$root.find('.uod-hide-empty').on('change', (e) => {
			this.hide_empty = e.target.checked;
			this.save_pref(UOD_HIDE_KEY, this.hide_empty ? '1' : '0');
			this.$root.find('.uod-hide-empty').prop('checked', this.hide_empty);
			this.adm_types().forEach(t => this.refresh_adm(t.key));
		});
	}

	draw_adm_scope(t) {
		const picks = this.adm_pick[t.key] || [];
		const n = Object.keys(this.adm_units(t)).length;
		this.$root.find(`.uod-adm-tools[data-adm="${t.key}"] .uod-adm-scope`).text(!n ? __('{0} is not split by programme', [__(t.label)])
			: picks.length ? __('Showing {0} of {1} programmes', [picks.length, n]) : __('All {0} programmes', [n]));
	}

	refresh_adm(key) {
		const t = this.adm_types().find(x => x.key === key);
		if (!t) return;
		const $body = this.$root.find(`.uod-adm-body[data-adm="${key}"]`).html(this.type_body(t));
		this.bind_cards($body);
		this.draw_adm_scope(t);
	}

	// One admission type: the funnel (Regular), a row of key cards, then every
	// other card as one row of the status × programme table.
	type_body(t) {
		const picks = this.adm_pick[t.key] || [];
		const out = [];
		if (t.funnel) out.push(this.funnel_html(picks));
		out.push(this.kpi_row(t.kpis, picks));
		const groups = this.adm_secs(t).map(s => ({
			title: String(s.title).replace(new RegExp('^' + t.label + '\\s*·\\s*', 'i'), ''),
			rows: [].concat(...this.visible_tiles(s).map(tile => tile.cards.map(c => ({ c, tile }))))
				.filter(r => this.allowed(r.c.key) && !t.hide.includes(r.c.key))
		})).filter(g => g.rows.length);
		if (groups.length) {
			const split = Object.keys(this.adm_units(t)).length > 0;
			const title = t.funnel ? __('Applications by status and programme') : (split ? __('Status by programme') : __('Status'));
			const table = this.status_table(groups, { prefix: !!t.prefix, share: t.share, picks, hide_empty: this.hide_empty, type: t.key });
			// Section buttons only when the table has sections to open / close.
			const fold = table.includes('uod-st-group') ? `<span class="uod-adm-fold" role="group" aria-label="${__('Table sections')}">
				<button type="button" data-fold="open" title="${__('Open every section of the table')}">${uod_icon('unfold')}<span>${__('Expand all')}</span></button>
				<button type="button" data-fold="close" title="${__('Close every section of the table')}">${uod_icon('fold')}<span>${__('Collapse all')}</span></button>
			</span>` : '';
			out.push(`<div class="uod-section"><div class="uod-section-title uod-st-title"><span>${title}</span>
				<span class="uod-section-note">${__('click a row for its list')}</span>${fold}</div>
				${table}</div>`);
		}
		return out.join('');
	}

	// A row of simple cards (value + one line); money cards show ₹ first.
	kpi_row(kpis, picks = []) {
		const cells = (kpis || []).filter(([k]) => this.find_card(k)).map(([k, label]) => {
			const c = this.find_card(k);
			const ok = this.allowed(k);
			const f = ok ? this.fv(k, picks) : { total: null, amount: null, split: true };
			const v = f.total;
			let value = '—';
			let sub = __('No access');
			if (ok && !f.split) { sub = __('not split by programme'); }
			else if (ok) {
				value = c.money ? (f.amount === null ? '—' : this.money(f.amount)) : this.n(v);
				sub = c.money ? `${this.n(v)} ${v === 1 ? __('payment') : __('payments')}` : (c.sub || (c.tone === 'action' ? __('needs action') : ''));
			}
			const click = ok && f.split;
			const color = click && v && ['action', 'time'].includes(c.tone) ? ` style="color:${UOD_TONES[c.tone]}"` : '';
			return `<div class="uod-kpi${click ? ' is-click' : ' is-denied'}" ${click ? `data-card="${k}" tabindex="0" role="button"${this.ps_attr(picks)}` : ''}>
				<div class="uod-kpi-top"><span class="uod-kpi-label">${this.esc(label)}</span>${this.info_html(c.guide)}</div>
				<div class="uod-kpi-value"${color}>${value}</div>
				<div class="uod-kpi-sub">${this.esc(sub)}</div>
			</div>`;
		}).join('');
		return cells ? `<div class="uod-section"><div class="uod-kpis">${cells}</div></div>` : '';
	}

	// groups: [{title, rows: [{c: card, tile}]}]. Columns: the picked programmes, or
	// (none picked) the 6 biggest + "Other". Rows whose records carry no programme
	// leave the programme cells blank.
	status_table(groups, opts = {}) {
		const MAX_COLS = 6;
		const picks = opts.picks || [];
		const grouped = (c) => !!(this.meta.sources[c.kind] || {}).grouped;
		let cols = [];
		let other = [];
		if (picks.length) {
			cols = picks.slice().sort((a, b) => this.unit_label(a).localeCompare(this.unit_label(b)));
		} else {
			const sums = {};
			groups.forEach(g => g.rows.forEach(({ c }) => {
				if (!grouped(c) || this.unused(c)) return;
				Object.entries((this.card_data(c.key) || {}).by || {}).forEach(([p, v]) => { if (v) sums[p] = (sums[p] || 0) + v; });
			}));
			const ranked = Object.keys(sums).sort((a, b) => sums[b] - sums[a] || this.unit_label(a).localeCompare(this.unit_label(b)));
			cols = ranked.length > MAX_COLS + 1 ? ranked.slice(0, MAX_COLS) : ranked;
			other = ranked.length > MAX_COLS + 1 ? ranked.slice(MAX_COLS) : [];
		}
		const has_amount = groups.some(g => g.rows.some(({ c }) => c.sum));
		const base = opts.share === 'app' ? this.fv('ov_apps', picks).total : null;
		const ncols = 1 + cols.length + (other.length ? 1 : 0) + 1 + (has_amount ? 1 : 0) + (opts.share ? 1 : 0);
		const ZERO = '<span class="uod-st-zero">–</span>';
		const NA = `<span class="uod-st-na" title="${__('These records are not linked to a programme')}"></span>`;
		const num = (key, v, ps) => v
			? `<a class="uod-st-num" data-card="${key}"${this.ps_attr(ps)} tabindex="0" role="button">${this.n(v)}</a>` : ZERO;
		let blank_note = false;
		let shown = 0;

		const body = groups.map((g, gi) => {
			const gkey = `${opts.type || ''}|${g.title}`;
			const closed = this.collapsed.has(gkey);
			let g_rows = 0;
			let g_action = 0;
			const rows = g.rows.map(({ c, tile }) => {
				const d = this.card_data(c.key) || {};
				const by = d.by || {};
				const f = this.fv(c.key, picks);
				const unused = this.unused(c);
				if (opts.hide_empty && (unused || !f.split || !f.total)) return '';
				shown += 1;
				g_rows += 1;
				const split = grouped(c);
				if (!split && (cols.length || other.length)) blank_note = true;
				const label = opts.prefix && String(tile.title).toLowerCase() !== String(c.label).toLowerCase()
					? `<span class="uod-st-pre">${this.esc(tile.title)}</span>${this.esc(c.label)}` : this.esc(c.label);
				const action = c.tone === 'action' && f.total && !unused;
				if (action) g_action += 1;
				const cell = (p) => unused ? '—' : (split ? num(c.key, by[p] || 0, [p]) : NA);
				const other_v = other.reduce((a, p) => a + (by[p] || 0), 0);
				const total = unused ? '—' : (f.split ? num(c.key, f.total || 0, picks) : NA);
				const amount = !c.sum || unused ? '' : (f.amount === null || f.amount === undefined ? (f.split ? '' : NA) : this.money(f.amount));
				const pct = base ? Math.min(100, (f.total || 0) / base * 100) : 0;
				// The whole row opens the row's list (narrowed to the picks when the records carry a programme).
				const row_ps = f.split ? picks : [];
				return `<tr class="uod-st-row${action ? ' is-action' : ''}${closed ? ' is-collapsed' : ''}" data-gi="${gi}" data-row="${c.key}"${this.ps_attr(row_ps)} tabindex="0" role="button"
					aria-label="${this.esc(__('Open the list: {0}', [c.label]))}">
					<td class="uod-st-name"><span class="uod-dot" style="--c:${UOD_TONES[c.tone] || UOD_TONES.neutral}"></span>${label}${action ? `<span class="uod-flag">${__('Action')}</span>` : ''}${this.info_html(c.guide)}</td>
					${cols.map(p => `<td class="uod-st-n">${cell(p)}</td>`).join('')}
					${other.length ? `<td class="uod-st-n">${unused ? '—' : (split ? num(c.key, other_v, other) : NA)}</td>` : ''}
					<td class="uod-st-n uod-st-tot">${total}</td>
					${has_amount ? `<td class="uod-st-n uod-st-amt">${amount}</td>` : ''}
					${opts.share ? `<td class="uod-st-share">${unused || !f.split ? '' : `<div class="uod-st-sharebox"><span class="uod-st-bar"><i style="width:${pct}%"></i></span><span class="uod-st-pct">${this.pct_txt(f.total || 0, base)}</span></div>`}</td>` : ''}
				</tr>`;
			}).join('');
			if (!rows) return '';
			const meta = `${g_rows} ${g_rows === 1 ? __('status') : __('statuses')}`
				+ (g_action ? ` · <b>${g_action} ${__('need action')}</b>` : '');
			return `<tr class="uod-st-group${closed ? ' is-closed' : ''}" data-gi="${gi}" data-gkey="${this.esc(gkey)}"><td colspan="${ncols}">
				<button type="button" class="uod-st-toggle" aria-expanded="${!closed}">
					<span class="uod-st-chev" aria-hidden="true">${uod_icon('chevron')}</span>
					<span class="uod-st-gtitle">${this.esc(g.title)}</span><span class="uod-st-gmeta">${meta}</span>
				</button></td></tr>${rows}`;
		}).join('');

		if (!shown) return `<div class="uod-st-panel"><div class="uod-empty">${__('No records for this selection.')}</div></div>`;
		const head = `<tr>
			<th class="uod-st-name">${__('Status')}</th>
			${cols.map(p => `<th class="uod-st-n">${this.esc(this.unit_label(p))}</th>`).join('')}
			${other.length ? `<th class="uod-st-n" title="${this.esc(other.map(p => this.unit_label(p)).join(', '))}">${__('Other ({0})', [other.length])}</th>` : ''}
			<th class="uod-st-n uod-st-tot">${__('Total')}</th>
			${has_amount ? `<th class="uod-st-n uod-st-amt">${__('Amount')}</th>` : ''}
			${opts.share ? `<th class="uod-st-share">${__('Share of applications')}</th>` : ''}
		</tr>`;
		return `<div class="uod-st-panel"><div class="uod-table-scroll"><table class="uod-st-table">
			<thead>${head}</thead><tbody>${body}</tbody></table></div>
			${blank_note ? `<div class="uod-st-foot">${__('Blank programme cells: those records (online payments, settlements) are not linked to a programme.')}</div>` : ''}</div>`;
	}
	show_adm(key) {
		this.adm = key;
		this.save_pref(UOD_ADM_KEY, key);
		this.$root.find('.uod-adm').each((_i, el) => {
			const on = $(el).data('adm') === key;
			$(el).toggleClass('is-on', on).attr({ 'aria-selected': on, tabindex: on ? 0 : -1 });
		});
		this.$root.find('.uod-adm-pane').each((_i, el) => { el.hidden = $(el).data('adm') !== key; });
	}

	// Top tabs: Overview, Admission (Regular / PACE / FLE inside), then the other modules.
	module_tabs() {
		const sub = new Set(UOD_ADM_TYPES.map(t => t.sections).filter(k => k !== 'admission'));
		return this.meta.modules.filter(m => !sub.has(m.key)).filter(m => m.key === 'admission'
			? this.adm_types().length > 0
			: this.meta.board.some(s => s.key === m.key && this.visible_tiles(s).length));
	}

	// Dashboard tab = a module tab bar and one pane per tab; only the active pane is visible.
	render_board() {
		const tabs = [{ key: 'overview', label: __('Overview'), html: this.overview_html() }];
		this.module_tabs().forEach((m) => {
			if (m.key === 'admission') { tabs.push({ key: m.key, label: m.label, html: this.admission_html() }); return; }
			const secs = this.meta.board.filter(s => s.key === m.key && this.visible_tiles(s).length);
			if (secs.some(s => s.scope)) {
				tabs.push({ key: m.key, label: m.label, html: this.scoped_module_html(m, secs) });
				return;
			}
			const total = secs.reduce((a, s) => a + this.visible_tiles(s).length, 0);
			const note = m.key === 'registration' ? ` · ${this.n(this.data.stu_total)} ${__('student records in scope')}` : '';
			tabs.push({
				key: m.key, label: m.label,
				html: this.module_head(m.key, m.label, `${total} ${total === 1 ? __('card') : __('cards')}${note} · ${__('click any number for the list behind it')}`)
					+ secs.map(s => this.section_html(s, secs.length > 1)).join('')
			});
		});

		if (!tabs.some(t => t.key === this.module)) this.module = 'overview';
		const nav = tabs.map(t => {
			const on = t.key === this.module;
			return `<button class="uod-mtab${on ? ' is-on' : ''}" role="tab" id="uod-mtab-${t.key}" data-m="${t.key}"
				aria-selected="${on}" aria-controls="uod-mpane-${t.key}" tabindex="${on ? 0 : -1}">
				<span class="uod-mtab-ico">${uod_icon(UOD_MODULE_ICONS[t.key] || 'grid')}</span><span class="uod-mtab-txt">${this.esc(t.label)}</span>
			</button>`;
		}).join('');
		const panes = tabs.map(t => `<div class="uod-mpane" role="tabpanel" id="uod-mpane-${t.key}" data-m="${t.key}"
			aria-labelledby="uod-mtab-${t.key}" ${t.key === this.module ? '' : 'hidden'}>${t.html}</div>`).join('');

		const $nav = this.$root.find('#uod-mnav').html(nav);
		const $panes = this.$root.find('#uod-mpanes').html(panes);
		$panes.find('.uod-mpane > .uod-section:first-child').css('margin-top', 0);
		this.bind_cards($panes);
		this.init_adm_tools();
		$panes.find('[data-goto]').on('click', (e) => { this.show_module(String($(e.currentTarget).data('goto')), true); });
		$panes.find('[data-money]').on('click', (e) => { e.stopPropagation(); this.drill_money(); });
		$panes.find('.uod-adm').on('click', (e) => { this.show_adm(String($(e.currentTarget).data('adm'))); });
		const scope_of = (el) => [String($(el).closest('.uod-mpane').data('m')), el.getAttribute('data-scope')];
		$panes.find('.uod-scope').on('click', (e) => { this.show_scope(...scope_of(e.currentTarget)); });
		$panes.find('.uod-scope-switch').each((_i, sw) => {
			this.arrow_keys($(sw), '.uod-scope', (el) => this.show_scope(...scope_of(el)));
		});
		this.load_scope_lists();
		this.arrow_keys($panes.find('.uod-adm-pick'), '.uod-adm', (el) => this.show_adm(String($(el).data('adm'))));
		$nav.find('.uod-mtab').on('click', (e) => { this.show_module(String($(e.currentTarget).data('m')), true); });
		this.arrow_keys($nav, '.uod-mtab', (el) => this.show_module(String($(el).data('m')), false));
		this.reveal_tab(false);
	}

	// A module whose sections carry a "scope" (Programme management, Attendance):
	// a switch and one pane per scope; only the chosen pane is visible.
	scoped_module_html(m, secs) {
		const defs = UOD_SCOPES[m.key] || [];
		const scopes = defs.filter(sc => secs.some(s => (s.scope || 'all') === sc.key));
		if (!scopes.some(sc => sc.key === this.scope[m.key])) this.scope[m.key] = scopes.length ? scopes[0].key : 'all';
		const cur = this.scope[m.key];
		const sw = scopes.map((sc) => {
			const on = sc.key === cur;
			return `<button type="button" class="uod-scope${on ? ' is-on' : ''}" role="tab" data-scope="${sc.key}" aria-selected="${on}" tabindex="${on ? 0 : -1}">${this.esc(sc.label)}</button>`;
		}).join('');
		const panes = scopes.map((sc) => {
			const mine = secs.filter(s => (s.scope || 'all') === sc.key);
			const list = sc.list ? `<div class="uod-section"><div class="uod-section-title"><span>${this.esc(sc.list.title)}</span>
				<span class="uod-section-note">${this.esc(sc.list.sub || '')}</span></div>
				<div class="uod-panel uod-scope-list" data-kind="${sc.list.kind}" data-export="${this.esc(sc.list.export || sc.list.kind)}"></div></div>` : '';
			return `<div class="uod-scope-pane" data-scope="${sc.key}" role="tabpanel" ${sc.key === cur ? '' : 'hidden'}>
				${mine.map(s => this.section_html(s, mine.length > 1)).join('')}${list}</div>`;
		}).join('');
		const hint = (scopes.find(sc => sc.key === cur) || {}).hint || '';
		const lead = m.key === 'programme' ? __('Pick a programme type') : __('Pick a view');
		return this.module_head(m.key, m.label, `${lead} · ${__('click any number for the list behind it')}`)
			+ `<div class="uod-scope-bar"><div class="uod-scope-switch" role="tablist" aria-label="${this.esc(m.label)}">${sw}</div>
				<span class="uod-muted uod-scope-hint">${this.esc(hint)}</span></div>` + panes;
	}

	show_scope(mkey, key) {
		const $pane = this.$root.find(`#uod-mpane-${mkey}`);
		if (!$pane.find(`.uod-scope-pane[data-scope="${key}"]`).length) return;
		this.scope[mkey] = key;
		this.save_pref(UOD_SCOPE_KEY, JSON.stringify(this.scope));
		$pane.find('.uod-scope').each((_i, el) => {
			const on = el.getAttribute('data-scope') === key;
			$(el).toggleClass('is-on', on).attr({ 'aria-selected': on, tabindex: on ? 0 : -1 });
		});
		$pane.find('.uod-scope-pane').each((_i, el) => { el.hidden = el.getAttribute('data-scope') !== key; });
		$pane.find('.uod-scope-hint').text(((UOD_SCOPES[mkey] || []).find(sc => sc.key === key) || {}).hint || '');
		this.load_scope_lists();
	}

	// Paged lists inside a visible scope pane load once per data load (filters change → reload).
	load_scope_lists() {
		this.$root.find('.uod-scope-pane:not([hidden]) .uod-scope-list').each((_i, el) => {
			if (el.getAttribute('data-loaded') === '1' || el.closest('.uod-mpane[hidden]')) return;
			el.setAttribute('data-loaded', '1');
			this.server_table($(el), el.getAttribute('data-kind'), {}, { export_name: el.getAttribute('data-export') });
		});
	}

	// Every number with data-card opens its drilldown; data-ps = JSON list of
	// programmes to open it narrowed to.
	bind_cards($scope) {
		const picks_of = (el) => {
			let ps = null;
			try { ps = JSON.parse(el.getAttribute('data-ps') || 'null'); } catch (e) { ps = null; }
			return Array.isArray(ps) && ps.length ? ps : null;
		};
		// Numbers first: bind_click stops the click there, so it never also opens the row.
		this.bind_click($scope.find('[data-card]'), (el) => this.drill_card($(el).data('card'), picks_of(el)));
		$scope.find('.uod-adm-fold [data-fold]').on('click', (e) => {
			const close = e.currentTarget.getAttribute('data-fold') === 'close';
			$(e.currentTarget).closest('.uod-section').find('tr.uod-st-group').each((_i, tr) => this.set_group(tr, close));
			this.save_collapsed();
		});
		$scope.find('tr.uod-st-group .uod-st-toggle').on('click', (e) => {
			const tr = $(e.currentTarget).closest('tr')[0];
			this.set_group(tr, !tr.classList.contains('is-closed'));
			this.save_collapsed();
		});
		const $rows = $scope.find('tr[data-row]');
		$rows.on('click', (e) => {
			if ($(e.target).closest('.uod-info, [data-card]').length) return;
			this.drill_card(String(e.currentTarget.getAttribute('data-row')), picks_of(e.currentTarget));
		});
		$rows.on('keydown', (e) => {
			if (e.target !== e.currentTarget || (e.key !== 'Enter' && e.key !== ' ')) return;
			e.preventDefault();
			this.drill_card(String(e.currentTarget.getAttribute('data-row')), picks_of(e.currentTarget));
		});
	}

	// Open / close one table section (its header row + the rows that follow it).
	set_group(tr, close) {
		const key = tr.getAttribute('data-gkey');
		tr.classList.toggle('is-closed', close);
		$(tr).find('.uod-st-toggle').attr('aria-expanded', String(!close));
		$(tr).closest('tbody').find(`tr.uod-st-row[data-gi="${tr.getAttribute('data-gi')}"]`).toggleClass('is-collapsed', close);
		if (close) this.collapsed.add(key); else this.collapsed.delete(key);
	}
	save_collapsed() { this.save_pref(UOD_COLLAPSE_KEY, JSON.stringify(Array.from(this.collapsed))); }

	// Arrow keys / Home / End move between tabs (WAI-ARIA tabs pattern).
	arrow_keys($list, sel, pick) {
		$list.find(sel).on('keydown', (e) => {
			const $all = $list.find(sel);
			const i = $all.index(e.currentTarget);
			let j = null;
			if (e.key === 'ArrowRight') j = (i + 1) % $all.length;
			else if (e.key === 'ArrowLeft') j = (i - 1 + $all.length) % $all.length;
			else if (e.key === 'Home') j = 0;
			else if (e.key === 'End') j = $all.length - 1;
			if (j === null) return;
			e.preventDefault();
			const el = $all.get(j);
			pick(el);
			el.focus();
		});
	}

	show_module(key, from_click) {
		if (!this.$root.find(`#uod-mpane-${key}`).length) return;
		this.module = key;
		this.save_pref(UOD_MODULE_KEY, key);
		this.$root.find('.uod-mtab').each((_i, el) => {
			const on = $(el).data('m') === key;
			$(el).toggleClass('is-on', on).attr({ 'aria-selected': on, tabindex: on ? 0 : -1 });
		});
		this.$root.find('.uod-mpane').each((_i, el) => { el.hidden = $(el).data('m') !== key; });
		this.load_scope_lists();
		this.reveal_tab(true);
		// If the tab bar is stuck to the top (user scrolled down), bring the new pane's top into view.
		if (from_click) {
			const wrap = this.$root.find('#uod-mnav-wrap')[0];
			const panes = this.$root.find('#uod-mpanes')[0];
			if (wrap && panes && panes.getBoundingClientRect().top < wrap.getBoundingClientRect().bottom - 1) {
				wrap.scrollIntoView({ block: 'start' });
			}
		}
	}

	// Arrows + edge fades appear only when the tab bar can scroll that way.
	update_arrows() {
		const nav = this.$root.find('#uod-mnav')[0];
		if (!nav) return;
		const left = nav.scrollLeft > 2;
		const right = nav.scrollLeft + nav.clientWidth < nav.scrollWidth - 2;
		this.$root.find('.uod-mnav-arrow.is-left').prop('hidden', !left);
		this.$root.find('.uod-mnav-arrow.is-right').prop('hidden', !right);
		$(nav).toggleClass('fade-l', left).toggleClass('fade-r', right);
	}

	// Keep the active tab visible inside the horizontally scrolling tab bar.
	reveal_tab(smooth) {
		const nav = this.$root.find('#uod-mnav')[0];
		const el = this.$root.find('.uod-mtab.is-on')[0];
		this.update_arrows();
		if (!nav || !el) return;
		const l = el.offsetLeft - nav.offsetLeft;
		if (l < nav.scrollLeft || l + el.offsetWidth > nav.scrollLeft + nav.clientWidth) {
			nav.scrollTo({ left: Math.max(0, l - 24), behavior: smooth ? 'smooth' : 'auto' });
		}
	}

	tile_html(t) {
		const guide = t.cards.map(c => `${c.label}: ${c.guide || ''}`).join('\n');
		const click = (c) => this.allowed(c.key) ? `is-click" data-card="${c.key}" tabindex="0" role="button` : 'is-denied" title="' + __('You do not have access to these records');
		const share = (c, v) => v === null || this.unused(c) || c.money ? '' : this.share_html(v, this.base_of(c));
		const value = (c, v) => {
			if (this.unused(c)) return '—';
			if (c.money) return v === null ? '—' : this.money((this.card_data(c.key) || {}).amount);
			return this.n(v);
		};
		const sub_of = (c, v) => c.money
			? (v === null ? '' : `${this.n(v)} ${v === 1 ? __('payment') : __('payments')}`)
			: this.sub_of(c);
		if (t.cards.length === 1) {
			const c = t.cards[0];
			const v = this.card_count(c.key);
			const color = ['action', 'time'].includes(c.tone) && v ? `color:${UOD_TONES[c.tone]}` : '';
			return `<div class="uod-tile uod-tile-1 ${click(c)}">
				<div class="uod-tile-head"><span class="uod-tile-title">${this.esc(t.title)}</span>${this.info_html(guide)}</div>
				<div class="uod-kpi-value" style="${color}">${value(c, v)}${share(c, v)}</div>
				<div class="uod-kpi-sub">${this.esc(sub_of(c, v))}</div>
			</div>`;
		}
		const money = t.cards.every(c => c.money);
		const halves = t.cards.map(c => {
			const v = this.card_count(c.key);
			const live = v && !this.unused(c);
			const color = c.tone === 'action' && live ? `color:${UOD_TONES.action}` : '';
			const flag = c.tone === 'action' && live ? `<span class="uod-flag">${__('Action')}</span>` : '';
			const sub = sub_of(c, v);
			return `<div class="uod-half ${click(c)}">
				<div class="uod-half-label"><span class="uod-dot" style="--c:${UOD_TONES[c.tone] || UOD_TONES.neutral}"></span>${this.esc(c.label)}${flag}</div>
				<div class="uod-kpi-value" style="${color}">${value(c, v)}${share(c, v)}</div>
				${sub ? `<div class="uod-kpi-sub">${this.esc(sub)}</div>` : ''}
			</div>`;
		}).join('');
		// Money tile: the grand total and a programme-wise breakdown sit in the header.
		let tools = '';
		if (money) {
			const readable = t.cards.filter(c => this.allowed(c.key));
			const total = readable.reduce((a, c) => a + Number((this.card_data(c.key) || {}).amount || 0), 0);
			tools = `<span class="uod-tile-tools">
				${readable.length ? `<span class="uod-money-total">${__('Total')} <b>${this.money(total)}</b></span>` : ''}
				${readable.length ? `<button class="uod-link-btn" data-money="1">${__('Programme-wise')} ›</button>` : ''}
			</span>`;
		}
		return `<div class="uod-tile uod-tile-${t.cards.length}${money ? ' is-money' : ''}">
			<div class="uod-tile-head"><span class="uod-tile-title">${this.esc(t.title)}${this.info_html(guide)}</span>${tools}</div>
			<div class="uod-halves" style="--n:${t.cards.length}">${halves}</div>
		</div>`;
	}

	// ── Money received, programme-wise, across admission types ──
	// Type chips → a programme table (every programme, ₹ and payments) → the
	// payment list for the programme(s) picked in that table.
	drill_money() {
		const d = new frappe.ui.Dialog({ title: __('Money received — programme-wise'), size: 'extra-large' });
		d.$wrapper.find('.modal-dialog').addClass('uod-modal');
		d.$body.html(`<style>${UOD_CSS}</style><div class="uod-root uod-in-modal">
			<div class="uod-muted uod-dd-note">${__('Payments received in the selected dates. Pick an admission type, then a programme to see its payments.')}</div>
			<div class="uod-mb"><div class="uod-empty">${__('Loading…')}</div></div>
			<div class="uod-mb-progs"></div>
			<div class="uod-mb-listhead"></div><div class="uod-dd-table"></div></div>`);
		this.bind_tip(d.$body);
		d.show();
		const state = { type: null, unit: null };   // unit null = all programmes
		let groups = [];
		const group = () => groups.find(g => g.card === state.type);
		const pay = (x) => `${this.n(x)} ${x === 1 ? __('payment') : __('payments')}`;
		const draw_types = () => {
			const amount = groups.reduce((a, g) => a + g.amount, 0);
			const n = groups.reduce((a, g) => a + g.n, 0);
			d.$body.find('.uod-mb').html(`<div class="uod-mb-total">${__('All admissions')}: <b>${this.money(amount)}</b> · ${pay(n)}</div>
				<div class="uod-mb-types">${groups.map(g => `<button class="uod-mb-type${g.card === state.type ? ' is-on' : ''}" data-type="${g.card}">
					<span>${this.esc(g.label)}</span><b>${this.money(g.amount)}</b><small>${pay(g.n)} · ${this.pct_txt(g.amount, amount)}</small></button>`).join('')}</div>`);
		};
		const draw_progs = () => {
			const g = group();
			const $p = d.$body.find('.uod-mb-progs');
			if (!g || !g.grouped) { $p.empty(); return; }
			const row = (key, name, n, amount, muted) => {
				const on = key === null ? state.unit === null : state.unit === key;
				const pct = g.amount ? Math.min(100, amount / g.amount * 100) : 0;
				return `<tr class="uod-mb-row${on ? ' is-on' : ''}${muted ? ' is-zero' : ''}" data-unit="${key === null ? '' : this.esc(key)}" data-all="${key === null ? 1 : 0}" tabindex="0" role="button">
					<td class="uod-st-name">${name}</td>
					<td class="uod-st-n">${this.n(n)}</td>
					<td class="uod-st-n uod-st-tot">${this.money(amount)}</td>
					<td class="uod-st-share"><div class="uod-st-sharebox"><span class="uod-st-bar"><i style="width:${pct}%"></i></span><span class="uod-st-pct">${this.pct_txt(amount, g.amount)}</span></div></td>
				</tr>`;
			};
			const units = g.units.slice().sort((a, b) => b.amount - a.amount || b.n - a.n || this.unit_label(a.key).localeCompare(this.unit_label(b.key)));
			$p.html(`<div class="uod-section-title"><span>${__('{0} by programme', [this.esc(g.label)])}</span>
					<span class="uod-section-note">${__('{0} programmes · click a row for its payments', [units.length])}</span></div>
				<div class="uod-st-panel uod-mb-panel"><div class="uod-mb-scroll"><table class="uod-st-table">
					<thead><tr><th class="uod-st-name">${__('Programme')}</th><th class="uod-st-n">${__('Payments')}</th>
						<th class="uod-st-n uod-st-tot">${__('Amount')}</th><th class="uod-st-share">${__('Share')}</th></tr></thead>
					<tbody>${row(null, `<b>${__('All programmes')}</b>`, g.n, g.amount, false)}
						${units.map(u => row(u.key, this.esc(this.unit_label(u.key)), u.n, u.amount, !u.n)).join('')}</tbody>
				</table></div></div>`);
		};
		const show_table = () => {
			const g = group();
			const $t = d.$body.find('.uod-dd-table');
			const $h = d.$body.find('.uod-mb-listhead');
			if (!g) { $h.empty(); $t.off().html(`<div class="uod-empty">${__('You cannot see any payment records.')}</div>`); return; }
			const which = state.unit === null ? __('all programmes') : this.unit_label(state.unit);
			$h.html(`<div class="uod-section-title"><span>${__('Payments')} · ${this.esc(g.label)} · ${this.esc(which)}</span></div>`);
			this.server_table($t, g.kind, { card: g.card, programme: g.grouped && state.unit !== null ? [state.unit] : '__all__' },
				{ export_name: `money-${g.label}` });
		};
		const pick_type = (card) => {
			state.type = card;
			state.unit = null;
			draw_types(); draw_progs(); show_table();
		};
		const pick_unit = (el) => {
			state.unit = el.getAttribute('data-all') === '1' ? null : el.getAttribute('data-unit');
			d.$body.find('.uod-mb-row').removeClass('is-on');
			$(el).addClass('is-on');
			show_table();
		};
		d.$body.on('click', '.uod-mb-type', (e) => { pick_type(String($(e.currentTarget).data('type'))); });
		d.$body.on('click', '.uod-mb-row', (e) => { pick_unit(e.currentTarget); });
		d.$body.on('keydown', '.uod-mb-row', (e) => {
			if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick_unit(e.currentTarget); }
		});
		frappe.xcall(UOD_API + 'get_money_breakdown', { filters: this.filters }).then((r) => {
			groups = r || [];
			const first = groups.find(g => g.n) || groups[0];
			if (!first) { d.$body.find('.uod-mb').empty(); show_table(); return; }
			pick_type(first.card);
		}).catch(() => { d.$body.find('.uod-mb').html(`<div class="uod-empty">${__('Could not load the breakdown.')}</div>`); });
	}

	bind_click($els, open) {
		$els.on('click', (e) => {
			if ($(e.target).closest('.uod-info').length) return;
			e.stopPropagation();
			open(e.currentTarget);
		});
		$els.on('keydown', (e) => {
			if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(e.currentTarget); }
		});
	}

	find_card(key) {
		for (const c of this.meta.headline) if (c.key === key) return c;
		for (const s of this.meta.board) for (const t of s.tiles) for (const c of t.cards) if (c.key === key) return c;
		return null;
	}
	// programmes: optional list to open the drilldown already narrowed to.
	drill_card(key, programmes = null) {
		const c = this.find_card(key);
		if (!c) return;
		const src = this.meta.sources[c.kind] || {};
		const honours = (src.honours || []).length ? ` ${__('Filters applied')}: ${src.honours.join(', ')}.` : ` ${__('The filters above do not apply to these records.')}`;
		this.drill(c.label, c.kind, { card: key }, (c.guide || '') + honours, programmes);
	}

	// Programme picker bar used by the drilldown popups (a searchable multi-select).
	prog_bar_html() {
		return `<div class="uod-dd-bar" hidden>
			<div class="uod-f uod-dd-prog"><label>${__('Programme')}</label><div class="uod-ms" data-placeholder="${__('All programmes')}"></div></div>
			<span class="uod-muted uod-dd-sum"></span>
		</div>`;
	}
	unit_label(k) { return k ? this.prog_name(k) : __('Programme not set'); }

	// ── drilldown popup ────────────────────────────────────────────────────
	drill(title, kind, extra = {}, note = '', programmes = null) {
		const d = new frappe.ui.Dialog({ title, size: 'extra-large' });
		d.$wrapper.find('.modal-dialog').addClass('uod-modal');
		d.$body.html(`<style>${UOD_CSS}</style><div class="uod-root uod-in-modal">
			${note ? `<div class="uod-muted uod-dd-note">${this.esc(note)}</div>` : ''}
			${this.prog_bar_html()}<div class="uod-dd-table"></div></div>`);
		this.bind_tip(d.$body);
		// A caller may pass one programme inside extra: treat it as the initial pick.
		if (extra.programme !== undefined && extra.programme !== null && !(programmes && programmes.length)) {
			programmes = extra.programme === '__all__' ? null : [String(extra.programme)];
		}
		extra = Object.assign({}, extra);
		delete extra.programme;
		const state = { programme: programmes && programmes.length ? programmes.slice() : '__all__' };
		let units = {};
		const draw_sum = () => {
			const keys = Object.keys(units);
			const total = keys.reduce((a, k) => a + units[k], 0);
			const picked = state.programme === '__all__' ? keys : state.programme.filter(k => k in units);
			const n = picked.reduce((a, k) => a + (units[k] || 0), 0);
			d.$body.find('.uod-dd-sum').text(state.programme === '__all__'
				? __('{0} records across {1} programmes', [this.n(total), keys.length])
				: __('{0} of {1} records · {2} of {3} programmes', [this.n(n), this.n(total), picked.length, keys.length]));
		};
		const run = (first) => {
			this.server_table(d.$body.find('.uod-dd-table'), kind, Object.assign({}, extra, { programme: state.programme, with_units: first ? 1 : 0 }), {
				export_name: title,
				on_data: (r) => { if (r.units) set_units(r.units); }
			});
		};
		const ms = this.make_multiselect(d.$body.find('.uod-dd-prog .uod-ms'), (v) => {
			state.programme = v.length ? v : '__all__';
			draw_sum();
			run(false);
		});
		const set_units = (u) => {
			units = u || {};
			const keys = Object.keys(units).sort((a, b) => units[b] - units[a] || this.unit_label(a).localeCompare(this.unit_label(b)));
			// One programme (and nothing pre-picked) → nothing to choose between.
			d.$body.find('.uod-dd-bar').prop('hidden', keys.length < 2 && state.programme === '__all__');
			ms.set_options(keys.map(k => ({ value: k, label: `${this.unit_label(k)} (${this.n(units[k])})` })));
			ms.set_value(state.programme === '__all__' ? [] : state.programme);
			draw_sum();
		};
		run(true);
		d.show();
	}

	// Server-paged table: search, sort, page size, pager, export all.
	server_table($el, kind, extra = {}, opts = {}) {
		const st = { search: '', sort: opts.sort || null, order: 'desc', page: 1, page_size: opts.page_size || 50 };
		// The same container is re-used on every filter change: drop old handlers first.
		$el.off();
		$el.html(`<div class="uod-tt">
			<div class="uod-tt-tools">
				<div class="uod-search"><input type="search" placeholder="${__('Search name, ID, email…')}"></div>
				<span class="uod-muted uod-tt-count"></span>
				<button class="btn btn-default btn-xs uod-tt-export">⬇ ${__('Export all (CSV)')}</button>
			</div>
			<div class="uod-table-scroll uod-tt-body"></div>
			<div class="uod-tt-pager"></div>
		</div>`);
		const $body = $el.find('.uod-tt-body');
		const args = () => ({ kind, filters: this.filters, extra, search: st.search, sort: st.sort, order: st.order, page: st.page, page_size: st.page_size });
		const fetch = () => {
			$body.addClass('uod-st-loading');
			frappe.xcall(UOD_API + 'get_table', args()).then((r) => {
				$body.removeClass('uod-st-loading');
				st.sort = r.sort; st.order = r.order;
				if (opts.on_data) opts.on_data(r);
				const from = r.total ? (r.page - 1) * r.page_size + 1 : 0;
				const to = Math.min(r.page * r.page_size, r.total);
				$el.find('.uod-tt-count').text(`${__('Rows')} ${this.n(from)}–${this.n(to)} ${__('of')} ${this.n(r.total)}`);
				$body.html(this.table_html(kind, r));
				const pages = Math.max(1, Math.ceil(r.total / r.page_size));
				$el.find('.uod-tt-pager').html(`
					<label class="uod-muted">${__('Rows per page')} <select class="uod-ps">${[25, 50, 100, 250].map(n => `<option ${n === r.page_size ? 'selected' : ''}>${n}</option>`).join('')}</select></label>
					<div class="uod-pages">
						<button class="uod-pg" data-g="1" ${r.page <= 1 ? 'disabled' : ''}>«</button>
						<button class="uod-pg" data-g="${r.page - 1}" ${r.page <= 1 ? 'disabled' : ''}>‹</button>
						<span class="uod-muted">${__('Page')} <b>${this.n(r.page)}</b> ${__('of')} ${this.n(pages)}</span>
						<button class="uod-pg" data-g="${r.page + 1}" ${r.page >= pages ? 'disabled' : ''}>›</button>
						<button class="uod-pg" data-g="${pages}" ${r.page >= pages ? 'disabled' : ''}>»</button>
					</div>`);
			}).catch(() => { $body.removeClass('uod-st-loading'); });
		};
		let timer = null;
		$el.find('.uod-search input').on('input', (e) => {
			clearTimeout(timer);
			timer = setTimeout(() => { st.search = e.target.value; st.page = 1; fetch(); }, 300);
		});
		$el.on('click', 'th[data-sort]', (e) => {
			const f = String($(e.currentTarget).data('sort'));
			st.order = st.sort === f && st.order === 'desc' ? 'asc' : 'desc';
			st.sort = f; st.page = 1;
			fetch();
		});
		$el.on('click', '.uod-pg', (e) => { st.page = Number($(e.currentTarget).data('g')) || 1; fetch(); });
		$el.on('change', '.uod-ps', (e) => { st.page_size = Number(e.target.value) || 50; st.page = 1; fetch(); });
		$el.find('.uod-tt-export').on('click', () => {
			const q = $.param({ kind, filters: JSON.stringify(this.filters), extra: JSON.stringify(extra), search: st.search,
				sort: st.sort || '', order: st.order, name: opts.export_name || kind });
			window.open(`/api/method/${UOD_API}export_table?${q}`);
		});
		$el.on('click', '.uod-person', (e) => {
			if (e.ctrlKey || e.metaKey || e.button === 1) return;
			// Stop here too: Frappe's router follows any desk href that reaches the document.
			e.preventDefault();
			e.stopPropagation();
			const $a = $(e.currentTarget);
			this.open_timeline(String($a.data('k')), String($a.data('id')));
		});
		fetch();
	}

	table_html(kind, r) {
		if (!r.rows.length) return `<div class="uod-empty">${__('Nothing here for these filters.')}</div>`;
		const pkind = kind === 'stu' ? 'stu' : 'app';
		const id_field = { app: 'name', stu: 'name' }[kind];
		const person_link = (k, id, text) => `<a class="uod-idlink uod-person" data-k="${k}" data-id="${this.esc(id)}" href="${this.desk_link(k === 'stu' ? 'Student Master' : 'Applicant', id)}">${this.esc(text || id)}</a>`;
		const head = r.columns.map(c => {
			const arrow = r.sort === c.field ? (r.order === 'asc' ? ' ▲' : ' ▼') : (c.sortable ? ' ↕' : '');
			return `<th ${c.sortable ? `data-sort="${c.field}"` : ''} class="${c.sortable ? 'is-sort' : ''}">${this.esc(c.label)}<span class="uod-arrow">${arrow}</span></th>`;
		}).join('');
		const cell = (row, c) => {
			const v = row[c.field];
			switch (c.type) {
				case 'id': return v ? `<a class="uod-idlink" target="_blank" href="${this.desk_link(r.doctype, v)}">${this.esc(v)} ↗</a>` : '';
				case 'applicant': return v ? person_link('app', v) : '';
				case 'student': return v ? person_link('stu', v) : '';
				case 'person': return id_field && row[id_field] ? `<a class="uod-cand uod-person" data-k="${pkind}" data-id="${this.esc(row[id_field])}" href="#">${this.esc(v || row[id_field])}</a>` : this.esc(v);
				case 'currency': return `<span class="uod-num-cell">${this.esc(this.money(v))}</span>`;
				case 'pct': return v === null || v === undefined ? '' : `<span class="uod-num-cell">${Math.round(Number(v) * 10) / 10}%</span>`;
				case 'check': return Number(v) ? `<span class="uod-pill" style="--c:${UOD_TONES.good}">${__('Yes')}</span>` : `<span class="uod-pill" style="--c:${UOD_TONES.neutral}">${__('No')}</span>`;
				case 'programme': return v ? this.prog_pill(v) : '';
				case 'stage': return this.stage_pill(v);
				case 'date': return this.esc(this.fmt_date(v));
				case 'datetime': return this.esc(this.fmt_dt(v));
				case 'days': return `<span class="uod-days ${v > 30 ? 'is-long' : ''}">${this.n(v)} ${__('days')}</span>`;
				default: return `<span class="uod-trunc" title="${this.esc(v)}">${this.esc(v)}</span>`;
			}
		};
		const body = r.rows.map(row => `<tr>${r.columns.map(c => `<td>${cell(row, c)}</td>`).join('')}</tr>`).join('');
		return `<table class="uod-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
	}

	// ── timeline tab ───────────────────────────────────────────────────────
	render_timeline_tab() {
		const t = this.tl;
		const sel = (key, label, opts, wide = false) => `<label class="uod-tl-tool ${wide ? 'uod-tl-tool-wide' : ''}"><span>${label}</span>
			<select data-k="${key}">${opts.map(([v, l]) => `<option value="${this.esc(v)}" ${String(t[key]) === String(v) ? 'selected' : ''}>${this.esc(l)}</option>`).join('')}</select></label>`;
		const statuses = [['', __('All statuses')]].concat(Object.keys(
			(this.data.status_prog || []).reduce((a, r) => { a[r.status] = 1; return a; }, {})).sort().map(s => [s, s]));
		const tools = t.people === 'app'
			? [sel('people', __('People'), [['app', __('Applicants')], ['stu', __('Students')]]),
				sel('stage', __('Stage'), [['', __('All stages')]].concat(this.meta.stages.map(s => [s.name, s.name]))),
				sel('status', __('Status'), statuses, true),
				sel('pipeline', __('Pipeline'), [['', __('Everyone')], ['open', __('Still in process')], ['ended', __('Ended (enrolled / not admitted)')]]),
				sel('days', __('Days in pipeline'), [['', __('Any')]].concat(UOD_DAY_RANGES))]
			: [sel('people', __('People'), [['app', __('Applicants')], ['stu', __('Students')]])];
		const $tools = this.$root.find('#uod-tl-tools').html(tools.join(''));
		$tools.find('select').on('change', (e) => {
			const k = $(e.currentTarget).data('k');
			t[k] = e.target.value;
			if (k === 'people') { t.stage = ''; t.status = ''; t.pipeline = ''; t.days = ''; }
			this.render_timeline_tab();
		});
		const extra = t.people === 'app' ? { stage: t.stage, status: t.status, pipeline: t.pipeline, days: t.days } : {};
		this.server_table(this.$root.find('#uod-tl-list'), t.people, extra, { export_name: 'timeline' });
	}

	open_timeline(kind, name) {
		const d = new frappe.ui.Dialog({ title: __('Timeline'), size: 'extra-large' });
		d.$wrapper.find('.modal-dialog').addClass('uod-modal-tl');
		d.$body.html(`<style>${UOD_CSS}</style><div class="uod-root uod-in-modal"><div class="uod-empty">${__('Loading…')}</div></div>`);
		d.show();
		frappe.xcall(UOD_API + 'get_timeline', { kind, name }).then((t) => {
			d.$body.find('.uod-root').html(this.timeline_html(t));
			d.$body.on('click', '.uod-tlf', (e) => {
				const k = String($(e.currentTarget).data('k'));
				d.$body.find('.uod-tlf').removeClass('is-on');
				$(e.currentTarget).addClass('is-on');
				d.$body.find('.uod-tli').each((_i, el) => { $(el).toggleClass('is-hidden', k !== 'all' && $(el).data('kind') !== k); });
				d.$body.find('.uod-tlg').each((_i, el) => { $(el).toggleClass('is-hidden', !$(el).find('.uod-tli:not(.is-hidden)').length); });
			});
		}).catch(() => { d.hide(); });
	}

	timeline_html(t) {
		const h = t.head || {};
		const c = UOD_STAGE_COLORS[h.stage] || '#920c24';
		const initial = String(h.name || '?').trim().charAt(0).toUpperCase();
		const ids = [h.applicant ? `<a class="uod-idlink" target="_blank" href="${this.desk_link('Applicant', h.applicant)}">${this.esc(h.applicant)} ↗</a>` : '',
			h.student ? `<a class="uod-idlink" target="_blank" href="${this.desk_link('Student Master', h.student)}">${this.esc(h.student)} ↗</a>` : '',
			h.registration_id ? `<span class="uod-regid">${__('Registration ID')}: <b>${this.esc(h.registration_id)}</b></span>` : ''].join(' ');
		const stats = [
			[__('Applied on'), h.applied_on ? this.fmt_date(h.applied_on) : '—', '#920c24'],
			[__('Days in process'), h.days !== undefined ? `${this.n(h.days)} ${__('days')}` : '—', '#A16207'],
			[__('Admission status'), h.status || '—', c],
			[__('Registration'), h.registration_status || '—', h.registration_status === 'Completed' ? '#2F7D4F' : '#6B7A8A']
		].map(([l, v, col]) => `<div style="--c:${col}"><span>${l}</span><b>${this.esc(v)}</b></div>`).join('');
		const journey = (t.journey || []).map(s => `<div class="uod-step ${s.done ? 'is-done' : ''} ${s.bad ? 'is-bad' : ''}">
			<span class="uod-step-dot">${s.bad ? '✕' : s.done ? '✓' : ''}</span><span class="uod-step-l">${this.esc(s.label)}</span></div>`).join('');

		const kinds = {};
		(t.events || []).forEach(e => { kinds[e.kind] = (kinds[e.kind] || 0) + 1; });
		const filt = `<div class="uod-tlp-filter"><button class="uod-tlf is-on" data-k="all">${__('Everything')}<span>${(t.events || []).length}</span></button>
			${Object.keys(kinds).map(k => `<button class="uod-tlf" data-k="${k}" style="--k:${UOD_KIND_COLORS[k] || '#6B7A8A'}"><span class="uod-dot" style="--c:${UOD_KIND_COLORS[k] || '#6B7A8A'}"></span>${this.esc(frappe.utils.to_title_case(k))}<span>${kinds[k]}</span></button>`).join('')}</div>`;

		const groups = {};
		(t.events || []).forEach(e => { (groups[e.when.slice(0, 10)] = groups[e.when.slice(0, 10)] || []).push(e); });
		const today = frappe.datetime.get_today();
		let today_drawn = false;
		const body = Object.keys(groups).sort().map(day => {
			let marker = '';
			if (!today_drawn && day > today) { marker = `<div class="uod-tl-today"><span>${__('Today')}</span></div>`; today_drawn = true; }
			const dt = frappe.datetime.str_to_obj(day);
			const items = groups[day].map(e => {
				const k = UOD_TONES[e.tone] || UOD_KIND_COLORS[e.kind] || '#6B7A8A';
				const time = e.when.length > 10 && e.when.slice(11, 16) !== '00:00' ? e.when.slice(11, 16) : '';
				const flow = e.flow ? `<div class="uod-tli-flow">${e.flow.map(x => `<span class="uod-pill" style="--c:${k}">${this.esc(x)}</span>`).join('<span class="uod-tli-arrow">→</span>')}</div>` : '';
				return `<div class="uod-tli ${day > today ? 'is-future' : ''}" data-kind="${this.esc(e.kind)}" style="--k:${k}">
					<div class="uod-tli-time">${time}</div>
					<div class="uod-tli-card">
						<div class="uod-tli-top"><span class="uod-tli-kind">${this.esc(e.kind)}</span><span class="uod-tli-title">${this.esc(e.title)}</span>
							${e.doctype && e.name ? `<a class="uod-tli-doc" target="_blank" href="${this.desk_link(e.doctype, e.name)}">${this.esc(e.name)} ↗</a>` : ''}</div>
						${flow}${e.meta ? `<div class="uod-tli-meta">${this.esc(e.meta)}</div>` : ''}
					</div></div>`;
			}).join('');
			return `${marker}<div class="uod-tlg"><div class="uod-tlg-date"><b>${dt.getDate()} ${dt.toLocaleString('en', { month: 'short' })}</b><span>${dt.getFullYear()}</span></div>
				<div class="uod-tlg-items">${items}</div></div>`;
		}).join('');

		return `<div class="uod-tlp-head">
				<div class="uod-tlp-who"><div class="uod-tlp-avatar" style="--c:${c}">${this.esc(initial)}</div>
					<div><div class="uod-tlp-name">${this.esc(h.name || '—')} ${ids}</div>
					<div class="uod-tlp-pills">${h.programme ? this.prog_pill(h.programme) : ''}${this.stage_pill(h.stage)}
						${h.cycle ? `<span class="uod-muted">${this.esc(h.cycle)}</span>` : ''}${h.email ? `<span class="uod-muted">${this.esc(h.email)}</span>` : ''}</div></div>
				</div>
			</div>
			<div class="uod-tlp-stats">${stats}</div>
			<div class="uod-journey">${journey}</div>
			${filt}
			<div class="uod-tlp-scroll">${body || `<div class="uod-empty">${__('No dated events recorded yet.')}</div>`}</div>`;
	}

	// ── funnel tab ─────────────────────────────────────────────────────────
	step_counts(program = null) {
		const out = {};
		this.meta.steps.forEach(s => {
			// No status list = every status (Total applications).
			const set = s.statuses ? new Set(s.statuses) : null;
			out[s.key] = (this.data.status_prog || []).filter(r => (!set || set.has(r.status)) && (program === null || r.program === program))
				.reduce((a, r) => a + r.n, 0);
		});
		return out;
	}
	programmes_in_scope() {
		const set = {};
		(this.data.status_prog || []).forEach(r => { set[r.program] = (set[r.program] || 0) + r.n; });
		Object.keys(this.data.stu_by || {}).forEach(p => { if (!(p in set)) set[p] = 0; });
		return Object.keys(set).sort((a, b) => set[b] - set[a]);
	}

	render_funnel_tab(refresh = false) {
		this.render_funbars();
		this.render_fununits();
		this.render_prog();
		this.render_stages();
		this.server_table(this.$root.find('#uod-apps'), 'app', {}, { export_name: 'applications' });
		this.server_table(this.$root.find('#uod-regs'), 'stu', {}, { export_name: 'registrations' });
		this.render_iv('all');
		this.server_table(this.$root.find('#uod-log'), 'audit', {}, {
			export_name: 'admission-log',
			on_data: (r) => { this.$root.find('#uod-log-wrap').toggle(r.total > 0); }
		});
		const $p = this.$root.find('#uod-pipe, #uod-profile, #uod-trend').addClass('uod-st-loading');
		frappe.xcall(UOD_API + 'get_funnel_data', { filters: this.filters, refresh: refresh ? 1 : 0 }).then((f) => {
			this.funnel = f;
			$p.removeClass('uod-st-loading');
			this.render_pipeline();
			this.render_profile();
			this.render_trend();
		}).catch(() => { $p.removeClass('uod-st-loading'); });
	}

	render_funbars() {
		const counts = this.step_counts();
		const total = counts.total || 0;
		let prev = null;
		const rows = this.meta.steps.map(s => {
			const v = counts[s.key];
			const of_prev = prev === null ? '' : `${this.pct_txt(v, prev)} ${__('of previous')}`;
			const lost = prev === null ? '' : `−${this.n(Math.max(prev - v, 0))} ${__('did not reach')}`;
			prev = v;
			return `<div class="uod-fun-row is-click" data-step="${s.key}" tabindex="0" role="button">
				<span class="uod-fun-label">${this.esc(s.label)}</span>
				<span class="uod-fun-track"><span class="uod-fun-bar" style="width:${total ? Math.max((v / total) * 100, v ? 0.6 : 0) : 0}%"></span></span>
				<b class="uod-fun-val">${this.n(v)}</b>
				<span class="uod-fun-pct">${of_prev}</span>
				<span class="uod-fun-pct uod-muted">${this.pct_txt(v, total)} ${__('of all')}</span>
				<span class="uod-fun-lost">${lost}</span>
			</div>`;
		}).join('');
		const $f = this.$root.find('#uod-funbars').html(`<div class="uod-fun">${rows}</div>`);
		this.bind_click($f.find('[data-step]'), (el) => {
			const s = this.meta.steps.find(x => x.key === $(el).data('step'));
			this.drill(s.label, 'app', { step: s.key });
		});
	}

	render_fununits() {
		const steps = this.meta.steps;
		const progs = this.programmes_in_scope();
		const head = `<tr><th>${__('Programme')}</th>${steps.map(s => `<th>${this.esc(s.label)}</th>`).join('')}</tr>`;
		const body = progs.map(p => {
			const c = this.step_counts(p);
			let prev = null;
			return `<tr><td>${this.prog_pill(p)}</td>${steps.map(s => {
				const v = c[s.key];
				const pct = prev === null ? '' : `<small class="uod-muted"> ${this.pct_txt(v, prev)}</small>`;
				prev = v;
				return `<td>${v ? `<a class="uod-num" data-step="${s.key}" data-p="${this.esc(p)}">${this.n(v)}</a>` : '<span class="uod-muted">0</span>'}${pct}</td>`;
			}).join('')}</tr>`;
		}).join('');
		const $t = this.$root.find('#uod-fununits').html(progs.length
			? `<table class="uod-table uod-fun-table"><thead>${head}</thead><tbody>${body}</tbody></table>`
			: `<div class="uod-empty">${__('No applications for these filters.')}</div>`);
		$t.find('.uod-num').on('click', (e) => {
			const $a = $(e.currentTarget);
			const s = steps.find(x => x.key === $a.data('step'));
			this.drill(`${s.label} · ${this.prog_name(String($a.data('p')))}`, 'app', { step: s.key, programme: String($a.data('p')) });
		});
	}

	render_prog() {
		const progs = this.programmes_in_scope();
		const stage_of = {};
		this.meta.stages.forEach(s => s.statuses.forEach(st => { stage_of[st] = s.name; }));
		const reg_done = ((this.data.cards || {}).reg_done || { by: {} }).by;
		const cols = [['apps', __('Applications')]].concat(this.meta.stages.map(s => [s.name, s.name]))
			.concat([['students', __('Student records')], ['registered', __('Registration completed')], ['conv', __('Conversion')]]);
		this.prog_rows = progs.map(p => {
			const row = { programme: this.prog_name(p), key: p, apps: 0, students: (this.data.stu_by || {})[p] || 0, registered: reg_done[p] || 0 };
			this.meta.stages.forEach(s => { row[s.name] = 0; });
			(this.data.status_prog || []).filter(r => r.program === p).forEach(r => {
				row.apps += r.n;
				row[stage_of[r.status] || 'Applying'] += r.n;
			});
			row.conv = this.pct(row['Offer / Admitted'], row.apps);
			return row;
		});
		const head = `<tr><th>${__('Programme')}</th>${cols.map(c => `<th>${this.esc(c[1])}</th>`).join('')}</tr>`;
		const body = this.prog_rows.map(r => `<tr><td>${this.prog_pill(r.key)}</td>${cols.map(([k]) => {
			if (k === 'conv') return `<td><b>${r.conv}%</b></td>`;
			const v = r[k];
			const color = k === 'Not admitted' && v ? `style="color:${UOD_TONES.bad}"` : '';
			return `<td>${v ? `<a class="uod-num" data-k="${this.esc(k)}" data-p="${this.esc(r.key)}" ${color}>${this.n(v)}</a>` : '<span class="uod-muted">0</span>'}</td>`;
		}).join('')}</tr>`).join('');
		const $t = this.$root.find('#uod-prog').html(this.prog_rows.length
			? `<table class="uod-table uod-fun-table"><thead>${head}</thead><tbody>${body}</tbody></table>`
			: `<div class="uod-empty">${__('Nothing for these filters.')}</div>`);
		$t.find('.uod-num').on('click', (e) => {
			const $a = $(e.currentTarget);
			const k = String($a.data('k'));
			const p = String($a.data('p'));
			const title = `${cols.find(c => c[0] === k)[1]} · ${this.prog_name(p)}`;
			if (k === 'apps') this.drill(title, 'app', { programme: p });
			else if (k === 'students') this.drill(title, 'stu', { programme: p });
			else if (k === 'registered') this.drill(title, 'stu', { card: 'reg_done', programme: p });
			else this.drill(title, 'app', { stage: k, programme: p });
		});
		this.$root.find('#uod-export-prog').off('click').on('click', () => {
			this.export_csv('programme-summary', [{ key: 'programme', label: __('Programme') }].concat(cols.map(([k, l]) => ({ key: k, label: l }))), this.prog_rows);
		});
	}

	render_stages() {
		const by = {};
		const stage_of = {};
		this.meta.stages.forEach(s => s.statuses.forEach(st => { stage_of[st] = s.name; }));
		(this.data.status_prog || []).forEach(r => { const s = stage_of[r.status] || 'Applying'; by[s] = (by[s] || 0) + r.n; });
		const total = this.data.app_total;
		const max = Math.max(1, ...Object.values(by));
		const rows = this.meta.stages.map(s => {
			const v = by[s.name] || 0;
			return `<div class="uod-bar-row is-click" data-stage="${this.esc(s.name)}" tabindex="0" role="button">
				<span class="uod-bar-label"><span class="uod-dot" style="--c:${UOD_STAGE_COLORS[s.name]}"></span>${this.esc(s.name)}</span>
				<span class="uod-bar-track"><span class="uod-bar-fill" style="width:${(v / max) * 100}%;background:${UOD_STAGE_COLORS[s.name]}"></span></span>
				<span class="uod-bar-val"><b>${this.n(v)}</b> <small class="uod-muted">${this.pct_txt(v, total)}</small></span></div>`;
		}).join('');
		const $s = this.$root.find('#uod-stages').html(rows);
		this.bind_click($s.find('[data-stage]'), (el) => {
			const s = String($(el).data('stage'));
			this.drill(s, 'app', { stage: s });
		});
	}

	range_tools() {
		return `<div class="uod-panel-tools uod-range">${[['all', __('All')], ['today', __('Today')], ['next7', __('Next 7 days')], ['last7', __('Last 7 days')], ['month', __('This month')]]
			.map(([k, l]) => `<button class="uod-preset uod-rpreset ${k === 'all' ? 'is-on' : ''}" data-r="${k}">${l}</button>`).join('')}</div>`;
	}
	render_iv(range) {
		const today = frappe.datetime.get_today();
		const r = { all: {}, today: { from: today, to: today }, next7: { from: today, to: frappe.datetime.add_days(today, 7) },
			last7: { from: frappe.datetime.add_days(today, -7), to: today }, month: { from: frappe.datetime.month_start(), to: frappe.datetime.month_end() } }[range];
		const $tools = this.$root.find('#uod-iv').closest('.uod-panel').find('.uod-rpreset');
		$tools.each((_i, el) => { $(el).toggleClass('is-on', $(el).data('r') === range); });
		$tools.off('click').on('click', (e) => { this.render_iv(String($(e.currentTarget).data('r'))); });
		this.server_table(this.$root.find('#uod-iv'), 'isa', r, { export_name: 'interviews' });
	}

	render_pipeline() {
		const p = this.funnel.pipeline;
		const o = this.funnel.offers;
		const kpi = (label, v, sub, c, extra) => `<div class="uod-tl-kpi ${extra ? 'is-click' : ''}" style="--c:${c}" ${extra ? `data-x='${this.esc(JSON.stringify(extra))}' tabindex="0" role="button"` : ''}>
			<div class="uod-tl-kpi-top"><span>${label}</span></div><b>${v}</b><small>${sub}</small></div>`;
		const kpis = [
			kpi(__('Average days in pipeline'), `${p.avg_days} ${__('days')}`, `${p.avg_open} ${__('days for those still in it')}`, '#920c24'),
			kpi(__('Still in pipeline'), this.n(p.open), `${this.pct_txt(p.open, p.open + p.ended)} ${__('of these applicants')}`, '#2b4f7e', { pipeline: 'open' }),
			kpi(__('Waiting over 30 days'), this.n(p.over30), __('still in process, 30+ days'), '#B7651B', { pipeline: 'open', days: '31-' }),
			kpi(__('Ended'), this.n(p.ended), __('enrolled or not admitted'), '#6B7A8A', { pipeline: 'ended' })
		].join('');
		const cats = p.buckets.map(b => `${b.label} ${__('days')}`);
		const days_chart = this.svg_bars(cats, [
			{ key: 'open', label: __('Still in pipeline'), color: 'var(--pipe-open)' },
			{ key: 'ended', label: __('Ended'), color: 'var(--pipe-ended)' }
		], p.buckets, { stacked: true, click: (i) => ({ days: UOD_DAY_RANGES[i][0] }) });
		const max_stage = Math.max(1, ...p.by_stage.map(s => s.avg));
		const stage_bars = p.by_stage.map(s => `<div class="uod-bar-row is-click" data-stage="${this.esc(s.stage)}" tabindex="0" role="button">
			<span class="uod-bar-label"><span class="uod-dot" style="--c:${UOD_STAGE_COLORS[s.stage]}"></span>${this.esc(s.stage)}</span>
			<span class="uod-bar-track"><span class="uod-bar-fill" style="width:${(s.avg / max_stage) * 100}%;background:${UOD_STAGE_COLORS[s.stage]}"></span></span>
			<span class="uod-bar-val"><b>${s.avg} ${__('days')}</b> <small class="uod-muted">${__('avg')} · ${this.n(s.n)} ${__('applicants')}</small></span></div>`).join('');

		const progs = Object.keys(o.by_programme).sort();
		const statuses = ['Issued', 'Accepted', 'Confirmation Fee Paid', 'Full Fee Paid', 'Rejected', 'Expired', 'Withdrawn'];
		const st_colors = { 'Issued': '#8a5a00', 'Accepted': '#2b4f7e', 'Confirmation Fee Paid': '#0D9488', 'Full Fee Paid': '#2F7D4F',
			'Rejected': '#B83232', 'Expired': '#8A96A3', 'Withdrawn': '#6B7A8A' };
		const used = statuses.filter(s => progs.some(pg => o.by_programme[pg][s]));
		const per_prog = this.svg_bars(progs.map(pg => this.prog_name(pg)), [{ key: 'n', label: __('Offers'), color: '#920c24' }],
			progs.map(pg => ({ n: Object.values(o.by_programme[pg]).reduce((a, b) => a + b, 0) })), {});
		const by_status = this.svg_bars(progs.map(pg => this.prog_name(pg)), used.map(s => ({ key: s, label: s, color: st_colors[s] })),
			progs.map(pg => o.by_programme[pg]), {});
		const g_keys = Array.from(new Set([].concat(...Object.values(o.gender || {}).map(x => Object.keys(x))))).sort();
		const g_colors = ['#7C3AED', '#0891B2', '#B7791F', '#8A96A3'];
		const gprogs = Object.keys(o.gender || {}).sort();
		const gender = this.svg_bars(gprogs.map(pg => this.prog_name(pg)), g_keys.map((g, i) => ({ key: g, label: g || __('Not set'), color: g_colors[i % g_colors.length] })),
			gprogs.map(pg => o.gender[pg]), {});
		const mprogs = Object.keys(o.median_days || {}).sort();
		const med = this.svg_dots(mprogs.map(pg => this.prog_name(pg)), mprogs.map(pg => o.median_days[pg]));
		const chart = (title, sub, body, legend = '') => `<div class="uod-tl-chart"><div class="uod-tl-chart-head"><div>
			<div class="uod-tl-chart-title">${title}</div><div class="uod-panel-sub">${sub}</div></div>${legend}</div>${body}</div>`;
		const legend = (items) => `<div class="uod-legend">${items.map(([l, c]) => `<span><i style="background:${c}"></i>${this.esc(l)}</span>`).join('')}</div>`;

		const $p = this.$root.find('#uod-pipe').html(`
			<div class="uod-tl-kpis">${kpis}</div>
			<div class="uod-grid-2">
				${chart(__('Days in pipeline'), __('How long applicants have been in the process · click a column for its list'), days_chart,
					legend([[__('Still in pipeline'), 'var(--pipe-open)'], [__('Ended'), 'var(--pipe-ended)']]))}
				${chart(__('Average days by current stage'), __('Where the time goes · click a stage for its list'), `<div class="uod-bars">${stage_bars}</div>`)}
			</div>
			<div class="uod-offers-head"><div class="uod-tl-chart-title">${__('Offer update')}</div>
				<div class="uod-panel-sub">${this.n(o.total)} ${__('offer letters issued to applicants within the filters above')}</div></div>
			<div class="uod-grid-2">
				${chart(__('Number of offers'), __('Per programme'), per_prog)}
				${chart(__('Offer status'), __('Where each offer stands now'), by_status, legend(used.map(s => [s, st_colors[s]])))}
				${chart(__('Gender'), __('Of the applicants who reached the offer step'), gender, legend(g_keys.map((g, i) => [g || __('Not set'), g_colors[i % g_colors.length]])))}
				${chart(__('Median days to offer'), __('From application to offer letter, per programme'), med)}
			</div>`);
		this.bind_click($p.find('.uod-tl-kpi.is-click'), (el) => {
			const x = JSON.parse($(el).attr('data-x'));
			this.drill($(el).find('span').first().text(), 'app', x);
		});
		this.bind_click($p.find('[data-stage]'), (el) => { const s = String($(el).data('stage')); this.drill(s, 'app', { stage: s }); });
		this.bind_svg_clicks($p, 'app', __('Days in pipeline'));
	}

	render_profile() {
		const f = this.funnel;
		const donut_chart = (title, field, data) => {
			const items = Object.keys(data).sort((a, b) => data[b] - data[a]).map((k, i) => ({ key: k, label: k || __('Not given'), value: data[k], color: UOD_PALETTE[i % UOD_PALETTE.length] }));
			return `<div class="uod-tl-chart"><div class="uod-tl-chart-title">${title}</div>${this.svg_donut(items, field)}</div>`;
		};
		const st = Object.keys(f.state).sort((a, b) => f.state[b] - f.state[a]).slice(0, 12);
		const max = Math.max(1, ...st.map(k => f.state[k]));
		const states = st.map(k => `<div class="uod-bar-row is-click" data-field="state" data-value="${this.esc(k)}" tabindex="0" role="button">
			<span class="uod-bar-label">${this.esc(k || __('Not given'))}</span>
			<span class="uod-bar-track"><span class="uod-bar-fill" style="width:${(f.state[k] / max) * 100}%"></span></span>
			<span class="uod-bar-val"><b>${this.n(f.state[k])}</b></span></div>`).join('');
		const $p = this.$root.find('#uod-profile').html(`<div class="uod-grid-2">
			${donut_chart(__('Category'), 'whether_scstobc_ncl', f.category)}
			${donut_chart(__('Gender'), 'gender', f.gender)}
			${donut_chart(__('Source of information'), 'source_of_information', f.source)}
			<div class="uod-tl-chart"><div class="uod-tl-chart-title">${__('State')} <small class="uod-muted">${__('top 12')}</small></div><div class="uod-bars">${states || `<div class="uod-empty">${__('No data')}</div>`}</div></div>
		</div>`);
		this.bind_click($p.find('[data-field]'), (el) => {
			const $e = $(el);
			this.drill(`${$e.closest('.uod-tl-chart').find('.uod-tl-chart-title').first().text()}: ${$e.data('value') || __('Not given')}`, 'app',
				{ field: String($e.data('field')), value: String($e.data('value') || '') });
		});
	}

	render_trend() {
		const w = this.funnel.weeks || [];
		const cats = w.map(x => frappe.datetime.str_to_user(x.week).slice(0, 5));
		const $t = this.$root.find('#uod-trend').html(w.length
			? this.svg_bars(cats, [{ key: 'n', label: __('Applications'), color: '#920c24' }], w, { click: (i) => ({ week: w[i].week }), compact: true })
			: `<div class="uod-empty">${__('No applications for these filters.')}</div>`);
		this.bind_svg_clicks($t, 'app', __('Applications in week'));
	}

	bind_svg_clicks($scope, kind, title) {
		$scope.find('[data-x]').filter('g, rect').on('click', (e) => {
			const x = JSON.parse($(e.currentTarget).attr('data-x'));
			this.drill(`${title} · ${$(e.currentTarget).attr('data-cat')}`, kind, x);
		});
	}

	// ── SVG charts (no chart library: crisp in both themes, never redraws on resize) ──
	svg_bars(cats, series, rows, opts = {}) {
		if (!cats.length) return `<div class="uod-empty">${__('No data')}</div>`;
		const W = 560, H = opts.compact ? 200 : 230, L = 36, B = 34, T = 18;
		const totals = rows.map(r => series.reduce((a, s) => a + (r[s.key] || 0), 0));
		const max = Math.max(1, ...(opts.stacked ? totals : rows.map(r => Math.max(0, ...series.map(s => r[s.key] || 0)))));
		const nice = Math.pow(10, Math.floor(Math.log10(max)));
		const top = Math.ceil(max / nice) * nice || 1;
		const step = (W - L - 8) / cats.length;
		const bw = Math.min(46, step * 0.7);
		const y = (v) => T + (H - T - B) * (1 - v / top);
		let g = '';
		[0, 0.5, 1].forEach(f => {
			const v = Math.round(top * f);
			g += `<line x1="${L}" x2="${W}" y1="${y(v)}" y2="${y(v)}" class="uod-grid"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end" class="uod-axis">${this.n(v)}</text>`;
		});
		cats.forEach((c, i) => {
			const x0 = L + i * step + (step - bw) / 2;
			const x_attr = opts.click ? `data-x='${this.esc(JSON.stringify(opts.click(i)))}' data-cat="${this.esc(c)}" class="uod-bar-g is-click"` : 'class="uod-bar-g"';
			let bars = '';
			if (opts.stacked) {
				let acc = 0;
				series.forEach(s => {
					const v = rows[i][s.key] || 0;
					if (!v) return;
					bars += `<rect x="${x0}" y="${y(acc + v)}" width="${bw}" height="${y(acc) - y(acc + v)}" fill="${s.color}" rx="2" data-tip="${this.esc(`${c} · ${s.label}: ${this.n(v)}`)}"/>`;
					acc += v;
				});
				bars += `<text x="${x0 + bw / 2}" y="${y(totals[i]) - 5}" text-anchor="middle" class="uod-axis-v">${totals[i] ? this.n(totals[i]) : ''}</text>`;
			} else {
				const sw = bw / series.length;
				series.forEach((s, j) => {
					const v = rows[i][s.key] || 0;
					bars += `<rect x="${x0 + j * sw}" y="${y(v)}" width="${Math.max(sw - 2, 2)}" height="${Math.max(y(0) - y(v), 0)}" fill="${s.color}" rx="2" data-tip="${this.esc(`${c} · ${s.label}: ${this.n(v)}`)}"/>`;
					if (v && series.length <= 2 && !opts.compact) bars += `<text x="${x0 + j * sw + (sw - 2) / 2}" y="${y(v) - 5}" text-anchor="middle" class="uod-axis-v">${this.n(v)}</text>`;
				});
			}
			const label = cats.length > 14 && i % Math.ceil(cats.length / 14) ? '' : c;
			g += `<g ${x_attr}><rect x="${L + i * step}" y="${T}" width="${step}" height="${H - T - B}" fill="transparent"/>${bars}
				<text x="${x0 + bw / 2}" y="${H - B + 16}" text-anchor="middle" class="uod-axis">${this.esc(String(label).slice(0, 16))}</text></g>`;
		});
		return `<svg class="uod-svg" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
	}

	svg_dots(cats, vals) {
		if (!cats.length) return `<div class="uod-empty">${__('No offers with an issue date yet.')}</div>`;
		const W = 560, H = 200, L = 36, B = 34, T = 18;
		const top = Math.max(1, ...vals) * 1.15;
		const step = (W - L - 8) / cats.length;
		const y = (v) => T + (H - T - B) * (1 - v / top);
		let g = `<line x1="${L}" x2="${W}" y1="${y(0)}" y2="${y(0)}" class="uod-grid"/>`;
		cats.forEach((c, i) => {
			const x = L + i * step + step / 2;
			g += `<line x1="${x}" x2="${x}" y1="${y(0)}" y2="${y(vals[i])}" stroke="#920c24" stroke-dasharray="2 3"/>
				<circle cx="${x}" cy="${y(vals[i])}" r="5" fill="#920c24" data-tip="${this.esc(`${c}: ${vals[i]} ${__('days')}`)}"/>
				<text x="${x}" y="${y(vals[i]) - 10}" text-anchor="middle" class="uod-axis-v">${vals[i]}</text>
				<text x="${x}" y="${H - B + 16}" text-anchor="middle" class="uod-axis">${this.esc(String(c).slice(0, 16))}</text>`;
		});
		return `<svg class="uod-svg" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
	}

	svg_donut(items, field) {
		const total = items.reduce((a, b) => a + b.value, 0);
		if (!total) return `<div class="uod-empty">${__('No data')}</div>`;
		const R = 70, r = 44, C = 85;
		let a0 = -Math.PI / 2;
		const arc = (a1) => {
			const p = (rad, a) => `${C + rad * Math.cos(a)} ${C + rad * Math.sin(a)}`;
			const large = a1 - a0 > Math.PI ? 1 : 0;
			const d = `M ${p(R, a0)} A ${R} ${R} 0 ${large} 1 ${p(R, a1)} L ${p(r, a1)} A ${r} ${r} 0 ${large} 0 ${p(r, a0)} Z`;
			a0 = a1;
			return d;
		};
		const slices = items.map(it => {
			const a1 = a0 + (it.value / total) * Math.PI * 2 - (items.length === 1 ? 0.0001 : 0);
			return `<path class="uod-slice is-click" d="${arc(a1)}" fill="${it.color}" data-field="${field}" data-value="${this.esc(it.key)}"
				data-tip="${this.esc(`${it.label}: ${this.n(it.value)} (${this.pct_txt(it.value, total)})`)}"/>`;
		}).join('');
		const legend = items.slice(0, 8).map(it => `<div class="is-click" data-field="${field}" data-value="${this.esc(it.key)}"><i style="background:${it.color}"></i>
			<span class="lbl">${this.esc(it.label)}</span><b>${this.n(it.value)}</b><span class="uod-muted">${this.pct_txt(it.value, total)}</span></div>`).join('');
		return `<div class="uod-donut"><svg class="uod-donut-svg" viewBox="0 0 170 170">${slices}
			<text x="${C}" y="${C + 7}" text-anchor="middle" class="uod-donut-total">${this.n(total)}</text></svg>
			<div class="uod-donut-legend">${legend}</div></div>`;
	}

	bind_tip($scope) {
		const $tip = () => this.$root.find('#uod-tip');
		$scope.on('mousemove', '[data-tip]', (e) => {
			const t = $(e.currentTarget).attr('data-tip');
			$tip().text(t).css({ left: e.clientX + 14, top: e.clientY + 14 }).addClass('is-on');
		});
		$scope.on('mouseleave', '[data-tip]', () => { $tip().removeClass('is-on'); });
	}

	export_csv(name, columns, rows) {
		const q = (v) => `"${String(v === null || v === undefined ? '' : v).replace(/"/g, '""')}"`;
		const csv = [columns.map(c => q(c.label)).join(',')].concat(rows.map(r => columns.map(c => q(r[c.key])).join(','))).join('\n');
		const a = document.createElement('a');
		a.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
		a.download = `${name}-${frappe.datetime.get_today()}.csv`;
		a.click();
		setTimeout(() => { URL.revokeObjectURL(a.href); }, 1000);
	}

	// ── card guide ─────────────────────────────────────────────────────────
	open_guide() {
		const d = new frappe.ui.Dialog({ title: __('Card guide — what each number means'), size: 'extra-large' });
		const row = (c) => `<tr><th>${this.esc(c.label)}</th><td>${this.esc(c.guide || '')}</td></tr>`;
		const sections = [`<div class="uod-guide-sec">${__('Headline')}</div><table class="uod-guide">${this.meta.headline.map(row).join('')}</table>`]
			.concat(this.meta.board.map(s => {
				const kinds = Array.from(new Set([].concat(...s.tiles.map(t => t.cards.map(c => c.kind)))));
				const notes = kinds.map(k => {
					const src = this.meta.sources[k] || {};
					return `${this.esc(src.label || k)}: ${(src.honours || []).length ? this.esc(src.honours.join(', ')) : __('no filters (always everything you can see)')}`;
				}).join(' · ');
				return `<div class="uod-guide-sec">${this.esc(s.title)}</div><div class="uod-muted uod-guide-note">${__('Filters that apply')} — ${notes}</div>
				<table class="uod-guide">${s.tiles.map(t => t.cards.map(row).join('')).join('')}</table>`;
			}));
		d.$body.html(`<style>${UOD_CSS}</style><div class="uod-root uod-in-modal">
			<p class="uod-muted">${__('Every card counts records that are in that state <b>right now</b>, for the filters you applied, and only records you are allowed to see. Each module responds to the filters that exist on its records — listed under each section below. Cards marked "any date" are backlogs and ignore the date range. Click any number to open the list behind it; click a person for their timeline.')}</p>
			${sections.join('')}</div>`);
		d.show();
	}
}

const UOD_CSS = `
.uod-root { --page:#f0f2f5; --bg:#ffffff; --bg-soft:#f8fafc; --border:#e2e8f0; --border-soft:#edf0f4; --text:#1f1a17;
	--text-2:#3b342f; --muted:#57504a; --head:#7a0a1e; --link:#920c24; --hover:#fbf1f3; --grid:#e8e4e0;
	--brand:#920c24; --brand-tint:#fbf1f3; --shadow:0 1px 2px rgba(31,26,23,.05), 0 2px 8px rgba(31,26,23,.04);
	--pipe-open:#920c24; --pipe-ended:#e7b3bd; --font:"Merriweather", Georgia, "Times New Roman", serif;
	color:var(--text); padding:18px 22px 48px; background:var(--page); min-height:100%; transition:opacity .15s; font-family:var(--font); }
:root[data-theme="dark"] .uod-root { --page:#151312; --bg:#1f1c1a; --bg-soft:#252220; --border:#35302d; --border-soft:#2c2826;
	--text:#f2eeea; --text-2:#d4cdc7; --muted:#a79f98; --head:#4d232b; --link:#f07a8e; --hover:#2a2220; --grid:#35302d;
	--brand:#f07a8e; --brand-tint:#3a1c22; --shadow:none; --pipe-open:#f07a8e; --pipe-ended:#5a2a33; }
.uod-root button, .uod-root input, .uod-root select, .uod-root table { font-family:var(--font); }
.modal-dialog.uod-modal .modal-title, .modal-dialog.uod-modal-tl .modal-title { font-family:"Merriweather", Georgia, serif; }
.uod-root.uod-in-modal { padding:0; background:transparent; min-height:0; }
.uod-root.uod-loading { opacity:.6; }
.uod-muted { color:var(--muted); font-size:12px; }
.uod-tabs { display:flex; gap:2px; margin-bottom:12px; border-bottom:1px solid var(--border); }
.uod-tab { background:none; border:0; border-bottom:2px solid transparent; margin-bottom:-1px; padding:7px 16px; font-size:13px; font-weight:600; color:var(--muted); cursor:pointer; }
.uod-tab:hover { color:var(--text); }
.uod-tab.is-on { color:var(--brand); border-bottom-color:var(--brand); }
.uod-pane[hidden] { display:none !important; }
.uod-filters { background:var(--bg); border:1px solid var(--border); border-radius:10px; padding:12px 16px 14px; margin-bottom:16px; box-shadow:var(--shadow); }
.uod-topbar { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap; }
.uod-topbar-right { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.uod-topbar-right b { color:var(--text); }
.uod-presets { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
.uod-preset { border:1px solid var(--border); background:var(--bg-soft); color:var(--text-2); border-radius:20px; padding:3px 12px; font-size:12px; font-weight:600; cursor:pointer; }
.uod-preset:hover { border-color:var(--brand); color:var(--brand); }
.uod-preset.is-on { background:var(--brand); border-color:var(--brand); color:#fff; }
:root[data-theme="dark"] .uod-preset.is-on, :root[data-theme="dark"] #uod-apply { color:#1f1a17; }
.uod-filter-row { display:flex; flex-wrap:wrap; gap:10px; align-items:flex-end; }
.uod-f { display:flex; flex-direction:column; gap:3px; }
.uod-f label { font-size:10.5px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; margin:0; }
.uod-f input[type=date] { height:32px; border:1px solid var(--border); border-radius:8px; padding:0 8px; font-size:12.5px; background:var(--bg); color:var(--text); }
.uod-f-btns { flex-direction:row; gap:6px; margin-left:auto; align-self:flex-end; }
#uod-apply { background:var(--brand); border-color:var(--brand); color:#fff; }
.uod-ms { position:relative; }
/* Wide screens: one row, the multi-selects share the free width. Narrower: wrap. */
@media (min-width:1251px) { .uod-filter-row { flex-wrap:nowrap; } .uod-f:has(.uod-ms) { flex:1 1 0; min-width:0; } }
@media (max-width:1250px) { .uod-ms { width:160px; } }
@media (max-width:700px) { .uod-f:has(.uod-ms), .uod-f:has(input[type=date]) { flex:1 1 calc(50% - 10px); min-width:0; } .uod-ms, .uod-f input[type=date] { width:100%; } }
.uod-ms-box { display:flex; flex-wrap:wrap; align-items:center; overflow:hidden; gap:4px; padding:3px 8px; border:1px solid var(--border); border-radius:8px; background:var(--bg); cursor:pointer; min-height:32px; }
.uod-ms.open .uod-ms-box { border-color:var(--brand); box-shadow:0 0 0 3px color-mix(in srgb, var(--brand) 18%, transparent); }
.uod-ms-ph { font-size:12.5px; color:var(--muted); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; min-width:0; }
.uod-ms-chip { display:inline-flex; align-items:center; gap:4px; background:color-mix(in srgb, var(--brand) 12%, transparent); color:var(--text-2); border-radius:6px; padding:1px 5px 1px 7px; font-size:11px; font-weight:600; max-width:120px; }
.uod-ms-chip .txt { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uod-ms-chip .x { cursor:pointer; opacity:.7; }
.uod-ms-more { font-size:11px; color:var(--muted); font-weight:600; }
.uod-ms-panel { display:none; position:absolute; top:calc(100% + 4px); left:0; z-index:60; background:var(--bg); border:1px solid var(--border); border-radius:10px;
	box-shadow:0 10px 24px -8px rgba(16,24,40,.25); width:max(100%,270px); max-width:min(360px,90vw); max-height:300px; overflow-y:auto; }
.uod-ms.open .uod-ms-panel { display:block; }
.uod-ms-search { position:sticky; top:0; background:var(--bg); padding:6px; border-bottom:1px solid var(--border-soft); }
.uod-ms-search input { width:100%; padding:5px 8px; border:1px solid var(--border); border-radius:6px; font-size:12px; background:var(--bg); color:var(--text); }
.uod-ms-actions { display:flex; justify-content:space-between; padding:5px 8px; border-bottom:1px solid var(--border-soft); font-size:11px; }
.uod-ms-actions a { color:var(--link); cursor:pointer; font-weight:600; }
.uod-ms-opt { display:flex; gap:8px; padding:6px 10px; font-size:12px; cursor:pointer; margin:0; font-weight:400; color:var(--text); }
.uod-ms-opt:hover { background:var(--hover); }
/* Options sit inside .uod-f, whose labels are small caps: undo that for the list. */
.uod-f .uod-ms-opt { text-transform:none; letter-spacing:0; font-size:12.5px; font-weight:400; color:var(--text); align-items:center; }
.uod-ms-empty, .uod-empty { padding:14px; font-size:12px; color:var(--muted); text-align:center; }
/* cards */
.uod-headline { display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); gap:12px; }
.uod-headline.is-funnel { column-gap:18px; }
.uod-headline.is-funnel .uod-kpi:not(:last-child)::after { content:'›'; position:absolute; right:-14px; top:30px; width:10px; text-align:center; font-size:20px; line-height:1; color:var(--muted); pointer-events:none; }
.uod-headline.is-funnel .uod-kpi:has(+ .is-aside)::after { display:none; }
.uod-kpi, .uod-tile { position:relative; background:var(--bg); border:1px solid var(--border); border-radius:12px; box-shadow:var(--shadow); min-width:0; transition:border-color .15s, box-shadow .15s, transform .15s; }
.uod-kpi { padding:14px 16px 12px; display:flex; flex-direction:column; gap:6px; }
.uod-kpi.is-click, .uod-half.is-click, .uod-tile-1.is-click { cursor:pointer; }
.uod-kpi.is-click:hover, .uod-tile-1.is-click:hover, .uod-tile-2:has(.uod-half.is-click:hover) { border-color:color-mix(in srgb, var(--brand) 45%, var(--border)); box-shadow:0 4px 14px -6px rgba(31,26,23,.18); transform:translateY(-1px); }
@media (prefers-reduced-motion:reduce) { .uod-kpi, .uod-tile { transition:none; transform:none !important; } }
.uod-kpi:focus-visible, .uod-half:focus-visible, .uod-tile-1:focus-visible { outline:none; box-shadow:0 0 0 2px var(--brand); }
.uod-kpi-top, .uod-tile-head { display:flex; align-items:center; justify-content:space-between; gap:8px; min-width:0; }
.uod-kpi-label, .uod-tile-title { font-size:13.5px; font-weight:650; color:var(--text); display:flex; align-items:center; min-width:0; line-height:1.3; }
.uod-kpi-value { font-size:28px; font-weight:700; letter-spacing:-.02em; line-height:1.15; color:var(--text); font-variant-numeric:tabular-nums; display:flex; align-items:center; }
.uod-share { font-size:11.5px; font-weight:600; color:var(--text-2); background:var(--bg-soft); border:1px solid var(--border); border-radius:20px; padding:1px 8px; margin-left:10px; letter-spacing:0; }
.uod-kpi-sub { font-size:12px; color:var(--muted); }
.uod-dot { display:inline-block; flex:none; width:8px; height:8px; border-radius:50%; background:var(--c); margin-right:7px; }
.uod-info { flex:none; display:inline-grid; place-items:center; width:16px; height:16px; border-radius:50%; border:1px solid var(--border); color:var(--muted); font-size:10px; font-style:italic; font-family:Georgia, serif; cursor:help; }
.uod-section { margin-top:22px; }
.uod-section-title { display:flex; align-items:center; gap:10px; font-size:11px; font-weight:700; color:var(--text-2); text-transform:uppercase; letter-spacing:.06em; margin:0 2px 10px; }
.uod-section-title::after { content:''; flex:1; border-top:1px solid var(--border); }
.uod-section-note { text-transform:none; letter-spacing:0; font-weight:500; color:var(--muted); order:2; }
.uod-tiles { display:grid; grid-template-columns:repeat(6, minmax(0,1fr)); gap:12px; }
.uod-tile { padding:14px 16px 12px; display:flex; flex-direction:column; gap:6px; }
.uod-tile-2 { grid-column:span 2; }
.uod-halves { display:grid; grid-template-columns:repeat(var(--n, 2), minmax(0,1fr)); gap:0; }
.uod-tile-3 { grid-column:span 3; }
@media (max-width:700px) { .uod-tile-3 { grid-column:1 / -1; } }
.uod-tile-head .uod-tile-title .uod-info { margin-left:8px; }
.uod-tile-tools { display:flex; align-items:center; gap:12px; flex-wrap:wrap; justify-content:flex-end; }
.uod-money-total { font-size:12px; color:var(--muted); }
.uod-money-total b { font-size:14px; color:var(--text); margin-left:4px; font-variant-numeric:tabular-nums; }
.uod-link-btn { border:1px solid color-mix(in srgb, var(--brand) 35%, var(--border)); background:var(--brand-tint); color:var(--brand); border-radius:20px;
	padding:3px 12px; font-size:12px; font-weight:600; cursor:pointer; }
.uod-link-btn:hover { background:var(--brand); color:#fff; }
:root[data-theme="dark"] .uod-link-btn:hover { color:#1f1a17; }
/* overview: four equal admission tiles, then one wide money tile */
.uod-tiles.is-ov { grid-template-columns:repeat(4, minmax(0,1fr)); }
.uod-tiles.is-ov .uod-tile { grid-column:span 1; }
.uod-tiles.is-wide .uod-tile { grid-column:1 / -1; }
.uod-tile.is-money .uod-kpi-value { font-size:26px; }
@media (max-width:1250px) { .uod-tiles.is-ov { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width:700px) { .uod-tiles.is-ov { grid-template-columns:minmax(0,1fr); }
	.uod-tile.is-money .uod-halves { grid-template-columns:minmax(0,1fr); }
	.uod-tile.is-money .uod-half + .uod-half { border-left:0; padding-left:0; border-top:1px solid var(--border-soft); padding-top:10px; margin-top:6px; } }
/* overview: module snapshots */
.uod-snaps { display:grid; grid-template-columns:repeat(auto-fill, minmax(230px, 1fr)); gap:12px; }
.uod-snap { background:var(--bg); border:1px solid var(--border); border-radius:12px; box-shadow:var(--shadow); display:flex; flex-direction:column; min-width:0; }
.uod-snap-head { display:flex; align-items:center; gap:10px; width:100%; background:none; border:0; border-bottom:1px solid var(--border-soft);
	padding:11px 14px; cursor:pointer; text-align:left; color:var(--text); border-radius:12px 12px 0 0; }
.uod-snap-head:hover { background:var(--brand-tint); }
.uod-snap-head:hover .uod-snap-go { transform:translateX(3px); color:var(--brand); }
.uod-snap-head:focus-visible { outline:none; box-shadow:inset 0 0 0 2px var(--brand); }
.uod-snap-ico { flex:none; width:28px; height:28px; padding:6px; border-radius:8px; color:var(--brand); background:var(--brand-tint); display:inline-flex; }
.uod-snap-ico svg { width:100%; height:100%; }
.uod-snap-name { flex:1; font-size:13.5px; font-weight:700; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uod-snap-go { font-size:18px; color:var(--muted); transition:transform .15s, color .15s; }
.uod-snap-figs { display:grid; grid-template-columns:1fr 1fr; }
.uod-snap-fig { display:flex; flex-direction:column; gap:2px; padding:10px 14px 12px; min-width:0; }
.uod-snap-fig + .uod-snap-fig { border-left:1px solid var(--border-soft); }
.uod-snap-fig b { font-size:20px; color:var(--text); font-variant-numeric:tabular-nums; line-height:1.2; }
.uod-snap-fig span { font-size:11.5px; color:var(--muted); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uod-snap-fig.is-click { cursor:pointer; border-radius:0 0 12px 12px; }
.uod-snap-fig.is-click:hover b { color:var(--link); }
.uod-snap-fig:focus-visible { outline:none; box-shadow:inset 0 0 0 2px var(--brand); }
/* admission: type picker */
.uod-adm-pick { display:grid; grid-template-columns:repeat(auto-fit, minmax(240px, 1fr)); gap:12px; margin-bottom:6px; }
.uod-adm { display:flex; flex-direction:column; gap:10px; text-align:left; background:var(--bg); border:1px solid var(--border); border-radius:12px;
	padding:12px 16px 14px; cursor:pointer; color:var(--text); box-shadow:var(--shadow); transition:border-color .15s, box-shadow .15s; }
.uod-adm:hover { border-color:color-mix(in srgb, var(--brand) 45%, var(--border)); }
.uod-adm:focus-visible { outline:none; box-shadow:0 0 0 2px var(--brand); }
.uod-adm.is-on { border-color:var(--brand); box-shadow:inset 0 0 0 1px var(--brand), var(--shadow); background:color-mix(in srgb, var(--brand) 4%, var(--bg)); }
.uod-adm-top { display:flex; align-items:center; gap:10px; }
.uod-adm-ico { flex:none; width:30px; height:30px; padding:7px; border-radius:8px; color:var(--muted); background:var(--bg-soft); border:1px solid var(--border); display:inline-flex; }
.uod-adm.is-on .uod-adm-ico { color:var(--brand); background:var(--brand-tint); border-color:color-mix(in srgb, var(--brand) 25%, transparent); }
.uod-adm-ico svg { width:100%; height:100%; }
.uod-adm-name { font-size:14px; font-weight:700; }
.uod-adm-figs { display:grid; grid-template-columns:repeat(3, minmax(0,1fr)); gap:8px; }
.uod-adm-fig { display:flex; flex-direction:column; min-width:0; }
.uod-adm-fig b { font-size:16px; font-variant-numeric:tabular-nums; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.uod-adm-fig small { font-size:11px; color:var(--muted); }
.uod-adm-pane[hidden] { display:none !important; }
/* programme management: programme-type switch */
.uod-scope-bar { display:flex; align-items:center; gap:10px 16px; flex-wrap:wrap; margin:0 0 16px; }
.uod-scope-switch { display:inline-flex; padding:3px; gap:2px; background:var(--bg); border:1px solid var(--border); border-radius:10px; box-shadow:var(--shadow); max-width:100%; overflow-x:auto; }
.uod-scope { border:0; background:none; padding:6px 16px; border-radius:7px; font-size:12.5px; font-weight:600; color:var(--text-2); cursor:pointer; white-space:nowrap; transition:background .15s, color .15s; }
.uod-scope:hover { color:var(--brand); background:var(--brand-tint); }
.uod-scope.is-on { background:var(--brand); color:#fff; }
:root[data-theme="dark"] .uod-scope.is-on { color:#1f1a17; }
.uod-scope:focus-visible { outline:2px solid var(--brand); outline-offset:1px; }
.uod-scope-pane[hidden] { display:none !important; }
.uod-scope-pane { animation:uod-fade .18s ease-out; }
.uod-scope-pane > .uod-section:first-child { margin-top:0; }
.uod-scope-list { margin-bottom:0; }
.uod-adm-pane { animation:uod-fade .18s ease-out; }
/* money breakdown popup */
.uod-mb-types { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:12px; }
.uod-mb-type { display:flex; flex-direction:column; align-items:flex-start; gap:1px; min-width:150px; text-align:left; border:1px solid var(--border);
	background:var(--bg); border-radius:10px; padding:8px 14px; cursor:pointer; color:var(--text); }
.uod-mb-type span { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.uod-mb-type b { font-size:18px; font-variant-numeric:tabular-nums; }
.uod-mb-type small { font-size:11.5px; color:var(--muted); }
.uod-mb-type:hover { border-color:var(--brand); }
.uod-mb-type.is-on { border-color:var(--brand); box-shadow:inset 0 0 0 1px var(--brand); background:color-mix(in srgb, var(--brand) 6%, var(--bg)); }
/* admission: key cards */
.uod-kpis { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; }
@media (max-width:1000px) { .uod-kpis { grid-template-columns:repeat(2, minmax(0,1fr)); } }
@media (max-width:520px) { .uod-kpis { grid-template-columns:minmax(0,1fr); } }
/* admission: programme filter toolbar */
.uod-adm-tools { display:flex; align-items:flex-end; gap:12px 20px; flex-wrap:wrap; margin:16px 0 4px; padding:12px 16px; background:var(--bg);
	border:1px solid var(--border); border-radius:12px; box-shadow:var(--shadow); }
/* Everything beside the Programme field sits on its 32px input row. */
.uod-adm-tools > .uod-switch, .uod-adm-tools > .uod-adm-scope { height:32px; display:inline-flex; align-items:center; margin:0; }
/* Programme count hugs the right edge. */
.uod-adm-tools > .uod-adm-scope { margin-left:auto; }
.uod-adm-tools .uod-adm-prog { flex:0 1 420px; min-width:240px; }
.uod-adm-tools .uod-adm-prog .uod-ms { width:100%; }
.uod-adm-tools .uod-ms-chip, .uod-dd-prog .uod-ms-chip { max-width:220px; }
.uod-adm-scope { margin-left:auto; white-space:nowrap; }
.uod-switch { display:inline-flex; align-items:center; gap:8px; margin:0 0 6px; font-size:12.5px; font-weight:500; color:var(--text-2); cursor:pointer; user-select:none; }
/* The real checkbox stays (keyboard, screen readers) but is hidden; the track is drawn. */
.uod-switch input[type=checkbox] { position:absolute; opacity:0; width:1px; height:1px; margin:0; pointer-events:none; }
.uod-switch-track { flex:none; width:32px; height:18px; border-radius:9px; background:var(--border); position:relative; transition:background .15s; }
.uod-switch-track::after { content:''; position:absolute; top:2px; left:2px; width:14px; height:14px; border-radius:50%; background:#fff; box-shadow:0 1px 2px rgba(0,0,0,.25); transition:transform .15s; }
.uod-switch input:checked + .uod-switch-track { background:var(--brand); }
.uod-switch input:checked + .uod-switch-track::after { transform:translateX(14px); }
.uod-switch input:focus-visible + .uod-switch-track { outline:2px solid var(--brand); outline-offset:2px; }
.uod-switch { position:relative; }
@media (max-width:700px) { .uod-st-title { flex-wrap:wrap; } .uod-st-title::after { display:none; } .uod-st-title .uod-section-note { display:none; } .uod-adm-fold { margin-left:auto; }
	.uod-adm-tools .uod-adm-prog { flex:1 1 100%; } .uod-adm-tools > .uod-adm-scope { margin-left:0; order:5; width:100%; height:auto; } }
/* admission: status × programme table */
.uod-st-panel { width:100%; background:var(--bg); border:1px solid var(--border); border-radius:12px; box-shadow:var(--shadow); overflow:hidden; }
.uod-st-table { width:100%; border-collapse:separate; border-spacing:0; font-size:13px; }
.uod-st-table th { background:var(--bg-soft); color:var(--muted); font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.05em;
	padding:11px 16px; border-bottom:1px solid var(--border); text-align:left; vertical-align:bottom; line-height:1.35; }
.uod-st-table td { padding:10px 16px; border-bottom:1px solid var(--border-soft); color:var(--text); white-space:nowrap; vertical-align:middle; }
.uod-st-table tbody tr:last-child td { border-bottom:0; }
.uod-st-table tbody tr:not(.uod-st-group):hover td { background:var(--hover); }
.uod-st-row { cursor:pointer; }
.uod-st-row:focus-visible { outline:none; }
.uod-st-row:focus-visible td { background:var(--hover); }
.uod-st-row:focus-visible td.uod-st-name { box-shadow:inset 3px 0 0 var(--brand); }
.uod-st-row:hover td.uod-st-name { box-shadow:inset 3px 0 0 color-mix(in srgb, var(--brand) 55%, transparent); }
/* Status takes about a third; the number columns share the rest. */
.uod-st-table th.uod-st-name, .uod-st-table td.uod-st-name { position:sticky; left:0; z-index:1; min-width:260px; width:34%; }
.uod-st-table td.uod-st-name { background:var(--bg); font-weight:600; }
.uod-st-table th.uod-st-name { z-index:2; }
.uod-st-table td.uod-st-name .uod-info { margin-left:8px; vertical-align:1px; }
.uod-st-table td.uod-st-name .uod-flag { vertical-align:1px; }
.uod-st-table .uod-st-n { text-align:right; min-width:96px; font-variant-numeric:tabular-nums; }
.uod-st-table th.uod-st-n { white-space:normal; }
.uod-st-pre { color:var(--muted); font-weight:500; margin-right:6px; }
.uod-st-pre::after { content:'·'; margin-left:6px; }
.uod-st-group td { background:var(--bg) !important; padding:0; border-bottom:1px solid var(--border); }
.uod-st-group:not(:first-child) td { border-top:6px solid var(--bg-soft); }
.uod-st-toggle { position:sticky; left:0; display:flex; align-items:center; gap:10px; width:auto; max-width:100vw; background:none; border:0;
	padding:12px 16px; cursor:pointer; text-align:left; color:var(--text); }
.uod-st-toggle:hover .uod-st-gtitle { text-decoration:underline; text-underline-offset:3px; }
.uod-st-toggle:focus-visible { outline:2px solid var(--brand); outline-offset:-2px; border-radius:6px; }
.uod-st-chev { display:inline-flex; width:16px; height:16px; color:var(--brand); transition:transform .18s; }
.uod-st-chev svg { width:100%; height:100%; }
.uod-st-group.is-closed .uod-st-chev { transform:rotate(-90deg); }
.uod-st-gtitle { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:.07em; color:var(--brand); white-space:nowrap; }
.uod-st-gmeta { font-size:12px; color:var(--muted); white-space:nowrap; }
.uod-st-gmeta b { color:${UOD_TONES.action}; font-weight:600; }
.uod-st-row.is-collapsed { display:none; }
.uod-st-title { min-height:30px; }
.uod-st-title .uod-section-note { order:2; }
.uod-adm-fold { order:3; display:inline-flex; align-items:stretch; height:28px; flex:none; border:1px solid var(--border); border-radius:8px; overflow:hidden;
	background:var(--bg); box-shadow:var(--shadow); text-transform:none; letter-spacing:0; }
.uod-adm-fold button { height:100%; display:inline-flex; align-items:center; gap:6px; padding:0 11px; border:0; background:none;
	font-size:12px; font-weight:600; color:var(--text-2); cursor:pointer; white-space:nowrap; }
.uod-adm-fold button + button { border-left:1px solid var(--border); }
.uod-adm-fold button svg { width:14px; height:14px; color:var(--muted); }
.uod-adm-fold button:hover { background:var(--brand-tint); color:var(--brand); }
.uod-adm-fold button:hover svg { color:var(--brand); }
.uod-adm-fold button:focus-visible { outline:2px solid var(--brand); outline-offset:-2px; }
@media (prefers-reduced-motion:reduce) { .uod-st-chev { transition:none; } }
/* Total (and Amount) read as summary columns: tinted, bold. */
.uod-st-table .uod-st-tot { background:color-mix(in srgb, var(--bg-soft) 70%, var(--bg)); font-weight:700; border-left:1px solid var(--border-soft); }
.uod-st-table th.uod-st-tot { background:color-mix(in srgb, var(--border-soft) 60%, var(--bg-soft)); color:var(--text-2); }
.uod-st-table tbody tr:not(.uod-st-group):hover td.uod-st-tot { background:color-mix(in srgb, var(--hover) 80%, var(--bg-soft)); }
.uod-st-amt { color:var(--text-2); font-weight:600; }
.uod-st-num { color:var(--text); font-weight:600; cursor:pointer; text-decoration:none; border-radius:6px; padding:2px 7px; margin:-2px -7px; }
.uod-st-num:hover, .uod-st-num:focus-visible { background:var(--brand-tint); color:var(--link); text-decoration:none; outline:none; }
.uod-st-zero { color:var(--muted); opacity:.45; }
.uod-st-na { display:inline-block; width:10px; }
.uod-st-table tr.is-action td.uod-st-name { color:${UOD_TONES.action}; }
.uod-st-table tr.is-action .uod-st-num { color:${UOD_TONES.action}; }
.uod-st-share { min-width:180px; }
.uod-st-sharebox { display:flex; align-items:center; gap:10px; }
.uod-st-bar { flex:1; height:6px; border-radius:3px; background:var(--border-soft); overflow:hidden; min-width:80px; }
.uod-st-bar i { display:block; height:100%; background:var(--brand); border-radius:3px; }
.uod-st-pct { width:46px; text-align:right; font-size:12px; color:var(--muted); font-variant-numeric:tabular-nums; }
.uod-st-foot { padding:9px 16px; font-size:11.5px; color:var(--muted); border-top:1px solid var(--border-soft); background:var(--bg-soft); }
/* drilldown programme picker */
.uod-dd-bar { display:flex; align-items:flex-end; gap:12px; flex-wrap:wrap; margin-bottom:12px; }
.uod-dd-bar[hidden] { display:none; }
.uod-dd-prog .uod-ms { width:360px; max-width:80vw; }
.uod-mb-progs .uod-section-title { margin-top:4px; }
.uod-mb-panel { width:100%; min-width:0; margin-bottom:16px; }
.uod-mb-scroll { max-height:300px; overflow:auto; overscroll-behavior:contain; }
.uod-mb-scroll thead th { position:sticky; top:0; z-index:3; }
.uod-mb-scroll thead th.uod-st-name { z-index:4; }
.uod-mb-row { cursor:pointer; }
.uod-mb-row:focus-visible td { outline:none; background:var(--hover); }
.uod-mb-row.is-on td, .uod-mb-row.is-on:hover td { background:color-mix(in srgb, var(--brand) 8%, var(--bg)) !important; }
.uod-mb-row.is-on td.uod-st-name { box-shadow:inset 3px 0 0 var(--brand); }
.uod-mb-row.is-zero td { color:var(--muted); }
.uod-mb-listhead .uod-section-title { margin:4px 2px 8px; }
.uod-mb-total { font-size:12.5px; color:var(--muted); margin-bottom:8px; }
.uod-mb-total b { color:var(--text); font-size:14px; }
.uod-regid { font-size:12.5px; font-weight:500; color:var(--text-2); background:var(--bg-soft); border:1px solid var(--border); border-radius:20px; padding:1px 10px; }
.uod-half { padding:2px 10px 2px 0; border-radius:6px; display:flex; flex-direction:column; gap:4px; min-width:0; }
.uod-half + .uod-half { border-left:1px solid var(--border-soft); padding-left:18px; }
.uod-half.is-click:hover .uod-kpi-value { color:var(--link) !important; }
/* Block (not flex) so a long label wraps as text and keeps its dot on the first line. */
.uod-half-label { font-size:12.5px; font-weight:600; color:var(--text); display:block; line-height:1.35; }
.uod-half-label .uod-dot { vertical-align:1px; }
.uod-half-label .uod-flag { display:inline-block; vertical-align:1px; }
.uod-flag { margin-left:6px; font-size:9.5px; font-weight:700; color:#B7651B; border:1px solid #B7651B; border-radius:3px; padding:0 4px; text-transform:uppercase; letter-spacing:.04em; }
@media (max-width:1250px) { .uod-headline, .uod-tiles { grid-template-columns:repeat(3, minmax(0,1fr)); } .uod-headline.is-funnel .uod-kpi::after { display:none; } }
@media (max-width:700px) { .uod-headline, .uod-tiles { grid-template-columns:repeat(2, minmax(0,1fr)); } .uod-tile-2 { grid-column:span 2; } .uod-root { padding:12px 16px 40px; } }
/* panels & tables */
.uod-panel { background:var(--bg); border:1px solid var(--border); border-radius:10px; box-shadow:var(--shadow); margin-bottom:16px; min-width:0; }
.uod-panel-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; flex-wrap:wrap; padding:12px 14px; border-bottom:1px solid var(--border-soft); }
.uod-panel-title { font-size:14px; font-weight:700; color:var(--text); }
.uod-panel-sub { font-size:11.5px; color:var(--muted); margin-top:2px; }
.uod-panel-body { padding:14px; transition:opacity .15s; }
.uod-panel-tools { display:flex; gap:6px; flex-wrap:wrap; }
.uod-st-loading { opacity:.55; }
.uod-grid-2 { display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:12px; }
.uod-grid-2 > .uod-panel { margin-bottom:16px; }
@media (max-width:900px) { .uod-grid-2 { grid-template-columns:minmax(0,1fr); } }
.uod-table-scroll { overflow-x:auto; position:relative; }
.uod-table { width:100%; border-collapse:collapse; font-size:12.5px; }
.uod-table th { background:var(--head); color:#fff; font-weight:600; text-align:left; padding:8px 10px; white-space:nowrap; position:sticky; top:0; }
.uod-table th.is-sort { cursor:pointer; }
.uod-arrow { opacity:.7; font-size:10px; }
.uod-table td { padding:8px 10px; border-bottom:1px solid var(--border-soft); color:var(--text); vertical-align:middle; white-space:nowrap; }
.uod-table tbody tr:hover td { background:var(--hover); }
.uod-trunc { display:inline-block; max-width:240px; overflow:hidden; text-overflow:ellipsis; vertical-align:bottom; }
.uod-idlink, .uod-cand, .uod-num { color:var(--link); font-weight:600; cursor:pointer; text-decoration:underline; text-decoration-color:color-mix(in srgb, var(--link) 35%, transparent); text-underline-offset:3px; }
.uod-pill { display:inline-block; font-size:11px; font-weight:600; color:color-mix(in srgb, var(--c) 80%, #000); background:color-mix(in srgb, var(--c) 12%, transparent);
	border:1px solid color-mix(in srgb, var(--c) 35%, transparent); border-radius:20px; padding:1px 8px; white-space:nowrap; }
:root[data-theme="dark"] .uod-pill { color:color-mix(in srgb, var(--c) 60%, #fff); }
.uod-days { font-weight:600; font-variant-numeric:tabular-nums; }
.uod-days.is-long { color:#B7651B; }
.uod-tt-tools { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 14px; }
.uod-search { flex:0 1 380px; }
.uod-search input { width:100%; height:34px; border:1px solid var(--border); border-radius:8px; padding:0 10px; font-size:12.5px; background:var(--bg); color:var(--text); }
.uod-tt-export { margin-left:auto; }
.uod-tt-pager { display:flex; justify-content:space-between; align-items:center; gap:10px; flex-wrap:wrap; padding:10px 14px; }
.uod-tt-pager select { margin-left:6px; height:28px; border:1px solid var(--border); border-radius:6px; background:var(--bg); color:var(--text); }
.uod-pages { display:flex; align-items:center; gap:4px; }
.uod-pg { border:1px solid var(--border); background:var(--bg); color:var(--text); border-radius:6px; min-width:28px; height:28px; cursor:pointer; }
.uod-pg:disabled { opacity:.4; cursor:default; }
/* funnel */
.uod-fun { display:flex; flex-direction:column; gap:2px; }
.uod-fun-row { display:grid; grid-template-columns:170px minmax(0,1fr) 80px 120px 90px 150px; align-items:center; gap:12px; padding:6px; border-radius:6px; font-size:12.5px; }
.uod-fun-row.is-click { cursor:pointer; }
.uod-fun-row.is-click:hover { background:var(--hover); }
.uod-fun-label { font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.uod-fun-track, .uod-bar-track { height:18px; background:var(--border-soft); border-radius:0 4px 4px 0; overflow:hidden; display:block; }
.uod-fun-bar, .uod-bar-fill { display:block; height:100%; background:var(--brand); border-radius:0 4px 4px 0; }
.uod-fun-val { text-align:right; font-variant-numeric:tabular-nums; }
.uod-fun-pct, .uod-fun-lost { white-space:nowrap; font-variant-numeric:tabular-nums; }
.uod-fun-lost { font-size:11.5px; color:var(--muted); }
@media (max-width:900px) { .uod-fun-row { grid-template-columns:110px minmax(0,1fr) 64px; } .uod-fun-pct, .uod-fun-lost { grid-column:2 / -1; } }
.uod-fun-table td { white-space:nowrap; }
.uod-bars { display:flex; flex-direction:column; gap:4px; }
.uod-bar-row { display:grid; grid-template-columns:150px minmax(0,1fr) 170px; align-items:center; gap:10px; padding:5px 6px; border-radius:6px; font-size:12.5px; }
.uod-bar-row.is-click { cursor:pointer; }
.uod-bar-row.is-click:hover { background:var(--hover); }
.uod-bar-label { display:flex; align-items:center; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.uod-bar-val { text-align:right; white-space:nowrap; font-variant-numeric:tabular-nums; }
@media (max-width:600px) { .uod-bar-row { grid-template-columns:100px minmax(0,1fr); } .uod-bar-val { grid-column:1 / -1; text-align:left; } }
.uod-tl-kpis { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:12px; margin-bottom:12px; }
.uod-tl-kpi { border:1px solid var(--border); border-top:3px solid var(--c); border-radius:8px; padding:10px 12px; background:var(--bg); display:flex; flex-direction:column; gap:2px; min-width:0; }
.uod-tl-kpi.is-click { cursor:pointer; }
.uod-tl-kpi.is-click:hover { background:var(--hover); }
.uod-tl-kpi-top span { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.uod-tl-kpi b { font-size:22px; color:var(--text); font-variant-numeric:tabular-nums; }
.uod-tl-kpi small { font-size:11.5px; color:var(--muted); }
@media (max-width:900px) { .uod-tl-kpis { grid-template-columns:repeat(2, minmax(0,1fr)); } }
.uod-tl-chart { border:1px solid var(--border); border-radius:8px; padding:12px 14px; background:var(--bg); min-width:0; }
.uod-tl-chart-head { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; flex-wrap:wrap; margin-bottom:8px; }
.uod-tl-chart-title { font-size:13.5px; font-weight:700; color:var(--text); margin-bottom:6px; }
.uod-offers-head { margin:16px 2px 10px; }
.uod-legend { display:flex; gap:12px; flex-wrap:wrap; font-size:11.5px; color:var(--text-2); }
.uod-legend span { display:inline-flex; align-items:center; gap:5px; white-space:nowrap; }
.uod-legend i { display:inline-block; width:10px; height:10px; border-radius:2px; }
.uod-svg { display:block; width:100%; height:auto; }
.uod-svg .uod-grid { stroke:var(--grid); }
.uod-svg .uod-axis { fill:var(--muted); font-size:11px; }
.uod-svg .uod-axis-v { fill:var(--text-2); font-size:11px; font-weight:600; }
.uod-svg .is-click { cursor:pointer; }
.uod-svg .is-click:hover > rect:first-child { fill:var(--hover); }
.uod-donut { display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
.uod-donut-svg { width:170px; height:170px; flex:none; }
.uod-slice { cursor:pointer; }
.uod-slice:hover { opacity:.85; }
.uod-donut-total { font-size:20px; font-weight:700; fill:var(--text); }
.uod-donut-legend { flex:1; min-width:150px; display:flex; flex-direction:column; gap:6px; font-size:12px; color:var(--text-2); }
.uod-donut-legend > div { display:grid; grid-template-columns:10px minmax(0,1fr) auto 42px; align-items:center; gap:8px; cursor:pointer; border-radius:4px; }
.uod-donut-legend > div:hover { background:var(--hover); }
.uod-donut-legend i { width:10px; height:10px; border-radius:2px; }
.uod-donut-legend .lbl { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.uod-donut-legend b { color:var(--text); font-variant-numeric:tabular-nums; }
.uod-donut-legend .uod-muted { text-align:right; }
.uod-tip { position:fixed; z-index:1100; pointer-events:none; background:#1A2B3C; color:#fff; font-size:12px; padding:5px 9px; border-radius:6px; opacity:0; transition:opacity .1s; max-width:320px; white-space:pre-line; }
.uod-tip.is-on { opacity:1; }
/* drilldown & timeline popups */
.modal-dialog.uod-modal, .modal-dialog.uod-modal-tl { max-width:min(1240px, 94vw); width:94vw; }
.uod-dd-note { margin-bottom:10px; }
.uod-dd-units { display:grid; grid-template-columns:repeat(auto-fit, minmax(150px, 1fr)); gap:8px; margin-bottom:12px; }
.uod-dd-units:empty { display:none; }
.uod-dd-unit { display:flex; flex-direction:column; align-items:flex-start; gap:2px; text-align:left; cursor:pointer; border:1px solid var(--border); border-radius:8px; background:var(--bg); padding:8px 12px; color:var(--text); }
.uod-dd-unit:hover { border-color:var(--brand); }
.uod-dd-unit.is-on { border-color:var(--brand); box-shadow:inset 0 0 0 1px var(--brand); background:color-mix(in srgb, var(--brand) 7%, var(--bg)); }
.uod-dd-unit-name { font-size:12px; font-weight:600; color:var(--text-2); }
.uod-dd-unit-v { display:flex; align-items:baseline; gap:6px; }
.uod-dd-unit-v b { font-size:18px; font-variant-numeric:tabular-nums; }
.uod-dd-unit-v small { font-size:11.5px; color:var(--muted); }
.uod-in-modal .uod-tt { border:1px solid var(--border); border-radius:10px; }
.uod-tl-tools { display:flex; align-items:flex-end; gap:10px; flex-wrap:wrap; padding:10px 14px; border-bottom:1px solid var(--border-soft); background:var(--bg-soft); }
.uod-tl-tool { display:flex; flex-direction:column; gap:3px; margin:0; }
.uod-tl-tool span { font-size:10.5px; font-weight:700; color:var(--muted); text-transform:uppercase; letter-spacing:.05em; }
.uod-tl-tool select { height:32px; min-width:170px; max-width:260px; border:1px solid var(--border); border-radius:8px; padding:0 8px; font-size:12.5px; background:var(--bg); color:var(--text); }
.uod-tl-tool-wide select { min-width:240px; }
@media (max-width:600px) { .uod-tl-tool, .uod-tl-tool select { width:100%; max-width:none; } }
.uod-tlp-head { display:flex; justify-content:space-between; align-items:center; gap:12px; flex-wrap:wrap; margin-bottom:14px; }
.uod-tlp-who { display:flex; align-items:center; gap:12px; min-width:0; }
.uod-tlp-avatar { flex:none; width:42px; height:42px; border-radius:50%; display:grid; place-items:center; font-size:17px; font-weight:700;
	color:color-mix(in srgb, var(--c) 85%, #000); background:color-mix(in srgb, var(--c) 14%, var(--bg)); border:1px solid color-mix(in srgb, var(--c) 35%, transparent); }
.uod-tlp-name { font-size:16px; font-weight:700; color:var(--text); display:flex; align-items:baseline; gap:10px; flex-wrap:wrap; }
.uod-tlp-name .uod-idlink { font-size:12.5px; }
.uod-tlp-pills { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:4px; }
.uod-tlp-stats { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:10px; }
.uod-tlp-stats > div { border:1px solid var(--border); border-top:3px solid var(--c); border-radius:8px; padding:9px 12px; background:color-mix(in srgb, var(--c) 4%, var(--bg)); display:flex; flex-direction:column; gap:2px; }
.uod-tlp-stats span { font-size:10.5px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:var(--muted); }
.uod-tlp-stats b { font-size:15px; color:var(--text); }
.uod-journey { display:flex; gap:0; margin:16px 0 6px; overflow-x:auto; padding-bottom:4px; }
.uod-step { flex:1; min-width:78px; display:flex; flex-direction:column; align-items:center; gap:4px; position:relative; font-size:11px; color:var(--muted); text-align:center; }
.uod-step::before { content:''; position:absolute; top:11px; left:-50%; width:100%; border-top:2px solid var(--border); z-index:0; }
.uod-step:first-child::before { display:none; }
.uod-step.is-done::before { border-color:#2F7D4F; }
.uod-step-dot { position:relative; z-index:1; width:24px; height:24px; border-radius:50%; display:grid; place-items:center; font-size:12px; font-weight:700;
	background:var(--bg); border:2px solid var(--border); color:#fff; }
.uod-step.is-done .uod-step-dot { background:#2F7D4F; border-color:#2F7D4F; }
.uod-step.is-done { color:var(--text); font-weight:600; }
.uod-step.is-bad .uod-step-dot { background:#B83232; border-color:#B83232; }
.uod-step.is-bad { color:#B83232; font-weight:600; }
.uod-tlp-filter { display:flex; gap:6px; flex-wrap:wrap; padding:10px 0; border-top:1px solid var(--border-soft); margin-top:8px; }
.uod-tlf { display:inline-flex; align-items:center; border:1px solid var(--border); background:var(--bg); color:var(--text-2); border-radius:20px; padding:3px 11px; font-size:12px; font-weight:600; cursor:pointer; }
.uod-tlf .uod-dot { width:7px; height:7px; margin-right:6px; }
.uod-tlf > span:last-child { margin-left:5px; color:var(--muted); font-weight:500; }
.uod-tlf.is-on { background:color-mix(in srgb, var(--k, var(--brand)) 12%, var(--bg)); border-color:var(--k, var(--brand)); color:var(--text); }
.uod-tlp-scroll { max-height:58vh; overflow:auto; overscroll-behavior:contain; border:1px solid var(--border); border-radius:10px; background:var(--bg-soft); padding:16px 18px 6px; }
.uod-tlg { display:grid; grid-template-columns:86px minmax(0,1fr); gap:14px; }
.uod-tlg.is-hidden, .uod-tli.is-hidden { display:none; }
.uod-tlg-date { text-align:right; padding-top:9px; display:flex; flex-direction:column; line-height:1.25; }
.uod-tlg-date b { font-size:13.5px; color:var(--text); }
.uod-tlg-date span { font-size:11px; color:var(--muted); }
.uod-tlg-items { border-left:2px solid var(--border); padding:0 0 10px 18px; display:flex; flex-direction:column; gap:6px; }
.uod-tli { position:relative; display:grid; grid-template-columns:40px minmax(0,1fr); gap:8px; align-items:start; }
.uod-tli::before { content:''; position:absolute; left:-25px; top:10px; width:12px; height:12px; border-radius:50%; background:var(--k); border:2px solid var(--bg-soft); box-shadow:0 0 0 1px var(--k); }
.uod-tli.is-future::before { background:var(--bg-soft); border:2px dashed var(--k); box-shadow:none; }
.uod-tli-time { font-size:11.5px; color:var(--muted); padding-top:8px; font-variant-numeric:tabular-nums; }
.uod-tli-card { background:var(--bg); border:1px solid var(--border-soft); border-left:3px solid var(--k); border-radius:8px; padding:7px 12px; min-width:0; }
.uod-tli-top { display:flex; align-items:center; gap:4px 8px; flex-wrap:wrap; }
.uod-tli-kind { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.05em; color:color-mix(in srgb, var(--k) 85%, #000); background:color-mix(in srgb, var(--k) 11%, transparent); border-radius:4px; padding:1px 6px; }
:root[data-theme="dark"] .uod-tli-kind { color:color-mix(in srgb, var(--k) 65%, #fff); }
.uod-tli-title { font-size:13px; font-weight:650; color:var(--text); }
.uod-tli-doc { margin-left:auto; font-size:11.5px; color:var(--link); white-space:nowrap; }
.uod-tli-flow { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-top:5px; }
.uod-tli-arrow { color:var(--muted); }
.uod-tli-meta { font-size:12px; color:var(--text-2); margin-top:3px; overflow-wrap:anywhere; }
.uod-tl-today { position:relative; margin:8px 0 12px; text-align:center; }
.uod-tl-today::before { content:''; position:absolute; left:0; right:0; top:50%; border-top:1px dashed #A16207; }
.uod-tl-today span { position:relative; background:var(--bg-soft); padding:0 10px; font-size:11px; font-weight:700; color:#A16207; text-transform:uppercase; letter-spacing:.05em; }
@media (max-width:600px) { .uod-tlp-stats { grid-template-columns:repeat(2, minmax(0,1fr)); } .uod-tlg { grid-template-columns:minmax(0,1fr); gap:4px; }
	.uod-tlg-date { text-align:left; flex-direction:row; gap:6px; padding-top:0; } .uod-tli { grid-template-columns:minmax(0,1fr); } .uod-tli-time:empty { display:none; } }
/* module tab bar — pinned while the page scrolls (the v16 desk scrolls .main-section, the sticky container) */
.uod-mnav-wrap { position:sticky; top:0; z-index:20; margin:0 -22px 18px; padding:10px 22px 0;
	background:color-mix(in srgb, var(--page) 94%, transparent); backdrop-filter:blur(8px); -webkit-backdrop-filter:blur(8px); }
.uod-mnav { display:flex; gap:4px; overflow-x:auto; scrollbar-width:none; border-bottom:1px solid var(--border); scroll-behavior:smooth; }
.uod-mnav::-webkit-scrollbar { display:none; }
.uod-mnav.fade-r { -webkit-mask-image:linear-gradient(90deg, #000 calc(100% - 56px), transparent); mask-image:linear-gradient(90deg, #000 calc(100% - 56px), transparent); }
.uod-mnav.fade-l { -webkit-mask-image:linear-gradient(90deg, transparent, #000 56px); mask-image:linear-gradient(90deg, transparent, #000 56px); }
.uod-mnav.fade-l.fade-r { -webkit-mask-image:linear-gradient(90deg, transparent, #000 56px, #000 calc(100% - 56px), transparent); mask-image:linear-gradient(90deg, transparent, #000 56px, #000 calc(100% - 56px), transparent); }
.uod-mnav-arrow { position:absolute; bottom:7px; z-index:2; width:28px; height:28px; border-radius:50%; border:1px solid var(--border);
	background:var(--bg); color:var(--text); font-size:18px; line-height:1; display:grid; place-items:center; cursor:pointer; box-shadow:var(--shadow); padding:0 0 2px; }
.uod-mnav-arrow:hover { border-color:var(--brand); color:var(--brand); }
.uod-mnav-arrow[hidden] { display:none; }
.uod-mnav-arrow.is-left { left:14px; }
.uod-mnav-arrow.is-right { right:14px; }
.uod-mtab { flex:none; display:inline-flex; align-items:center; gap:7px; background:none; border:0; border-bottom:2.5px solid transparent;
	margin-bottom:-1px; padding:9px 12px 10px; font-size:12.5px; font-weight:600; color:var(--muted); cursor:pointer; white-space:nowrap;
	border-radius:8px 8px 0 0; transition:color .15s, background .15s, border-color .15s; }
.uod-mtab:hover { color:var(--text); background:color-mix(in srgb, var(--brand) 5%, transparent); }
.uod-mtab:focus-visible { outline:none; box-shadow:inset 0 0 0 2px var(--brand); }
.uod-mtab.is-on { color:var(--brand); border-bottom-color:var(--brand); background:var(--bg); }
.uod-mtab-ico { display:inline-flex; width:15px; height:15px; opacity:.85; }
.uod-mtab-ico svg, .uod-mhead-ico svg { width:100%; height:100%; }
.uod-mpane { animation:uod-fade .18s ease-out; }
.uod-mpane[hidden] { display:none !important; }
@keyframes uod-fade { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
@media (prefers-reduced-motion:reduce) { .uod-mpane { animation:none; } .uod-mnav { scroll-behavior:auto; } }
.uod-mhead { display:flex; align-items:center; gap:12px; margin:0 2px 16px; }
.uod-mhead-ico { flex:none; width:38px; height:38px; padding:9px; border-radius:10px; color:var(--brand); background:var(--brand-tint);
	border:1px solid color-mix(in srgb, var(--brand) 18%, transparent); }
.uod-mhead-title { font-size:16px; font-weight:700; color:var(--text); line-height:1.25; }
.uod-mhead-sub { font-size:12px; color:var(--muted); margin-top:2px; }
.uod-mhead + .uod-section { margin-top:0; }
@media (max-width:700px) { .uod-mnav-wrap { margin:0 -16px 14px; padding:8px 16px 0; } .uod-mtab { padding:8px 10px 9px; } }
.uod-is-denied, .uod-tile-1.is-denied, .uod-half.is-denied { opacity:.55; cursor:not-allowed; }
.uod-num-cell { font-variant-numeric:tabular-nums; }
.uod-guide-note { margin:-2px 0 6px; }
/* guide */
.uod-guide-sec { font-size:11px; font-weight:700; color:var(--text-2); text-transform:uppercase; letter-spacing:.06em; margin:18px 0 6px; padding-bottom:6px; border-bottom:1px solid var(--border); }
.uod-guide { width:100%; border-collapse:collapse; font-size:12.5px; }
.uod-guide th { width:230px; text-align:left; vertical-align:top; padding:8px 12px 8px 0; color:var(--text); font-weight:650; border-bottom:1px solid var(--border-soft); }
.uod-guide td { padding:8px 0; color:var(--text-2); border-bottom:1px solid var(--border-soft); }
`;
