"""Hostel allocation 2026-27 (VC office list, 13 Nov) -> Hostel / Hostel Room / Hostel Bed masters + Student Master.

NOTHING IS IMPORTED. Reads the sheet and the database, writes Data Import files + a report, then dry-validates
the files with Frappe's own Data Import parser and document validators (no save, rollback at the end).

Decisions (confirmed with the user):
  * Hostel names = names used in the VC office sheet (old Student Master link names are replaced).
  * Direct update of Student Master (no Hostel Allocation records -> no Housing & Mess fee demands).
  * The sheet wins over an existing hostel / room on Student Master (old -> new listed in the report).
  * Room-code suffix letter (P / A) is unknown -> full office code kept as bed_no and listed in the report.

Run:  bench --site <site> execute slcm.scratch.hostel_mapping.run
      bench --site <site> execute slcm.scratch.hostel_mapping.run --kwargs "{'base': '<Admissions Data path>', 'tag': 'production'}"
"""
import os
import re
from collections import Counter, OrderedDict, defaultdict

import frappe
import pandas as pd

from slcm.scratch.admissions_mapping import clean, name_overlap, name_tokens, strong_name_match

DT = "Student Master"
SRC = "Hostel wise list of students 2026-27_13Nov_VCoffice.xlsx"
COLS = ["sr", "code", "room", "hostel", "type", "email", "sid", "name", "prog", "batch", "gender", "room2"]
PAT = re.compile(r"^([A-Z]+)(\d+)([A-Z])(\d)([A-Z]?)$")
FILES = OrderedDict([
	("H1_Hostel_Insert.xlsx", ("Hostel", "Insert New Records")),
	("H1b_Hostel_Update.xlsx", ("Hostel", "Update Existing Records")),
	("H2_Hostel_Room_Insert.xlsx", ("Hostel Room", "Insert New Records")),
	("H2b_Hostel_Room_Update.xlsx", ("Hostel Room", "Update Existing Records")),
	("H3_Hostel_Bed_Insert.xlsx", ("Hostel Bed", "Insert New Records")),
	("H3b_Hostel_Bed_Update.xlsx", ("Hostel Bed", "Update Existing Records")),
	("H4_Student_Master_Hostel_Update.xlsx", (DT, "Update Existing Records")),
])
SM_FIELDS = ["hostel", "hostel_block", "floor", "hostel_room", "hostel_bed", "campus", "is_hosteller", "hostel_status"]


def H(dt, fn):
	return f"{frappe.get_meta(dt).get_label(fn).strip()} ({fn})"


def floor_of(rn):
	return rn[0] if len(rn) == 3 else str(int(rn) // 100)


def run(base=None, tag="local"):
	base = base or os.path.realpath(os.path.join(frappe.get_app_path("slcm"), "..", "docs", "Admissions Data"))
	out_dir = os.path.join(base, "output", tag)
	os.makedirs(out_dir, exist_ok=True)

	raw = pd.read_excel(os.path.join(base, SRC), header=0, dtype=str).iloc[:, 1:]
	raw.columns = COLS
	rows = []
	for i, r in raw.iterrows():
		r = {k: clean(r[k]) for k in COLS}
		if not (r["email"] or r["sid"] or r["room"]):
			continue
		r["excel_row"] = i + 2
		rows.append(r)

	# ---------------- Student Master snapshot + indexes
	sms = frappe.get_all(DT, fields=["name", "first_name", "official_email_id", "email", "registration_id", "gender", "batch",
		"programme_of_study", "student_status", "needs_accommodation"] + SM_FIELDS, limit_page_length=0)
	smap = {s.name: s for s in sms}
	by_mail, by_sid, by_nb = defaultdict(set), defaultdict(set), defaultdict(set)
	for s in sms:
		for e in (s.official_email_id, s.email):
			if (e or "").strip():
				by_mail[e.strip().lower()].add(s.name)
		if s.registration_id:
			by_sid[re.sub(r"\s", "", s.registration_id).upper()].add(s.name)
		by_nb[(" ".join(sorted(name_tokens(s.first_name))), str(s.batch or ""))].add(s.name)

	# ---------------- parse rooms, build hostel / room / bed model
	hostels = OrderedDict()   # sheet hostel name -> info
	rooms = OrderedDict()     # (hostel, room_number) -> info
	data_checks, held = [], []
	suffix_rows = Counter()
	for r in rows:
		m = PAT.match(r["room"])
		if not m:
			data_checks.append(OrderedDict(excel_row=r["excel_row"], student_id=r["sid"], name=r["name"], check="Room code not parseable", sheet_value=r["room"], student_master_value="", action="Not imported"))
			r["skip"] = "Room code not parseable"
			continue
		pre, rn, bed, cap, suf = m.groups()
		r.update(prefix=pre, rn=rn, bed_letter=bed, cap=int(cap), suffix=suf)
		code = r["code"] or pre
		if r["code"] and r["code"] != pre:
			data_checks.append(OrderedDict(excel_row=r["excel_row"], student_id=r["sid"], name=r["name"], check="Hostel code differs from room prefix", sheet_value=f'{r["code"]} / {r["room"]}', student_master_value="", action="Room prefix used"))
		h = hostels.setdefault(r["hostel"], OrderedDict(hostel_name=r["hostel"], code=code, code_from_sheet=bool(r["code"]), type=r["type"],
			hostel_type="Girls" if r["type"].lower().startswith("women") else "Boys",
			campus="Off Campus" if "off campus" in r["type"].lower() else "On Campus"))
		if suf:
			suffix_rows[(r["hostel"], suf)] += 1
		key = (r["hostel"], rn)
		ro = rooms.setdefault(key, OrderedDict(hostel=r["hostel"], room_number=rn, floor=floor_of(rn), capacity=0, suffix=suf, letters=set(), codes={}))
		idx = ord(bed) - 64
		ro["capacity"] = max(ro["capacity"], int(cap), idx)
		ro["letters"].add(bed)
		ro["codes"][bed] = r["room"]
		if ro["suffix"] != suf:
			data_checks.append(OrderedDict(excel_row=r["excel_row"], student_id=r["sid"], name=r["name"], check="Different suffix inside one room", sheet_value=r["room"], student_master_value="", action="Kept as-is in bed code"))
		if r["room2"] and r["room2"] != r["room"]:
			r["skip"] = "Room code column and last column disagree"
			data_checks.append(OrderedDict(excel_row=r["excel_row"], student_id=r["sid"], name=r["name"], check="'room code' column vs last (unnamed) column differ", sheet_value=f'{r["room"]} vs {r["room2"]}', student_master_value="", action="HELD - not imported; confirm the correct room"))
	for (hn, rn), ro in rooms.items():
		ex = next(iter(ro["codes"].values()))
		pre, _rn, _b, cap, suf = PAT.match(ex).groups()
		ro["beds"] = OrderedDict()
		for k in range(ro["capacity"]):
			L = chr(65 + k)
			ro["beds"][L] = ro["codes"].get(L) or f"{pre}{rn}{L}{ro['capacity'] if int(cap) != ro['capacity'] else cap}{suf}"
		ro["name"] = f"{hn}-{rn}"

	# ---------------- match students
	match_rows, assigned, changes = [], {}, []
	used = defaultdict(list)
	for r in rows:
		mail = r["email"].lower()
		sid = re.sub(r"\s", "", r["sid"]).upper()
		a, b = by_mail.get(mail, set()), by_sid.get(sid, set())
		cand, method, conf, note = None, "", "", ""
		if len(a) == 1 and len(b) == 1 and a != b:
			method, conf, note = "Email / Student ID conflict", "Review", f"email -> {next(iter(a))}, student id -> {next(iter(b))}"
		elif len(a) == 1:
			cand, method, conf = next(iter(a)), "Official Email", "High"
		elif len(b) == 1:
			cand, method, conf = next(iter(b)), "Student ID", "High"
		elif len(a) > 1 or len(b) > 1:
			method, conf, note = "Ambiguous (several students share email / ID)", "Review", ", ".join(sorted(a | b))
		else:
			nb = by_nb.get((" ".join(sorted(name_tokens(r["name"]))), r["batch"]), set())
			if len(nb) == 1:
				cand, method, conf = next(iter(nb)), "Exact name + batch", "Medium"
			else:
				method, conf = "UNMATCHED", ""
		s = smap.get(cand) if cand else None
		if s and conf == "High" and not strong_name_match(r["name"], s.first_name) and name_overlap(r["name"], s.first_name) == 0:
			conf, note = "Review", f"name mismatch: sheet '{r['name']}' vs Student Master '{s.first_name}'"
		if s and r.get("skip"):
			conf, note = "Review", r["skip"]
		if not s and r.get("skip"):
			note = r["skip"]
		mr = OrderedDict(excel_row=r["excel_row"], hostel=r["hostel"], room_code=r["room"], student_id=r["sid"], email=r["email"], name=r["name"],
			programme=r["prog"], batch=r["batch"], match_method=method, confidence=conf, student_master=cand if s else "",
			sm_name=s.first_name if s else "", sm_student_id=s.registration_id if s else "", sm_status=s.student_status if s else "", note=note)
		match_rows.append(mr)
		if s:
			used[cand].append(r["excel_row"])
		if s and conf in ("High", "Medium"):
			assigned[cand] = r
	for cand, ex_rows in used.items():
		if len(ex_rows) > 1:
			for mr in match_rows:
				if mr["student_master"] == cand:
					mr["confidence"], mr["note"] = "Review", f"same student on rows {ex_rows}"
			assigned.pop(cand, None)

	# ---------------- per-student checks
	for cand, r in assigned.items():
		s = smap[cand]
		g = (s.gender or "").lower()
		if r["gender"] and g and r["gender"].lower() != g and not (g.startswith("other") and r["gender"].lower().startswith("other")):
			data_checks.append(OrderedDict(excel_row=r["excel_row"], student_id=r["sid"], name=r["name"], check="Gender differs", sheet_value=r["gender"], student_master_value=s.gender, action="Imported (gender not changed)"))
		ht = hostels[r["hostel"]]["hostel_type"]
		if r["gender"].lower() in ("male", "female") and ((ht == "Girls") != (r["gender"].lower() == "female")):
			data_checks.append(OrderedDict(excel_row=r["excel_row"], student_id=r["sid"], name=r["name"], check=f"Gender vs hostel type ({ht})", sheet_value=r["gender"], student_master_value=s.gender, action="Imported - verify"))
		if r["batch"] and s.batch and r["batch"] not in str(s.batch):
			data_checks.append(OrderedDict(excel_row=r["excel_row"], student_id=r["sid"], name=r["name"], check="Batch differs", sheet_value=r["batch"], student_master_value=s.batch, action="Imported (batch not changed)"))
		if s.student_status and s.student_status not in ("Active", "Enrolled", "Registered"):
			data_checks.append(OrderedDict(excel_row=r["excel_row"], student_id=r["sid"], name=r["name"], check="Student status is not active", sheet_value="in hostel list", student_master_value=s.student_status, action="Imported - verify"))

	# ---------------- existing masters
	ex_h = {d.name: d for d in frappe.get_all("Hostel", fields=["name", "hostel_code", "hostel_type", "total_rooms", "total_capacity"], limit_page_length=0)}
	ex_r = {d.name: d for d in frappe.get_all("Hostel Room", fields=["name", "hostel", "room_number", "floor", "capacity", "occupied", "is_available"], limit_page_length=0)}
	ex_b = {d.name: d for d in frappe.get_all("Hostel Bed", fields=["name", "room", "bed_no", "is_occupied", "hostel"], limit_page_length=0)}
	codes_in_db = {d.hostel_code: d.name for d in ex_h.values() if d.hostel_code}
	master_notes = []

	occupied_bed = {}  # bed name -> student
	for cand, r in assigned.items():
		ro = rooms[(r["hostel"], r["rn"])]
		occupied_bed[f"BED-{ro['name']}-{r['room']}"] = cand

	h_ins, h_upd, r_ins, r_upd, b_ins, b_upd = [], [], [], [], [], []
	hostel_list, room_list = [], []
	for hn, h in hostels.items():
		hr = [ro for (x, _), ro in rooms.items() if x == hn]
		h["total_rooms"] = len(hr)
		h["total_capacity"] = sum(ro["capacity"] for ro in hr)
		h["listed"] = sum(len(ro["letters"]) for ro in hr)
		h["linked"] = sum(1 for c, r in assigned.items() if r["hostel"] == hn)
		code = h["code"]
		if code in codes_in_db and codes_in_db[code] != hn:
			master_notes.append(OrderedDict(doctype="Hostel", record=hn, issue=f"hostel_code {code} already used by '{codes_in_db[code]}'", action="code left blank"))
			code = ""
		if hn in ex_h:
			e = ex_h[hn]
			# Hostel is named by field:hostel_name, so that column is the ID for Update Existing Records
			row = OrderedDict([(H("Hostel", "hostel_name"), hn), (H("Hostel", "hostel_type"), h["hostel_type"]), (H("Hostel", "total_rooms"), h["total_rooms"]), (H("Hostel", "total_capacity"), h["total_capacity"])])
			if not e.hostel_code and code:
				row[H("Hostel", "hostel_code")] = code
			elif e.hostel_code and e.hostel_code != h["code"]:
				master_notes.append(OrderedDict(doctype="Hostel", record=hn, issue=f"existing hostel_code '{e.hostel_code}' vs sheet room prefix '{h['code']}'", action="existing code kept"))
			h_upd.append(row)
			h["status"] = "Exists - totals updated"
		else:
			h_ins.append(OrderedDict([(H("Hostel", "hostel_name"), hn), (H("Hostel", "hostel_code"), code), (H("Hostel", "hostel_type"), h["hostel_type"]),
				(H("Hostel", "total_rooms"), h["total_rooms"]), (H("Hostel", "total_capacity"), h["total_capacity"])]))
			h["status"] = "New"
		hostel_list.append(OrderedDict(hostel=hn, code=h["code"], type_in_sheet=h["type"], hostel_type=h["hostel_type"], campus=h["campus"],
			rooms=h["total_rooms"], beds_capacity=h["total_capacity"], students_in_sheet=h["listed"], students_linked=h["linked"],
			vacant_beds=h["total_capacity"] - h["listed"], master_status=h["status"],
			suffixes=", ".join(f"{s}:{n}" for (x, s), n in sorted(suffix_rows.items()) if x == hn)))

		for ro in hr:
			occ = sum(1 for L, bc in ro["beds"].items() if f"BED-{ro['name']}-{bc}" in occupied_bed)
			avail = 1 if occ < ro["capacity"] else 0
			if ro["name"] in ex_r:
				e = ex_r[ro["name"]]
				r_upd.append(OrderedDict([("ID", ro["name"]), (H("Hostel Room", "floor"), ro["floor"]), (H("Hostel Room", "capacity"), ro["capacity"]),
					(H("Hostel Room", "occupied"), occ), (H("Hostel Room", "is_available"), avail)]))
				if int(e.capacity or 0) != ro["capacity"]:
					master_notes.append(OrderedDict(doctype="Hostel Room", record=ro["name"], issue=f"capacity {e.capacity} in DB vs {ro['capacity']} from room code", action="sheet value used"))
				rstat = "Exists - updated"
			else:
				r_ins.append(OrderedDict([(H("Hostel Room", "hostel"), hn), (H("Hostel Room", "room_number"), ro["room_number"]), (H("Hostel Room", "floor"), ro["floor"]),
					(H("Hostel Room", "capacity"), ro["capacity"]), (H("Hostel Room", "occupied"), occ), (H("Hostel Room", "is_available"), avail)]))
				rstat = "New"
			occupants = []
			for L, bc in ro["beds"].items():
				bname = f"BED-{ro['name']}-{bc}"
				st = occupied_bed.get(bname)
				sheet_r = next((r for r in rows if r.get("room") == bc), None)
				occupants.append(f"{L}: {smap[st].registration_id or st if st else ('(' + sheet_r['sid'] + ' not linked)' if sheet_r else 'vacant')}")
				if bname in ex_b:
					b_upd.append(OrderedDict([("ID", bname), (H("Hostel Bed", "is_occupied"), 1 if st else 0)]))
				else:
					b_ins.append(OrderedDict([(H("Hostel Bed", "room"), ro["name"]), (H("Hostel Bed", "bed_no"), bc), (H("Hostel Bed", "hostel"), hn),
						(H("Hostel Bed", "is_occupied"), 1 if st else 0)]))
			room_list.append(OrderedDict(hostel=hn, room=ro["name"], room_number=ro["room_number"], floor=ro["floor"], capacity=ro["capacity"],
				listed_in_sheet=len(ro["letters"]), occupied_linked=occ, vacant=ro["capacity"] - occ, suffix=ro["suffix"],
				bed_codes=", ".join(ro["beds"].values()), occupants=" | ".join(occupants), master_status=rstat))

	sheet_rooms = {ro["name"] for ro in rooms.values()}
	sheet_beds = {f"BED-{ro['name']}-{bc}" for ro in rooms.values() for bc in ro["beds"].values()}
	for n, e in ex_r.items():
		if n not in sheet_rooms:
			master_notes.append(OrderedDict(doctype="Hostel Room", record=n, issue="existing room not in the 13-Nov list", action="left unchanged"))
	for n, e in ex_b.items():
		if n not in sheet_beds:
			master_notes.append(OrderedDict(doctype="Hostel Bed", record=n, issue=f"existing bed (bed_no {e.bed_no}) not in the 13-Nov list", action="left unchanged"))
	for n in ex_h:
		if n not in hostels:
			master_notes.append(OrderedDict(doctype="Hostel", record=n, issue="existing hostel not in the 13-Nov list", action="left unchanged"))

	# ---------------- Student Master update
	sm_out = []
	for cand, r in sorted(assigned.items()):
		s, ro, h = smap[cand], rooms[(r["hostel"], r["rn"])], hostels[r["hostel"]]
		new = OrderedDict(hostel=r["hostel"], hostel_block=r["hostel"], floor=ro["floor"], hostel_room=ro["name"],
			hostel_bed=f"BED-{ro['name']}-{r['room']}", campus=h["campus"], is_hosteller=1, hostel_status="Allocated")
		old_vals = {k: s.get(k) for k in new}
		if any(str(old_vals[k] or "") not in ("", "0") for k in ("hostel", "hostel_room", "hostel_bed")):
			if str(old_vals["hostel_room"] or "") != new["hostel_room"] or str(old_vals["hostel"] or "") != new["hostel"]:
				changes.append(OrderedDict(student_master=cand, student_id=s.registration_id, name=s.first_name, old_hostel=s.hostel or "", old_room=s.hostel_room or "",
					old_bed=s.hostel_bed or "", new_hostel=new["hostel"], new_room=new["hostel_room"], new_bed=new["hostel_bed"]))
		o = OrderedDict(ID=cand)
		for k, v in new.items():
			o[H(DT, k)] = v
		sm_out.append(o)

	stale = []
	for s in sms:
		if s.name in assigned:
			continue
		if s.hostel or s.hostel_room or s.hostel_bed or s.is_hosteller:
			stale.append(OrderedDict(student_master=s.name, student_id=s.registration_id, name=s.first_name, batch=s.batch, status=s.student_status,
				is_hosteller=s.is_hosteller, hostel=s.hostel or "", hostel_room=s.hostel_room or "", hostel_bed=s.hostel_bed or "",
				hostel_exists=("" if not s.hostel else ("Yes" if s.hostel in ex_h or s.hostel in hostels else "NO - broken link")),
				room_exists=("" if not s.hostel_room else ("Yes" if s.hostel_room in ex_r or s.hostel_room in sheet_rooms else "NO - broken link"))))

	# ---------------- write import files
	def write_import(fname, data):
		p = os.path.join(out_dir, fname)
		if not data:
			if os.path.exists(p):
				os.remove(p)
			return None
		df = pd.DataFrame(data)
		sheet = FILES[fname][0][:31]
		with pd.ExcelWriter(p, engine="openpyxl") as xw:
			df.to_excel(xw, index=False, sheet_name=sheet)
			ws = xw.sheets[sheet]
			for c in ws[1]:
				c.font = c.font.copy(bold=True)
			ws.freeze_panes = "B2"
			for col in ws.columns:
				ws.column_dimensions[col[0].column_letter].width = min(45, max(12, len(str(col[0].value or "")) + 2))
			for row in ws.iter_rows(min_row=2):
				for c in row:
					if isinstance(c.value, str):
						c.number_format = "@"
		return p

	written = OrderedDict()
	for fname, data in zip(FILES, (h_ins, h_upd, r_ins, r_upd, b_ins, b_upd, sm_out)):
		if write_import(fname, data):
			written[fname] = len(data)

	# ---------------- report
	conf = Counter(m["confidence"] or "Unmatched" for m in match_rows)
	summary = [
		OrderedDict(item="Source file", value=SRC),
		OrderedDict(item="Students in sheet", value=len(rows)),
		OrderedDict(item="Hostels", value=len(hostels)),
		OrderedDict(item="Rooms", value=len(rooms)),
		OrderedDict(item="Bed capacity (from room codes)", value=sum(ro["capacity"] for ro in rooms.values())),
		OrderedDict(item="Matched - High (official email / student ID)", value=conf.get("High", 0)),
		OrderedDict(item="Matched - Medium (exact name + batch)", value=conf.get("Medium", 0)),
		OrderedDict(item="Review (held, not imported)", value=conf.get("Review", 0)),
		OrderedDict(item="Unmatched (not in Student Master)", value=conf.get("Unmatched", 0)),
		OrderedDict(item="Students to update (file H4)", value=len(sm_out)),
		OrderedDict(item="...of which hostel / room changes (old -> new)", value=len(changes)),
		OrderedDict(item="Students with a hostel in Student Master but not in this list", value=len(stale)),
		OrderedDict(item="New Hostel records (H1)", value=len(h_ins)),
		OrderedDict(item="Existing Hostel records updated (H1b)", value=len(h_upd)),
		OrderedDict(item="New Hostel Room records (H2)", value=len(r_ins)),
		OrderedDict(item="Existing rooms updated (H2b)", value=len(r_upd)),
		OrderedDict(item="New Hostel Bed records (H3)", value=len(b_ins)),
		OrderedDict(item="Existing beds updated (H3b)", value=len(b_upd)),
		OrderedDict(item="Data checks raised", value=len(data_checks)),
	]
	readme = [
		["Hostel allocation 2026-27 -> Student Master: mapping & import pack", ""],
		["Generated", frappe.utils.now()],
		["Site", frappe.local.site],
		["Source", SRC + " (Sheet1, 1 row per student)"],
		["", ""],
		["ROOM CODE", "e.g. BR101B3P = hostel prefix BR + room 101 + bed B + room capacity 3 + optional suffix letter (P / A, meaning unknown - kept in the bed code). Floor = first digit of the room number (0 = ground)."],
		["MASTERS", "Hostel name = sheet name. Room record name = '<Hostel>-<room number>' (e.g. Brahmaputra-101). Bed record name = 'BED-<room>-<office code>' (e.g. BED-Brahmaputra-101-BR101B3P). Every bed of a room is created (A..capacity), vacant ones included."],
		["MATCH ORDER", "1 Official email -> 2 Student ID (registration_id) -> 3 exact name + batch. High-tier hits whose names do not overlap at all, email/ID pointing to different students, and rows whose two room columns differ are HELD (Review)."],
		["UPDATE RULE", "Sheet wins: hostel, hostel_block (= hostel name), floor, hostel_room, hostel_bed, campus (On/Off Campus from the sheet Type), is_hosteller = 1, hostel_status = Allocated. Previous values are listed in 'Allocation_Changes'. No Hostel Allocation records are created (they would raise Housing & Mess fee demands). Occupancy: room.occupied / bed.is_occupied count only students linked in H4."],
		["", ""],
		["IMPORT ORDER", "Data Import, one file at a time: H1 (Insert) -> H1b (Update) -> H2 (Insert) -> H2b (Update) -> H3 (Insert) -> H3b (Update) -> H4 (Student Master, Update Existing Records). Masters must exist before H4. Files that are not generated had nothing to do."],
		["is_hosteller", "is_hosteller has permlevel 3 on Student Master - import H4 as Administrator / a user with level-3 write, otherwise that column is ignored."],
		["ADMISSIONS PACK", "Import H1-H4 BEFORE the admissions files (1-4): students whose old hostel links were broken are fixed by H4, which unblocks them for the admissions import."],
		["PRODUCTION", "Masters are matched by name per site. Re-run on production to get files that reflect production's existing hostels/rooms: bench --site <site> execute slcm.scratch.hostel_mapping.run --kwargs \"{'base': '<Admissions Data path>', 'tag': 'production'}\" (if production is an exact copy of local, the local files work as-is)."],
		["Before import", "bench --site <site> backup"],
	]
	doctype_issues = [
		OrderedDict(area="Hostel Room", issue="No field for the office room code / suffix letter (P / A).", impact="Suffix only kept inside bed_no.", recommendation="Add room_code (Data) and clarify P / A (e.g. AC, premium, partitioned) -> room_type options."),
		OrderedDict(area="Hostel Room", issue="room_type options are Non-AC / AC only; the sheet has no AC information.", impact="room_type left blank.", recommendation="Fill after the suffix meaning is confirmed."),
		OrderedDict(area="Hostel", issue="No campus / location (on-campus vs off-campus: RR Nagar, Pattanagere) or address field on Hostel; hostel_type is Boys / Girls / Co-ed.", impact="Campus stored on each Student Master (campus field).", recommendation="Add campus + address on Hostel."),
		OrderedDict(area="Hostel Block / Floor", issue="Hostel Block and Hostel Floor doctypes exist but have no records; Student Master hostel_block / floor are free-text Data fields.", impact="hostel_block = hostel name (same as Hostel Allocation logic), floor = digit.", recommendation="Either use the Block/Floor masters (Link) or remove them."),
		OrderedDict(area="Hostel Allocation", issue="after_insert raises a Housing & Mess Fee demand, so it cannot be used for back-filling current residents.", impact="Allocation history not created by this migration.", recommendation="If allocation history is needed, add a 'migration' flag that skips the fee hook, then create allocations."),
		OrderedDict(area="Student Master", issue="key_number, allocation_date, meal_plan not in the sheet.", impact="Left blank.", recommendation="Collect from the hostel office if needed."),
		OrderedDict(area="Hostel", issue="Existing local record 'Narmada' has code NM; the sheet uses NA in room codes and leaves the Narmada code blank.", impact="NM kept.", recommendation="Confirm the official code."),
		OrderedDict(area="Old links", issue="Student Master already pointed to hostels that do not exist in the Hostel master ('ANNAPURNA (NEW) Women', 'NARMADA Women', 'Olive' ...).", impact="Students in this list get the new names; others stay broken (Stale_Allocations).", recommendation="Clear hostel fields for students listed in Stale_Allocations who have left / are day scholars."),
	]
	unmatched = [m for m in match_rows if m["confidence"] in ("", "Review")]
	rp = os.path.join(out_dir, "Hostel_Mapping_Report.xlsx")
	with pd.ExcelWriter(rp, engine="openpyxl") as xw:
		pd.DataFrame(readme, columns=["Item", "Detail"]).to_excel(xw, index=False, sheet_name="README")
		pd.DataFrame(summary).to_excel(xw, index=False, sheet_name="Summary")
		pd.DataFrame(hostel_list).to_excel(xw, index=False, sheet_name="Hostel_List")
		pd.DataFrame(room_list).to_excel(xw, index=False, sheet_name="Room_List")
		pd.DataFrame([OrderedDict(sheet_column=a, target=b) for a, b in [
			("Sr No.", "(not imported)"), ("Hostel", "Hostel.hostel_code"), ("room code", "Hostel Room.room_number / floor / capacity, Hostel Bed.bed_no, Student Master.hostel_room / hostel_bed / floor"),
			("hostel", "Hostel.hostel_name, Student Master.hostel / hostel_block"), ("Type", "Hostel.hostel_type (Men->Boys, Women->Girls), Student Master.campus (off campus -> Off Campus)"),
			("Student NLS email", "match key 1 (official_email_id / email)"), ("Student ID", "match key 2 (registration_id)"), ("Student Name", "match key 3 + name check"),
			("Programme", "check only"), ("Batch Year", "match key 3 + check"), ("Gender", "check only"), ("(last unnamed column)", "check only - must equal room code")]]).to_excel(xw, index=False, sheet_name="Column_Mapping")
		pd.DataFrame(match_rows).to_excel(xw, index=False, sheet_name="Match_Results")
		pd.DataFrame(unmatched).to_excel(xw, index=False, sheet_name="Unmatched_Review")
		pd.DataFrame(changes).to_excel(xw, index=False, sheet_name="Allocation_Changes")
		pd.DataFrame(stale).to_excel(xw, index=False, sheet_name="Stale_Allocations")
		pd.DataFrame(data_checks).to_excel(xw, index=False, sheet_name="Data_Checks")
		pd.DataFrame(master_notes).to_excel(xw, index=False, sheet_name="Existing_Masters")
		pd.DataFrame(doctype_issues).to_excel(xw, index=False, sheet_name="Doctype_Issues")
		for ws in xw.sheets.values():
			for c in ws[1]:
				c.font = c.font.copy(bold=True)
			ws.freeze_panes = "A2"
			for col in ws.columns:
				w = max([len(str(col[0].value or ""))] + [min(60, len(str(c.value or ""))) for c in col[1:200]])
				ws.column_dimensions[col[0].column_letter].width = min(60, max(10, w + 2))

	print("OUT", out_dir)
	for s in summary:
		print(f"  {s['item']}: {s['value']}")
	print("files", dict(written))
	print("checks", Counter(d["check"] for d in data_checks))
	print("match", Counter((m["match_method"], m["confidence"]) for m in match_rows))
	plan = dict(hostels=set(hostels) | set(ex_h), rooms=sheet_rooms | set(ex_r), beds=sheet_beds | set(ex_b))
	validate(out_dir, plan, written)


# --------------------------------------------------------------------------------------
def validate(out_dir, plan, written):
	"""DRY validation - nothing saved. Frappe Data Import parser + in-memory document validators.
	Links to hostels / rooms / beds that H1-H3 will create count as valid."""
	from frappe.core.doctype.data_import import importer as imod
	from frappe.core.doctype.data_import.importer import Importer

	imod.ImportFile.read_file = lambda self, fp: (open(fp, "rb").read(), os.path.splitext(fp)[1][1:])
	planned = {"Hostel": plan["hostels"], "Hostel Room": plan["rooms"], "Hostel Bed": plan["beds"]}
	results, rows_out = [], []
	for fname in written:
		dt, itype = FILES[fname]
		path = os.path.join(out_dir, fname)
		di = frappe.get_doc(doctype="Data Import", import_type=itype, reference_doctype=dt)
		imp = Importer(dt, data_import=di, file_path=path, import_type=itype)
		prev = imp.import_file.get_data_for_import_preview()
		warns = prev.get("warnings") or []
		payloads = imp.import_file.get_payloads_for_import()
		err = Counter()
		names_seen = set()
		for p in payloads:
			d = p.doc
			sent = set(d.keys())
			if itype == "Insert New Records":
				doc = frappe.get_doc(dict(d, doctype=dt))
				try:
					doc.set_new_name()
				except Exception as e:
					rows_out.append(OrderedDict(file=fname, record="", category="IMPORT - naming", detail=str(e)[:200]))
					err["IMPORT"] += 1
				if doc.name in names_seen or frappe.db.exists(dt, doc.name):
					rows_out.append(OrderedDict(file=fname, record=doc.name, category="IMPORT - duplicate name", detail="already exists / repeated in file"))
					err["IMPORT"] += 1
				names_seen.add(doc.name)
				expected = {"Hostel": plan["hostels"], "Hostel Room": plan["rooms"], "Hostel Bed": plan["beds"]}[dt]
				if doc.name not in expected:
					rows_out.append(OrderedDict(file=fname, record=doc.name, category="IMPORT - name differs from plan", detail="Student Master links would not resolve"))
					err["IMPORT"] += 1
			else:
				try:
					doc = frappe.get_doc(dt, d.get(imod.get_id_field(dt).fieldname))
				except Exception as e:
					rows_out.append(OrderedDict(file=fname, record=d.get("name"), category="IMPORT - ID not found", detail=str(e)[:200]))
					err["IMPORT"] += 1
					continue
				doc.update(d)
			for fn_ in (doc._fix_numeric_types, doc._validate_length, doc._validate_data_fields, doc._validate_selects,
						doc._validate_non_negative, doc._validate_mandatory):
				try:
					fn_()
				except Exception as e:
					rows_out.append(OrderedDict(file=fname, record=doc.name, category="IMPORT - value rejected", detail=re.sub(r"<[^>]+>", "", str(e))[:200]))
					err["IMPORT"] += 1
				finally:
					frappe.clear_messages()
			for df in doc.meta.get_link_fields():
				v = doc.get(df.fieldname)
				if not v or frappe.db.exists(df.options, v) or v in planned.get(df.options, ()):
					continue
				cat = "IMPORT - invalid link from sheet" if df.fieldname in sent else "PRE-EXISTING - broken link already on record (save will fail until fixed)"
				rows_out.append(OrderedDict(file=fname, record=doc.name, category=cat, detail=f"{df.fieldname} = {v} ({df.options})"))
				err[cat.split(" ")[0]] += 1
		results.append(OrderedDict(file=fname, doctype=dt, import_type=itype, documents=len(payloads), parser_warnings=len(warns),
			import_errors=err.get("IMPORT", 0), pre_existing_link_errors=err.get("PRE-EXISTING", 0),
			warnings_sample=" | ".join(str(w.get("message", w))[:150] for w in warns[:5])))
	frappe.db.rollback()
	vdf = pd.DataFrame(rows_out)
	blockers = vdf[vdf.category.str.startswith("PRE-EXISTING")].drop_duplicates(["record", "detail"]) if not vdf.empty else pd.DataFrame()
	with pd.ExcelWriter(os.path.join(out_dir, "Hostel_Import_Validation.xlsx"), engine="openpyxl") as xw:
		pd.DataFrame(results).to_excel(xw, index=False, sheet_name="Summary")
		blockers.to_excel(xw, index=False, sheet_name="Fix_Before_Import")
		vdf.to_excel(xw, index=False, sheet_name="All_Errors")
		for ws in xw.sheets.values():
			ws.freeze_panes = "A2"
			for col in ws.columns:
				ws.column_dimensions[col[0].column_letter].width = min(70, max(12, max(len(str(c.value or "")) for c in col[:200]) + 2))
	for r in results:
		print("FILE", dict(r))
	if not vdf.empty:
		print(vdf.groupby("category").size().to_string())
		print(vdf.head(20).to_string(max_colwidth=90))
