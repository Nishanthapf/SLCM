"""Fee Component groups shared by Fee Demand (one per student per Academic Year) and the
fee certificates (row order and "– per annum" labels).

Groups are matched on keywords in the Fee Component name and its component_type,
because sites name their types differently (e.g. "Tuition Fee" vs "Tuition and
Facilities Fee", "Hostel Fee" vs "Housing Fee")."""

ADMISSION, READMISSION, TUITION, HOUSING, REFUNDABLE, OTHER = range(6)

GROUP_LABELS = {
	ADMISSION: "Admission Fee",
	READMISSION: "Re-admission Fee",
	TUITION: "Tuition and Facilities Fee",
	HOUSING: "Housing Fee",
	REFUNDABLE: "Student Refundable Deposit",
}

# Charged at most once per student per Academic Year.
ONCE_PER_YEAR_GROUPS = {ADMISSION, READMISSION, TUITION, HOUSING, REFUNDABLE}


def component_group(component, component_type=None):
	"""ADMISSION / READMISSION / TUITION / HOUSING / REFUNDABLE / OTHER."""
	text = f"{component or ''} {component_type or ''}".lower()
	if "re-admission" in text or "readmission" in text or "re admission" in text:
		return READMISSION
	if "admission" in text:
		return ADMISSION
	if "tuition" in text and "registration" not in text:
		return TUITION
	if "hostel" in text or "housing" in text:
		return HOUSING
	if "refundable" in text or "deposit" in text:
		return REFUNDABLE
	return OTHER
