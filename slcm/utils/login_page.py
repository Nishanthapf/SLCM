"""The unified sign-in page at /login (slcm/www/login.py + frontend/src/login).

One page for everyone except admission / PACE applicants (they keep their own
login pages). Three tabs:

  staff            office users -> the desk (/desk). Username + password and the
                   stock Frappe options in System Settings (email link) plus
                   Google when a Google Social Login Key is enabled.
  faculty-student  Google only. Each group is switched on/off by
                   "Enable Google Login" in Faculty / Student Portal Settings.
  parent           username + password, plus Google when Parent Portal
                   Settings allows it.

Rules enforced on the server (the page only mirrors them):

  * `enforce_password_login_policy` (on_login hook): faculty and students can
    not sign in with a password or email link; they must use Google. Accounts
    that also have real desk access (staff) are exempt.
  * `enforce_google_login` (on_session_creation hook): Google sign-ins are
    checked against the portal settings (switched on, allowed domain) and
    linked to their Faculty / Student Master record.

After signing in the browser comes back to /login?tab=..., and
`get_landing_page` sends the user to their own portal.
"""

from urllib.parse import quote

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit

from slcm.security.access import safe_redirect_path

TAB_STAFF = "staff"
TAB_FACULTY_STUDENT = "faculty-student"
TAB_PARENT = "parent"
TABS = (TAB_STAFF, TAB_FACULTY_STUDENT, TAB_PARENT)

# /login?switch-account=1 signs the current user out and shows the sign-in form.
SWITCH_ACCOUNT_PARAM = "switch-account"

STAFF_HOME = "/desk"
PORTAL_HOMES = {
	"faculty": "/faculty-portal",
	"student": "/student-portal",
	"parent": "/parent-portal",
}

# Which account kind wins when a user has several, per tab they signed in from.
LANDING_ORDER = {
	TAB_STAFF: ("staff", "faculty", "student", "parent"),
	TAB_FACULTY_STUDENT: ("faculty", "student", "staff", "parent"),
	TAB_PARENT: ("parent", "staff", "faculty", "student"),
}

# Roles with desk access that do not make someone office staff.
# ("Student" is a legacy role that has desk access switched on.)
NON_STAFF_DESK_ROLES = {"Student", "Desk User", "All", "Guest"}

SETTINGS = {
	"faculty": "Faculty Portal Settings",
	"student": "Student Portal Settings",
	"parent": "Parent Portal Settings",
}

DEFAULT_TITLE = "National Law School of India University"
DEFAULT_PRIMARY = "#920c24"


class LoginNotAllowed(frappe.AuthenticationError):
	"""Credentials were right, but this account may not sign in this way."""


# --------------------------------------------------------------------------- #
# Messages shown on the page (keyed by code so a URL can't inject text)
# --------------------------------------------------------------------------- #


def get_error_message(code: str) -> str:
	if not code:
		return ""
	group, _sep, reason = code.partition("_")
	label = {"faculty": _("Faculty"), "student": _("Student"), "parent": _("Parent")}.get(group)

	if reason == "disabled" and label:
		return _("{0} sign-in is currently disabled. Please contact the administration office if you need access.").format(label)
	if reason == "domain" and label:
		domain = _allowed_domain(group)
		return _("Please sign in with your @{0} Google account. Other Google accounts can't be used here.").format(domain)
	if code == "no_account":
		return _(
			"We couldn't find a staff, faculty, student or parent account for this Google account. "
			"Please contact the administration office to get access."
		)
	if code == "use_google":
		return _("Faculty and students sign in with their institutional Google account. Use the Faculty & Student tab.")
	return _("Sign-in didn't complete. Please try again.")


# --------------------------------------------------------------------------- #
# Who is this user?
# --------------------------------------------------------------------------- #


def get_account_kinds(user: str) -> dict:
	"""{"staff", "faculty", "student", "parent"} -> bool"""
	from slcm.slcm.utils.parent_portal import get_parent_wards

	return {
		"staff": is_staff(user),
		"faculty": bool(get_faculty_for(user)),
		"student": bool(get_student_for(user)),
		"parent": bool(get_parent_wards(user)),
	}


def is_staff(user: str) -> bool:
	"""Office staff: a System User with at least one real desk role."""
	if user == "Administrator":
		return True
	if frappe.db.get_value("User", user, "user_type") != "System User":
		return False
	roles = set(frappe.get_roles(user)) - NON_STAFF_DESK_ROLES
	if not roles:
		return False
	return bool(frappe.get_all("Role", filters={"name": ["in", list(roles)], "desk_access": 1}, limit=1))


def get_faculty_for(user: str):
	for field in ("user_id", "official_email_id", "email"):
		name = frappe.db.get_value("Faculty", {field: user}, "name")
		if name:
			return name
	return None


def get_student_for(user: str):
	return frappe.db.get_value("Student Master", {"official_email_id": user}, "name") or frappe.db.get_value(
		"Student Master", {"user": user}, "name"
	)


def google_enabled(group: str) -> bool:
	return bool(frappe.db.get_single_value(SETTINGS[group], "enable_google_login"))


def _allowed_domain(group: str) -> str:
	return (frappe.db.get_single_value(SETTINGS[group], "google_login_allowed_domain") or "").strip().lstrip("@").lower()


# --------------------------------------------------------------------------- #
# Where to go after signing in
# --------------------------------------------------------------------------- #


def get_landing_page(user: str, tab: str, redirect_to: str = "") -> str | None:
	"""The page to open for a signed-in user, or None when the account has no access."""
	kinds = get_account_kinds(user)
	kind = next((k for k in LANDING_ORDER.get(tab, LANDING_ORDER[TAB_STAFF]) if kinds[k]), None)
	if not kind:
		return None

	home = STAFF_HOME if kind == "staff" else PORTAL_HOMES[kind]
	redirect_to = safe_redirect_path(redirect_to, "")
	if redirect_to and not redirect_to.startswith("/login"):
		if kind == "staff":
			return redirect_to
		# Portal users may only be sent somewhere inside their own portal.
		if redirect_to == home or redirect_to.startswith(home + "/") or redirect_to.startswith(home + "?"):
			return redirect_to
	return home


def tab_for_redirect(redirect_to: str) -> str | None:
	"""Guess the tab from where the user was going (e.g. /parent-portal -> parent)."""
	if not redirect_to:
		return None
	if redirect_to.startswith(("/faculty-portal", "/student-portal")):
		return TAB_FACULTY_STUDENT
	if redirect_to.startswith("/parent-portal"):
		return TAB_PARENT
	if redirect_to.startswith(("/desk", "/app")):
		return TAB_STAFF
	return None


# --------------------------------------------------------------------------- #
# What the page shows
# --------------------------------------------------------------------------- #


def get_page_config(tab: str, redirect_to: str, error_code: str) -> dict:
	"""Branding and the sign-in options of each tab, from the portal settings."""
	student = frappe.get_cached_doc("Student Portal Settings")
	password = not frappe.get_system_settings("disable_user_pass_login")
	google_ready = _google_provider_ready()
	faculty_on, student_on = google_enabled("faculty"), google_enabled("student")

	return {
		"brand": {
			"title": student.get("portal_title") or DEFAULT_TITLE,
			"subtitle": student.get("portal_subtitle") or "",
			"logo": student.get("portal_favicon") or frappe.db.get_single_value("Website Settings", "app_logo") or "",
			"background": student.get("login_page_background_image") or "",
			"primary": student.get("primary_color") or DEFAULT_PRIMARY,
			"font": student.get("font_family") or "Merriweather",
		},
		"tabs": {
			TAB_STAFF: {
				"password": password,
				"google": google_ready,
			},
			TAB_FACULTY_STUDENT: {
				"faculty": faculty_on,
				"student": student_on,
				"google": google_ready and (faculty_on or student_on),
				"domains": sorted({d for d in (_allowed_domain("faculty"), _allowed_domain("student")) if d}),
			},
			TAB_PARENT: {
				"password": password,
				"google": google_ready and google_enabled("parent"),
			},
		},
		"tab": tab,
		"redirect_to": redirect_to,
		"error": get_error_message(error_code),
	}


def _google_provider_ready() -> bool:
	return bool(
		frappe.db.exists("Social Login Key", {"social_login_provider": "Google", "enable_social_login": 1})
	)


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=30, seconds=60)
def get_google_login_url(tab: str, redirect_to: str = "") -> str:
	"""Google authorize URL that returns to /login on the same tab.

	Made on click (not when the page renders): each URL holds a single-use
	state that Frappe keeps for 10 minutes.
	"""
	from frappe.utils.oauth import get_oauth2_authorize_url

	if tab not in TABS:
		tab = TAB_STAFF
	config = get_page_config(tab, "", "")["tabs"][tab]
	if not config.get("google"):
		frappe.throw(_("Google sign-in is not available here."), LoginNotAllowed)

	callback = f"/login?tab={tab}"
	redirect_to = safe_redirect_path(redirect_to, "")
	if redirect_to:
		callback += "&redirect-to=" + quote(redirect_to, safe="")
	return get_oauth2_authorize_url("google", callback)


# --------------------------------------------------------------------------- #
# Hooks
# --------------------------------------------------------------------------- #


def _is_google_request() -> bool:
	path = getattr(getattr(frappe.local, "request", None), "path", "") or ""
	return "oauth2_logins.login_via_google" in path


def _is_impersonation() -> bool:
	path = getattr(getattr(frappe.local, "request", None), "path", "") or ""
	return path.endswith(".impersonate") or (frappe.form_dict.get("cmd") or "").endswith(".impersonate")


def enforce_password_login_policy(login_manager=None):
	"""on_login: faculty and students must use Google (staff accounts are exempt).

	Covers every non-Google way in (password, email link, login token). Runs
	after the password check, so it never tells a stranger what kind of
	account an email belongs to.
	"""
	user = getattr(login_manager, "user", None)
	if not user or user in ("Guest", "Administrator") or _is_google_request() or _is_impersonation():
		return
	if is_staff(user):
		return

	for group, finder in (("faculty", get_faculty_for), ("student", get_student_for)):
		if finder(user):
			code = "use_google" if google_enabled(group) else f"{group}_disabled"
			frappe.throw(get_error_message(code), LoginNotAllowed, title=_("Sign-in not allowed"))


def enforce_google_login(login_manager=None):
	"""on_session_creation: check Google sign-ins against the portal settings.

	All three portals share Frappe's Google callback, so the account decides
	which settings apply: Faculty, then Student, then Parent, then staff.
	A switched-off portal or wrong domain is refused (staff who also hold that
	record still get in, to the desk). Unknown Google accounts are refused.
	"""
	from slcm.slcm.utils.parent_portal import get_parent_wards

	user = getattr(login_manager, "user", None) or frappe.session.user
	if not user or user in ("Guest", "Administrator") or not _is_google_request():
		return

	staff = is_staff(user)
	checks = (
		("faculty", get_faculty_for(user)),
		("student", get_student_for(user)),
		("parent", bool(get_parent_wards(user))),
	)
	for group, record in checks:
		if not record:
			continue
		problem = None
		if not google_enabled(group):
			problem = f"{group}_disabled"
		else:
			domain = _allowed_domain(group)
			if domain and user.split("@")[-1].lower() != domain:
				problem = f"{group}_domain"
		if problem:
			if staff:
				return
			_reject(login_manager, problem, TAB_PARENT if group == "parent" else TAB_FACULTY_STUDENT)
		_link_account(user, group, record)
		return

	if not staff:
		_reject(login_manager, "no_account", TAB_STAFF)


def _link_account(user, group, record):
	"""Point the record at this Google user and give it the portal role."""
	if group == "faculty" and frappe.db.get_value("Faculty", record, "user_id") != user:
		frappe.db.set_value("Faculty", record, "user_id", user)
	if group == "student" and frappe.db.get_value("Student Master", record, "user") != user:
		# NLSIU issues the institutional email after admission; Student Master.user
		# still holds the application email until the first Google sign-in.
		frappe.db.set_value("Student Master", record, "user", user)

	role = {"faculty": "slcm_Faculty", "student": "slcm_Student", "parent": "slcm_parent"}[group]
	if not frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": role}):
		user_doc = frappe.get_doc("User", user)
		user_doc.append("roles", {"role": role})
		user_doc.save(ignore_permissions=True)


def _reject(login_manager, code, tab):
	"""End the just-created Google session and go back to /login with a message.

	AuthRedirect (a werkzeug HTTPException), not frappe.Redirect: nothing in
	Frappe's login internals catches frappe.Redirect.
	"""
	from slcm.utils.auth_routing import AuthRedirect

	user = getattr(login_manager, "user", None) or frappe.session.user
	frappe.local.login_manager.logout()
	frappe.set_user("Guest")
	frappe.db.commit()
	frappe.log_error(f"Rejected Google sign-in for {user}: {code}", "Google login rejected")
	raise AuthRedirect(f"/login?tab={tab}&error={quote(code)}")


# --------------------------------------------------------------------------- #
# "Not Permitted" page
# --------------------------------------------------------------------------- #


def switch_account_on_not_permitted(context):
	"""update_website_context hook: make the Not Permitted page's Login button sign out first.

	Frappe's Not Permitted page (e.g. a portal user opening /desk) links its
	button to /login, but /login sends a signed-in user straight back to their
	landing page, so the sign-in form never shows. Point the button at
	/login?switch-account=1 instead, which signs out and then shows the form.
	"""
	if frappe.session.user == "Guest":
		return

	response_context = getattr(frappe.local, "response", {}).get("context")
	if not response_context:
		return

	action = response_context.get("primary_action") or ""
	if response_context.get("primary_label") != _("Login") or not action.startswith("/login"):
		return
	if f"{SWITCH_ACCOUNT_PARAM}=" in action:
		return

	separator = "&" if "?" in action else "?"
	response_context["primary_action"] = f"{action}{separator}{SWITCH_ACCOUNT_PARAM}=1"
