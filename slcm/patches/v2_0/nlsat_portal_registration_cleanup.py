"""
NLSAT portal clean-up (User.nlsat_portal becomes the single source of a candidate's portal).

1. Create User.nlsat_registration_url (fixtures/custom_field.json never reaches User fields on
   sites without ERPNext; see create_user_nlsat_portal_field).
2. Candidates with an empty NLSAT Portal and an application: set it from their latest
   application (Foreign National Yes → International, No → Domestic). Candidates without an
   application get it on their next login (nlsat_portal.enforce_login_portal).
3. Log, for the admission office to review (Error Log, title "NLSAT portal review: …"):
   * candidates with both Indian-national and foreign-national applications;
   * candidates whose NLSAT Portal differs from their latest application;
   * desk users (System Users) with the Applicant role, who can't log in on the NLSAT pages.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

# Same definition as "User-nlsat_registration_url" in fixtures/custom_field.json
REGISTRATION_URL_FIELD = {
	"fieldname": "nlsat_registration_url",
	"label": "Registration URL",
	"fieldtype": "Code",
	"insert_after": "nlsat_portal",
	"read_only": 1,
	"no_copy": 1,
	"description": "Full URL of the page the user signed up from. Set once at sign-up.",
}

CANDIDATES = """
	from `tabUser` u
	where u.user_type = 'Website User'
	  and exists (select 1 from `tabHas Role` r where r.parent = u.name and r.role = 'Applicant')
"""
LATEST_FN = """
	(select a.foriegn_national from `tabApplicant` a
	 where a.email = u.name and a.foriegn_national in ('Yes', 'No')
	 order by a.creation desc limit 1)
"""


def execute():
	if not frappe.db.exists("Custom Field", "User-nlsat_registration_url"):
		create_custom_field("User", REGISTRATION_URL_FIELD)
		frappe.clear_cache(doctype="User")

	if not frappe.db.has_column("User", "nlsat_portal"):
		return

	# 2. Backfill NLSAT Portal from the latest application
	rows = frappe.db.sql(
		f"select u.name, {LATEST_FN} as fn {CANDIDATES} and ifnull(u.nlsat_portal, '') = ''",
		as_dict=True,
	)
	filled = 0
	for row in rows:
		if row.fn:
			portal = "International" if row.fn == "Yes" else "Domestic"
			frappe.db.set_value("User", row.name, "nlsat_portal", portal, update_modified=False)
			filled += 1

	# 3. Review lists
	mixed = frappe.db.sql_list(
		f"""select u.name {CANDIDATES}
		and exists (select 1 from `tabApplicant` a where a.email = u.name and a.foriegn_national = 'Yes')
		and exists (select 1 from `tabApplicant` a where a.email = u.name and a.foriegn_national = 'No')"""
	)
	disagree = frappe.db.sql(
		f"""select u.name, u.nlsat_portal, {LATEST_FN} as fn {CANDIDATES}
		and ifnull(u.nlsat_portal, '') != ''""",
		as_dict=True,
	)
	disagree = [
		f"{r.name}: NLSAT Portal {r.nlsat_portal}, latest application "
		f"{'foreign national' if r.fn == 'Yes' else 'Indian national'}"
		for r in disagree
		if r.fn and (r.nlsat_portal == "International") != (r.fn == "Yes")
	]
	desk_applicants = frappe.db.sql_list(
		"""select u.name from `tabUser` u
		where u.user_type = 'System User' and u.name != 'Administrator'
		  and exists (select 1 from `tabHas Role` r where r.parent = u.name and r.role = 'Applicant')"""
	)

	_log(
		"candidates with both Indian-national and foreign-national applications",
		mixed,
		"NLSAT Portal was set from the latest application where it was empty. Decide which type "
		"is right, set NLSAT Portal on the User, and update Foreign National on the other "
		"applications (or cancel them).",
	)
	_log(
		"NLSAT Portal differs from the latest application",
		disagree,
		"NLSAT Portal now decides the candidate's portal. Change it on the User, or update "
		"Foreign National on the application.",
	)
	_log(
		"desk users with the Applicant role",
		desk_applicants,
		"Desk users can't log in on the NLSAT login pages. If this is a candidate account, make "
		"it a Website User; otherwise remove the Applicant role.",
	)
	print(
		f"NLSAT portal clean-up: filled {filled}; review: {len(mixed)} mixed, "
		f"{len(disagree)} differing, {len(desk_applicants)} desk users with Applicant role"
	)


def _log(title, items, action):
	if not items:
		return
	message = f"{action}\n\n" + "\n".join(items)
	frappe.log_error(title=f"NLSAT portal review: {title} ({len(items)})", message=message)
