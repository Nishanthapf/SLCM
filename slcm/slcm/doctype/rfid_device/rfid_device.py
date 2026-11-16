# Copyright (c) 2026, Nishanth and contributors
# For license information, please see license.txt

from frappe.model.document import Document

from slcm.slcm.doctype.rfid_device_room_mapping.rfid_device_room_mapping import (
	get_active_rooms_for_device,
)


class RFIDDevice(Document):
	@property
	def current_venue(self):
		"""Virtual field: venue from today's active RFID Device Room Mapping."""
		if not self.name or self.is_new():
			return None
		venues = get_active_rooms_for_device(self.name)
		return venues[0] if venues else None
