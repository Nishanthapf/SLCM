"""
Sidebar partial for the admission portal pages (profile, applications, scholarships,
offer letter, helpdesk …), shared by NLSAT (Domestic + International) and PACE pages.

_sidebar.html holds the portal_sidebar_css / portal_sidebar_html / portal_sidebar_js macros
and is imported by each page, not served as a page. The menu data comes from
get_nlsat_sidebar_context(), exposed to Jinja through the `jinja.methods` hook.
"""

import frappe


def get_context(context):
	# Partial only — must not render as a page
	raise frappe.PageDoesNotExistError


def _show_scholarships(user):
	"""Scholarships entry: shown when the active cycle enables it, or the user already applied."""
	active_cycle = frappe.db.get_value("Admission Cycle", {"status": "Active"}, "name")
	if active_cycle and frappe.db.get_value("Admission Cycle", active_cycle, "enable_scholarship"):
		return True
	applicant_names = frappe.get_all("Applicant", {"email": user}, pluck="name")
	return bool(
		applicant_names
		and frappe.db.count("Scholarship Application", {"applicant_id": ("in", applicant_names)})
	)


def _show_offer_letter(user, roles):
	"""Offer Letter entry: shown only when the user/candidate has at least one offer letter record."""
	if not user or user == "Guest":
		return False

	is_admin = user == "Administrator" or bool({"Administrator", "System Manager", "Admission Admin"} & roles)
	if is_admin:
		return bool(frappe.db.count("Offer Letter"))

	if frappe.db.exists("Offer Letter", {"email": user}):
		return True

	if frappe.db.exists("Offer Letter", {"owner": user}):
		return True

	applicant_names = set(frappe.get_all("Applicant", {"email": user}, pluck="name"))
	applicant_names.update(frappe.get_all("Applicant", {"owner": user}, pluck="name"))
	if applicant_names and frappe.db.exists("Offer Letter", {"applicant": ("in", list(applicant_names))}):
		return True

	if frappe.db.exists("Offer Letter", {"applicant": user}):
		return True

	return False


def get_nlsat_sidebar_context():
	from slcm.admission.utils.nlsat_portal import NLSAT_PREFIX, get_candidate_prefix
	from slcm.admission.utils.portal import get_portal_sidebar_pages

	user = frappe.session.user
	prefix = get_candidate_prefix(user)  # /nlsat or /pace — shared pages are served under it

	# Logged-out visitors (Announcements opened from the navbar): only the Announcements item
	if not user or user == "Guest":
		pages = get_portal_sidebar_pages() if prefix == NLSAT_PREFIX else frappe._dict()
		return frappe._dict(
			is_guest=True,
			show_profile=False,
			show_applications=False,
			show_pace_applications=False,
			show_admission_items=False,
			show_documents=False,
			show_sample_questions=False,
			show_announcements=bool(pages.get("announcements")),
			show_scholarships=False,
			show_offer_letter=False,
			show_helpdesk=False,
			urls=frappe._dict(announcements="/nlsat/announcements"),
		)

	roles = set(frappe.get_all("Has Role", filters={"parent": user}, pluck="role"))
	is_admin = user == "Administrator" or bool({"Administrator", "System Manager"} & roles)
	has_applicant = "Applicant" in roles
	has_pace = "PACE Applicant" in roles
	is_pace_staff = not is_admin and ("Document Verifier" in roles or "PACE Admission Manager" in roles)
	pace_only = has_pace and not has_applicant and not is_admin
	show_admission_items = not pace_only and not is_pace_staff

	# Documents / Sample Question Papers / Announcements: NLSAT only, each switched on per
	# portal (Domestic / International) in Applicant Portal Config.
	nlsat_pages = show_admission_items and prefix == NLSAT_PREFIX
	pages = get_portal_sidebar_pages() if nlsat_pages else frappe._dict()

	return frappe._dict(
		show_profile=not is_pace_staff,
		show_applications=show_admission_items,
		show_pace_applications=not (has_applicant and not has_pace),
		show_admission_items=show_admission_items,
		show_documents=bool(pages.get("documents")),
		show_sample_questions=bool(pages.get("sample_questions")),
		show_announcements=bool(pages.get("announcements")),
		show_scholarships=show_admission_items and _show_scholarships(user),
		show_offer_letter=show_admission_items and _show_offer_letter(user, roles),
		show_helpdesk=not is_pace_staff,
		urls=frappe._dict(
			profile=prefix + "/my-profile",
			applications="/nlsat/dashboard?panel=applications",
			pace_applications="/paceadmissions/application-card",
			documents="/nlsat/documents",
			sample_questions="/nlsat/sample-questions",
			announcements="/nlsat/announcements",
			scholarships="/nlsat/scholarships",
			offer_letter="/nlsat/offer_letter/offer-letter-list",
			helpdesk=prefix + "/helpdesk",
			change_password="/update-password",
		),
	)
