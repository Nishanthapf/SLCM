"""/login: the unified sign-in page (staff, faculty & student, parent & guardian).

Replaces Frappe's own www/login (apps installed after frappe override its www
pages). The page body is the Vue app in frontend/src/login; the rules live in
slcm/utils/login_page.py. Admission and PACE applicants are sent to their own
login pages earlier, by slcm.utils.auth_routing.intercept_login.

There is no sign-up here: accounts are created by the institution.
"""

from urllib.parse import urlencode

import frappe

from slcm.security.access import safe_redirect_path
from slcm.utils.login_page import (
	SWITCH_ACCOUNT_PARAM,
	TAB_FACULTY_STUDENT,
	TABS,
	get_landing_page,
	get_page_config,
	tab_for_redirect,
)
from slcm.utils.vite_assets import get_entry_assets

no_cache = 1
sitemap = 0

ENTRY = "src/login/main.js"


def get_context(context):
	args = frappe.local.request.args
	redirect_to = safe_redirect_path(
		args.get("redirect-to") or args.get("redirect_to") or args.get("redirect") or args.get("next") or "",
		"",
	)

	tab = args.get("tab") or ""
	if tab not in TABS:
		tab = (
			tab_for_redirect(redirect_to)
			or getattr(frappe.local.flags, "default_login_tab", None)  # set by intercept_login
			or TAB_FACULTY_STUDENT
		)

	error_code = args.get("error") or ""

	if frappe.session.user != "Guest" and args.get(SWITCH_ACCOUNT_PARAM):
		# Sent here from a page this account may not open (e.g. the Not Permitted
		# page's Login button): sign out, then show the sign-in form.
		frappe.local.login_manager.logout()
		frappe.db.commit()
		query = {k: v for k, v in (("redirect-to", redirect_to), ("tab", args.get("tab"))) if v}
		frappe.local.flags.redirect_location = "/login" + ("?" + urlencode(query) if query else "")
		raise frappe.Redirect(302)

	if frappe.session.user != "Guest":
		landing = get_landing_page(frappe.session.user, tab, redirect_to)
		if not landing:
			# Signed in, but not staff, faculty, student or parent (e.g. an applicant).
			from frappe.website.utils import get_home_page

			landing = "/" + (get_home_page() or "me").lstrip("/")
		frappe.local.flags.redirect_location = landing
		# 302, not the default 301: browsers cache a 301 and would skip /login later.
		raise frappe.Redirect(302)

	config = get_page_config(tab, redirect_to, error_code)
	context.no_cache = 1
	context.config = config
	context.brand = config["brand"]
	context.assets = get_entry_assets(ENTRY)
	context.csrf_token = frappe.local.session.data.csrf_token or ""
	context.title = "Login | " + config["brand"]["title"]
