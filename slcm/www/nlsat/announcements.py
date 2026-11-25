"""/nlsat/announcements — Portal Announcements whose Target Audience includes the
applicant's portal (Domestic / International), newest first."""

import frappe
from frappe.utils import cint, date_diff, getdate, nowdate

from slcm.admission.utils.portal_pages import prepare_sidebar_page

no_cache = 1

# Announcements per page
PAGE_SIZE = 10

# An announcement shows the "New" tag for this many days after its publish date
NEW_FOR_DAYS = 7


def get_context(context):
	from slcm.admission.utils.web import _get_portal_announcement_read_ids, get_portal_announcement_filters

	# Open to logged-out visitors too (navbar link); they get a sidebar with only this page
	prepare_sidebar_page(context, "announcements", "/nlsat/announcements", allow_guest=True)
	context.title = "Announcements"
	context.page_subtitle = "Latest admission updates from the Admissions Office."

	user = frappe.session.user
	is_guest = not user or user == "Guest"
	filters = get_portal_announcement_filters(user)

	# Pagination: ?page=N (1-based), PAGE_SIZE per page
	total = frappe.db.count("Portal Announcement", filters)
	total_pages = max(1, -(-total // PAGE_SIZE))
	page = min(max(cint(frappe.form_dict.get("page")) or 1, 1), total_pages)
	rows = frappe.get_all(
		"Portal Announcement",
		filters=filters,
		fields=["name", "title", "publish_date", "announcement_type", "summary"],
		order_by="publish_date desc, creation desc",
		limit_start=(page - 1) * PAGE_SIZE,
		limit_page_length=PAGE_SIZE,
	)
	context.cur_page = page
	context.total_pages = total_pages
	context.total = total
	context.range_start = (page - 1) * PAGE_SIZE + 1 if total else 0
	context.range_end = (page - 1) * PAGE_SIZE + len(rows)
	# Page links: first, last and two either side of the current page; None marks a gap
	nums, last = [], 0
	for n in range(1, total_pages + 1):
		if n in (1, total_pages) or abs(n - page) <= 2:
			if last and n - last > 1:
				nums.append(None)
			nums.append(n)
			last = n
	context.page_numbers = nums
	# "New": published within the last 7 days (for everyone, read or not).
	# Read state is per user and only shown to logged-in users.
	today = getdate(nowdate())
	read = set() if is_guest else _get_portal_announcement_read_ids(user)
	for row in rows:
		row.is_new = bool(row.publish_date) and 0 <= date_diff(today, row.publish_date) < NEW_FOR_DAYS
		row.is_read = is_guest or row.name in read
		row.url = "/nlsat/announcement/" + row.name
	context.announcements = rows
	context.show_read_state = not is_guest
	return context
