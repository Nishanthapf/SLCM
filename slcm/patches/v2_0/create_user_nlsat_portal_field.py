"""
Create User.nlsat_portal (the NLSAT portal a candidate signed up on: Domestic / International).

The field is in fixtures/custom_field.json, but on sites without ERPNext migrate never reaches it:
Frappe imports that file as one unit and stops at the first record whose doctype is missing
(Quotation-crm_deal, an ERPNext/CRM field), skipping every record after it.

Without this field, a candidate who has not started an application is treated as Domestic
unless their browser still has the portal cookie, and pre-application emails use the
Domestic domain. See slcm.admission.utils.nlsat_portal.get_applicant_portal_type.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_field

# Same definition as "User-nlsat_portal" in fixtures/custom_field.json
NLSAT_PORTAL_FIELD = {
	"fieldname": "nlsat_portal",
	"label": "NLSAT Portal",
	"fieldtype": "Select",
	"options": "Domestic\nInternational",
	"insert_after": "last_pace_reminder_sent",
	"read_only": 0,
	"no_copy": 1,
	"description": "NLSAT portal the user signed up on. Links in emails sent before they start an application use this portal's domain.",
}


def execute():
	if frappe.db.exists("Custom Field", "User-nlsat_portal") and frappe.db.has_column("User", "nlsat_portal"):
		# Field already there (possibly created read-only earlier): the fixture can't update it
		# on non-ERPNext sites, so bring it in line with the definition here.
		frappe.db.set_value("Custom Field", "User-nlsat_portal", "read_only", NLSAT_PORTAL_FIELD["read_only"])
	else:
		create_custom_field("User", NLSAT_PORTAL_FIELD)
	frappe.clear_cache(doctype="User")
