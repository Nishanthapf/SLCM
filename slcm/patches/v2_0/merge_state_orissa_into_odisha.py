# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

"""
The State master holds both 'Orissa' (old name) and 'Odisha'. Only 'Odisha'
is in the State fixture. Merge 'Orissa' into 'Odisha' with
frappe.rename_doc(merge=True), which repoints every Link field that uses
'Orissa' before deleting the duplicate.
"""

import frappe


def execute():
	if not frappe.db.exists("State", "Orissa"):
		return

	if frappe.db.exists("State", "Odisha"):
		frappe.rename_doc("State", "Orissa", "Odisha", merge=True, force=True, show_alert=False)
	else:
		frappe.rename_doc("State", "Orissa", "Odisha", force=True, show_alert=False)
		frappe.db.set_value("State", "Odisha", "state_name", "Odisha")
