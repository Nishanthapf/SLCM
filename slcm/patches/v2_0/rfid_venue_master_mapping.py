"""RFID attendance now uses Venue Master (the Time Table's venue) instead of Room.

`room` on RFID Device Room Mapping, Attendance Session and Student Attendance
changed its Link target from Room to Venue Master (fieldname unchanged). This
patch makes the existing data consistent with that:

1. Mappings whose `room` is not a Venue Master are deactivated (with a remark)
   so they can be remapped; they never matched a Time Table venue anyway.
2. Attendance Session.room: values that aren't a Venue Master are cleared,
   then every session is backfilled from its Time Table entry's venue.
3. Student Attendance.room is copied from its session.
4. RFID Device.device_type: blank -> Classroom; readers labelled GATE-* ->
   Entry Gate (their taps never count towards a class).

Safe to re-run.
"""

import frappe


def execute():
	_deactivate_non_venue_mappings()
	_backfill_session_venues()
	_backfill_student_attendance_venues()
	_set_device_types()


def _deactivate_non_venue_mappings():
	rows = frappe.db.sql("""
		SELECT m.name, m.room
		FROM `tabRFID Device Room Mapping` m
		LEFT JOIN `tabVenue Master` v ON v.name = m.room
		WHERE m.is_active = 1 AND v.name IS NULL
	""", as_dict=True)
	for row in rows:
		note = f"Deactivated by migration: '{row.room}' is a Room, not a Venue Master. Remap this device to a venue."
		frappe.db.sql("""
			UPDATE `tabRFID Device Room Mapping`
			SET is_active = 0,
				remarks = TRIM(CONCAT(IFNULL(remarks, ''), '\n', %s))
			WHERE name = %s
		""", (note, row.name))
	if rows:
		print(f"RFID venue patch: deactivated {len(rows)} mapping(s) pointing at Room records")


def _backfill_session_venues():
	frappe.db.sql("""
		UPDATE `tabAttendance Session` s
		LEFT JOIN `tabVenue Master` v ON v.name = s.room
		SET s.room = NULL
		WHERE IFNULL(s.room, '') != '' AND v.name IS NULL
	""")
	frappe.db.sql("""
		UPDATE `tabAttendance Session` s
		JOIN `tabTime Table` tt ON tt.name = s.class_schedule
		SET s.room = tt.venue
		WHERE IFNULL(s.room, '') = '' AND IFNULL(tt.venue, '') != ''
	""")


def _backfill_student_attendance_venues():
	frappe.db.sql("""
		UPDATE `tabStudent Attendance` sa
		JOIN `tabAttendance Session` s ON s.name = sa.attendance_session
		SET sa.room = s.room
		WHERE NOT (sa.room <=> s.room)
	""")
	# Rows not tied to a session can't have a venue; drop stale Room values.
	frappe.db.sql("""
		UPDATE `tabStudent Attendance` sa
		LEFT JOIN `tabVenue Master` v ON v.name = sa.room
		SET sa.room = NULL
		WHERE IFNULL(sa.room, '') != '' AND v.name IS NULL
	""")


def _set_device_types():
	frappe.db.sql("""
		UPDATE `tabRFID Device` SET device_type = 'Entry Gate'
		WHERE IFNULL(device_type, '') IN ('', 'Classroom') AND UPPER(IFNULL(location, '')) LIKE 'GATE%%'
		AND IFNULL(device_type, '') != 'Entry Gate'
	""")
	frappe.db.sql("""
		UPDATE `tabRFID Device` SET device_type = 'Classroom'
		WHERE IFNULL(device_type, '') = ''
	""")
