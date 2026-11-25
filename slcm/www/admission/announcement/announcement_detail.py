import frappe

login_required = False

def get_context(context):
    from slcm.admission.utils.portal import get_portal_config

    context.portal_config = get_portal_config()

    name = frappe.form_dict.get("name") or ""
    if not name or not frappe.db.exists(
        "Portal Announcement",
        {"name": name, "is_active": 1, "status": "Published"},
    ):
        frappe.throw("Announcement not found or inactive", frappe.DoesNotExistError)

    ann = frappe.get_doc("Portal Announcement", name)

    # Validate target audience access
    from slcm.admission.utils.nlsat_portal import (
        DOMESTIC, INTERNATIONAL, get_applicant_portal_type, get_current_portal_type,
        get_candidate_prefix, PACE_PREFIX,
    )
    user_session = frappe.session.user or "Guest"
    user_app_type = get_applicant_portal_type(user_session) if user_session != "Guest" else None
    resolved_portal = user_app_type or get_current_portal_type()
    is_pace = (get_candidate_prefix(user_session) == PACE_PREFIX) or (resolved_portal == "PACE")

    audience = (ann.target_audience or "").strip()
    is_intl_ann = ("international" in audience.lower() and "domestic" not in audience.lower())
    is_dom_ann = ("domestic" in audience.lower() and "international" not in audience.lower())
    is_pace_ann = (audience.lower() == "pace")

    if is_pace and not is_pace_ann and audience != "Global":
        frappe.throw("Announcement not available for your portal", frappe.PermissionError)
    elif not is_pace and is_pace_ann:
        frappe.throw("Announcement not available for your portal", frappe.PermissionError)
    elif resolved_portal == DOMESTIC and is_intl_ann:
        frappe.throw("Announcement not available for Domestic candidates", frappe.PermissionError)
    elif resolved_portal == INTERNATIONAL and is_dom_ann:
        frappe.throw("Announcement not available for International candidates", frappe.PermissionError)

    context.announcement = ann
    context.no_cache = 1
    context.title = ann.title

    user = frappe.session.user or "Guest"
    context.portal_user_logged_in = user != "Guest"
    context.announcement_id = ann.name
    # Opening an announcement marks it as read; the page offers "Mark as unread"
    if context.portal_user_logged_in:
        from slcm.admission.utils.web import set_portal_announcement_read
        set_portal_announcement_read(user, ann.name, True)

    context.sidebar_active = "announcements"

    # "Back" goes to the Announcements page when the NLSAT portal has it switched on
    # (for visitors too — the Announcements page is open without login)
    from slcm.admission.utils.portal import get_portal_sidebar_pages
    ann_page_on = not is_pace and bool(get_portal_sidebar_pages().get("announcements"))
    context.back_url = "/nlsat/announcements" if ann_page_on else ""

    # Logged-in candidates see the page inside the portal sidebar layout. Visitors get the
    # sidebar with only Announcements when that page is on, else no sidebar.
    context.hide_sidebar = not context.portal_user_logged_in and not ann_page_on
