"""User Activity Log: records every action performed under a user login.

What is captured (one `User Activity Log` row each):
  * Login / Logout / Login Failed            on_session_creation, on_logout, Activity Log (failed)
  * Create / Update / Submit / Cancel /      doc_events "*" on every non-system DocType, with the
    Update After Submit / Delete / Rename    changed fields (old -> new) stored as JSON
  * Export / Print / Download                Frappe's Access Log (report & list exports, PDFs, files)
  * View                                     a user opening a record in the desk form
  * Action                                   any SLCM whitelisted method a user calls (page buttons,
                                             dashboards, portal actions)

Not captured: scheduler jobs, migrate / install / patches (no user is acting), Guest requests, and the
system DocTypes in IGNORED_DOCTYPES (logs, queues, caches). Logging never raises: a failure is written
to the Error Log and the user's action carries on.
"""

import json

import frappe
from frappe.utils import cstr

LOG_DOCTYPE = "User Activity Log"

# System / log DocTypes whose rows are side-effects, not user actions.
IGNORED_DOCTYPES = {
	LOG_DOCTYPE,
	"Version",
	"Activity Log",
	"Access Log",
	"Error Log",
	"Scheduled Job Log",
	"Scheduled Job Type",
	"Route History",
	"Email Queue",
	"Email Queue Recipient",
	"Notification Log",
	"Deleted Document",
	"Prepared Report",
	"Data Import Log",
	"Submission Queue",
	"Integration Request",
	"Webhook Request Log",
	"Energy Point Log",
	"View Log",
	"Transaction Log",
	"Permission Log",
	"Document Follow",
	"Unhandled Email",
	"Session Default Settings",
	"Installed Applications",
	"Patch Log",
	"Console Log",
	"Recorder",
	"Desktop Icon",
	"Dashboard Chart",
	"Number Card",
	"OAuth Bearer Token",
	"OAuth Authorization Code",
	"Communication",
	# SLCM machine-generated logs (RFID agent pushes, import/generation detail rows)
	"Attendance Log",
	"RFID SQL Punch Log",
	"Marks Import Log Detail",
}

# Whitelisted methods logged as "Action": everything in the SLCM app.
LOGGED_METHOD_PREFIXES = ("slcm.",)
VIEW_METHOD = "frappe.desk.form.load.getdoc"

MAX_VALUE_LEN = 300
SECRET_ARG_WORDS = ("password", "pwd", "secret", "token", "otp", "account_number", "api_key")
MAX_CHANGES_LEN = 60000


# ----------------------------------------------------------------- writer


def _should_skip(user=None):
	flags = frappe.flags
	if flags.in_install or flags.in_migrate or flags.in_patch or flags.in_setup_wizard or flags.in_test:
		return True
	if (user or frappe.session.user) == "Guest":
		return True
	if not getattr(frappe.local, "request", None):
		job = getattr(frappe.local, "job", None)
		# Only user-triggered background jobs (imports, bulk actions) count; scheduler runs don't,
		# and neither do console / bench execute sessions.
		if not job or "scheduled_job_type" in cstr(job.get("method")):
			return True
	return False


def _client():
	req = getattr(frappe.local, "request", None)
	if not req:
		return None, None
	return getattr(frappe.local, "request_ip", None) or req.remote_addr, cstr(req.headers.get("User-Agent"))[:500]


def log_activity(action, reference_doctype=None, reference_name=None, summary=None, changes=None, method=None, user=None):
	user = user or frappe.session.user
	if _should_skip(user):
		return
	try:
		ip, agent = _client()
		doc = frappe.get_doc(
			{
				"doctype": LOG_DOCTYPE,
				"user": user if frappe.db.exists("User", user) else None,
				"full_name": frappe.utils.get_fullname(user) if user else None,
				"action": action,
				"reference_doctype": reference_doctype,
				"reference_name": cstr(reference_name)[:140] or None,
				"summary": cstr(summary)[:1000] or None,
				"changes": json.dumps(changes, default=str)[:MAX_CHANGES_LEN] if changes else None,
				"method": cstr(method)[:140] or None,
				"source": "Web" if getattr(frappe.local, "request", None) else "Background Job",
				"ip_address": ip,
				"user_agent": agent,
			}
		)
		doc.flags.ignore_links = True
		doc.db_insert()
	except Exception:
		frappe.log_error(title="User Activity Log: could not record action")


# ----------------------------------------------------------- document events


def _short(value):
	value = cstr(value)
	return value if len(value) <= MAX_VALUE_LEN else value[:MAX_VALUE_LEN] + "…"


def _diff(doc):
	"""Changed fields (old -> new) between the saved version and the one before this save."""
	before = doc.get_doc_before_save()
	if not before:
		return None
	from frappe.core.doctype.version.version import get_diff

	diff = get_diff(before, doc)
	if not diff:
		return None
	meta = doc.meta
	secret = {df.fieldname for df in meta.fields if df.fieldtype == "Password"}

	def label(fieldname, m=meta):
		df = m.get_field(fieldname)
		return df.label if df and df.label else fieldname

	changed = [
		{"field": label(f), "from": "*****" if f in secret else _short(old), "to": "*****" if f in secret else _short(new)}
		for f, old, new in diff.get("changed", [])
	]
	rows = []
	for kind in ("added", "removed"):
		for table, row in diff.get(kind, []):
			rows.append({"table": label(table), "row": kind, "idx": row.get("idx")})
	for table, idx, _name, fields in diff.get("row_changed", []):
		child_meta = frappe.get_meta(meta.get_field(table).options) if meta.get_field(table) else meta
		rows.append(
			{
				"table": label(table),
				"row": "changed",
				"idx": idx,
				"fields": [{"field": label(f, child_meta), "from": _short(o), "to": _short(n)} for f, o, n in fields],
			}
		)
	if not changed and not rows:
		return None
	return {"changed": changed, "rows": rows}


def _secret(key):
	key = cstr(key).lower()
	return any(w in key for w in SECRET_ARG_WORDS)


def _ignored(doc):
	if doc.doctype in IGNORED_DOCTYPES or doc.meta.istable:
		return True
	if doc.doctype == "Comment" and doc.get("comment_type") != "Comment":
		return True  # only real user comments, not auto "Info"/"Like"/"Attachment" timeline entries
	return False


def on_update(doc, method=None):
	if _ignored(doc) or _should_skip():
		return
	if doc.flags.in_insert:
		log_activity("Create", doc.doctype, doc.name, f"Created {doc.doctype} {doc.name}")
		return
	changes = _diff(doc)
	if not changes:
		return  # saved without changing anything
	fields = [c["field"] for c in changes["changed"]] + [f"{r['table']} (rows)" for r in changes["rows"]]
	log_activity(
		"Update", doc.doctype, doc.name, f"Updated {doc.doctype} {doc.name}: " + ", ".join(dict.fromkeys(fields)), changes
	)


def on_submit(doc, method=None):
	if not _ignored(doc):
		log_activity("Submit", doc.doctype, doc.name, f"Submitted {doc.doctype} {doc.name}")


def on_cancel(doc, method=None):
	if not _ignored(doc):
		log_activity("Cancel", doc.doctype, doc.name, f"Cancelled {doc.doctype} {doc.name}")


def on_update_after_submit(doc, method=None):
	if _ignored(doc) or _should_skip():
		return
	changes = _diff(doc)
	if changes:
		log_activity(
			"Update After Submit", doc.doctype, doc.name, f"Updated submitted {doc.doctype} {doc.name}", changes
		)


def on_trash(doc, method=None):
	if not _ignored(doc):
		title = doc.get_title() if hasattr(doc, "get_title") else doc.name
		log_activity("Delete", doc.doctype, doc.name, f"Deleted {doc.doctype} {doc.name} ({title})")


def after_rename(doc, method=None, old=None, new=None, merge=False):
	if not _ignored(doc):
		verb = "Merged" if merge else "Renamed"
		log_activity("Rename", doc.doctype, new or doc.name, f"{verb} {doc.doctype} {old} → {new}")


# ------------------------------------------------------- logins and downloads


def on_session_creation(login_manager=None):
	user = getattr(login_manager, "user", None) or frappe.session.user
	log_activity("Login", "User", user, f"{user} logged in", user=user)


def on_logout(login_manager=None):
	user = getattr(login_manager, "user", None) or frappe.session.user
	log_activity("Logout", "User", user, f"{user} logged out", user=user)


def on_activity_log(doc, method=None):
	"""Frappe writes failed logins to Activity Log (committed even though the request fails)."""
	if doc.operation != "Login" or doc.status != "Failed" or not getattr(frappe.local, "request", None):
		return
	known = bool(doc.user) and frappe.db.exists("User", doc.user)
	try:
		ip, agent = _client()
		frappe.get_doc(
			{
				"doctype": LOG_DOCTYPE,
				"user": doc.user if known else None,
				"full_name": frappe.utils.get_fullname(doc.user) if known else cstr(doc.user)[:140],
				"action": "Login Failed",
				"reference_doctype": "User" if known else None,
				"reference_name": doc.user if known else None,
				# unknown user names are still recorded (password guessing), just without a User link
				"summary": f"Failed login for {'' if known else 'unknown user '}{doc.user}: {doc.subject}"[:1000],
				"source": "Web",
				"ip_address": ip,
				"user_agent": agent,
			}
		).db_insert()
	except Exception:
		frappe.log_error(title="User Activity Log: could not record failed login")


def on_access_log(doc, method=None):
	"""Exports, prints and file downloads (Access Log is inserted later by a deferred job)."""
	if doc.user in (None, "", "Guest"):
		return
	if doc.file_type == "PDF" or doc.method in ("PDF", "Print"):
		action = "Print"
	elif doc.export_from == "File" or doc.report_name == "Backup":
		action = "Download"
	else:
		action = "Export"
	what = doc.report_name or doc.export_from or ("page" if doc.page else "")
	summary = f"{action}: {what}" + (f" {doc.reference_document}" if doc.reference_document else "")
	if doc.file_type:
		summary += f" ({doc.file_type})"
	# Deferred insert runs in a worker as Administrator; the actor is doc.user.
	try:
		frappe.get_doc(
			{
				"doctype": LOG_DOCTYPE,
				"user": doc.user if frappe.db.exists("User", doc.user) else None,
				"full_name": frappe.utils.get_fullname(doc.user),
				"action": action,
				"reference_doctype": doc.export_from if doc.export_from and frappe.db.exists("DocType", doc.export_from) else None,
				"reference_name": doc.reference_document,
				"summary": summary[:1000],
				"method": cstr(doc.method)[:140] or None,
				"changes": json.dumps({"filters": doc.filters, "columns": doc.columns}, default=str)[:MAX_CHANGES_LEN]
				if (doc.filters or doc.columns)
				else None,
				"source": "Web",
			}
		).db_insert()
	except Exception:
		frappe.log_error(title="User Activity Log: could not record export")


# --------------------------------------------------------- views and actions


def after_request(response=None, request=None):
	"""Record-opens and SLCM method calls. Runs after the request's commit, so it commits its own row."""
	try:
		if not request or frappe.session.user == "Guest" or not request.path.startswith("/api/method/"):
			return
		if response is not None and getattr(response, "status_code", 200) >= 400:
			return
		method = request.path[len("/api/method/") :].strip("/")
		form = frappe.form_dict or {}
		if method == VIEW_METHOD:
			doctype, name = form.get("doctype"), form.get("name")
			if not doctype or doctype in IGNORED_DOCTYPES:
				return
			log_activity("View", doctype, name, f"Viewed {doctype} {name}", method=method)
		elif method.startswith(LOGGED_METHOD_PREFIXES):
			args = {k: v for k, v in form.items() if k not in ("cmd", "data") and not k.startswith("_")}
			log_activity(
				"Action",
				summary=f"Called {method.rsplit('.', 1)[-1]}",
				method=method,
				changes={"args": {k: "*****" if _secret(k) else _short(v) for k, v in args.items()}} if args else None,
			)
		else:
			return
		frappe.db.commit()
	except Exception:
		frappe.logger().error("User Activity Log after_request failed", exc_info=True)
