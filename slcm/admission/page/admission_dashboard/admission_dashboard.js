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

	// The Vue app draws its own header (title, Academic Year, Settings).
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

	// Frappe has no `on_page_hide` for desk pages (checked on v16.33 and v16.53), but the
	// container fires `page-change` on every page switch, after `frappe.container.page`
	// is set. Bind once; turn the styles off whenever another page is on screen.
	if (!wrapper.slcm_page_change_bound) {
		wrapper.slcm_page_change_bound = true;
		$(document).on("page-change.slcm_admission_dashboard", () => {
			toggle_styles(wrapper, frappe.container?.page === wrapper);
		});
	}
};

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
