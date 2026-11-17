# Copyright (c) 2026, TFSS and contributors
# For license information, please see license.txt

"""Sign-in rules of the unified /login page (slcm/utils/login_page.py, slcm/www/login.py).

Run:  bench --site <site> run-tests --module slcm.tests.test_login_page

Who an account is (staff / faculty / student / parent / nothing) is patched,
so no Faculty or Student Master records are needed and nothing is written.

Agreed rules (confirmed 2026-11-17):
  R1  Faculty/students may not use a password; on /login the page moves to the
      Faculty & Student tab. Staff who also hold such a record are exempt.
  R2  Signing in on a tab the account doesn't belong on (password or Google)
      is refused and the page moves to the account's own tab.
  R3  On /login, accounts with no staff/faculty/student/parent record are
      refused (applicants too).
  R4  Applicant login pages (NLSAT / PACE) keep password sign-in for
      applicants who have become students.
  R5  After signing in, users land on their own home; portal users only follow
      redirect-to inside their own portal.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from slcm.utils import login_page as lp

NOBODY = {"staff": False, "faculty": False, "student": False, "parent": False}


def kinds(*names):
	return {**NOBODY, **{n: True for n in names}}


class FakeRequest:
	def __init__(self, referer=""):
		self.headers = {"Referer": referer} if referer else {}
		self.path = "/api/method/login"


class LoginRulesTestCase(unittest.TestCase):
	def setUp(self):
		self._saved = {
			"form_dict": frappe.local.form_dict,
			"response": getattr(frappe.local, "response", None),
			"request": getattr(frappe.local, "request", None),
		}
		frappe.local.form_dict = frappe._dict()
		frappe.local.response = frappe._dict()
		frappe.local.request = FakeRequest()
		patcher = patch.object(lp, "google_enabled", return_value=True)
		self.google_enabled = patcher.start()
		self.addCleanup(patcher.stop)

	def tearDown(self):
		frappe.local.form_dict = self._saved["form_dict"]
		frappe.local.response = self._saved["response"]
		frappe.local.request = self._saved["request"]

	# helpers ---------------------------------------------------------------

	def password_sign_in(self, account, tab=None, referer=""):
		"""Run the on_login rule. Returns None (allowed) or (code, tab to show)."""
		frappe.local.form_dict = frappe._dict({lp.TAB_FIELD: tab} if tab else {})
		frappe.local.request = FakeRequest(referer)
		frappe.local.response = frappe._dict()
		with patch.object(lp, "get_account_kinds", return_value=account):
			try:
				lp.enforce_password_login_policy(SimpleNamespace(user="someone@example.com"))
			except lp.LoginNotAllowed:
				return frappe.local.response.get("login_code"), frappe.local.response.get("login_tab")
		return None


class TestPasswordSignInOnLoginPage(LoginRulesTestCase):
	"""Password sign-ins sent from /login (the page sends its tab)."""

	# --- right tab: allowed ---------------------------------------------------

	def test_staff_on_staff_tab_allowed(self):
		self.assertIsNone(self.password_sign_in(kinds("staff"), lp.TAB_STAFF))

	def test_parent_on_parent_tab_allowed(self):
		self.assertIsNone(self.password_sign_in(kinds("parent"), lp.TAB_PARENT))

	def test_staff_who_is_also_parent_on_either_tab_allowed(self):
		self.assertIsNone(self.password_sign_in(kinds("staff", "parent"), lp.TAB_STAFF))
		self.assertIsNone(self.password_sign_in(kinds("staff", "parent"), lp.TAB_PARENT))

	def test_staff_who_is_also_faculty_may_use_password_on_staff_tab(self):
		self.assertIsNone(self.password_sign_in(kinds("staff", "faculty"), lp.TAB_STAFF))

	# --- R1: faculty / students must use Google --------------------------------

	def test_student_on_staff_tab_moves_to_faculty_student(self):
		self.assertEqual(
			self.password_sign_in(kinds("student"), lp.TAB_STAFF), ("use_google", lp.TAB_FACULTY_STUDENT)
		)

	def test_faculty_on_staff_tab_moves_to_faculty_student(self):
		self.assertEqual(
			self.password_sign_in(kinds("faculty"), lp.TAB_STAFF), ("use_google", lp.TAB_FACULTY_STUDENT)
		)

	def test_student_on_parent_tab_moves_to_faculty_student(self):
		self.assertEqual(
			self.password_sign_in(kinds("student"), lp.TAB_PARENT), ("use_google", lp.TAB_FACULTY_STUDENT)
		)

	def test_student_who_is_also_parent_still_must_use_google(self):
		self.assertEqual(
			self.password_sign_in(kinds("student", "parent"), lp.TAB_PARENT),
			("use_google", lp.TAB_FACULTY_STUDENT),
		)

	def test_student_with_google_switched_off_is_told_sign_in_is_disabled(self):
		self.google_enabled.return_value = False
		self.assertEqual(
			self.password_sign_in(kinds("student"), lp.TAB_STAFF), ("student_disabled", lp.TAB_FACULTY_STUDENT)
		)

	# --- R2: wrong tab ----------------------------------------------------------

	def test_parent_on_staff_tab_moves_to_parent(self):
		self.assertEqual(
			self.password_sign_in(kinds("parent"), lp.TAB_STAFF), ("wrong_tab_parent", lp.TAB_PARENT)
		)

	def test_staff_on_parent_tab_moves_to_staff(self):
		self.assertEqual(
			self.password_sign_in(kinds("staff"), lp.TAB_PARENT), ("wrong_tab_staff", lp.TAB_STAFF)
		)

	# --- R3: no account -----------------------------------------------------------

	def test_no_account_on_staff_tab_refused(self):
		self.assertEqual(self.password_sign_in(NOBODY, lp.TAB_STAFF), ("no_account", lp.TAB_STAFF))

	def test_no_account_on_parent_tab_refused(self):
		self.assertEqual(self.password_sign_in(NOBODY, lp.TAB_PARENT), ("no_account", lp.TAB_PARENT))

	def test_unknown_tab_value_is_treated_as_no_tab(self):
		# A made-up slcm_tab is ignored: only the Google-only rule applies.
		self.assertIsNone(self.password_sign_in(NOBODY, "admin"))
		self.assertEqual(self.password_sign_in(kinds("student"), "admin"), ("use_google", lp.TAB_FACULTY_STUDENT))

	def test_refusal_message_is_readable(self):
		frappe.local.form_dict = frappe._dict({lp.TAB_FIELD: lp.TAB_STAFF})
		with patch.object(lp, "get_account_kinds", return_value=kinds("parent")):
			with self.assertRaises(lp.LoginNotAllowed) as ctx:
				lp.enforce_password_login_policy(SimpleNamespace(user="p@example.com"))
		self.assertIn("parent account", str(ctx.exception))


class TestPasswordSignInElsewhere(LoginRulesTestCase):
	"""Password sign-ins that don't come from /login (no tab sent)."""

	def test_applicant_login_page_lets_converted_student_in(self):
		for path in lp.ADMISSION_LOGIN_PATHS:
			with self.subTest(path=path):
				self.assertIsNone(
					self.password_sign_in(kinds("student"), referer=f"https://site.example{path}?redirect-to=/x")
				)

	def test_applicant_with_no_record_can_use_applicant_login(self):
		self.assertIsNone(self.password_sign_in(NOBODY, referer="https://site.example/nlsatadmissions/login"))

	def test_other_pages_still_enforce_google_only_for_students(self):
		self.assertEqual(
			self.password_sign_in(kinds("student"), referer="https://site.example/some-page"),
			("use_google", lp.TAB_FACULTY_STUDENT),
		)

	def test_admission_page_lookalike_path_is_not_exempt(self):
		self.assertEqual(
			self.password_sign_in(kinds("faculty"), referer="https://site.example/nlsatadmissions/login-help"),
			("use_google", lp.TAB_FACULTY_STUDENT),
		)

	def test_api_sign_in_without_tab_for_staff_and_parent_allowed(self):
		self.assertIsNone(self.password_sign_in(kinds("staff")))
		self.assertIsNone(self.password_sign_in(kinds("parent")))

	def test_administrator_and_google_requests_are_skipped(self):
		with patch.object(lp, "get_account_kinds", return_value=kinds("student")):
			lp.enforce_password_login_policy(SimpleNamespace(user="Administrator"))
			with patch.object(lp, "_is_google_request", return_value=True):
				lp.enforce_password_login_policy(SimpleNamespace(user="s@example.com"))


class TestTabMatching(unittest.TestCase):
	"""check_tab: used for both password and Google sign-ins (R2, R3)."""

	CASES = [
		# account,                       tab used,                  expected
		(kinds("staff"), lp.TAB_STAFF, None),
		(kinds("staff"), lp.TAB_FACULTY_STUDENT, ("wrong_tab_staff", lp.TAB_STAFF)),
		(kinds("staff"), lp.TAB_PARENT, ("wrong_tab_staff", lp.TAB_STAFF)),
		(kinds("faculty"), lp.TAB_FACULTY_STUDENT, None),
		(kinds("faculty"), lp.TAB_STAFF, ("wrong_tab_faculty-student", lp.TAB_FACULTY_STUDENT)),
		(kinds("student"), lp.TAB_STAFF, ("wrong_tab_faculty-student", lp.TAB_FACULTY_STUDENT)),
		(kinds("student"), lp.TAB_PARENT, ("wrong_tab_faculty-student", lp.TAB_FACULTY_STUDENT)),
		(kinds("parent"), lp.TAB_PARENT, None),
		(kinds("parent"), lp.TAB_STAFF, ("wrong_tab_parent", lp.TAB_PARENT)),
		(kinds("parent"), lp.TAB_FACULTY_STUDENT, ("wrong_tab_parent", lp.TAB_PARENT)),
		(kinds("staff", "faculty"), lp.TAB_STAFF, None),
		(kinds("staff", "faculty"), lp.TAB_FACULTY_STUDENT, None),
		(kinds("staff", "faculty"), lp.TAB_PARENT, ("wrong_tab_faculty-student", lp.TAB_FACULTY_STUDENT)),
		(kinds("faculty", "parent"), lp.TAB_PARENT, None),
		(NOBODY, lp.TAB_STAFF, ("no_account", lp.TAB_STAFF)),
		(NOBODY, lp.TAB_FACULTY_STUDENT, ("no_account", lp.TAB_FACULTY_STUDENT)),
	]

	def test_matrix(self):
		for account, tab, expected in self.CASES:
			with self.subTest(account=[k for k, v in account.items() if v], tab=tab):
				self.assertEqual(lp.check_tab(account, tab), expected)

	def test_every_code_has_its_own_message(self):
		default = lp.get_error_message("anything-else")
		for code in (
			"wrong_tab_staff",
			"wrong_tab_faculty-student",
			"wrong_tab_parent",
			"no_account",
			"use_google",
			"faculty_disabled",
			"student_disabled",
			"parent_disabled",
		):
			with self.subTest(code=code):
				self.assertNotEqual(lp.get_error_message(code), default)


class TestGoogleSignInTab(unittest.TestCase):
	"""After Google, /login checks the tab once per new session (R2, R3)."""

	SID = "test-sid-login-page"

	def setUp(self):
		self._session = frappe.local.session
		frappe.local.session = frappe._dict({"sid": self.SID, "user": "g@example.com", "data": frappe._dict()})
		self.key = lp.GOOGLE_TAB_CHECK_KEY + self.SID

	def tearDown(self):
		frappe.cache.delete_value(self.key)
		frappe.local.session = self._session

	def check(self, account, tab):
		with patch.object(lp, "get_account_kinds", return_value=account):
			return lp.check_google_sign_in_tab("g@example.com", tab)

	def test_student_via_google_on_staff_tab_is_sent_to_faculty_student(self):
		frappe.cache.set_value(self.key, 1)
		self.assertEqual(self.check(kinds("student"), lp.TAB_STAFF), ("wrong_tab_faculty-student", lp.TAB_FACULTY_STUDENT))

	def test_faculty_via_google_on_right_tab_is_fine(self):
		frappe.cache.set_value(self.key, 1)
		self.assertIsNone(self.check(kinds("faculty"), lp.TAB_FACULTY_STUDENT))

	def test_staff_via_google_on_faculty_tab_is_sent_to_staff(self):
		frappe.cache.set_value(self.key, 1)
		self.assertEqual(self.check(kinds("staff"), lp.TAB_FACULTY_STUDENT), ("wrong_tab_staff", lp.TAB_STAFF))

	def test_checked_only_once(self):
		frappe.cache.set_value(self.key, 1)
		self.assertIsNotNone(self.check(kinds("student"), lp.TAB_STAFF))
		self.assertIsNone(self.check(kinds("student"), lp.TAB_STAFF))

	def test_not_a_fresh_google_session_is_not_checked(self):
		# e.g. a signed-in student opening /login?tab=staff later: just sent home.
		self.assertIsNone(self.check(kinds("student"), lp.TAB_STAFF))


class TestLandingPage(unittest.TestCase):
	"""R5: where /login sends a signed-in user."""

	def land(self, account, tab, redirect_to=""):
		with patch.object(lp, "get_account_kinds", return_value=account):
			return lp.get_landing_page("u@example.com", tab, redirect_to)

	def test_homes(self):
		self.assertEqual(self.land(kinds("staff"), lp.TAB_STAFF), "/desk")
		self.assertEqual(self.land(kinds("faculty"), lp.TAB_FACULTY_STUDENT), "/faculty-portal")
		self.assertEqual(self.land(kinds("student"), lp.TAB_FACULTY_STUDENT), "/student-portal")
		self.assertEqual(self.land(kinds("parent"), lp.TAB_PARENT), "/parent-portal")
		self.assertIsNone(self.land(NOBODY, lp.TAB_STAFF))

	def test_tab_decides_for_multi_role_accounts(self):
		both = kinds("staff", "faculty")
		self.assertEqual(self.land(both, lp.TAB_STAFF), "/desk")
		self.assertEqual(self.land(both, lp.TAB_FACULTY_STUDENT), "/faculty-portal")
		self.assertEqual(self.land(kinds("staff", "parent"), lp.TAB_PARENT), "/parent-portal")

	def test_redirect_to_inside_own_portal_is_followed(self):
		self.assertEqual(
			self.land(kinds("student"), lp.TAB_FACULTY_STUDENT, "/student-portal/fees"), "/student-portal/fees"
		)

	def test_redirect_to_outside_own_portal_is_ignored(self):
		self.assertEqual(self.land(kinds("student"), lp.TAB_FACULTY_STUDENT, "/desk"), "/student-portal")
		self.assertEqual(self.land(kinds("student"), lp.TAB_FACULTY_STUDENT, "/faculty-portal"), "/student-portal")
		self.assertEqual(self.land(kinds("parent"), lp.TAB_PARENT, "/student-portal-evil"), "/parent-portal")

	def test_staff_follow_redirect_to(self):
		self.assertEqual(self.land(kinds("staff"), lp.TAB_STAFF, "/desk/student-master"), "/desk/student-master")

	def test_redirect_to_login_or_offsite_is_ignored(self):
		self.assertEqual(self.land(kinds("staff"), lp.TAB_STAFF, "/login?tab=parent"), "/desk")
		self.assertEqual(self.land(kinds("staff"), lp.TAB_STAFF, "https://evil.example/x"), "/desk")
