// Copyright (c) 2026, TFSS and contributors
// For license information, please see license.txt

frappe.ui.form.on('Evaluation Schema', {
	setup(frm) {
		frm._ep_components = null;
		frm._ep_atypes = null;
	},

	refresh(frm) {
		_inject_styles();
		_hide_flat_sections(frm);
		_ensure_dyn_area(frm);
		_load_and_render(frm);
		frm.set_query('component', 'schema_components', function (doc, _cdt, cdn) {
			const selected = (doc.schema_components || [])
				.filter(r => r.name !== cdn && r.component)
				.map(r => r.component);
			return selected.length
				? { filters: [['name', 'not in', selected]] }
				: {};
		});
	},

	total_marks(frm) { frm.$wrapper.find('#es-dynamic-sections .es-ov-total').text(_fmt(frm.doc.total_marks)); },

	// Same required fields Frappe checks on save, but named the way this form shows them
	// (the assessment / re-exam tables are hidden behind the cards, so Frappe's
	// "table Assessment Configuration, Row 7" points at nothing the user can see).
	validate(frm) {
		const issues = _es_collect_issues(frm);
		if (!issues.length) return;
		frappe.validated = false;
		frappe.msgprint({
			title: __('Fix these before saving'),
			indicator: 'red',
			message: `<p style="margin-bottom:8px;">${__('Some rows are missing information:')}</p><ul style="padding-left:18px;margin:0;">` +
				issues.map(i => `<li style="margin-bottom:4px;">${i.msg}</li>`).join('') + '</ul>',
		});
		const $first = issues.find(i => i.$el && i.$el.length);
		if ($first) $first.$el[0].scrollIntoView({ behavior: 'smooth', block: 'center' });
	},
});

frappe.ui.form.on('Evaluation Schema Component', {
	component(frm) { _load_and_render(frm); },

	label(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (!row.component) return;
		const ci = (frm._ep_components || []).find(c => c.name === row.component);
		const comp_name = ci ? ci.component_name : row.component;
		const lbl = row.label || comp_name;
		const ctype = _comp_type(frm, row.component);
		const title = (ctype === 'Re Exam' || ctype === 'Makeup')
			? `${comp_name} | ${lbl}`
			: lbl;
		frm.$wrapper.find(`.es-sub-section[data-comp="${row.component}"] .es-sect-title`).text(title);
		_upd_overview(frm.$wrapper.find('#es-dynamic-sections'));
	},

	effective_max_marks(frm, cdt, cdn) {
		const row = frappe.get_doc(cdt, cdn);
		if (row.component) {
			frm.$wrapper.find(`.es-sub-section[data-comp="${row.component}"] .es-assess-eq`).text(row.effective_max_marks || 0);
			const $sec = frm.$wrapper.find(`.es-sub-section[data-comp="${row.component}"]`);
			if ($sec.length) _upd_assess_sum($sec);
		}
	},

	schema_components_remove(frm) { _load_and_render(frm); }
});

/* ── Styles ───────────────────────────────────────── */

function _inject_styles() {
	if (document.getElementById('es-form-styles-v2')) return;
	$('#es-form-styles').remove();
	const s = document.createElement('style');
	s.id = 'es-form-styles-v2';
	/* NLSIU maroon theme; green / red / amber only where they carry meaning */
	s.textContent = `
		#es-dynamic-sections {
			--es-brand: #920C24; --es-brand-dark: #6E091B; --es-brand-soft: #F5D9DE; --es-brand-softest: #FBEEF0;
			--es-brand-border: #E8B4BE; --es-ink: #1e293b; --es-muted: #64748b; --es-faint: #94a3b8;
			--es-line: #e2e8f0; --es-line-soft: #f1f5f9; --es-bg: #f8fafc;
			--es-ok: #15803d; --es-ok-bg: #f0fdf4; --es-ok-line: #86efac;
			--es-bad: #b91c1c; --es-bad-bg: #fef2f2; --es-bad-line: #fca5a5;
			--es-warn: #92400e; --es-warn-bg: #fffbeb; --es-warn-line: #fcd34d;
			padding: 8px 0 20px;
		}
		/* overview strip */
		#es-dynamic-sections .es-overview {
			display: flex; flex-wrap: wrap; align-items: center; gap: 10px 18px;
			padding: 14px 18px; margin-bottom: 18px; border-radius: 10px;
			background: linear-gradient(135deg, var(--es-brand) 0%, var(--es-brand-dark) 100%);
			color: #fff; box-shadow: 0 2px 10px rgba(110, 9, 27, .18);
		}
		#es-dynamic-sections .es-ov-stat { display: flex; flex-direction: column; min-width: 90px; }
		#es-dynamic-sections .es-ov-stat b { font-size: 20px; line-height: 1.1; font-weight: 700; }
		#es-dynamic-sections .es-ov-stat span { font-size: 10.5px; text-transform: uppercase; letter-spacing: .08em; opacity: .8; }
		#es-dynamic-sections .es-ov-sep { width: 1px; align-self: stretch; background: rgba(255,255,255,.25); }
		#es-dynamic-sections .es-ov-chips { display: flex; flex-wrap: wrap; gap: 6px; flex: 1; }
		#es-dynamic-sections .es-ov-chip {
			display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px; border-radius: 999px;
			background: rgba(255,255,255,.14); border: 1px solid rgba(255,255,255,.25);
			font-size: 12px; font-weight: 600; color: #fff; cursor: pointer; transition: background .15s;
		}
		#es-dynamic-sections .es-ov-chip:hover { background: rgba(255,255,255,.24); }
		#es-dynamic-sections .es-ov-chip i { font-style: normal; font-weight: 700; width: 16px; height: 16px; border-radius: 50%;
			display: inline-flex; align-items: center; justify-content: center; font-size: 10px; }
		#es-dynamic-sections .es-ov-chip.ok i { background: #22c55e; }
		#es-dynamic-sections .es-ov-chip.bad i { background: #fbbf24; color: #78350f; }
		#es-dynamic-sections .es-ov-chip.na i { background: rgba(255,255,255,.35); }
		/* cards */
		#es-dynamic-sections .es-sub-section {
			margin-bottom: 18px; border: 1px solid var(--es-line); border-radius: 10px; overflow: hidden;
			background: #fff; box-shadow: 0 1px 3px rgba(15, 23, 42, .06); scroll-margin-top: 90px;
			border-left: 4px solid var(--es-brand);
		}
		#es-dynamic-sections .es-sub-section.es-kind-reexam { border-left-color: #d97706; }
		#es-dynamic-sections .es-sub-section.es-flash { animation: es-flash 1.2s ease; }
		@keyframes es-flash { 0% { box-shadow: 0 0 0 0 rgba(146,12,36,.45); } 100% { box-shadow: 0 0 0 10px rgba(146,12,36,0); } }
		#es-dynamic-sections .es-card-hdr {
			display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap;
			padding: 12px 16px; background: #fff; border-bottom: 1px solid var(--es-line);
		}
		#es-dynamic-sections .es-hdr-left { display: flex; align-items: center; gap: 8px; min-width: 0; }
		#es-dynamic-sections .es-hdr-sub { font-size: 11.5px; color: var(--es-muted); font-weight: 500; }
		#es-dynamic-sections .es-sect-title { font-weight: 700; font-size: 14px; color: var(--es-ink); letter-spacing: .01em; }
		#es-dynamic-sections .es-badge {
			display: inline-block; font-size: 10px; padding: 2px 9px; border-radius: 999px; font-weight: 700;
			letter-spacing: .04em; text-transform: uppercase; vertical-align: middle; border: 1px solid transparent;
		}
		#es-dynamic-sections .es-hdr-actions { display: flex; align-items: center; gap: 8px; }
		#es-dynamic-sections .es-add-btn {
			display: inline-flex; align-items: center; gap: 5px; font-size: 12px; font-weight: 600;
			padding: 6px 12px; border: 1px solid var(--es-brand); border-radius: 7px; background: #fff;
			color: var(--es-brand); cursor: pointer; transition: all .15s;
		}
		#es-dynamic-sections .es-add-btn:hover { background: var(--es-brand); color: #fff; }
		#es-dynamic-sections .es-add-btn:focus-visible { outline: none; box-shadow: 0 0 0 3px var(--es-brand-soft); }
		/* tables */
		#es-dynamic-sections .es-tbl-wrap { overflow-x: auto; }
		#es-dynamic-sections table.es-tbl { width: 100%; margin: 0; border-collapse: collapse; font-size: 12.5px; }
		#es-dynamic-sections table.es-tbl th {
			background: var(--es-bg); padding: 9px 10px; font-weight: 700; color: var(--es-muted);
			font-size: 10.5px; text-transform: uppercase; letter-spacing: .06em;
			border-bottom: 1px solid var(--es-line); white-space: nowrap; text-align: left;
		}
		#es-dynamic-sections table.es-tbl th[title] { cursor: help; }
		#es-dynamic-sections table.es-tbl th[title]::after { content: 'ⓘ'; margin-left: 4px; color: var(--es-faint); font-size: 10px; text-transform: none; }
		#es-dynamic-sections table.es-tbl td { padding: 7px 8px; border-bottom: 1px solid var(--es-line-soft); vertical-align: middle; }
		#es-dynamic-sections table.es-tbl tbody tr:last-child td { border-bottom: none; }
		#es-dynamic-sections table.es-tbl tbody tr:not(.es-subst-row):hover > td { background: var(--es-brand-softest); }
		#es-dynamic-sections .es-inp {
			width: 100%; min-width: 56px; height: 32px; border: 1px solid #d1d5db; border-radius: 7px;
			padding: 4px 9px; font-size: 12.5px; color: var(--es-ink); background: #fff; box-sizing: border-box;
			transition: border-color .15s, box-shadow .15s, background .15s;
		}
		#es-dynamic-sections select.es-inp { padding-right: 24px; }
		#es-dynamic-sections .es-inp:hover:not([readonly]) { border-color: var(--es-brand-border); }
		#es-dynamic-sections .es-inp:focus { outline: none; border-color: var(--es-brand); box-shadow: 0 0 0 3px var(--es-brand-soft); }
		#es-dynamic-sections .es-inp[readonly] { background: var(--es-bg); color: var(--es-muted); border-style: dashed; cursor: default; }
		#es-dynamic-sections .es-inp[readonly]:focus { box-shadow: none; border-color: #d1d5db; }
		#es-dynamic-sections .es-inp-at-selected { border-color: var(--es-brand-border) !important; background: var(--es-brand-softest) !important; color: var(--es-brand-dark) !important; font-weight: 600; }
		#es-dynamic-sections .es-inp.es-inp-err, #es-dynamic-sections .es-ms-trigger.es-inp-err {
			border-color: var(--es-bad) !important; background: var(--es-bad-bg) !important; box-shadow: 0 0 0 3px rgba(185,28,28,.12) !important;
		}
		#es-dynamic-sections .es-err-hint { display: block; margin-top: 3px; font-size: 11px; font-weight: 600; color: var(--es-bad); white-space: nowrap; }
		#es-dynamic-sections .es-chk { width: 16px; height: 16px; cursor: pointer; accent-color: var(--es-brand); }
		#es-dynamic-sections .es-unit { color: var(--es-faint); font-size: 11px; }
		#es-dynamic-sections .es-del-btn {
			display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px;
			background: none; border: 1px solid transparent; color: var(--es-faint); cursor: pointer;
			border-radius: 7px; transition: all .15s;
		}
		#es-dynamic-sections .es-del-btn:hover { color: var(--es-bad); background: var(--es-bad-bg); border-color: #fecaca; }
		#es-dynamic-sections .es-del-btn:focus-visible { outline: none; box-shadow: 0 0 0 3px #fecaca; }
		/* sum bar */
		#es-dynamic-sections .es-sum-bar {
			padding: 9px 16px; font-size: 12.5px; border-top: 1px solid var(--es-line); display: flex; align-items: center;
			gap: 6px; flex-wrap: wrap; font-weight: 500; background: var(--es-bg); color: var(--es-muted); transition: all .2s;
		}
		#es-dynamic-sections .es-sum-bar.ok { background: var(--es-ok-bg); color: var(--es-ok); border-top-color: var(--es-ok-line); }
		#es-dynamic-sections .es-sum-bar.bad { background: var(--es-warn-bg); color: var(--es-warn); border-top-color: var(--es-warn-line); }
		#es-dynamic-sections .es-sum-bar .es-sum-msg { margin-left: auto; font-weight: 600; }
		/* re-exam */
		#es-dynamic-sections .es-reexam-mode {
			height: 32px; padding: 4px 26px 4px 10px; border: 1px solid #d97706; color: #92400e; font-weight: 600;
			background-color: #fffbeb; border-radius: 7px; font-size: 12px; cursor: pointer; min-width: 175px;
		}
		#es-dynamic-sections .es-reexam-mode:focus { outline: none; box-shadow: 0 0 0 3px #fde68a; }
		#es-dynamic-sections .es-subst-toggle-bar {
			padding: 8px 16px; cursor: pointer; display: flex; align-items: center; gap: 6px; font-size: 12px;
			color: var(--es-brand); font-weight: 600; user-select: none; border-top: 1px dashed var(--es-line);
			background: #fff; transition: background .15s;
		}
		#es-dynamic-sections .es-subst-toggle-bar:hover { background: var(--es-brand-softest); }
		#es-dynamic-sections .es-subst-body { padding: 14px 16px 16px; background: var(--es-brand-softest); border-top: 1px solid var(--es-brand-soft); }
		#es-dynamic-sections .es-subst-grid { display: grid; grid-template-columns: 2fr 1fr 1fr 1fr; gap: 14px; margin-bottom: 12px; }
		#es-dynamic-sections .es-subst-grid.es-subst-grid-3 { grid-template-columns: 1fr 1fr 1fr; }
		@media (max-width: 900px) { #es-dynamic-sections .es-subst-grid { grid-template-columns: 1fr 1fr; } }
		#es-dynamic-sections .es-sf-label { display: block; font-size: 10.5px; font-weight: 700; color: var(--es-muted); text-transform: uppercase; letter-spacing: .07em; margin-bottom: 5px; }
		#es-dynamic-sections .es-subst-note { font-size: 11.5px; color: var(--es-muted); line-height: 1.6; padding: 10px 12px; border-radius: 8px; background: #fff; border: 1px solid var(--es-brand-soft); }
		#es-dynamic-sections .es-subst-note strong { color: var(--es-brand-dark); }
		#es-dynamic-sections .es-empty-row td { text-align: center; color: var(--es-faint); font-style: italic; padding: 16px; }
		#es-dynamic-sections .es-empty-hint { padding: 22px; text-align: center; color: var(--es-muted); border: 1px dashed var(--es-brand-border); border-radius: 10px; background: var(--es-brand-softest); font-size: 13px; }
		/* multi-select */
		#es-dynamic-sections .es-ms-wrap { position: relative; min-width: 120px; }
		#es-dynamic-sections .es-ms-trigger { cursor: pointer; display: flex; justify-content: space-between; align-items: center; user-select: none; }
		#es-dynamic-sections .es-ms-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12.5px; color: var(--es-ink); }
		#es-dynamic-sections .es-ms-label.es-ms-placeholder { color: #9ca3af; }
		#es-dynamic-sections .es-ms-arrow { color: var(--es-faint); margin-left: 6px; flex-shrink: 0; font-size: 10px; }
		/* Panel floats on <body> while open so card/table overflow can't clip it */
		.es-ms-panel {
			display: none; position: fixed; z-index: 1050; background: #fff; border: 1px solid #E8B4BE; border-radius: 8px;
			box-shadow: 0 10px 28px rgba(15,23,42,.14); min-width: 170px; max-height: 260px; overflow-y: auto;
			overscroll-behavior: contain; padding: 4px 0;
		}
		.es-ms-empty { padding: 6px 12px; font-size: 12px; color: #9ca3af; }
		.es-ms-item { display: flex; align-items: center; gap: 8px; padding: 7px 12px; cursor: pointer; font-size: 12.5px; color: #1f2937; margin: 0; font-weight: 400; }
		.es-ms-item:hover { background: #FBEEF0; }
		.es-ms-item input[type=checkbox] { accent-color: #920C24; width: 14px; height: 14px; cursor: pointer; flex-shrink: 0; }
	`;
	document.head.appendChild(s);
}

/* ── Private helpers ──────────────────────────────── */

function _hide_flat_sections(frm) {
	frm.toggle_display(
		['section_break_assessments', 'assessment_configs', 'section_break_reexam', 'reexam_configs'],
		false
	);
}

function _ensure_dyn_area(frm) {
	if (frm.$wrapper.find('#es-dynamic-sections').length) return;
	const $comp_sec = frm.fields_dict['schema_components'].$wrapper.closest('.form-section');
	if ($comp_sec.length) {
		$(`<div id="es-dynamic-sections"></div>`).insertAfter($comp_sec);
	} else {
		frm.$wrapper.find('.form-layout').append(`<div id="es-dynamic-sections"></div>`);
	}
}

function _load_and_render(frm) {
	const need_c = !frm._ep_components;
	const need_a = !frm._ep_atypes;
	if (!need_c && !need_a) { _render(frm); return; }

	const calls = [];
	if (need_c) calls.push(new Promise(res => frappe.call({
		method: 'slcm.slcm.page.examination_planner.examination_planner.get_components',
		callback: r => { frm._ep_components = r.message || []; res(); }
	})));
	if (need_a) calls.push(new Promise(res => frappe.call({
		method: 'slcm.slcm.page.examination_planner.examination_planner.get_assessment_types',
		callback: r => { frm._ep_atypes = r.message || []; res(); }
	})));
	Promise.all(calls).then(() => _render(frm));
}

function _comp_type(frm, name) {
	const c = (frm._ep_components || []).find(x => x.name === name);
	return c ? (c.component_type || 'Custom') : 'Custom';
}

function _render(frm) {
	const $area = frm.$wrapper.find('#es-dynamic-sections');
	if (!$area.length) return;
	_esms_close_all();
	$area.empty();

	const comps = (frm.doc.schema_components || []).filter(r => r.component);
	if (!comps.length) {
		$area.html(`<div class="es-empty-hint">${__('Add the components (e.g. Internal, End Term, Re-Exam) in the table above. Each one gets a card here to set up its assessments.')}</div>`);
		return;
	}
	$area.append(`<div class="es-overview">
		<div class="es-ov-stat"><b class="es-ov-total">${_fmt(frm.doc.total_marks)}</b><span>${__('Total marks')}</span></div>
		<div class="es-ov-stat"><b>${comps.length}</b><span>${__('Components')}</span></div>
		<div class="es-ov-sep"></div>
		<div class="es-ov-chips"></div>
	</div>`);
	$area.find('.es-overview').on('click', '.es-ov-chip', function () {
		const $t = $area.find('.es-sub-section').filter((_, el) => $(el).attr('data-comp') === $(this).attr('data-comp'));
		if (!$t.length) return;
		$t[0].scrollIntoView({ behavior: 'smooth', block: 'start' });
		$t.removeClass('es-flash'); void $t[0].offsetWidth; $t.addClass('es-flash');
	});

	comps.forEach(cr => {
		const ctype = _comp_type(frm, cr.component);
		const ci = (frm._ep_components || []).find(c => c.name === cr.component);
		const comp_name = ci ? ci.component_name : cr.component;
		const lbl = cr.label || comp_name;

		if (ctype === 'Re Exam' || ctype === 'Makeup') {
			_render_reexam_sec(frm, $area, cr.component, lbl, ctype, comp_name);
		} else {
			_render_assess_sec(frm, $area, cr.component, lbl, ctype, cr.effective_max_marks || 0);
		}
	});
	_upd_overview($area);
}

/* One chip per component in the overview: does it add up? Click to jump to its card */
function _upd_overview($area) {
	const $chips = $area.find('.es-ov-chips');
	if (!$chips.length) return;
	$chips.empty();
	$area.find('.es-sub-section').each(function () {
		const $sec = $(this);
		const title = $sec.find('.es-sect-title').first().text();
		const $sum = $sec.find('.es-sum');
		let cls = 'na', mark = '•', tip = __('Re-exam / makeup settings');
		if ($sum.length) {
			const t = parseFloat($sum.text()) || 0, eq = parseFloat($sec.find('.es-assess-eq').text()) || 0;
			const ok = t === eq && eq !== 0;
			cls = ok ? 'ok' : 'bad'; mark = ok ? '✓' : '!';
			tip = ok ? __('Adds up') : __('{0} of {1} marks shared out', [_fmt(t), _fmt(eq)]);
		}
		$chips.append($('<span class="es-ov-chip"></span>').addClass(cls).attr({ 'data-comp': $sec.attr('data-comp'), title: tip })
			.append($('<i></i>').text(mark)).append($('<span></span>').text(title)));
	});
}

/* ── Save check: the same mandatory fields, with readable messages ── */

function _es_collect_issues(frm) {
	const issues = [];
	const $area = frm.$wrapper.find('#es-dynamic-sections');
	$area.find('.es-inp-err').each(function () { _es_clear_err($(this)); });
	const comp_label = comp => {
		const cr = (frm.doc.schema_components || []).find(c => c.component === comp);
		const ci = (frm._ep_components || []).find(c => c.name === comp);
		return (cr && cr.label) || (ci && ci.component_name) || comp;
	};

	(frm.doc.schema_components || []).forEach(r => {
		if (!r.component) issues.push({ msg: __('Components table, row {0}: pick a <b>Component</b>, or delete the empty row.', [r.idx]) });
	});

	// assessment rows, numbered as they appear in each card
	$area.find('.es-sub-section').each(function () {
		const $sec = $(this), comp = $sec.attr('data-comp');
		$sec.find('.es-tbody > tr[data-fn]').not('.es-subst-row').each(function (i) {
			const $at = $(this).find('select[name=at]');
			if ($at.length && !$at.val()) {
				_es_set_err($at, __('Pick a type or remove the row'));
				issues.push({ $el: $at, msg: __('<b>{0}</b>, assessment row {1}: pick an <b>Assessment type</b>, or remove the row with the bin icon.', [_esc(comp_label(comp)), i + 1]) });
			}
		});
	});
	// assessment rows with no card on screen (their component was removed or has no type)
	const shown = new Set($area.find('select[name=at]').closest('tr').map((_, el) => $(el).attr('data-fn')).get());
	(frm.doc.assessment_configs || []).forEach(r => {
		if (shown.has(r.name)) return;
		if (!r.assessment_type || !r.component) {
			issues.push({ msg: __('Assessment Configuration row {0} ({1}) has no {2}. Re-add the component or remove that row.', [r.idx, _esc(comp_label(r.component) || __('no component')), !r.component ? __('component') : __('assessment type')]) });
		}
	});
	(frm.doc.reexam_configs || []).forEach(r => {
		if (!r.component) issues.push({ msg: __('Re-Exam Configuration row {0} has no component.', [r.idx]) });
	});
	return issues;
}

/* ── Badge helper ─────────────────────────────────── */

function _badge(ctype) {
	const map = {
		'Custom': ['#920C24', '#FBEEF0', '#E8B4BE'],
		'Assessment': ['#1d4ed8', '#eff6ff', '#bfdbfe'],
		'Re Exam': ['#92400e', '#fffbeb', '#fcd34d'],
		'Makeup': ['#9a3412', '#fff7ed', '#fdba74'],
		'Default Assessment': ['#475569', '#f8fafc', '#cbd5e1'],
	};
	const [color, bg, line] = map[ctype] || map['Custom'];
	return `<span class="es-badge" style="background:${bg};color:${color};border-color:${line};">${_esc(ctype || 'Custom')}</span>`;
}

/* ── Assessment section ───────────────────────────── */

function _render_assess_sec(frm, $area, comp, lbl, ctype, eff_marks) {
	const $sec = $(`
		<div class="es-sub-section" data-comp="${_esc(comp)}">
			<div class="es-card-hdr">
				<div class="es-hdr-left">
					<span class="es-sect-title">${_esc(lbl)}</span>
					${_badge(ctype)}
					<span class="es-hdr-sub">${__('Component marks')}: <b class="es-hdr-eq">${_fmt(eff_marks)}</b></span>
				</div>
				<button type="button" class="es-add-btn es-add-row">+ ${__('Add assessment')}</button>
			</div>
			<div class="es-tbl-wrap">
				<table class="es-tbl">
					<thead>
						<tr>
							<th style="min-width:140px;">${__('Assessment type')}</th>
							<th style="min-width:100px;">${__('Label')}</th>
							<th style="min-width:90px;" title="${__('Worked out for you: Maximum marks × Weightage %. These add up to the component marks.')}">${__('Effective')}</th>
							<th style="min-width:90px;" title="${__('What the assessment is marked out of.')}">${__('Max marks')}</th>
							<th style="min-width:75px;">${__('Min marks')}</th>
							<th style="min-width:90px;">${__('Passing marks')}</th>
							<th style="min-width:70px;text-align:center;" title="${__('Tick when failing this assessment fails the course.')}">${__('Pass / fail')}</th>
							<th style="min-width:90px;">${__('Weightage')}</th>
							<th style="min-width:90px;" title="${__('Auto: every student of the course takes it. Manual: students are added one by one.')}">${__('Enrolment')}</th>
							<th style="width:36px;"></th>
						</tr>
					</thead>
					<tbody class="es-tbody"></tbody>
				</table>
			</div>
			<div class="es-sum-bar">
				<span>${__('Effective marks')}:</span>
				<b class="es-sum">0</b>
				<span>/</span>
				<b class="es-assess-eq">${eff_marks}</b>
				<span>${__('component marks')}</span>
				<span class="es-sum-msg"></span>
			</div>
		</div>
	`);
	$area.append($sec);

	const existing = (frm.doc.assessment_configs || []).filter(r => r.component === comp);
	(existing.length ? existing : [{}]).forEach(r => _add_assess_row(frm, $sec, comp, r));
	_refresh_at_options($sec);
	_upd_assess_sum($sec);

	$sec.on('click', '.es-add-row', () => _add_assess_row(frm, $sec, comp, {}));
}

function _add_assess_row(frm, $sec, comp, data) {
	let frow = data.name
		? (frm.doc.assessment_configs || []).find(r => r.name === data.name)
		: null;
	if (!frow) {
		frow = frappe.model.add_child(frm.doc, 'Schema Assessment Config', 'assessment_configs');
		frow.component = comp;
	}
	const fn = frow.name;

	const at_opts = (frm._ep_atypes || [])
		.filter(a => a.assessment_type !== 'ReExam/Makeup Assessment')
		.map(a =>
			`<option value="${a.name}" ${(data.assessment_type || '') === a.name ? 'selected' : ''}>${a.type_name || a.name}</option>`
		).join('');

	const $row = $(`
		<tr data-fn="${fn}">
			<td>
				<select name="at" class="es-inp" style="min-width:120px;">
					<option value="">— Select —</option>${at_opts}
				</select>
			</td>
			<td><input name="lbl" class="es-inp" value="${_esc(data.label || '')}" placeholder="Label"/></td>
			<td><input name="eff" type="number" class="es-inp" value="${data.effective_marks || ''}" readonly tabindex="-1" placeholder="Auto"/></td>
			<td><input name="max" type="number" class="es-inp" value="${data.maximum_marks || ''}" placeholder="0"/></td>
			<td><input name="min" type="number" class="es-inp" value="${data.minimum_marks || 0}" placeholder="0"/></td>
			<td><input name="pass" type="number" class="es-inp" value="${data.passing_marks || 0}" placeholder="0"/></td>
			<td style="text-align:center;">
				<input type="checkbox" name="pfail" ${data.consider_for_pass_fail ? 'checked' : ''}
					class="es-chk"/>
			</td>
			<td>
				<div style="display:flex;align-items:center;gap:3px;">
					<input name="wt" type="number" class="es-inp" value="${data.weightage !== undefined ? data.weightage : 100}" placeholder="100"/>
					<span class="es-unit">%</span>
				</div>
			</td>
			<td>
				<select name="enroll" class="es-inp">
					<option value="Auto" ${(data.enrollment || 'Auto') === 'Auto' ? 'selected' : ''}>Auto</option>
					<option value="Manual" ${data.enrollment === 'Manual' ? 'selected' : ''}>Manual</option>
				</select>
			</td>
			<td><button type="button" class="es-del-btn es-del" title="Remove this row" aria-label="Remove this row">${_ES_TRASH}</button></td>
		</tr>
	`);
	$sec.find('.es-tbody').append($row);

	const _upd_at_indicator = () => {
		const $at = $row.find('[name=at]');
		$at.val() ? $at.addClass('es-inp-at-selected') : $at.removeClass('es-inp-at-selected');
		if ($at.val()) _es_clear_err($at);
	};

	const sync = () => {
		const wt = parseFloat($row.find('[name=wt]').val()) || 0;
		const max = parseFloat($row.find('[name=max]').val()) || 0;
		const eff = Math.round((wt / 100) * max * 100) / 100;
		$row.find('[name=eff]').val(eff || '');
		const r = (frm.doc.assessment_configs || []).find(x => x.name === fn);
		if (r) {
			r.component = comp;
			r.assessment_type = $row.find('[name=at]').val();
			r.label = $row.find('[name=lbl]').val();
			r.effective_marks = eff;
			r.maximum_marks = max;
			r.minimum_marks = parseFloat($row.find('[name=min]').val()) || 0;
			r.passing_marks = parseFloat($row.find('[name=pass]').val()) || 0;
			r.consider_for_pass_fail = $row.find('[name=pfail]').is(':checked') ? 1 : 0;
			r.weightage = wt;
			r.enrollment = $row.find('[name=enroll]').val();
		}
		_upd_at_indicator();
		_refresh_at_options($sec);
		_upd_assess_sum($sec);
		frm.dirty();
	};

	_upd_at_indicator();
	_refresh_at_options($sec);
	$row.find('input, select').on('change input', sync);
	$row.on('click', '.es-del', () => {
		frm.doc.assessment_configs = (frm.doc.assessment_configs || []).filter(x => x.name !== fn);
		$row.remove();
		_refresh_at_options($sec);
		_upd_assess_sum($sec);
		frm.dirty();
	});
}

function _refresh_at_options($sec) {
	const selected = [];
	$sec.find('.es-tbody [name=at]').each(function () {
		const v = $(this).val();
		if (v) selected.push(v);
	});
	$sec.find('.es-tbody [name=at]').each(function () {
		const $sel = $(this);
		const own = $sel.val();
		$sel.find('option').each(function () {
			const v = $(this).val();
			$(this).prop('disabled', !!(v && v !== own && selected.includes(v)));
		});
	});
}

function _upd_assess_sum($sec) {
	let t = 0;
	$sec.find('.es-tbody tr').each(function () {
		t += parseFloat($(this).find('[name=eff]').val()) || 0;
	});
	t = Math.round(t * 100) / 100;
	$sec.find('.es-sum').text(t);
	const eq = parseFloat($sec.find('.es-assess-eq').text()) || 0;
	const $bar = $sec.find('.es-sum-bar').removeClass('ok bad');
	const diff = Math.round((eq - t) * 100) / 100;
	let msg = '';
	if (eq === 0 && t === 0) {
		msg = __('Set the component marks in the Components table above.');
	} else if (diff === 0) {
		$bar.addClass('ok');
		msg = '✓ ' + __('Adds up to the component marks');
	} else {
		$bar.addClass('bad');
		msg = diff > 0
			? '⚠ ' + __('{0} marks still to share out', [_fmt(diff)])
			: '⚠ ' + __('{0} marks more than the component marks', [_fmt(-diff)]);
	}
	$bar.find('.es-sum-msg').text(msg);
	$sec.find('.es-hdr-eq').text(_fmt(eq));
	_upd_overview($sec.closest('#es-dynamic-sections'));
}

/* ── Custom multi-select dropdown ────────────────── */

function _make_multiselect(opts, savedVals) {
	/* opts: [{value, label}]  savedVals: string[] */
	const $wrap = $(`<div class="es-ms-wrap"></div>`);
	const $trigger = $(`<div class="es-ms-trigger es-inp" tabindex="0">
		<span class="es-ms-label es-ms-placeholder">— Select —</span>
		<span class="es-ms-arrow">&#9660;</span>
	</div>`);
	const $panel = $(`<div class="es-ms-panel"></div>`);

	if (!opts.length) $panel.append(`<div class="es-ms-empty">No options available</div>`);
	opts.forEach(o => {
		const $item = $(`<label class="es-ms-item">
			<input type="checkbox" value="${_esc(String(o.value))}"/>
			<span>${_esc(String(o.label))}</span>
		</label>`);
		$item.find('input').prop('checked', savedVals.includes(String(o.value)));
		$panel.append($item);
	});

	$wrap.append($trigger).append($panel);

	const _refresh = () => {
		const sel = $panel.find('input:checked').map((_, el) => el.value).get();
		const lbls = sel.map(v => {
			const o = opts.find(x => String(x.value) === v);
			return o ? String(o.label) : v;
		});
		$trigger.find('.es-ms-label')
			.text(lbls.length ? lbls.join(', ') : '— Select —')
			.toggleClass('es-ms-placeholder', !lbls.length);
	};
	_refresh();

	/* Place the panel under the trigger, or above it when there is more room there */
	const _position = () => {
		const r = $trigger[0].getBoundingClientRect();
		const gap = 2, edge = 8;
		const below = window.innerHeight - r.bottom - gap - edge;
		const above = r.top - gap - edge;
		const natural = Math.min($panel[0].scrollHeight, 260);
		const openUp = below < natural && above > below;
		const width = Math.max(r.width, 170);
		$panel.css({
			width: width,
			maxHeight: Math.max(Math.min(260, openUp ? above : below), 80),
			left: Math.max(edge, Math.min(r.left, window.innerWidth - width - edge)),
			top: openUp ? 'auto' : r.bottom + gap,
			bottom: openUp ? window.innerHeight - r.top + gap : 'auto',
		});
	};

	const _onScroll = e => {
		if ($panel[0].contains(e.target)) return;  // scrolling the list itself
		_close();
	};
	const _onKey = e => { if (e.key === 'Escape') { _close(); $trigger.trigger('focus'); } };

	const _close = () => {
		if (!$panel.is(':visible')) return;
		$panel.hide().appendTo($wrap);
		$(document).off('mousedown.esms keydown.esms');
		$(window).off('resize.esms');
		window.removeEventListener('scroll', _onScroll, true);
		if (_esms_close_active === _close) _esms_close_active = null;
	};

	const _open = () => {
		if (_esms_close_active) _esms_close_active();
		$panel.appendTo(document.body).show();
		_position();
		_esms_close_active = _close;
		$(document).on('mousedown.esms', e => {
			if (!$wrap[0].contains(e.target) && !$panel[0].contains(e.target)) _close();
		});
		$(document).on('keydown.esms', _onKey);
		$(window).on('resize.esms', _close);
		window.addEventListener('scroll', _onScroll, true);
	};

	$trigger.on('click', () => ($panel.is(':visible') ? _close() : _open()));
	$trigger.on('keydown', e => {
		if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
			e.preventDefault();
			if (!$panel.is(':visible')) _open();
		}
	});
	$panel.on('change', 'input[type=checkbox]', function () {
		_refresh();
		$wrap.trigger('esms:change');
	});

	$wrap.getVal = () => $panel.find('input:checked').map((_, el) => el.value).get();
	return $wrap;
}

/* Only one multi-select panel is open at a time; this closes it */
var _esms_close_active = null;

function _esms_close_all() {
	if (_esms_close_active) _esms_close_active();
}

/* Close an open panel when leaving the form (registered once; router.off can't unbind) */
if (!frappe._esms_route_hook) {
	frappe._esms_route_hook = true;
	frappe.router.on('change', () => _esms_close_all());
}

/* ── Re-Exam section ─────────────────────────────── */

function _render_reexam_sec(frm, $area, comp, lbl, ctype, comp_name) {
	const existing = (frm.doc.reexam_configs || []).filter(r => r.component === comp);
	const defaultMode = (existing[0] && existing[0].re_exam_type_category) || 'Assessment';

	const $sec = $(`
		<div class="es-sub-section es-kind-reexam" data-comp="${_esc(comp)}">
			<div class="es-card-hdr">
				<div class="es-hdr-left">
					<span class="es-sect-title">${_esc(comp_name || comp)} | ${_esc(lbl)}</span>
					${_badge(ctype)}
				</div>
				<div class="es-hdr-actions">
					<span class="es-hdr-sub">${__('Based on')}</span>
					<select class="es-reexam-mode">
						<option value="Assessment" ${defaultMode === 'Assessment' ? 'selected' : ''}>Assessment</option>
						<option value="ReExam/Makeup Assessment" ${defaultMode === 'ReExam/Makeup Assessment' ? 'selected' : ''}>ReExam / Makeup</option>
						<option value="Component" ${defaultMode === 'Component' ? 'selected' : ''}>Component</option>
					</select>
					<button type="button" class="es-add-btn es-add-row">+ ${__('Add')}</button>
				</div>
			</div>
			<div class="es-tbl-wrap">
				<table class="es-tbl">
					<thead>
						<tr>
							<th class="es-col-first" style="min-width:130px;">${defaultMode === 'Component' ? 'Component' : 'Assessment Type'}</th>
							<th style="min-width:100px;">${__('Label')}</th>
							<th style="min-width:100px;" title="${__('In Component mode this is the total of the chosen components and is filled in for you.')}">${__('Max marks')}</th>
							<th style="min-width:80px;">${__('Min marks')}</th>
							<th style="min-width:100px;">${__('Passing marks')}</th>
							<th style="min-width:90px;" title="${__('Auto: every eligible student takes it. Manual: students are added one by one.')}">${__('Enrolment')}</th>
							<th style="width:36px;"></th>
						</tr>
					</thead>
					<tbody class="es-tbody"></tbody>
				</table>
			</div>
		</div>
	`);
	$area.append($sec);

	(existing.length ? existing : [{ re_exam_type_category: defaultMode }])
		.forEach(r => _add_reexam_row(frm, $sec, comp, r));

	$sec.on('click', '.es-add-row', () => {
		const mode = $sec.find('.es-reexam-mode').val();
		_add_reexam_row(frm, $sec, comp, { re_exam_type_category: mode });
	});

	$sec.on('change', '.es-reexam-mode', function () {
		const mode = $(this).val();
		$sec.find('.es-col-first').text(mode === 'Component' ? 'Component' : 'Assessment Type');
		const rows = (frm.doc.reexam_configs || []).filter(r => r.component === comp);
		rows.forEach(r => { r.re_exam_type_category = mode; });
		_esms_close_all();
		$sec.find('.es-tbody').empty();
		if (rows.length) {
			rows.forEach(r => _add_reexam_row(frm, $sec, comp, r));
		} else {
			_add_reexam_row(frm, $sec, comp, { re_exam_type_category: mode });
		}
		frm.dirty();
	});
}

function _add_reexam_row(frm, $sec, comp, data) {
	const mode = data.re_exam_type_category
		|| $sec.find('.es-reexam-mode').val()
		|| 'Assessment';

	let frow = data.name
		? (frm.doc.reexam_configs || []).find(r => r.name === data.name)
		: null;
	if (!frow) {
		frow = frappe.model.add_child(frm.doc, 'Schema Reexam Config', 'reexam_configs');
		frow.component = comp;
		frow.re_exam_type_category = mode;
	}
	const fn = frow.name;

	/* ── first column HTML based on mode ── */
	const _non_reexam_comps = (frm.doc.schema_components || []).filter(cr => {
		const _ct = _comp_type(frm, cr.component);
		return _ct !== 'Re Exam' && _ct !== 'Makeup';
	});
	const sub_opts = _non_reexam_comps.map(cr => {
		const _ci = (frm._ep_components || []).find(c => c.name === cr.component);
		const _disp = cr.label || (_ci ? _ci.component_name : cr.component);
		return `<option value="${cr.component}">${_disp}</option>`;
	}).join('');

	/* ── helper: assessment options for a given component ── */
	const _get_comp_at_opts = (compVal, selAt) => {
		return (frm.doc.assessment_configs || [])
			.filter(r => r.component === compVal && r.assessment_type)
			.map(r => {
				const at = (frm._ep_atypes || []).find(a => a.name === r.assessment_type);
				const lbl = at ? (at.type_name || at.name) : r.assessment_type;
				return `<option value="${r.assessment_type}" ${selAt === r.assessment_type ? 'selected' : ''}>${lbl}</option>`;
			}).join('');
	};

	/* ── multi-select widget for first column ── */
	const _ms_opts = mode === 'Component'
		? _non_reexam_comps.map(cr => {
			const _ci = (frm._ep_components || []).find(c => c.name === cr.component);
			return { value: cr.component, label: cr.label || (_ci ? _ci.component_name : cr.component) };
		})
		: (frm._ep_atypes || []).filter(a => a.assessment_type === mode)
			.map(a => ({ value: a.name, label: a.type_name || a.name }));

	const _ms_saved = mode === 'Component'
		? (data.substitute_for || '').split(',').filter(Boolean)
		: (data.assessment_type || '').split(',').filter(Boolean);

	const $ms = _make_multiselect(_ms_opts, _ms_saved);

	const $main = $(`
		<tr data-fn="${fn}">
			<td class="es-ms-td" style="min-width:160px;"></td>
			<td><input name="lbl" class="es-inp" value="${_esc(data.label || '')}" placeholder="Label"/></td>
			<td><input name="max" type="number" class="es-inp" value="${data.maximum_marks || ''}" placeholder="Auto" ${mode === 'Component' ? 'readonly tabindex="-1"' : ''}/></td>
			<td><input name="min" type="number" class="es-inp" value="${data.minimum_marks || 0}" placeholder="0"/></td>
			<td><input name="pass" type="number" class="es-inp" value="${data.passing_marks || 0}" placeholder="0"/></td>
			<td>
				<select name="enroll" class="es-inp">
					<option value="Auto" ${(data.enrollment || 'Manual') === 'Auto' ? 'selected' : ''}>Auto</option>
					<option value="Manual" ${(data.enrollment || 'Manual') === 'Manual' ? 'selected' : ''}>Manual</option>
				</select>
			</td>
			<td><button type="button" class="es-del-btn es-del" title="Remove this row" aria-label="Remove this row">${_ES_TRASH}</button></td>
		</tr>
	`);
	$sec.find('.es-tbody').append($main);
	$main.find('.es-ms-td').append($ms);


	/* ── Substitution settings row ── */
	const init_comp_at_opts = (mode === 'Component' && data.substitute_for)
		? (data.substitute_for || '').split(',').filter(Boolean)
			.map(v => _get_comp_at_opts(v, '')).join('')
		: '';
	const init_sub_at_opts = (mode !== 'Component' && data.substitute_for)
		? _get_comp_at_opts(data.substitute_for, '')
		: '';
	const firstSubColHtml = mode === 'Component'
		? `<span class="es-sf-label">Select Assessment</span>
			<select name="comp_at" class="es-inp">
				<option value="">— Select Assessment —</option>${init_comp_at_opts}
			</select>`
		: `<span class="es-sf-label">Substitute For</span>
			<select name="sub_for" class="es-inp">
				<option value="">— Select Component —</option>${sub_opts}
			</select>
			<select name="sub_at" class="es-inp" style="margin-top:4px;">
				<option value="">— Select Assessment —</option>${init_sub_at_opts}
			</select>`;
	const show_sub = (mode === 'Component' || data.substitute_for) ? '' : 'display:none;';
	const sub_lbl = (mode === 'Component' || data.substitute_for)
		? 'Hide Substitution Settings ▲'
		: 'Show Substitution Settings ▼';

	const $subst = $(`
		<tr data-fn="${fn}-s" class="es-subst-row">
			<td colspan="7" style="padding:0;">
				<div class="es-subst-toggle-bar es-subst-toggle">${sub_lbl}</div>
				<div class="es-subst-body" style="${show_sub}">
					<div class="es-subst-grid">
						<div>${firstSubColHtml}</div>
						<div>
							<span class="es-sf-label">Weightage</span>
							<div style="display:flex;align-items:center;gap:4px;">
								<input name="sub_wt" type="number" class="es-inp" value="${data.substitute_weightage || 100}"/>
								<span class="es-unit">%</span>
							</div>
						</div>
						<div>
							<span class="es-sf-label">Effective Marks</span>
							<input name="eff" class="es-inp" value="${data.effective_marks || ''}" readonly placeholder="Auto"/>
						</div>
						<div>
							<span class="es-sf-label">Substitute Effective Marks</span>
							<input name="sub_eff" class="es-inp" value="${data.effective_marks || ''}" readonly placeholder="Auto"/>
						</div>
					</div>
					<div class="es-subst-note">
						<strong>Note:</strong>
						Substitute exam effective marks must be ≤ the effective maximum marks of assessment.<br>
						If a student is enrolled for this component, marks will be distributed as per the above schema.
					</div>
				</div>
			</td>
		</tr>
	`);
	$sec.find('.es-tbody').append($subst);

	$subst.on('click', '.es-subst-toggle', () => {
		const $body = $subst.find('.es-subst-body');
		$body.toggle();
		$subst.find('.es-subst-toggle').text(
			$body.is(':visible') ? 'Hide Substitution Settings ▲' : 'Show Substitution Settings ▼'
		);
	});

	const sync = () => {
		const r = (frm.doc.reexam_configs || []).find(x => x.name === fn);
		if (!r) return;
		r.component = comp;
		r.re_exam_type_category = $sec.find('.es-reexam-mode').val() || mode;
		r.label = $main.find('[name=lbl]').val();
		r.minimum_marks = parseFloat($main.find('[name=min]').val()) || 0;
		r.passing_marks = parseFloat($main.find('[name=pass]').val()) || 0;
		r.enrollment = $main.find('[name=enroll]').val();
		if (mode === 'Component') {
			r.substitute_for = ($ms.getVal() || []).join(',') || null;
			r.assessment_type = $subst.find('[name=comp_at]').val() || null;
			const selected = $ms.getVal() || [];
			let total = 0;
			(frm.doc.schema_components || []).forEach(sc => {
				if (selected.includes(sc.component)) {
					total += parseFloat(sc.effective_max_marks) || 0;
				}
			});
			total = Math.round(total * 100) / 100;
			$main.find('[name=max]').val(total || '');
			r.maximum_marks = total;
		} else {
			r.assessment_type = ($ms.getVal() || []).join(',');
			r.substitute_for = $subst.find('[name=sub_for]').val() || null;
			r.maximum_marks = parseFloat($main.find('[name=max]').val()) || 0;
		}
		r.substitute_weightage = parseFloat($subst.find('[name=sub_wt]').val()) || 100;
		const _sub_cr = (frm.doc.schema_components || []).find(c => c.component === r.substitute_for);
		const _sub_eff_max = _sub_cr ? (_sub_cr.effective_max_marks || 0) : 0;
		const _eff = r.substitute_for
			? Math.round((r.substitute_weightage / 100) * _sub_eff_max * 100) / 100
			: 0;
		r.effective_marks = _eff;
		$subst.find('[name=eff]').val(_eff || '');
		$subst.find('[name=sub_eff]').val(_eff || '');
		frm.dirty();
	};

	$main.find('input, select').on('change input', sync);
	$subst.find('input, select').on('change input', sync);
	$ms.on('esms:change', sync);

	if (mode === 'Component') {
		$ms.on('esms:change', function () {
			const selected = $ms.getVal() || [];
			const allOpts = selected.map(v => _get_comp_at_opts(v, '')).join('');
			$subst.find('[name=comp_at]').html(
				`<option value="">— Select Assessment —</option>${allOpts}`
			);
		});
	} else {
		$subst.find('[name=sub_for]').on('change', function () {
			$subst.find('[name=sub_at]').html(
				`<option value="">— Select Assessment —</option>${_get_comp_at_opts($(this).val(), '')}`
			);
		});
	}

	$main.on('click', '.es-del', () => {
		frm.doc.reexam_configs = (frm.doc.reexam_configs || []).filter(x => x.name !== fn);
		$main.remove();
		$subst.remove();
		frm.dirty();
	});
}

/* ── Utility ─────────────────────────────────────── */

const _ES_TRASH = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>';

function _fmt(n) { return String(Math.round((parseFloat(n) || 0) * 100) / 100); }

/* Mark / clear a field that blocks saving, with a short hint under it */
function _es_set_err($el, msg) {
	$el.addClass('es-inp-err').attr('title', msg);
	const $cell = $el.closest('td, div');
	if (!$cell.find('> .es-err-hint').length) $cell.append(`<span class="es-err-hint">${_esc(msg)}</span>`);
}
function _es_clear_err($el) {
	$el.removeClass('es-inp-err').removeAttr('title');
	$el.closest('td, div').find('> .es-err-hint').remove();
}

function _esc(s) {
	if (!s) return '';
	return String(s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
