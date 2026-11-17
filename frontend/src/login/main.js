// /login: the unified sign-in page. Rendered by slcm/www/login.html, which
// puts the page settings (from slcm/utils/login_page.py) in a JSON script tag
// and the CSRF token in window.csrf_token.

import { createApp } from "vue";
import App from "./App.vue";
import "./index.css";

const config = JSON.parse(document.getElementById("slcm-login-config").textContent);
const el = document.getElementById("slcm-login");

// Brand colour and font come from Student Portal Settings.
el.style.setProperty("--login-brand", config.brand.primary);
el.style.setProperty("--login-font", `"${config.brand.font}", Georgia, serif`);

// Overlays (tooltips) teleport here, so they stay inside the .slcm-fui CSS scope.
const portal = document.createElement("div");
portal.className = "slcm-fui slcm-fui-portal";
document.body.appendChild(portal);

const app = createApp(App, { config });
app.provide(Symbol.for("frappe-ui:portal-target"), portal);
app.mount(el);
