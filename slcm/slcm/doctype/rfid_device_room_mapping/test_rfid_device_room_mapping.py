# Copyright (c) 2026, Nishanth and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase

from slcm.slcm.doctype.rfid_device_room_mapping.rfid_device_room_mapping import (
	get_active_rooms_for_device,
	get_devices_for_venue,
)


EXTRA_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]
IGNORE_TEST_RECORD_DEPENDENCIES = []  # eg. ["User"]


def _venue(name):
	if not frappe.db.exists("Venue Master", name):
		doc = frappe.get_doc({
			"doctype": "Venue Master",
			"venue_name_or_number": name,
			"venue_type": "Classroom",
			"capacity": 10,
		})
		doc.flags.ignore_mandatory = True
		doc.flags.ignore_links = True
		doc.insert(ignore_permissions=True)
	return name


def _device(device_id):
	if not frappe.db.exists("RFID Device", device_id):
		frappe.get_doc({"doctype": "RFID Device", "device_id": device_id}).insert(ignore_permissions=True)
	return device_id


def _mapping(device, venue, start, end=None):
	return frappe.get_doc({
		"doctype": "RFID Device Room Mapping",
		"device": device,
		"room": venue,
		"effective_from": start,
		"effective_to": end,
	}).insert(ignore_permissions=True)


class TestRFIDDeviceRoomMapping(IntegrationTestCase):
	def test_overlap_blocks_same_device_any_venue(self):
		device = _device("TEST-DEVICE-001")
		_mapping(device, _venue("TEST-VENUE-001"), "2026-01-01")

		# Same venue, overlapping
		with self.assertRaises(frappe.ValidationError):
			_mapping(device, "TEST-VENUE-001", "2026-02-01")
		# Different venue, overlapping — a reader can't be in two places
		with self.assertRaises(frappe.ValidationError):
			_mapping(device, _venue("TEST-VENUE-002"), "2026-02-01")

	def test_moved_device_resolves_by_date(self):
		device = _device("TEST-DEVICE-002")
		_mapping(device, _venue("TEST-VENUE-001"), "2026-01-01", "2026-01-31")
		_mapping(device, _venue("TEST-VENUE-002"), "2026-02-01")

		self.assertEqual(get_active_rooms_for_device(device, "2026-01-15"), ["TEST-VENUE-001"])
		self.assertEqual(get_active_rooms_for_device(device, "2026-03-01"), ["TEST-VENUE-002"])
		self.assertEqual(get_active_rooms_for_device(device, "2025-12-31"), [])
		self.assertIn(device, get_devices_for_venue("TEST-VENUE-002", "2026-03-01"))
		self.assertNotIn(device, get_devices_for_venue("TEST-VENUE-001", "2026-03-01"))

	def test_blank_effective_from_defaults_to_today(self):
		device = _device("TEST-DEVICE-003")
		doc = _mapping(device, _venue("TEST-VENUE-003"), None)
		self.assertTrue(doc.effective_from)
		self.assertEqual(get_active_rooms_for_device(device), ["TEST-VENUE-003"])
