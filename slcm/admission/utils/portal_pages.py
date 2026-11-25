"""
Applicant sidebar pages of the NLSAT portals: Documents, Sample Question Papers and
Announcements (www/nlsat/documents, sample-questions, announcements).

Each page is switched on per portal (Domestic / International) in Applicant Portal Config.
When it is off, the sidebar hides the menu and the page returns 404.
"""

from urllib.parse import quote

import frappe

ALLOWED_ROLES = {"Applicant", "System Manager", "Administrator"}


def prepare_sidebar_page(context, page, path, allow_guest=False):
	"""Check access for a sidebar page and fill the context shared by all of them.

	page: key in get_portal_sidebar_pages() ("documents", "sample_questions", "announcements")
	path: the page's own route, used to come back after login
	allow_guest: logged-out visitors may open the page (Announcements); their sidebar
	    shows only that page (see get_nlsat_sidebar_context)
	"""
	from slcm.admission.utils.nlsat_portal import get_portal_login_url
	from slcm.admission.utils.portal import get_portal_config, get_portal_sidebar_pages

	user = frappe.session.user
	is_guest = not user or user == "Guest"
	if is_guest and not allow_guest:
		frappe.local.flags.redirect_location = get_portal_login_url() + "?redirect-to=" + quote(path, safe="/")
		raise frappe.Redirect

	if not is_guest and not (ALLOWED_ROLES & set(frappe.get_roles(user))):
		raise frappe.PermissionError

	pages = get_portal_sidebar_pages()
	if not pages.get(page):
		raise frappe.PageDoesNotExistError

	context.no_cache = 1
	context.portal_config = get_portal_config()
	context.sidebar_active = page
	return pages
