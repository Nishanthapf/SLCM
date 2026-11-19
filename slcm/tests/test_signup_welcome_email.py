"""Welcome / sign-up email on new users.

- Google (SSO) sign-up: no email of any kind.
- User added from the desk with "Send Welcome Email" ticked: the email is sent.
- Ticked off: no email.

Run: bench --site <site> run-tests --module slcm.tests.test_signup_welcome_email
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.utils.oauth import update_oauth_user

SSO_USER = "zz-sso-signup@example.com"
DESK_USER = "zz-desk-welcome@example.com"


class TestSignupWelcomeEmail(unittest.TestCase):
	def setUp(self):
		self.cleanup()
		real_get_single = frappe.get_single

		def get_single(doctype, *a, **k):
			doc = real_get_single(doctype, *a, **k)
			if doctype == "Institution Settings":
				doc.enable_signup_email = 1  # the setting that turns on the custom sign-up email
			return doc

		patches = [
			patch("slcm.api.user_events.frappe.get_single", side_effect=get_single),
			patch("slcm.api.user_events.frappe.sendmail"),  # slcm's sign-up email
			patch("frappe.core.doctype.user.user.User.send_welcome_mail_to_user"),  # Frappe's own
		]
		self.mocks = [p.start() for p in patches]
		self.sendmail, self.frappe_welcome = self.mocks[1], self.mocks[2]
		for p in patches:
			self.addCleanup(p.stop)
		self.addCleanup(self.cleanup)

	def cleanup(self):
		for user in (SSO_USER, DESK_USER):
			if frappe.db.exists("User", user):
				frappe.delete_doc("User", user, ignore_permissions=True, force=True)

	def emails_sent(self):
		return self.sendmail.call_count + self.frappe_welcome.call_count

	def test_google_sign_up_sends_no_email(self):
		data = {"id": "zz-google-id-1", "email": SSO_USER, "given_name": "ZZ", "family_name": "SSO"}
		with patch("frappe.integrations.doctype.social_login_key.social_login_key.provider_allows_signup", return_value=True):
			update_oauth_user(SSO_USER, data, "google")
		self.assertTrue(frappe.db.exists("User", SSO_USER))
		self.assertEqual(self.emails_sent(), 0)
		self.assertEqual(frappe.db.get_value("User", SSO_USER, "send_welcome_email"), 0)

	def test_desk_user_with_box_ticked_gets_email(self):
		frappe.get_doc(
			{"doctype": "User", "email": DESK_USER, "first_name": "ZZ", "user_type": "Website User", "send_welcome_email": 1}
		).insert(ignore_permissions=True)
		self.assertEqual(self.emails_sent(), 1)

	def test_desk_user_with_box_unticked_gets_no_email(self):
		frappe.get_doc(
			{"doctype": "User", "email": DESK_USER, "first_name": "ZZ", "user_type": "Website User", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
		self.assertEqual(self.emails_sent(), 0)
