// Admission Dashboard — desk page shell.
//
// The dashboard itself is a Vue 3 + frappe-ui app (frontend/src/admission_dashboard),
// built by Vite into /assets/slcm/frontend/admission_dashboard/ with hashed file
// names. `get_bootstrap` reads the Vite manifest and returns the current files.
//
// The frappe-ui stylesheet is only enabled while this page is shown, so its
// Tailwind classes can never restyle other desk pages.

(() => {
const ADMISSION_DASHBOARD_API = "slcm.admission.page.admission_dashboard.admission_dashboard";

frappe.pages["admission-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Admission Dashboard"),
		single_column: true,
	});

	// The Vue app draws its own header (title, Admission Cycle, Settings).
	$(wrapper).find(".page-head").addClass("hide");
	$(wrapper).addClass("slcm-admission-dashboard-page");

	const $root = $('<div class="slcm-fui slcm-admission-dashboard"></div>').appendTo(page.main);
	$root.html(
		`<div class="text-muted" style="padding: 48px; text-align: center;">${__("Loading dashboard…")}</div>`
	);

	wrapper.slcm_dashboard = { styles: [], app: null };

	frappe
		.call({ method: `${ADMISSION_DASHBOARD_API}.get_bootstrap` })
		.then(async (r) => {
			const boot = r.message;
			wrapper.slcm_dashboard.styles = boot.assets.css.map(add_stylesheet);
			const module = await import(boot.assets.js);
			$root.empty();
			wrapper.slcm_dashboard.app = module.mount($root.get(0), {
				api: ADMISSION_DASHBOARD_API,
				boot,
			});
		})
		.catch((e) => {
			console.error(e);
			$root.html(
				`<div class="text-muted" style="padding: 48px; text-align: center;">${__(
					"Could not load the Admission Dashboard."
				)}</div>`
			);
		});
};

frappe.pages["admission-dashboard"].on_page_show = function (wrapper) {
	toggle_styles(wrapper, true);
	fold_sidebar(wrapper);

	// Frappe has no `on_page_hide` for desk pages (checked on v16.33 and v16.53), but the
	// container fires `page-change` on every page switch, after `frappe.container.page`
	// is set. Bind once; turn the styles off whenever another page is on screen.
	if (!wrapper.slcm_page_change_bound) {
		wrapper.slcm_page_change_bound = true;
		$(document).on("page-change.slcm_admission_dashboard", () => {
			const on_screen = frappe.container?.page === wrapper;
			toggle_styles(wrapper, on_screen);
			if (on_screen) fold_sidebar(wrapper);
			else unfold_sidebar(wrapper);
		});
	}
};

// ---- Desk sidebar: folded on this page only ----
//
// The dashboard is wide, so the sidebar starts folded here. Desk saves the sidebar's
// open/closed state for every page (localStorage "desk-sidebar-collapsed") whenever it is
// toggled, including from the rail while this page is open. So the user's setting is
// remembered on the way in and put back on the way out: nothing done here carries over.

const SIDEBAR_PREF_KEY = "desk-sidebar-collapsed";

function read_sidebar_pref() {
	try {
		return localStorage.getItem(SIDEBAR_PREF_KEY);
	} catch {
		return null;
	}
}

function write_sidebar_pref(value) {
	try {
		if (value === null) localStorage.removeItem(SIDEBAR_PREF_KEY);
		else localStorage.setItem(SIDEBAR_PREF_KEY, value);
	} catch {
		// storage refused: desk falls back to an open sidebar
	}
}

function fold_sidebar(wrapper) {
	const sidebar = frappe.app?.sidebar;
	if (!sidebar?.fold_for_page) return;
	if (!wrapper.slcm_sidebar_folded) {
		wrapper.slcm_sidebar_pref = read_sidebar_pref();
		wrapper.slcm_sidebar_folded = true;
	}
	sidebar.fold_for_page();
}

function unfold_sidebar(wrapper) {
	const sidebar = frappe.app?.sidebar;
	if (!wrapper.slcm_sidebar_folded || !sidebar) return;
	wrapper.slcm_sidebar_folded = false;
	write_sidebar_pref(wrapper.slcm_sidebar_pref);
	sidebar.unfold_after_leaving_page?.();
	// Re-read the restored setting and draw it, whichever way the sidebar was left here.
	sidebar.load_expanded_state?.();
	sidebar.apply_expanded_state?.();
	if (sidebar.sidebar_expanded) sidebar.highlight_active_item?.();
}

function toggle_styles(wrapper, enabled) {
	(wrapper.slcm_dashboard?.styles || []).forEach((link) => (link.disabled = !enabled));
	// Overlays (dialogs, dropdowns) live in a portal on <body>; hide it with the page.
	document
		.querySelectorAll(".slcm-fui-portal")
		.forEach((el) => (el.style.display = enabled ? "" : "none"));
}

function add_stylesheet(href) {
	let link = document.querySelector(`link[data-slcm-href="${href}"]`);
	if (!link) {
		link = document.createElement("link");
		link.rel = "stylesheet";
		link.href = href;
		link.dataset.slcmHref = href;
		document.head.appendChild(link);
	}
	link.disabled = false;
	return link;
}
})();
