import { createApp } from "vue";
import { frappeRequest, setConfig } from "frappe-ui";
import App from "./App.vue";
import "./index.css";

// frappe-ui's injection key for where overlays teleport (registered globally).
const portalTargetKey = Symbol.for("frappe-ui:portal-target");

/**
 * Mount the dashboard inside the desk page.
 *
 * @param {HTMLElement} el  page root (carries the `slcm-fui` scope class)
 * @param {{ api: string, boot: object }} options  server method prefix + get_bootstrap() result
 */
export function mount(el, { api, boot }) {
	// frappe-ui's fetcher reads the CSRF token from window.csrf_token.
	if (window.frappe?.csrf_token) window.csrf_token = window.frappe.csrf_token;
	// createResource({ url: "dotted.method" }) -> POST /api/method/dotted.method
	setConfig("resourceFetcher", frappeRequest);

	// Dialogs and dropdowns teleport here, so they stay inside the CSS scope.
	let portal = document.querySelector(".slcm-fui-portal");
	if (!portal) {
		portal = document.createElement("div");
		portal.className = "slcm-fui slcm-fui-portal";
		document.body.appendChild(portal);
	}

	const app = createApp(App, { api, boot });
	app.provide(portalTargetKey, portal);
	app.mount(el);
	return app;
}
