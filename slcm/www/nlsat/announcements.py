"""/nlsat/announcements — Portal Announcements whose Target Audience includes the
applicant's portal (Domestic / International), newest first."""

import frappe

from slcm.admission.utils.portal_pages import prepare_sidebar_page

no_cache = 1


def get_context(context):
	from slcm.admission.utils.web import _get_portal_announcement_read_ids, get_portal_announcement_filters

	prepare_sidebar_page(context, "announcements", "/nlsat/announcements")
	context.title = "Announcements"
	context.page_subtitle = "Latest admission updates from the Admissions Office."

	user = frappe.session.user
	rows = frappe.get_all(
		"Portal Announcement",
		filters=get_portal_announcement_filters(user),
		fields=["name", "title", "publish_date", "announcement_type", "summary"],
		order_by="publish_date desc, creation desc",
		limit_page_length=200,
	)
	read = _get_portal_announcement_read_ids(user)
	for row in rows:
		row.is_read = row.name in read
		row.url = "/nlsat/announcement/" + row.name
	context.announcements = rows
	return context
