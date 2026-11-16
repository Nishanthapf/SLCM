"""
Admissions Data -> Student Master mapping, matching and Data-Import sheet builder.

READ-ONLY against the database: nothing is inserted/updated. It only reads Student Master
and writes Excel files.

Run (local):
    bench --site slcm.com execute slcm.scratch.admissions_mapping.run
Run (production, after copying this file to apps/slcm/slcm/scratch/ and the
"docs/Admissions Data" folder to the server):
    bench --site <prod-site> execute slcm.scratch.admissions_mapping.run \
        --kwargs "{'base': '/path/to/Admissions Data', 'tag': 'production'}"

Outputs (in <base>/output/<tag>/):
    1_Student_Master_Update.xlsx       -> Data Import, "Update Existing Records", DocType Student Master
    2_Student_Parents_Update.xlsx      -> Data Import, "Update Existing Records" (parents child table)
    3_Student_Qualification_Update.xlsx-> Data Import, "Update Existing Records" (UG / PG / Employment tables)
    4_Student_Documents_Update.xlsx    -> Data Import, "Update Existing Records" (Attach fields - optional)
    Admissions_Mapping_Report.xlsx     -> analysis report
"""

import glob
import os
import re
import warnings
from collections import Counter, OrderedDict, defaultdict

import frappe
import pandas as pd

warnings.filterwarnings("ignore")

DT = "Student Master"

# --------------------------------------------------------------------------------------
# Source sheets
# --------------------------------------------------------------------------------------
# kind: report = NLS admissions-portal export, form = Google form, clat = CLAT counselling form,
#       legacy = old ERP dump
SOURCES = [
    dict(ay="2022-23", file="AY 2022-23/student_records.xlsx", sheet="student_records", header=0, kind="legacy", prog=None),
    dict(ay="2023-24", file="AY 2023-24/BA-LLB.xlsx", sheet="Form Responses 1", header=0, kind="form", prog="5-Year B.A., LL.B. (Hons.)"),
    dict(ay="2023-24", file="AY 2023-24/LLB.xlsx", sheet="Report", header=6, kind="report", prog="3-Year LL.B. (Hons.)"),
    dict(ay="2023-24", file="AY 2023-24/LLM.xlsx", sheet="Form Responses 1", header=0, kind="form", prog="LL.M."),
    dict(ay="2023-24", file="AY 2023-24/MPP.xlsx", sheet="Report", header=6, kind="report", prog="MASTER'S OF PUBLIC POLICY PROGRAMME"),
    dict(ay="2023-24", file="AY 2023-24/PhD.xls", sheet="Report", header=6, kind="phd", prog="Ph.D"),
    dict(ay="2024-25", file="AY 2024-25/B.A LLB and LLM Students Data Dump 2024-25 (5).xlsx", sheet="BALLB", header=2, kind="clat24", prog="5-Year B.A., LL.B. (Hons.)"),
    dict(ay="2024-25", file="AY 2024-25/B.A LLB and LLM Students Data Dump 2024-25 (5).xlsx", sheet="LLM", header=2, kind="clat24llm", prog="LL.M."),
    dict(ay="2024-25", file="AY 2024-25/Data Dump for LLB,MPP and Phd_2024-25 (3).xlsx", sheet="LLB 3 Years", header=3, kind="report", prog="3-Year LL.B. (Hons.)"),
    dict(ay="2024-25", file="AY 2024-25/Data Dump for LLB,MPP and Phd_2024-25 (3).xlsx", sheet="MPP", header=3, kind="report", prog="MASTER'S OF PUBLIC POLICY PROGRAMME"),
    dict(ay="2024-25", file="AY 2024-25/Data Dump for LLB,MPP and Phd_2024-25 (3).xlsx", sheet="PHD", header=3, kind="phd", prog="Ph.D"),
    dict(ay="2025-26", file="AY 2025-26/BA-LLB.xlsx", sheet="FINAL", header=0, kind="clat", prog="5-Year B.A., LL.B. (Hons.)"),
    dict(ay="2025-26", file="AY 2025-26/BA-LLB.xlsx", sheet="Consolidated", header=0, kind="clat", prog="5-Year B.A., LL.B. (Hons.)"),
    dict(ay="2025-26", file="AY 2025-26/BA-LLB.xlsx", sheet="Sheet3", header=0, kind="clat", prog="5-Year B.A., LL.B. (Hons.)"),
    dict(ay="2025-26", file="AY 2025-26/BA.xlsx", sheet="Form Responses 1", header=0, kind="form", prog="BA (Hons)"),
    dict(ay="2025-26", file="AY 2025-26/LLB.xlsx", sheet="Report", header=0, kind="report", prog="3-Year LL.B. (Hons.)"),
    dict(ay="2025-26", file="AY 2025-26/LLM.xlsx", sheet="Form Responses 1", header=0, kind="form_positional", prog="LL.M."),
    dict(ay="2025-26", file="AY 2025-26/LLM.xlsx", sheet="Sheet1", header=None, kind="names_only", prog="LL.M."),
    dict(ay="2025-26", file="AY 2025-26/MPP.xlsx", sheet="Report", header=0, kind="report", prog="MASTER'S OF PUBLIC POLICY PROGRAMME"),
    dict(ay="2026-27", file="AY 2026-27/LLM.xlsx", sheet="Sheet1", header=0, kind="clat", prog="LL.M."),
    dict(ay="2026-27", file="AY 2026-27/LLM.xlsx", sheet="Sheet2", header=0, kind="report", prog="LL.M."),
    dict(ay="2026-27", file="AY 2026-27/LLM.xlsx", sheet="Form Responses 1", header=0, kind="clat", prog="LL.M."),
    dict(ay="2026-27", file="AY 2026-27/BA-LLB.xlsx", sheet="Form Responses 1", header=0, kind="clat", prog="5-Year B.A., LL.B. (Hons.)"),
    dict(ay="2026-27", file="AY 2026-27/BA.xlsx", sheet="Form Responses 1", header=0, kind="form", prog="BA (Hons)"),
    dict(ay="2026-27", file="AY 2026-27/LLB.xlsx", sheet="Form Responses 1", header=0, kind="form", prog="3-Year LL.B. (Hons.)"),
    dict(ay="2026-27", file="AY 2026-27/MPP.xlsx", sheet="Form Responses 1", header=0, kind="form", prog="MASTER'S OF PUBLIC POLICY PROGRAMME"),
    dict(ay="2026-27", file="AY 2026-27/NLSAT International.xlsx", sheet="Form Responses 1", header=0, kind="form", prog=None),
]
EMPTY_SHEETS = [
    ("AY 2023-24/LLB.xlsx", "Worksheet"), ("AY 2023-24/MPP.xlsx", "Worksheet"),
    ("AY 2023-24/PhD.xls", "Worksheet"), ("AY 2025-26/LLB.xlsx", "Sheet1"),
]

# 2025-26 LLM form has "Column1..Column41" headers; real meaning by position (same Google form
# template as the 2025-26 BA form, plus a Gender column).
POSITIONAL_LLM_2526 = [
    "Timestamp", "Email Address", "First name of the student", "Middle name of the student",
    "Last name of the student", "Gender", "Personal email ID of the student", "Mobile number of the student",
    "Blood Group", "Upload your passport size photo", "Any pre-existing health issues/known allergies",
    "First name of the Father/Guardian", "Middle name of the Father/Guardian", "Last name of the Father/Guardian",
    "Email ID of the Father/Guardian", "Mobile number used by the Father/Guardian",
    "First name of the Mother/Guardian", "Middle name of the Mother/Guardian", "Last name of the Mother/Guardian",
    "Email ID of the Mother/Guardian", "Mobile number used by the Mother/Guardian",
    "House number/Flat number", "Street name/Locality", "City", "State", "Pincode",
    "First name of the local guardian", "Middle name of the local guardian", "Last name of the local guardian",
    "Email ID of the local guardian", "Phone number of the local guardian",
    "House number/Flat number 2", "Street name/Locality 2", "Pincode 2",
    "Disciplinary Undertaking", "Medical Fitness Certificate", "Health and Wellness undertaking",
    "Antiragging undertaking", "Please enter the unique reference number received (payment)",
    "Hostel Application Form", "Residential Undertaking by the student",
    "Any other information that you want the University to know",
]

# --------------------------------------------------------------------------------------
# Header -> target rules.  Header is normalised (lower, quotes unified, first line only).
# target prefixes:
#   id:<key>          identity / matching key (also written to SM where applicable)
#   sm:<fieldname>    Student Master field
#   par:<Rel>:<part>  Student Parent row  (part: name/first/middle/last/phone/email/occupation/
#                                         address/house/street/city/state/pin)
#   addr:<part>       student's home address parts (house/street/full) -> permanent_address
#   ug:/pg:<part>     UG / PG degree child row
#   emp:<n>:<part>    Employment child row
#   att:<fieldname>   Attach field (separate optional import)
# occ = which occurrence of a duplicated header (None = any)
# kinds = restrict rule to source kinds
# --------------------------------------------------------------------------------------
R = []


def rule(pattern, target, occ=None, kinds=None):
    R.append((re.compile(pattern), target, occ, kinds))


# ---- identity
rule(r"^nls email id$", "id:official")
rule(r"^student email address$", "id:email_any")
rule(r"^(student id|nls student id( no\.?)?|id no|nls id no\.?)$", "id:regid")
rule(r"^(clat (2024 )?)?admit card number$", "id:admit")
rule(r"^registration number \(nlsat admit card number\)$", "id:admit")
rule(r"^nlsat admit card number$", "id:admit")
rule(r"^clat id$", "id:clat_id")
rule(r"^(application no|application number|clat application number)$", "id:appno")
rule(r"^(personal email id of the student|email id|email-id of the (applicant|candidate))$", "id:pemail")
rule(r"^old email$", "id:pemail")
rule(r"^email address$", "id:formemail")
rule(r"^(student name|name of the applicant.*|applicant name|candidate's name|full name.*|name)$", "id:fullname")
rule(r"^(first name of the student|candidate's first name)$", "id:first")
rule(r"^(middle name of the student|candidate's middle name)$", "id:middle")
rule(r"^(last name of the student|candidate's last name)$", "id:last")

# ---- personal / contact
rule(r"^(student mobile number|mobile number of the student|mobile number of (applicant|candidate)|candidate mobile number|mobile number|mobile)$", "sm:phone")
rule(r"^applicant mobile$", "sm:phone")
rule(r"^(alternate (contact|mobile) number|mobile number 2|alternate number)$", "sm:alternate_phone")
rule(r"^date of birth", "sm:dob")
rule(r"^gender$", "sm:gender")
rule(r"^nationality$", "sm:nationality")
rule(r"^religion\.?$", "sm:religion")
rule(r"^blood group$", "sm:blood_group")
rule(r"(pwd/sap|^are you a pwd candidate|^whether person with disability|^are you a person with disability)", "sm:pwd")
rule(r"^any pre-existing health", "sm:pre_existing_conditions")
rule(r"^passport no$", "sm:passport_number")
rule(r"^date of registration$", "sm:date_of_registration")
rule(r"^(whether sc/st/obc-ncl|actual caste category|caste category|category)$", "sm:quota")
rule(r"^whether ews$", "sm:whether_ews")
rule(r"^(whether karnataka category|have you been allotted a karnataka category seat)$", "sm:karnataka_category")
rule(r"^(studied for not less than|have you studied in karnataka)", "sm:ka_study_7yrs")
rule(r"^child of defence", "sm:ka_defence_child")
rule(r"^child of a serving or retired employee belonging to the karnataka cadre", "sm:ka_govt_child")
rule(r"^child of a working or retired employee in the central armed", "sm:ka_capf_child")
rule(r"(annual family income|annual household income)", "sm:annual_income")
rule(r"^do you want to opt for scholarship", "sm:applying_scholarship")
rule(r"^(hostelite|is hostel accommodation provided to you\?)$", "sm:is_hosteller")
rule(r"^(do you require hostel facility|hostel facility required|hostel accommodation required)$", "sm:needs_accommodation")
rule(r"^do you want residential accommodation", "sm:needs_accommodation")
rule(r"^are you interested in off-campus accommodation", "sm:are_you_interested_in_off_campus_accommodation")
rule(r"^are you a resident of bengaluru", "sm:are_you_a_resident_of_bengaluru")
rule(r"^(local emergency contact's mobile number|phone number of the local emergency contact)$", "sm:emergency_contact")

# ---- student address
rule(r"^address for correspondence with pincode$", "sm:present_address")
rule(r"^(address correspondence city|city/town/village|a\. city/town/village)$", "sm:city", kinds={"legacy"})
rule(r"^(a\. state|state/ut|state to which you belong to)$", "sm:state", kinds={"legacy"})
rule(r"^(a\. pincode|pincode)$", "sm:pincode", kinds={"legacy"})
rule(r"^(district|a\. district)$", "sm:district")
rule(r"^a\. address$", "addr:full", kinds={"legacy"})
rule(r"^country$", "sm:country", kinds={"legacy"})
rule(r"^(state|state/ut)$", "sm:state", occ=0)
rule(r"^city$", "sm:city", occ=0)
rule(r"^(pincode|pin code)$", "sm:pincode", occ=0)
rule(r"^address$", "addr:full", occ=0)
rule(r"^house number/ ?flat number$", "addr:house", occ=0)
rule(r"^street name/ ?locality$", "addr:street", occ=0)
rule(r"^father's/guardian's address$", "addr:full", kinds={"clat24", "clat24llm"})

# ---- parents
for rel, words in (("Father", "father"), ("Mother", "mother")):
    w = words
    rule(rf"^({w} name|{w}'s name|{w}'s/guardian's name)$", f"par:{rel}:name")
    rule(rf"^first name of the {w}(/guardian)?$", f"par:{rel}:first")
    rule(rf"^middle name of the {w}(/guardian)?$", f"par:{rel}:middle")
    rule(rf"^last name of the {w}(/guardian)?$", f"par:{rel}:last")
    rule(rf"^({w} email|{w}'s email id|email id of the {w}(/guardian)?|{w} email id|{w}'s/guardian's email id)$", f"par:{rel}:email")
    rule(rf"^({w} mobile|{w}'s mobile number|mobile number used by the {w}(/guardian)?|{w} mobile number|{w}'s/guardian's mobile number)$", f"par:{rel}:phone")
    rule(rf"^({w} profession|{w}'s occupation|{w} occupation|{w}'s/guardian's occupation)$", f"par:{rel}:occupation")
    rule(rf"^({w} address with pincode|{w}'s/guardian's address)$", f"par:{rel}:address")
rule(r"^(state)$", "par:Father:state", occ=0, kinds={"clat24", "clat24llm"})
rule(r"^(city)$", "par:Father:city", occ=0, kinds={"clat24", "clat24llm"})
rule(r"^(pin code)$", "par:Father:pin", occ=0, kinds={"clat24", "clat24llm"})
rule(r"^(state)$", "par:Mother:state", occ=1, kinds={"clat24", "clat24llm"})
rule(r"^(city)$", "par:Mother:city", occ=1, kinds={"clat24", "clat24llm"})
rule(r"^(pin code)$", "par:Mother:pin", occ=1, kinds={"clat24", "clat24llm"})
rule(r"^(local guardian name|local guardian's name|guardian name|local emergency contact's name)$", "par:Guardian:name")
rule(r"^first name of the local (guardian|emergency contact)$", "par:Guardian:first")
rule(r"^middle name of the local (guardian|emergency contact)$", "par:Guardian:middle")
rule(r"^last name of the local (guardian|emergency contact)$", "par:Guardian:last")
rule(r"^(local guardian mobile no\.|local guardian's mobile number|guardian mobile number|phone number of the local guardian)$", "par:Guardian:phone")
rule(r"^(local emergency contact's mobile number|phone number of the local emergency contact)$", "par:Guardian:phone")
rule(r"^(local guardian email|local guardian's email id|guardian email id|email id of the local (guardian|emergency contact)|local emergency contact's email id)$", "par:Guardian:email")
rule(r"^(local guardian address with pincode|local guardian's address with pin ?code|emergency contact's address with pin code|g\. address)$", "par:Guardian:address")
rule(r"^house number/ ?flat number( 2)?$", "par:Guardian:house", occ=1)
rule(r"^house number/flat number 2$", "par:Guardian:house")
rule(r"^street name/ ?locality( 2)?$", "par:Guardian:street", occ=1)
rule(r"^street name/locality 2$", "par:Guardian:street")
rule(r"^pincode$", "par:Guardian:pin", occ=1)
rule(r"^(pincode 2|g pin code)$", "par:Guardian:pin")
rule(r"^guardian residence city$", "par:Guardian:city")
rule(r"^g\. state$", "par:Guardian:state")

# ---- school
rule(r"^year of completion \(class x\)$", "sm:class_x_completion_year")
rule(r"^school/college/university \(class x\)$", "sm:class_x_school")
rule(r"^board(/university)? \(class x\)$", "sm:class_x_board")
rule(r"^percentage/cgpa obtained \(class x\)$", "sm:class_x_percentage")
rule(r"^if cgpa, maximum cpga \(class x\)$", "sm:class_x_max_cgpa")
rule(r"^(examination \(class xii/equivalent\)|name of examination \(class xii)", "sm:class_xii_exam_name")
rule(r"^year of completion \(class xii/equivalent\)$", "sm:class_xii_completion_year")
rule(r"^school/college/university \(class xii/equivalent\)$", "sm:class_xii_school")
rule(r"^board(/university)? \(class xii/equivalent\)$", "sm:class_xii_board")
rule(r"^percentage/cgpa obtained \(class xii/equivalent\)$", "sm:class_xii_percentage")
rule(r"^if cgpa, maximum cpga \(class xii/equivalent\)$", "sm:class_xii_max_cgpa")
rule(r"^class 12 or equivalent: name of the school$", "sm:class_xii_school")
rule(r"^class 12 or equivalent: board name$", "sm:class_xii_board")
rule(r"^class 12 or equivalent: year of passing$", "sm:class_xii_completion_year")
rule(r"^name of the college/school$", "sm:class_xii_school", kinds={"clat24"})
rule(r"^board$", "sm:class_xii_board", kinds={"clat24"})
rule(r"^year of writing/passing$", "sm:class_xii_completion_year", kinds={"clat24"})

# ---- UG / PG / employment
rule(r"^name of degree \(ug\)$", "ug:program")
rule(r"^year of completion \(ug degree\)$", "ug:year")
rule(r"^(school/)?college/university \(ug degree\)$", "ug:college")
rule(r"^board/university \(ug degree\)$", "ug:board")
rule(r"^percentage/cgpa obtained \(ug degree\)$", "ug:cgpa")
rule(r"^if cgpa, maximum cpga \(ug degree\)$", "ug:max")
rule(r"^ug degree certificate/bonafide", "ug:cert")
rule(r"^transcripts/marksheets to be uploaded", "ug:marks", occ=0)
rule(r"^transcripts/marksheets to be uploaded", "pg:marks", occ=1, kinds={"phd"})
rule(r"^name of the college/university$", "ug:college", kinds={"clat24llm"})
rule(r"^year of completion/writing the final exam$", "ug:year", kinds={"clat24llm"})
rule(r"^name of the university from which you have obtai", "ug:college")
rule(r"^llb : year of completion", "ug:year")
rule(r"^name of degree \(pg\)$", "pg:program")
rule(r"^year of completion \(pg degree\)$", "pg:year")
rule(r"^school/college/university \(pg degree\)$", "pg:college")
rule(r"^board/university \(pg degree\)$", "pg:board")
rule(r"^percentage/cgpa obtained \(pg degree\)$", "pg:cgpa")
rule(r"^if cgpa, maximum cpga \(pg degree\)$", "pg:max")
rule(r"^pg degree certificate/bonafide", "pg:cert")
for n in range(1, 6):
    rule(rf"^employer's name {n}$", f"emp:{n}:employers_name")
    rule(rf"^designation in the organization {n}$", f"emp:{n}:designation_in_the_organization")
    rule(rf"^duration of employment {n}$", f"emp:{n}:duration_of_the_employment")
rule(r"^do you have any post-degree work experince", "sm:do_you_have_any_post_degree_work_experince")
rule(r"^how many years of work experince", "sm:how_many_years_of_work_experince_do_you_have")

# ---- entrance / admission
rule(r"^(total marks obtained|marks scored in clat|clat 2024 marks|nlsat exam score)$", "sm:total_marks_obtained")
rule(r"^(final rank|clat ranking|clat 2024 rank|rank|clat rank 2020)$", "sm:final_rank")
rule(r"^final percentile$", "sm:final_percentile")
rule(r"^(final vertical|allocated category|alloted category)$", "sm:final_vertical")
rule(r"^(final horizontal|horizontal category)$", "sm:final_horizontal")
rule(r"^final category rank$", "sm:final_category_rank")
rule(r"^final rank category$", "sm:final_rank_category")
rule(r"^(rank category|part a rank category)$", "sm:rank_category")
rule(r"^(allotment round|clat round)$", "sm:allotment_round")
rule(r"^exam attended$", "sm:exam_attended")
rule(r"^where did you hear about the program", "sm:where_did_you_hear_about_the_programme")
rule(r"^(section|section alloted)$", "sm:section")
rule(r"^combination$", "sm:concentration", kinds={"legacy"})
rule(r"^(proposed ph\.d topic|research topic)$", "sm:proposed_phd_topic")
rule(r"^(which programme are you applying for\?|ph\.d stream)$", "sm:phd_programme")

# ---- attachments
rule(r"^(student photo|upload your passport size photo|recent passport size student photograph|upload your photograph)", "att:passport_size_photo")
rule(r"^(id proof \(govt\. issued photo id|valid photo id proof|upload valid photo id document)", "att:id_proof_govt_issued_photo_id")
rule(r"^(class x marksheet to be uploaded|10th marks sheet|original 10th mark)", "att:std_x_marksheet")
rule(r"^(class xii marksheet|12th marks sheet|original 12th marks)", "att:class_xii_marksheet")
rule(r"^migration", "att:transfer_certificate")
rule(r"^(caste certificate|caste/disability certificate)", "att:caste_certificate")
rule(r"^ews certificate", "att:ews_certificate")
rule(r"^(pwd certificate|disability certificate)", "att:pwd_certificate")
rule(r"^curriculum vitae", "att:curriculum_vitae")
rule(r"^ph\.d proposal to be uploaded", "att:phd_proposal")
rule(r"^aadhar card$", "att:aadhaar_card")
rule(r"^score card", "att:entrance_exam_score_marksheet")
rule(r"^(karnataka study certificate \(mandatory|study certificate$)", "att:ka_study_7yrs_certificate")
rule(r"^certificate \(max 5mb", "att:ka_study_7yrs_certificate", occ=0)
rule(r"^certificate \(max 5mb", "att:ka_defence_child_certificate", occ=1)
rule(r"^certificate \(max 5mb", "att:ka_govt_child_certificate", occ=3)
rule(r"^certificate \(max 5mb", "att:ka_capf_child_certificate", occ=4)
rule(r"^antiragging undertaking", "att:posh_anti_ragging_declaration")
rule(r"^disciplinary undertaking", "att:student_declaration")
rule(r"^parent undertaking", "att:parent_declaration")
rule(r"^upload proof of citizenship", "att:passport")
rule(r"^fin\. certificate \(h\)$", "att:fin_certificate_h")
rule(r"^fin\. certificate \(wh\)$", "att:fin_certificate_wh")

# --------------------------------------------------------------------------------------
# Columns with data but NO field in Student Master -> grouped into concepts for the report
# (pattern, concept, suggested fieldname, suggested fieldtype / location, recommendation)
# --------------------------------------------------------------------------------------
MISSING_CONCEPTS = [
    (r"mother tongue", "Mother tongue", "mother_tongue", "Data (Personal)", "Add field"),
    (r"^caste\.?$|caste \(for foreign", "Caste / sub-caste name", "caste", "Data (Personal)", "Add field"),
    (r"religion \(for foreign", "Religion (foreign national)", "-", "-", "Covered by religion; ignore"),
    (r"^visa no", "Visa number", "visa_number", "Data (Personal, next to passport)", "Add field (international students)"),
    (r"aadhar card no|valid id proof number|kindly enter valid id proof number", "Govt ID proof number (Aadhaar / PAN / Passport no.)", "id_proof_number", "Data (Documents)", "Add field (sensitive - restrict permission)"),
    (r"select valid photo id proof", "Govt ID proof type", "id_proof_type", "Select Aadhaar/PAN/Passport/DL/Voter ID (Documents)", "Add field"),
    (r"coaching class", "Attended CLAT coaching", "attended_coaching", "Select Yes/No (Admission)", "Optional"),
    (r"^clat id$", "CLAT ID (legacy)", "clat_id", "Data (Admission)", "Optional - legacy only"),
    (r"^(clat fee|counselling fee paid)$", "CLAT counselling fee paid", "counselling_fee_paid", "Currency (Admission)", "Optional"),
    (r"^copy of clat admit card|^upload the clat admit card|admit card path", "Admit card copy", "admit_card_copy", "Attach (Documents)", "Optional"),
    (r"^date of joining$", "Date of joining", "date_of_joining", "Date (Registration)", "Add field (historic records)"),
    (r"year of joining$|^year temp$|^year of joining \(school", "Year of joining (legacy)", "-", "-", "Derivable from batch; ignore"),
    (r"^program name$|^course$|^programme$|^class$", "Programme / class label in sheet", "-", "-", "Already in programme_of_study / current_year"),
    (r"^discontinued$", "Discontinued flag (legacy)", "-", "student_status", "Map to student_status=Dropped manually after review"),
    (r"is iccr student", "ICCR scholarship student", "is_iccr_student", "Check (Registration)", "Add field"),
    (r"hostel exemption", "Hostel exemption", "hostel_exemption", "Check (Residence)", "Add field"),
    (r"koha library id", "Koha library ID", "library_id", "Data (Account)", "Add field"),
    (r"makeup group", "Makeup group (legacy)", "-", "-", "Ignore"),
    (r"exam extra time mode", "Exam extra time / scribe mode", "exam_accommodation", "Data (Personal - PWD)", "Add field"),
    (r"scribe", "Scribe required / arrangement", "scribe_required", "Select Yes/No (Personal - PWD)", "Add field"),
    (r"ph\.d (joining year|year|status)", "PhD joining year / current year / status", "phd_status", "Select + Data (PhD section)", "Add fields"),
    (r"dissertation topic", "Master's / M.Phil dissertation topic", "pg dissertation_topic", "Data (PG Degree Details row)", "Add field to PG Degree Details"),
    (r"m\.phil", "M.Phil degree details", "-", "PG Degree Details row", "Load as PG row manually (rare)"),
    (r"solicitor|masters of business laws|company secretaryship|chartered accountants", "Professional qualification (CS/CA/Solicitor/MBL)", "professional_qualification", "Table or Small Text (Academic Qualification)", "Optional"),
    (r"ugc net|jrf", "UGC NET / JRF status + letter", "ugc_net_qualified / jrf_recipient", "Select + Attach (PhD section)", "Add fields"),
    (r"proposal and interview score|interview marks|final marks", "Interview / proposal score", "interview_score", "Data (Admission)", "Add field"),
    (r"^part [ab] ", "NLSAT Part A / Part B marks, percentile, rank, qualified", "part_a_marks, part_b_marks ...", "Section in Admission tab", "Add fields if needed for audit"),
    (r"^total percentile$", "Total percentile", "-", "final_percentile", "Covered by final_percentile"),
    (r"^test city allocated|allotted test center|^(first|second|third) preference$", "Test city / centre / preferences", "test_city", "Data (Admission)", "Optional"),
    (r"admit card (downloaded|regenerated)", "Admit card download status", "-", "-", "Ignore (portal metadata)"),
    (r"^fee category$", "Fee category (Gen/...)", "fee_category", "Select (Finance)", "Add field (affects fee structure)"),
    (r"^(form status|status|admission status|university status|candidate status)$", "Application / admission status", "-", "registration_status", "Ignore (do not overwrite workflow)"),
    (r"preference for concentration|branchwise preference", "LLM concentration preferences 1-4", "concentration_preference_1..4", "Data (Admission)", "Add fields (only 'concentration' exists)"),
    (r"^(school name|school [1-5] name|city/town|city/town \(school|year of leaving|year of joining \(school)", "School history (schools 1-5, city, years)", "school_history", "Table (Academic Qualification)", "Add child table (Karnataka 10-yr study proof)"),
    (r"^(name of degree [2-5]|year of completion \(degree|(school/)?college/university \(degree|board/university \(degree|percentage/cgpa obtained \(degree|if cgpa, maximum cpga \(degree|any other educational qualifications|name of degree$|year of completion$|school/college/university$|board/university$|percentage/cgpa obtained$|if cgpa, maximum cpga$|do you need to add additional)", "Additional degrees 2-5", "-", "UG/PG Degree Details rows", "Extend import to add as extra rows (not done - ambiguous UG vs PG)"),
    (r"^degree/bonafide certificate|^transcripts/marksheets to be uploaded", "Additional degree certificates", "-", "UG/PG Degree Details rows", "As above"),
    (r"^have you completed your ug degree", "UG completion status", "ug_status", "Select (Academic Qualification)", "Optional"),
    (r"^examination \(class x", "Class X examination name", "class_x_exam_name", "Data (Class X section)", "Add field (Class XII has one)"),
    (r"^class 12 or equivalent: city name|^city/town$", "School city (Class XII)", "class_xii_city", "Data (Class XII section)", "Optional"),
    (r"^(name of the college/school/university|board|educational background - stream|marks secured/cgpa|total marks 2020|percentage|year of passing|total marks|marks secured|stream|if any other stream|total marks/cgpa|percentage/cgpa|branch|if any other branch)", "Qualifying exam marks (legacy / CLAT dumps - programme-dependent)", "-", "Class XII or UG section", "Not mapped: column mixes 12th & LLB for different programmes"),
    (r"^(ll\.b\. marks sheet|degree certificate|ll\.b degree certificate|ll\.m degree certificate|pg degree certificate$|original llb)", "Qualifying degree certificate / marksheet (LL.B.)", "-", "UG Degree Details.degree_certificate", "Attach manually / extend import"),
    (r"^(medical fitness certificate|health and wellness undertaking)", "Medical fitness / health undertaking", "medical_fitness_certificate", "Attach (Documents)", "Add field"),
    (r"(hostel application form|residence application form|residential undertaking|residential students' undertaking|i voluntarily opt in)", "Hostel application / residential undertaking", "hostel_application_form", "Attach (Residence)", "Add field"),
    (r"^(student undertaking)", "Student undertaking (legacy)", "-", "student_declaration", "Covered"),
    (r"income certificate", "Income certificate / ITR", "income_certificate", "Attach (Income Details)", "Add field"),
    (r"domicile certificate", "Domicile certificate", "domicile_certificate", "Attach (Documents)", "Add field"),
    (r"(any other relevant documents|sample document|proof of fees paid|fees paid in previous counselling|kindly enter the fees paid)", "Other / previous-counselling fee documents", "other_documents", "Table of attachments", "Optional"),
    (r"receipt for the payment|unique reference number", "Admission fee payment reference", "admission_fee_reference", "Data (Finance)", "Add field (helps reconciliation)"),
    (r"^father company|occupation address|^mother company", "Parent employer / office address", "employer, office_address", "Data/Text (Student Parent)", "Add fields to Student Parent"),
    (r"^father occupation$", "Father occupation (empty column)", "-", "-", "Empty"),
    (r"child of an employee of the karnataka state gov", "Karnataka category: child of Karnataka State Govt employee", "ka_state_govt_child", "Check + Attach (Karnataka section)", "Add field (no matching field today)"),
    (r"^certificate \(max 5mb", "Certificate for Karnataka State Govt employee child", "ka_state_govt_child_certificate", "Attach", "Add with the field above"),
    (r"^(if contact details of both parents)", "Flag: parents' contact details not available", "-", "-", "Ignore (guardian row used)"),
    (r"^karnataka study certificate \(where there are", "Karnataka study certificate (study gaps)", "-", "ka_study_7yrs_certificate", "Second certificate - attach manually"),
    (r"^(age|timestamp|sl no|sl\. no\.|nan|column 85|duplicate|date/time|date|slot|remarks|counselling fee paid|)$", "Form metadata (timestamp / serial / age)", "-", "-", "Ignore"),
    (r"^(i hereby|declaration|i consent)", "Declarations / consent", "-", "-", "Ignore (or store consent flag)"),
    (r"^any other information", "Any other information for university", "-", "status_remark / Comment", "Optional"),
    (r"^financial aid applied|do you require financial aid", "Financial aid applied", "financial_aid_applied", "Select Yes/No (Finance)", "Add field"),
    (r"^(do you belong to sc/st|category combination|quota|category\.)", "Reservation flags (legacy duplicates)", "-", "quota", "Covered by quota"),
    (r"physically challenged", "Physically challenged (legacy, empty)", "-", "pwd", "Covered"),
    (r"place of birth", "Place of birth", "place_of_birth", "Data", "Empty in source"),
    (r"residential status|resident status|domicile state", "Residential status / domicile state", "domicile_state", "Link State", "Empty in source"),
    (r"terms of mou", "Exchange MOU terms", "-", "-", "Ignore"),
    (r"bridge course|exchange student", "Bridge course / exchange student", "is_exchange_student", "Check", "Add field"),
    (r"^(email address)$", "Google form login e-mail", "-", "-", "Used only for matching"),
    (r"^(phone number)$", "Landline (legacy)", "-", "alternate_phone", "Optional"),
    (r"^please mention$", "Where did you hear - details", "-", "where_did_you_hear_about_the_programme", "Appended to that field"),
    (r"^number of positions held$", "Number of positions held", "-", "Employment rows", "Derivable"),
    (r"^(local guardian|guardian|local emergency)", "Guardian detail", "-", "Student Parent (Guardian)", "Covered"),
    (r"^(applicant mobile)$", "Applicant mobile", "-", "phone", "Covered"),
]

YES = {"y", "yes", "true", "1", "yes.", "ye"}
NO = {"n", "no", "false", "0", "no."}
STATE_SYNONYMS = {
    "tamilnadu": "Tamil Nadu", "new delhi": "Delhi", "nct of delhi": "Delhi", "delhi ncr": "Delhi",
    "pondicherry": "Puducherry", "j&k": "Jammu and Kashmir", "jammu & kashmir": "Jammu and Kashmir",
    "orissa": "Odisha", "uttaranchal": "Uttarakhand", "chattisgarh": "Chhattisgarh", "chhatisgarh": "Chhattisgarh",
    "telengana": "Telangana", "andaman & nicobar islands": "Andaman and Nicobar Islands", "bengaluru": "Karnataka",
    "karnatak": "Karnataka", "u.p.": "Uttar Pradesh", "up": "Uttar Pradesh", "mp": "Madhya Pradesh",
    "uttarkhand": "Uttarakhand", "uttrakhand": "Uttarakhand", "uttranchal": "Uttarakhand", "keralam": "Kerala",
    "west tripura": "Tripura", "pudducherry": "Puducherry", "dadra and nagar haveli and daman and diu": "Dadra and Nagar Haveli",
}
# section: academic allocation changes after admission -> never touched from admission sheets
NEVER_UPDATE = {"registration_id", "official_email_id", "email", "first_name", "section"}
# Values that are form DEFAULTS in Student Master (first Select option set on every record) - treated as
# "blank": the sheet value replaces them, and each replacement is listed in report tab Default_Overrides.
DEFAULT_VALUES = {
    "needs_accommodation": {"Yes"}, "applying_scholarship": {"Yes"}, "passport_available": {"Yes"},
    "blood_group": {"A+"}, "quota": {"General"},
}
BLANK_VALUES = {"0", "'+91", "+91", "0.0"}
RELIGION_EQ = {"hinduism": "hindu", "islam": "muslim", "christianity": "christian", "sikhism": "sikh",
               "buddhism": "buddhist", "jainism": "jain"}


# --------------------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------------------
def norm_header(h):
    h = str(h if h is not None else "")
    h = h.replace("â€™", "'").replace("’", "'").replace("‘", "'").replace("`", "'")
    h = h.split("\n")[0]
    h = re.sub(r"\s+", " ", h).strip().lower()
    h = re.sub(r"\s*/\s*", "/", h)
    return h


def clean(v):
    if v is None:
        return ""
    s = str(v).strip()
    if s.lower() in ("nan", "none", "nat", "-", "--", "na", "n/a", "nil", "null", "0000-00-00", "-1", "#n/a", "not applicable"):
        return ""
    if re.fullmatch(r"-?\d+\.0", s):
        s = s[:-2]
    return s


def digits(s):
    return re.sub(r"\D", "", s or "")


def phone10(s):
    d = digits(s)
    if len(d) > 10 and (d.startswith("91") or d.startswith("0")):
        d = d[-10:]
    return d if len(d) >= 8 else ""


def name_tokens(s):
    toks = [t for t in re.sub(r"[^a-z ]", " ", (s or "").lower()).split() if t]
    big = {t for t in toks if len(t) >= 3}
    return big or set(toks)


def name_overlap(a, b):
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def _tok_eq(a, b):
    from difflib import SequenceMatcher
    if a == b:
        return True
    if min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a)):
        return True
    return min(len(a), len(b)) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.85


def strong_name_match(a, b):
    """Same person, not just same family: the given (first) name of one must appear in the other
    and at least half of the shorter name's tokens must match (minor spelling differences allowed)."""
    def ordered(s):
        return [t for t in re.sub(r"[^a-z ]", " ", (s or "").lower()).split() if len(t) >= 3]
    A, B = ordered(a), ordered(b)
    if not A or not B:
        return False
    cov = sum(1 for t in A if any(_tok_eq(t, u) for u in B)) / min(len(A), len(B))
    given = any(_tok_eq(A[0], u) for u in B) or any(_tok_eq(B[0], u) for u in A)
    return given and cov >= 0.5


def to_date(s, dayfirst=None):
    s = clean(s)
    if not s:
        return None, ""
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}( 00:00:00)?", s):
        return s[:10], ""
    try:
        if re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", s):
            d = pd.to_datetime(s, dayfirst=bool(dayfirst))
        else:
            d = pd.to_datetime(s)
        return d.strftime("%Y-%m-%d"), ("ambiguous day/month" if dayfirst is None and re.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", s) else "")
    except Exception:
        return None, "unparseable date"


def to_float(s):
    s = clean(s)
    if not s:
        return None
    m = re.search(r"-?\d+(\.\d+)?", s.replace(",", ""))
    return float(m.group(0)) if m else None


def year_of(s):
    s = clean(s)
    m = re.findall(r"(19|20)\d{2}", s)
    if not m:
        return None
    yrs = re.findall(r"(?:19|20)\d{2}", s)
    return yrs[-1]


def valid_email(e):
    try:
        return bool(frappe.utils.validate_email_address((e or "").strip(), throw=False))
    except Exception:
        return False


def title_if_caps(s):
    return s.title() if s and s.isupper() and len(s) > 3 else s


# --------------------------------------------------------------------------------------
def run(base=None, tag="local"):
    base = base or os.path.realpath(os.path.join(frappe.get_app_path("slcm"), "..", "docs", "Admissions Data"))
    out_dir = os.path.join(base, "output", tag)
    os.makedirs(out_dir, exist_ok=True)

    meta = frappe.get_meta(DT)
    fmeta = {df.fieldname: df for df in meta.fields}

    # ---------------- Student Master snapshot
    data_fields = [df.fieldname for df in meta.fields if df.fieldtype not in
                   ("Section Break", "Column Break", "Tab Break", "Table", "Table MultiSelect", "HTML", "Button", "Heading", "Fold")]
    sms = frappe.get_all(DT, fields=["name"] + data_fields, limit_page_length=0)
    smap = {s.name: s for s in sms}
    parents_existing = defaultdict(list)
    for r in frappe.get_all("Student Parent", filters={"parenttype": DT, "parentfield": "parents"},
                            fields=["name", "parent", "relation", "first_name", "dob", "phone", "email", "address", "occupation", "annual_income", "idx"],
                            order_by="parent, idx", limit_page_length=0):
        parents_existing[r.parent].append(r)
    child_counts = {}
    for t, pf in (("UG Degree Detail", "ug_degree_details"), ("PG Degree Details", "pg_degree_details"), ("Employment", "employement_details")):
        child_counts[pf] = {r[0]: r[1] for r in frappe.db.sql(
            f"select parent, count(*) from `tab{t}` where parenttype=%s and parentfield=%s group by parent", (DT, pf))}

    states = {s.lower(): s for s in frappe.get_all("State", pluck="name")}
    cities = {c.lower(): c for c in frappe.get_all("City", pluck="name")}
    sections = {c.lower(): c for c in frappe.get_all("Section", pluck="name")} if frappe.db.exists("DocType", "Section") else {}
    genders = {g.lower(): g for g in frappe.get_all("Genders", pluck="name")}

    # match indexes
    idx = defaultdict(lambda: defaultdict(set))

    def add(key, val, name):
        if val:
            idx[key][val].add(name)

    for s in sms:
        for e in (s.official_email_id, s.email):
            e = (e or "").strip().lower()
            if e.endswith("nls.ac.in"):
                add("official", e, s.name)
            elif e:
                add("pemail", e, s.name)
        if (s.personal_email or "").strip():
            add("pemail", s.personal_email.strip().lower(), s.name)
        add("regid", re.sub(r"\s", "", (s.registration_id or "")).upper(), s.name)
        add("admit", digits(s.admit_card_number).lstrip("0"), s.name)
        add("appno", re.sub(r"\s", "", (s.application_number or "")).upper(), s.name)
        for p in (s.phone, s.alternate_phone):
            add("phone", phone10(p), s.name)
        if s.dob:
            add("namedob", (" ".join(sorted(name_tokens(s.first_name))), str(s.dob)), s.name)
        add("name_batch", (" ".join(sorted(name_tokens(s.first_name))), s.batch or ""), s.name)

    # ---------------- read sources
    col_report = []        # one row per source column
    match_rows = []        # one row per source data row
    value_issues = []
    student_vals = defaultdict(OrderedDict)  # sm name -> fieldname -> (value, source)
    student_parents = defaultdict(lambda: defaultdict(dict))  # sm -> rel -> part -> (value, src)
    student_ug = defaultdict(dict)
    student_pg = defaultdict(dict)
    student_emp = defaultdict(lambda: defaultdict(dict))
    student_att = defaultdict(OrderedDict)
    summary = []
    seen_in_sheet = defaultdict(list)

    # newest academic year first: when two sheets give a value for the same student, the newer wins
    for src in sorted(SOURCES, key=lambda s: s["ay"], reverse=True):
        path = os.path.join(base, src["file"])
        tagsrc = f'{src["file"]} [{src["sheet"]}]'
        if not os.path.exists(path):
            summary.append(OrderedDict(source=tagsrc, ay=src["ay"], rows=0, note="FILE NOT FOUND"))
            continue
        eng = "xlrd" if path.endswith(".xls") else "openpyxl"
        kw = {"ignore_workbook_corruption": True} if eng == "xlrd" else {}
        raw = pd.read_excel(path, sheet_name=src["sheet"], header=None, dtype=str, engine=eng, engine_kwargs=kw)
        if src["kind"] == "names_only":
            summary.append(OrderedDict(source=tagsrc, ay=src["ay"], rows=len(raw), note="Only a list of names - no identifiers; not used"))
            col_report.append(OrderedDict(ay=src["ay"], source=tagsrc, col_no=1, header="(names list)", filled=len(raw), target="NOT USED", field_label="", note="Names only (no ID/email); cannot be matched reliably"))
            continue
        hdr = raw.iloc[src["header"]].tolist()
        body = raw.iloc[src["header"] + 1:].reset_index(drop=True)
        if src["kind"] == "form_positional":
            hdr = POSITIONAL_LLM_2526[: len(hdr)]
        # drop fully-empty rows
        body = body[body.apply(lambda r: any(clean(x) for x in r), axis=1)].reset_index(drop=True)
        # map columns
        occ = Counter()
        colmap = []
        for j, h in enumerate(hdr):
            nh = norm_header(h)
            k = occ[nh]
            occ[nh] += 1
            target = None
            for pat, tgt, o, kinds in R:
                if kinds and src["kind"] not in kinds:
                    continue
                if o is not None and o != k:
                    continue
                if pat.search(nh):
                    target = tgt
                    break
            filled = int(body.iloc[:, j].map(lambda x: bool(clean(x))).sum()) if j < body.shape[1] else 0
            if target and target.startswith("id:email_any"):
                pass
            concept = None
            if not target:
                for pat, cname, sug, ftype, rec in MISSING_CONCEPTS:
                    if re.search(pat, nh):
                        concept = (cname, sug, ftype, rec)
                        break
            label = ""
            if target and target.split(":")[0] in ("sm", "att"):
                fn = target.split(":")[1]
                label = f"{fmeta[fn].label.strip()} ({fn})" if fn in fmeta else f"?? {fn}"
            elif target and target.startswith("id:"):
                label = {"official": "Official Email ID (official_email_id) - match key", "regid": "Student ID (registration_id) - match key",
                         "admit": "Admit Card Number (admit_card_number) - match key", "appno": "Application Number (application_number)",
                         "pemail": "Personal Email (personal_email)", "formemail": "match only", "fullname": "Full Name - match/verify only",
                         "first": "Full Name (part) - verify only", "middle": "Full Name (part)", "last": "Full Name (part)",
                         "email_any": "official_email_id if @nls.ac.in else personal_email", "clat_id": "match only"}.get(target[3:], target)
            elif target and target.startswith("par:"):
                _, rel, part = target.split(":")
                label = f"Parents table -> {rel} row ({part})"
            elif target and target.split(":")[0] in ("ug", "pg"):
                label = f"{'UG Degree Details' if target.startswith('ug') else 'PG Degree Details'} -> {target.split(':')[1]}"
            elif target and target.startswith("emp:"):
                label = f"Employment table row {target.split(':')[1]} -> {target.split(':')[2]}"
            elif target and target.startswith("addr:"):
                label = "Permanent Address (permanent_address) - composed"
            colmap.append((j, target))
            col_report.append(OrderedDict(
                ay=src["ay"], source=tagsrc, col_no=j + 1, header=str(h).replace("\n", " ")[:150], filled=filled,
                target=("MAPPED" if target else ("NOT IN DOCTYPE" if filled else "EMPTY COLUMN")),
                field_label=label or (concept[0] if concept else ""),
                note=(f"Suggest: {concept[1]} [{concept[2]}] - {concept[3]}" if concept and filled else ""),
            ))

        tier_counter = Counter()
        # names occurring more than once in this sheet can't be used for name-only matching
        name_cols = [j for j, t in colmap if t == "id:fullname"]
        sheet_name_count = Counter(" ".join(sorted(name_tokens(clean(r.iloc[name_cols[0]])))) for _, r in body.iterrows()) if name_cols else Counter()
        for i, row in body.iterrows():
            vals = defaultdict(list)
            for j, tgt in colmap:
                if not tgt or j >= len(row):
                    continue
                v = clean(row.iloc[j])
                if v:
                    vals[tgt].append((v, norm_header(hdr[j])))
            first = lambda k: vals[k][0][0] if vals.get(k) else ""
            # identities
            off = first("id:official").lower()
            ea = first("id:email_any").lower()
            pem = first("id:pemail").lower()
            if ea:
                if ea.endswith("nls.ac.in"):
                    off = off or ea
                else:
                    pem = pem or ea
            regid = re.sub(r"\s", "", first("id:regid")).upper()
            admit = digits(first("id:admit")).lstrip("0")
            appno = re.sub(r"\s", "", first("id:appno")).upper()
            femail = first("id:formemail").lower()
            fullname = first("id:fullname") or " ".join(x for x in (first("id:first"), first("id:middle"), first("id:last")) if x)
            phone = phone10(first("sm:phone"))
            dob, _ = to_date(first("sm:dob"), dayfirst=None)
            pemails = [x[0].lower() for x in vals.get("id:pemail", [])]

            # matching
            hit, method, conf, cands_note = None, "", "", ""
            tried = [
                ("Official Email", "official", off, "High"),
                ("Student ID", "regid", regid, "High"),
                ("Admit Card Number", "admit", admit, "High"),
                ("Application Number", "appno", appno, "High"),
            ]
            for e in pemails + ([pem] if pem else []) + ([femail] if femail else []):
                tried.append(("Personal Email", "pemail", e, "Medium"))
            tried.append(("Mobile + Name", "phone", phone, "Medium"))
            if dob:
                tried.append(("Name + DOB", "namedob", (" ".join(sorted(name_tokens(fullname))), dob), "Medium"))
            conflicts = []
            for label_, key, val, c in tried:
                if not val:
                    continue
                cset = idx[key].get(val)
                if not cset:
                    continue
                if len(cset) > 1:
                    conflicts.append(f"{label_}: ambiguous {sorted(cset)}")
                    continue
                cand = next(iter(cset))
                if key in ("phone", "pemail", "namedob") and not strong_name_match(fullname, smap[cand].first_name):
                    conflicts.append(f"{label_} -> {cand} but name differs ({smap[cand].first_name})")
                    continue
                if hit and cand != hit:
                    conflicts.append(f"{label_} points to {cand} (row matched {hit} by {method})")
                    continue
                if not hit:
                    hit, method, conf = cand, label_, c
            # low-confidence: unique name within batch
            if not hit and fullname:
                batch = src["ay"][:4] if src["ay"] != "2022-23" else ""
                cset = idx["name_batch"].get((" ".join(sorted(name_tokens(fullname))), batch)) if batch else None
                if cset and len(cset) == 1:
                    cand = next(iter(cset))
                    prog_ok = bool(src["prog"]) and (smap[cand].programme_of_study or "").startswith(src["prog"])
                    unique_in_sheet = sheet_name_count.get(" ".join(sorted(name_tokens(fullname))), 0) <= 1 or not name_cols
                    if prog_ok and unique_in_sheet:
                        # exact full-name tokens + same batch + same programme -> accepted
                        hit, method, conf = cand, "Name + Batch + Programme", "Medium"
                    else:
                        cands_note = f"Possible (name only, batch {batch}): {cand} ({smap[cand].programme_of_study})"
            if hit and name_overlap(fullname, smap[hit].first_name) == 0 and fullname:
                conf = "Review - name mismatch"
            if hit:
                seen_in_sheet[(tagsrc, hit)].append(i)
            tier_counter[method or "UNMATCHED"] += 1
            sm = smap.get(hit) if hit else None
            bcheck = ""
            if sm and src["ay"] != "2022-23" and sm.batch and str(sm.batch) != src["ay"][:4]:
                bcheck = f"Batch mismatch: SM batch {sm.batch} vs sheet AY {src['ay']}"
            match_rows.append(OrderedDict(
                ay=src["ay"], source=tagsrc, row_no=i + src["header"] + 3 if src["header"] is not None else i + 1,
                sheet_name=fullname, sheet_official_email=off, sheet_student_id=regid, sheet_admit_card=admit,
                sheet_application_no=appno, sheet_personal_email=pem or (pemails[0] if pemails else ""), sheet_mobile=phone,
                matched_student=hit or "", sm_registration_id=sm.registration_id if sm else "", sm_name=sm.first_name if sm else "",
                sm_programme=sm.programme_of_study if sm else "", sm_batch=sm.batch if sm else "",
                match_method=method or "UNMATCHED", confidence=conf, warnings="; ".join(conflicts + ([bcheck] if bcheck else []) + ([cands_note] if cands_note else [])),
            ))
            usable = hit and conf in ("High", "Medium")
            if not usable:
                continue

            def put(store, key, value, srcname):
                if value in (None, ""):
                    return
                if key not in store:
                    store[key] = (value, srcname)

            # ---- fields
            for tgt, items in vals.items():
                kind = tgt.split(":")[0]
                for v, nh in items:
                    if kind == "sm":
                        fn = tgt[3:]
                        nv, issue = convert(fn, v, nh, fmeta, states, cities, sections, genders)
                        if issue:
                            value_issues.append(OrderedDict(ay=src["ay"], source=tagsrc, student=hit, field=fn, sheet_value=v, issue=issue))
                        if nv not in (None, ""):
                            if fn == "where_did_you_hear_about_the_programme" and vals.get("id:none"):
                                pass
                            put(student_vals[hit], fn, nv, tagsrc)
                            break  # first valid value in column order wins
                    elif kind == "att":
                        if v.lower().startswith(("http", "/sites", "/files")):
                            put(student_att[hit], tgt[4:], v, tagsrc)
                        break
                    elif kind == "par":
                        _, rel, part = tgt.split(":")
                        put(student_parents[hit][rel], part, v, tagsrc)
                        break
                    elif kind == "ug":
                        put(student_ug[hit], tgt[3:], v, tagsrc)
                        break
                    elif kind == "pg":
                        put(student_pg[hit], tgt[3:], v, tagsrc)
                        break
                    elif kind == "emp":
                        _, n, part = tgt.split(":")
                        put(student_emp[hit][n], part, v, tagsrc)
                        break
            # id-derived SM fields
            if admit:
                put(student_vals[hit], "admit_card_number", first("id:admit").strip().replace(".0", ""), tagsrc)
            if appno:
                put(student_vals[hit], "application_number", first("id:appno").strip(), tagsrc)
            pe = pem or (pemails[0] if pemails else "")
            if pe and "@" in pe and not pe.endswith("nls.ac.in") and valid_email(pe):
                put(student_vals[hit], "personal_email", pe, tagsrc)
            # where did you hear: append "please mention"
            # composed permanent address
            parts = [first("addr:full"), first("addr:house"), first("addr:street")]
            if any(parts):
                tail = [first("sm:city") or first("par:Father:city"), first("sm:state") or first("par:Father:state"), first("sm:pincode") or first("par:Father:pin")]
                addr = ", ".join(p for p in parts if p)
                for t in tail:
                    if t and t.lower() not in addr.lower():
                        addr += ", " + t
                put(student_vals[hit], "permanent_address", addr, tagsrc)
            if src["kind"] in ("clat24llm",) or "university from which you have obtai" in " ".join(norm_header(h) for h in hdr):
                if student_ug[hit]:
                    put(student_ug[hit], "program", "LL.B.", tagsrc)
            if src["prog"] and src["prog"].startswith("Ph.D") and fullname:
                pass

        summary.append(OrderedDict(
            source=tagsrc, ay=src["ay"], rows=len(body),
            **{k: tier_counter.get(k, 0) for k in ("Official Email", "Student ID", "Admit Card Number", "Application Number", "Personal Email", "Mobile + Name", "Name + DOB", "Name + Batch + Programme")},
            unmatched=tier_counter.get("UNMATCHED", 0),
            match_pct=round(100 * (len(body) - tier_counter.get("UNMATCHED", 0)) / len(body), 1) if len(body) else 0,
        ))

    for f, sh in EMPTY_SHEETS:
        summary.append(OrderedDict(source=f"{f} [{sh}]", ay=f.split("/")[0][3:], rows=0, note="Empty sheet"))

    # ---------------- duplicates within same sheet
    dup_rows = [OrderedDict(source=k[0], student=k[1], sheet_rows=", ".join(str(x) for x in v)) for k, v in seen_in_sheet.items() if len(v) > 1]

    # ---------------- build update rows (fill-blank only) + conflicts
    conflicts = []
    upd_rows = []
    fill_counter = Counter()

    def same(fn, a, b):
        a, b = str(a or "").strip(), str(b or "").strip()
        if fn in ("phone", "alternate_phone", "emergency_contact"):
            return phone10(a) == phone10(b)
        df = fmeta.get(fn)
        if df and df.fieldtype in ("Float", "Percent", "Currency", "Int", "Check"):
            try:
                return abs(float(a) - float(b)) < 0.01
            except Exception:
                pass
        if fn == "religion":
            a, b = RELIGION_EQ.get(a.lower(), a), RELIGION_EQ.get(b.lower(), b)
        if fn == "pincode":
            return digits(a) == digits(b)
        return re.sub(r"[^a-z0-9]", "", a.lower()) == re.sub(r"[^a-z0-9]", "", b.lower())

    default_overrides = []

    for name, fields in student_vals.items():
        sm = smap[name]
        row = OrderedDict()
        for fn, (v, srcname) in fields.items():
            if fn in NEVER_UPDATE:
                continue
            cur = sm.get(fn)
            ft = fmeta[fn].fieldtype
            blank = cur in (None, "") or str(cur).strip() in BLANK_VALUES
            if ft in ("Float", "Percent", "Currency", "Int") and not cur:
                blank = True
            if ft == "Check":
                blank = not cur  # only ever set 0->1
                if str(v) != "1":
                    continue
            is_default = (not blank) and str(cur) in DEFAULT_VALUES.get(fn, ())
            if is_default and same(fn, cur, v):
                continue
            if blank or is_default:
                row[fn] = v
                fill_counter[fn] += 1
                if is_default:
                    default_overrides.append(OrderedDict(student=name, registration_id=sm.registration_id, field=fn,
                                                         current_default_value=str(cur), new_value=str(v), source=srcname))
            elif not same(fn, cur, v):
                conflicts.append(OrderedDict(student=name, registration_id=sm.registration_id, field=fn,
                                             field_label=fmeta[fn].label, current_value=str(cur), sheet_value=str(v), source=srcname))
        if row:
            row["__name"] = name
            upd_rows.append(row)

    # ---------------- parents
    parent_out = []
    parent_changes = 0
    parent_email_cleared = []
    for name, rels in student_parents.items():
        existing = parents_existing.get(name, [])
        rows = [dict(r) for r in existing]
        changed = False
        for rel in ("Father", "Mother", "Guardian"):
            p = rels.get(rel)
            if not p:
                continue
            pname = (p.get("name") or ("", ""))[0] or " ".join(x[0] for x in (p.get("first"), p.get("middle"), p.get("last")) if x and x[0])
            if not pname:
                continue
            addr = (p.get("address") or ("", ""))[0]
            extra = [p[k][0] for k in ("house", "street", "city", "state", "pin") if p.get(k)]
            if extra:
                addr = ", ".join([addr] + extra if addr else extra)
            pemail_ = (p.get("email") or ("",))[0].lower().strip()
            if pemail_ and not valid_email(pemail_):
                value_issues.append(OrderedDict(ay="", source=(p.get("email") or ("", ""))[1], student=name, field=f"parents[{rel}].email", sheet_value=pemail_, issue="invalid email - skipped"))
                pemail_ = ""
            newv = {"phone": phone10((p.get("phone") or ("",))[0]) or (p.get("phone") or ("",))[0][:140],
                    "email": pemail_, "occupation": (p.get("occupation") or ("",))[0][:140],
                    "address": addr}
            ex = next((r for r in rows if r["relation"] == rel), None)
            if ex:
                for k, v in newv.items():
                    if v and not ex.get(k):
                        ex[k] = v
                        changed = True
                    elif v and ex.get(k) and not same(k if k == "phone" else "x", ex.get(k), v):
                        conflicts.append(OrderedDict(student=name, registration_id=smap[name].registration_id, field=f"parents[{rel}].{k}",
                                                     field_label=f"{rel} {k}", current_value=str(ex.get(k)), sheet_value=v, source=(p.get(k) or p.get("name") or ("", ""))[1]))
            else:
                rows.append(dict(name="", relation=rel, first_name=pname.strip(), dob=None, annual_income=None, **newv))
                changed = True
        if changed:
            parent_changes += 1
            for r in rows:
                # existing rows must be re-sent (update replaces the table); invalid stored e-mails would
                # block the save, so they are cleared and listed
                if r.get("email") and not valid_email(r["email"]):
                    parent_email_cleared.append(OrderedDict(student=name, registration_id=smap[name].registration_id, relation=r["relation"],
                                                            parent_name=r.get("first_name"), invalid_email_cleared=r["email"]))
                    r["email"] = ""
            for k, r in enumerate(rows):
                parent_out.append(OrderedDict([
                    ("ID", name if k == 0 else ""),
                    ("ID (Parents)", r.get("name") or ""),
                    ("Relationship (Parents)", r["relation"]),
                    ("Full Name (Parents)", r.get("first_name") or ""),
                    ("Date of Birth (Parents)", str(r.get("dob") or "") if r.get("dob") else ""),
                    ("Phone Number (Parents)", r.get("phone") or ""),
                    ("Email ID (Parents)", r.get("email") or ""),
                    ("Address (Parents)", r.get("address") or ""),
                    ("Occupation (Parents)", r.get("occupation") or ""),
                    ("Annual Income (Parents)", r.get("annual_income") or ""),
                    ("Student (for reference - not imported)", smap[name].first_name),
                ]))

    # ---------------- UG / PG / Employment (only where table currently empty)
    qual_out = []
    qual_skipped = []
    for name in sorted(set(student_ug) | set(student_pg) | set(student_emp)):
        ug, pg, emp = student_ug.get(name, {}), student_pg.get(name, {}), student_emp.get(name, {})
        rows = []
        if ug and (ug.get("college") or ug.get("program")):
            if child_counts["ug_degree_details"].get(name):
                qual_skipped.append(OrderedDict(student=name, table="UG Degree Details", reason="already has rows"))
            else:
                rows.append(("ug", ug))
        if pg and (pg.get("college") or pg.get("program")):
            if child_counts["pg_degree_details"].get(name):
                qual_skipped.append(OrderedDict(student=name, table="PG Degree Details", reason="already has rows"))
            else:
                rows.append(("pg", pg))
        emps = [emp[n] for n in sorted(emp) if emp[n].get("employers_name")]
        if emps:
            if child_counts["employement_details"].get(name):
                qual_skipped.append(OrderedDict(student=name, table="Employment", reason="already has rows"))
            else:
                rows += [("emp", e) for e in emps]
        if not rows:
            continue
        ugs = [r for t, r in rows if t == "ug"]
        pgs = [r for t, r in rows if t == "pg"]
        ems = [r for t, r in rows if t == "emp"]
        for k in range(max(len(ugs), len(pgs), len(ems))):
            g = lambda d, f: (d.get(f) or ("", ""))[0] if d else ""
            u = ugs[k] if k < len(ugs) else None
            p = pgs[k] if k < len(pgs) else None
            e = ems[k] if k < len(ems) else None
            qual_out.append(OrderedDict([
                ("ID", name if k == 0 else ""),
                ("Name of Degree (UG) (UG Degree Details)", g(u, "program")),
                ("Year Of Completion (UG degree) (UG Degree Details)", year_of(g(u, "year")) or g(u, "year")),
                ("College / University (UG degree) (UG Degree Details)", g(u, "college")),
                ("University (UG Degree) (UG Degree Details)", g(u, "board")),
                ("Percentage/CGPA Obtained (UG degree) (UG Degree Details)", to_float(g(u, "cgpa")) if u and to_float(g(u, "cgpa")) is not None else ""),
                ("If CGPA, Maximum CPGA (UG Degree) (UG Degree Details)", to_float(g(u, "max")) if u and to_float(g(u, "max")) is not None else ""),
                ("UG Degree Certificate / Bonafide (UG Degree Details)", g(u, "cert")),
                ("Transcripts / Marksheets (UG Degree Details)", g(u, "marks")),
                ("Name of Degree (PG) (PG Degree Details)", g(p, "program")),
                ("Year Of Completion (PG degree) (PG Degree Details)", year_of(g(p, "year")) or g(p, "year")),
                ("College/University (PG degree) (PG Degree Details)", g(p, "college")),
                ("University (PG Degree) (PG Degree Details)", g(p, "board")),
                ("Percentage/CGPA Obtained (PG degree) (PG Degree Details)", to_float(g(p, "cgpa")) if p and to_float(g(p, "cgpa")) is not None else ""),
                ("If CGPA, Maximum CPGA (PG Degree) (PG Degree Details)", to_float(g(p, "max")) if p and to_float(g(p, "max")) is not None else ""),
                ("PG Degree Certificate / Bonafide (PG Degree Details)", g(p, "cert")),
                ("Transcripts / Marksheets (PG Degree Details)", g(p, "marks")),
                ("Employer's Name (Employement Details)", g(e, "employers_name")),
                ("Designation in the Organization (Employement Details)", g(e, "designation_in_the_organization")),
                ("Duration of the Employment (Employement Details)", g(e, "duration_of_the_employment")),
            ]))

    # ---------------- attachments (fill blank)
    att_out = []
    att_fill = Counter()
    for name, atts in student_att.items():
        row = OrderedDict(ID=name)
        for fn, (v, _s) in atts.items():
            if fn in fmeta and not smap[name].get(fn):
                row[f"{fmeta[fn].label.strip()} ({fn})"] = v
                att_fill[fn] += 1
        if len(row) > 1:
            att_out.append(row)

    # ---------------- write Data Import files
    main_fields = [fn for fn in fmeta if fill_counter.get(fn)]
    main_out = []
    for r in upd_rows:
        o = OrderedDict(ID=r["__name"])
        for fn in main_fields:
            v = r.get(fn, "")
            o[f"{fmeta[fn].label.strip()} ({fn})"] = v
        main_out.append(o)

    def write_import(fname, rows, sheet="Student Master"):
        p = os.path.join(out_dir, fname)
        df = pd.DataFrame(rows)
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

    write_import("1_Student_Master_Update.xlsx", main_out)
    write_import("2_Student_Parents_Update.xlsx", [{k: v for k, v in r.items() if not k.startswith("Student (")} for r in parent_out])
    write_import("3_Student_Qualification_Update.xlsx", qual_out)
    write_import("4_Student_Documents_Update.xlsx", att_out)

    # ---------------- report workbook
    impact = []
    for fn, df_ in fmeta.items():
        if df_.fieldtype in ("Section Break", "Column Break", "Tab Break", "HTML"):
            continue
        cur = sum(1 for s in sms if s.get(fn) not in (None, "", 0)) if fn in data_fields else None
        add_ = fill_counter.get(fn, 0) + att_fill.get(fn, 0)
        if add_ or fn in ("dob", "gender", "personal_email", "admit_card_number", "application_number"):
            impact.append(OrderedDict(fieldname=fn, label=df_.label, fieldtype=df_.fieldtype,
                                      filled_now=cur, will_be_filled=add_, filled_after=(cur or 0) + add_, total_students=len(sms)))
    impact.append(OrderedDict(fieldname="parents (table)", label="Parents", fieldtype="Table", filled_now=len(parents_existing),
                              will_be_filled=parent_changes, filled_after="", total_students=len(sms)))
    impact.append(OrderedDict(fieldname="ug/pg/employment (tables)", label="Qualifications", fieldtype="Table", filled_now="",
                              will_be_filled=len({r['ID'] for r in qual_out if r['ID']}), filled_after="", total_students=len(sms)))

    # missing-field consolidated
    miss = defaultdict(lambda: dict(sheets=set(), headers=set(), values=0, sug="", ftype="", rec=""))
    for c in col_report:
        if c["target"] != "NOT IN DOCTYPE":
            continue
        concept = c["field_label"] or f"(unclassified) {c['header'][:60]}"
        m = miss[concept]
        m["sheets"].add(c["source"])
        m["headers"].add(c["header"][:80])
        m["values"] += c["filled"]
        if c["note"]:
            seg = c["note"].replace("Suggest: ", "")
            m["sug"] = seg
    missing_rows = []
    for k, m in sorted(miss.items(), key=lambda kv: -kv[1]["values"]):
        missing_rows.append(OrderedDict(concept=k, values_in_sheets=m["values"], sheet_count=len(m["sheets"]),
                                        suggestion=m["sug"], source_headers=" | ".join(sorted(m["headers"]))[:1000],
                                        sheets=" | ".join(sorted(m["sheets"]))[:1000]))

    doctype_issues = [
        OrderedDict(area="Karnataka category", issue="ka_ais_child label = 'Child of CAPF employee with Karnataka domicile' and ka_capf_child label = 'Child of Central Armed Police Force employee' - both mean CAPF. Source forms have 4 options: Defence, Karnataka State Govt employee, Karnataka-cadre AIS, CAPF.", impact="'Child of Karnataka State Govt employee' answers have no field; ka_ais_child is effectively a duplicate.", recommendation="Relabel ka_ais_child to 'Child of Karnataka State Government employee' (or add ka_state_govt_child)."),
        OrderedDict(area="Karnataka category", issue="ka_study_7yrs says 'not less than 7 years'; 2023-25 source forms ask 'not less than 10 years'.", impact="Value imported as-is; meaning differs by year.", recommendation="Keep label generic ('... required years') or add note."),
        OrderedDict(area="District", issue="district is a Link to City (944 Indian cities). Many sheet districts are not in City master.", impact="Those values are skipped (see Value_Issues).", recommendation="Create missing City records or change district to Data."),
        OrderedDict(area="State", issue="State master contains both 'Orissa' and 'Odisha'; sheets use variants (Tamilnadu, New Delhi...).", impact="Normalised via synonyms; unknown values skipped.", recommendation="Remove duplicate state 'Orissa'."),
        OrderedDict(area="Class X", issue="No 'Class X examination name' field (Class XII has one).", impact="Column not imported.", recommendation="Add class_x_exam_name if needed."),
        OrderedDict(area="Parents", issue="Student Parent has no employer/office address; local guardian vs emergency contact not distinguished.", impact="Father/Mother company & occupation address not imported; emergency contacts stored as Guardian rows.", recommendation="Add fields if required."),
        OrderedDict(area="Identity", issue="No field for Aadhaar / ID-proof number, ID-proof type, mother tongue, caste, visa number.", impact="Present in most sheets but not imported.", recommendation="Add fields (restrict Aadhaar permission)."),
        OrderedDict(area="Entrance exam", issue="Only final_* summary fields exist; NLSAT Part A/B marks, percentiles, ranks, test city, interview score are not stored.", impact="Not imported.", recommendation="Add an 'Entrance Exam' section if audit needs it."),
        OrderedDict(area="Legacy (AY 2022-23 dump)", issue="Discontinued / ICCR / Hostel exemption / PhD status / Koha library id / Date of joining have no fields.", impact="Not imported.", recommendation="Add fields or map Discontinued -> student_status after review."),
        OrderedDict(area="Qualifications", issue="UG/PG child rows have 'reqd' attachment fields (ignored for Student Master by OPTIONAL_CHILD_TABLES).", impact="Import works even without certificate files.", recommendation="None."),
        OrderedDict(area="Labels", issue="first_name label is 'Full Name'; quota label is 'Whether SC/ST/OBC-NCL' but options include General/EWS/NRI; present_address label typo 'Comminication Address'; 'employement_details' / 'experince' typos.", impact="Cosmetic.", recommendation="Fix labels."),
    ]

    readme = [
        ["Admissions Data -> Student Master: mapping & import pack", ""],
        ["Generated", frappe.utils.now()],
        ["Site", frappe.local.site],
        ["Student Master records in DB", len(sms)],
        ["", ""],
        ["MATCH ORDER", "1 Official Email (official_email_id / @nls.ac.in email) -> 2 Student ID (registration_id) -> 3 Admit Card Number -> 4 Application Number -> 5 Personal e-mail (name must overlap) -> 6 Mobile + name -> 7 Name + DOB -> 8 exact full name + same batch + same programme. Other name-only hits are NOT imported (Unmatched_Review). Tiers 1-4 = High confidence, 5-8 = Medium (check Match_Results)."],
        ["UPDATE RULE", "Only blank fields in Student Master are filled. Existing values are never overwritten; differences are listed in 'Conflicts'. registration_id, official_email_id, email, first_name, section, registration_status and fee fields are never touched."],
        ["DEFAULT VALUES", "needs_accommodation / applying_scholarship / passport_available are 'Yes' on every record, blood_group 'A+' on ~2/3 and quota 'General' on ~95% - these are form defaults, not data. Sheet values replace them; every replacement is listed in 'Default_Overrides' - review / delete rows there (and in file 1) if a default was in fact correct. Numeric 0 and phone '0' are treated as blank."],
        ["", ""],
        ["FILES", ""],
        ["1_Student_Master_Update.xlsx", "Data Import > DocType: Student Master > Import Type: Update Existing Records. Personal, contact, address, school, entrance-exam fields."],
        ["2_Student_Parents_Update.xlsx", "Same, Update Existing Records. Contains ALL existing parent rows (with their row ID) + new rows; Frappe replaces the whole child table on update, so do not delete rows from this file."],
        ["3_Student_Qualification_Update.xlsx", "Same. Only students whose UG/PG/Employment tables are currently empty."],
        ["4_Student_Documents_Update.xlsx", "OPTIONAL. Attach fields with external links (old S3 portal + Google Drive). Links are stored as-is (not downloaded); Drive links need sharing permission. Recommend downloading files first."],
        ["", ""],
        ["PRODUCTION", "Student Master IDs (STUD-2026-xxxxx) are generated per site. Do NOT import the local files on production unless production is a copy of this database. Re-run the generator on production: bench --site <site> execute slcm.scratch.admissions_mapping.run --kwargs \"{'base': '<path to Admissions Data>', 'tag': 'production'}\""],
        ["Before import", "Take a backup: bench --site <site> backup. Import file 1 first, then 2, 3, (4). Use 'Don't send emails' and check the Data Import log."],
    ]

    rp = os.path.join(out_dir, "Admissions_Mapping_Report.xlsx")
    with pd.ExcelWriter(rp, engine="openpyxl") as xw:
        pd.DataFrame(readme, columns=["Item", "Detail"]).to_excel(xw, index=False, sheet_name="README")
        pd.DataFrame(summary).fillna("").to_excel(xw, index=False, sheet_name="Summary")
        pd.DataFrame(impact).to_excel(xw, index=False, sheet_name="Field_Fill_Impact")
        pd.DataFrame(missing_rows).to_excel(xw, index=False, sheet_name="Missing_In_Doctype")
        pd.DataFrame(doctype_issues).to_excel(xw, index=False, sheet_name="Doctype_Issues")
        pd.DataFrame(col_report).to_excel(xw, index=False, sheet_name="Column_Mapping")
        pd.DataFrame(match_rows).to_excel(xw, index=False, sheet_name="Match_Results")
        pd.DataFrame([m for m in match_rows if m["match_method"] == "UNMATCHED" or m["confidence"] not in ("High", "Medium")]).to_excel(xw, index=False, sheet_name="Unmatched_Review")
        pd.DataFrame(conflicts).to_excel(xw, index=False, sheet_name="Conflicts")
        pd.DataFrame(default_overrides).to_excel(xw, index=False, sheet_name="Default_Overrides")
        pd.DataFrame(parent_email_cleared).to_excel(xw, index=False, sheet_name="Parent_Email_Cleared")
        pd.DataFrame(value_issues).to_excel(xw, index=False, sheet_name="Value_Issues")
        pd.DataFrame(dup_rows).to_excel(xw, index=False, sheet_name="Duplicate_Rows")
        pd.DataFrame(qual_skipped).to_excel(xw, index=False, sheet_name="Qualification_Skipped")
        for ws in xw.sheets.values():
            for c in ws[1]:
                c.font = c.font.copy(bold=True)
            ws.freeze_panes = "A2"
            for col in ws.columns:
                w = max([len(str(col[0].value or ""))] + [min(60, len(str(c.value or ""))) for c in col[1:200]])
                ws.column_dimensions[col[0].column_letter].width = min(60, max(10, w + 2))

    # console summary
    tot = sum(s.get("rows", 0) for s in summary)
    unm = sum(s.get("unmatched", 0) for s in summary)
    print("OUT", out_dir)
    print("source rows", tot, "unmatched", unm, "students with updates", len(upd_rows), "fields", len(main_fields))
    print("parents students", parent_changes, "rows", len(parent_out), "qual rows", len(qual_out), "att students", len(att_out))
    print("conflicts", len(conflicts), "value issues", len(value_issues), "dups", len(dup_rows), "default overrides", Counter(d["field"] for d in default_overrides))
    for s in summary:
        print(" ", s)
    print("fill", dict(fill_counter.most_common()))
    print("issues by field", Counter(v["field"] for v in value_issues).most_common(20))
    print("conflicts by field", Counter(c["field"] for c in conflicts).most_common(30))
    # dry validation of the generated files (nothing is saved)
    validate_files(base, tag)


# --------------------------------------------------------------------------------------
def convert(fn, v, nh, fmeta, states, cities, sections, genders):
    """Return (value, issue). value '' / None = not importable."""
    df = fmeta.get(fn)
    if not df:
        return None, f"field {fn} not in doctype"
    ft = df.fieldtype
    lv = v.strip().lower()
    if fn in ("phone", "alternate_phone", "emergency_contact"):
        p = phone10(v)
        return (p, "") if p else (None, "invalid phone")
    if fn == "dob" or ft == "Date":
        dayfirst = True if "dd-mm" in nh else (False if "mm-dd" in nh else None)
        d, issue = to_date(v, dayfirst)
        return d, issue
    if fn == "gender":
        g = {"m": "male", "f": "female", "transgender": "other", "others": "other"}.get(lv, lv)
        return (genders[g], "") if g in genders else (None, f"gender '{v}' not in Genders")
    if fn == "blood_group":
        b = lv.replace(" ", "").replace("positive", "+").replace("negative", "-").replace("ve", "").replace("(", "").replace(")", "").upper()
        b = b.replace("0", "O")
        opts = [o for o in (df.options or "").split("\n") if o]
        return (b, "") if b in opts else (None, f"blood group '{v}' not an option")
    if fn == "quota":
        u = v.upper().replace(" ", "")
        if "SC/ST/SAP" in u:
            return None, f"ambiguous category '{v}'"
        if "OBC" in u and "NCL" in u:
            return "OBC-NCL", ""
        for key, out in (("OBC", "OBC"), ("EWS", "EWS"), ("NRI", "NRI"), ("SC", "SC"), ("ST", "ST"), ("GEN", "General"), ("UR", "General"), ("OPEN", "General"), ("UNRESERVED", "General"), ("NOTAPPLICABLE", "NA")):
            if u.startswith(key):
                return out, ""
        if lv in ("no", "none"):
            return None, ""
        return None, f"category '{v}' not an option"
    if fn == "state":
        c = re.sub(r"\(.*?\)|[.]", "", lv).strip()
        c = re.sub(r"^(ut|u\.t\.)\s+", "", c).strip()
        s = STATE_SYNONYMS.get(c, c)
        if s.lower() in states:
            return states[s.lower()], ""
        nospace = {k.replace(" ", ""): val for k, val in states.items()}
        if s.lower().replace(" ", "") in nospace:
            return nospace[s.lower().replace(" ", "")], ""
        return None, f"state '{v}' not in State master"
    if fn == "district":
        if lv in cities:
            return cities[lv], ""
        for suf in (" urban", " rural", " district"):
            if lv.endswith(suf) and lv[: -len(suf)] in cities:
                return cities[lv[: -len(suf)]], ""
        return None, f"district '{v}' not in City master"
    if fn == "section":
        return (sections[lv], "") if lv in sections else (None, f"section '{v}' not in Section master")
    if fn == "phd_programme":
        if "inter" in lv:
            return "Interdisciplinary", ""
        if "law" in lv:
            return "Law", ""
        return None, f"phd programme '{v}' not an option"
    if fn == "exam_attended":
        return ("Attended", "") if lv in YES else (("Not Attended", "") if lv in NO else (None, f"'{v}'"))
    if ft == "Check":
        if lv in YES:
            return 1, ""
        if lv in NO:
            return 0, ""
        return None, f"'{v}' not yes/no"
    if ft == "Select":
        opts = [o for o in (df.options or "").split("\n") if o]
        if set(opts) >= {"Yes", "No"}:
            if lv in YES:
                return "Yes", ""
            if lv in NO:
                return "No", ""
            return None, f"'{v}' not Yes/No"
        for o in opts:
            if o.lower() == lv:
                return o, ""
        return None, f"'{v}' not in options {opts}"
    if ft in ("Float", "Percent", "Currency", "Int"):
        f = to_float(v)
        if f is None:
            return None, f"'{v}' not numeric"
        if "%" in v or ft == "Percent":
            pass
        return f, ""
    if fn.endswith("completion_year"):
        y = year_of(v)
        return (y, "") if y else (None, f"'{v}' no year")
    if fn == "pincode":
        d = digits(v.split(".")[0])
        return (d, "") if len(d) == 6 else (v.strip() if len(d) >= 4 else None, "" if len(d) >= 4 else f"pincode '{v}' invalid")
    if fn in ("nationality", "religion"):
        n = title_if_caps(v.strip())
        if fn == "nationality" and n.lower() in ("india",):
            n = "Indian"
        return n, ""
    maxlen = (df.length or 140) if ft == "Data" else 0
    if maxlen and len(v.strip()) > maxlen:
        if fn in ("annual_income", "annual_income_candidate"):
            m = re.match(r"\D*([\d,]+(\.\d+)?)", v)
            if m and len(m.group(1)) <= maxlen:
                return m.group(1), f"trimmed to amount (original: {v[:80]})"
        return None, f"longer than field length {maxlen} ({len(v.strip())} chars)"
    return v.strip(), ""


# --------------------------------------------------------------------------------------
def validate_files(base=None, tag="local"):
    """DRY validation - nothing is saved. Parses each import file with Frappe's own Data Import
    parser (same as the Data Import preview) and runs the document validators in memory."""
    from frappe.core.doctype.data_import import importer as imod
    from frappe.core.doctype.data_import.importer import Importer

    # read the local xlsx as bytes (the stock reader only reads File docs, or text in console mode)
    imod.ImportFile.read_file = lambda self, fp: (open(fp, "rb").read(), os.path.splitext(fp)[1][1:])

    base = base or os.path.realpath(os.path.join(frappe.get_app_path("slcm"), "..", "docs", "Admissions Data"))
    out_dir = os.path.join(base, "output", tag)
    results = []
    rows_out = []
    for fname in ("1_Student_Master_Update.xlsx", "2_Student_Parents_Update.xlsx",
                  "3_Student_Qualification_Update.xlsx", "4_Student_Documents_Update.xlsx"):
        path = os.path.join(out_dir, fname)
        di = frappe.get_doc(doctype="Data Import", import_type="Update Existing Records", reference_doctype=DT)
        imp = Importer(DT, data_import=di, file_path=path, import_type="Update Existing Records")
        prev = imp.import_file.get_data_for_import_preview()
        warns = prev.get("warnings") or []
        payloads = imp.import_file.get_payloads_for_import()
        errors = Counter()
        samples = []
        for p in payloads:
            d = p.doc
            sent = set(d.keys())
            try:
                doc = frappe.get_doc(DT, d.get("name"))
            except Exception as e:
                rows_out.append(OrderedDict(file=fname, student=d.get("name"), registration_id="", category="IMPORT - ID not found", detail=str(e)[:200]))
                errors["IMPORT"] += 1
                continue
            doc.update(d)
            checks = [doc._fix_numeric_types, doc._validate_length, doc._validate_data_fields, doc._validate_selects,
                      doc._validate_non_negative, doc._validate_mandatory]
            for ch in doc.get_all_children():
                checks += [ch._validate_length, ch._validate_selects, ch._validate_data_fields]
            for fn_ in checks:
                try:
                    fn_()
                except Exception as e:
                    msg = re.sub(r"<[^>]+>", "", str(e))[:200]
                    rows_out.append(OrderedDict(file=fname, student=doc.name, registration_id=doc.registration_id, category="IMPORT - value rejected", detail=msg))
                    errors["IMPORT"] += 1
                finally:
                    frappe.clear_messages()
            bad = doc.get_invalid_links()
            for link in (bad[0] if bad else []) + (bad[1] if bad and len(bad) > 1 else []):
                fieldname = link[0]
                cat = "IMPORT - invalid link from sheet" if fieldname in sent else "PRE-EXISTING - broken link already on record (save will fail until fixed)"
                rows_out.append(OrderedDict(file=fname, student=doc.name, registration_id=doc.registration_id, category=cat,
                                            detail=f"{fieldname} = {link[1]} ({link[2]})"))
                errors[cat.split(" ")[0]] += 1
        results.append((fname, len(payloads), len(warns), dict(errors), [str(w.get("message", w))[:200] for w in warns[:8]]))
    frappe.db.rollback()
    vdf = pd.DataFrame(rows_out)
    summary = pd.DataFrame([OrderedDict(file=r[0], documents=r[1], parser_warnings=r[2],
                                        import_errors=r[3].get("IMPORT", 0), pre_existing_link_errors=r[3].get("PRE-EXISTING", 0),
                                        warnings_sample=" | ".join(r[4])) for r in results])
    blockers = pd.DataFrame()
    if not vdf.empty:
        pre = vdf[vdf.category.str.startswith("PRE-EXISTING")]
        if not pre.empty:
            blockers = pre.drop_duplicates(["student", "detail"])[["student", "registration_id", "detail"]].sort_values("student")
    with pd.ExcelWriter(os.path.join(out_dir, "Import_Validation.xlsx"), engine="openpyxl") as xw:
        summary.to_excel(xw, index=False, sheet_name="Summary")
        blockers.to_excel(xw, index=False, sheet_name="Fix_Before_Import")
        vdf.to_excel(xw, index=False, sheet_name="All_Errors")
        for ws in xw.sheets.values():
            ws.freeze_panes = "A2"
            for col in ws.columns:
                ws.column_dimensions[col[0].column_letter].width = min(70, max(12, max(len(str(c.value or "")) for c in col[:200]) + 2))
    for r in results:
        print("FILE", r[0], "docs", r[1], "parser-warnings", r[2], "errors", r[3])
        for s in r[4]:
            print("   W:", s)
    if not vdf.empty:
        print(vdf.groupby(["category"]).size().to_string())
        print(vdf[vdf.category.str.startswith("IMPORT")].head(15).to_string(max_colwidth=90))
        print("pre-existing by field:", Counter(x.split(" = ")[0] for x in blockers.get("detail", [])))
        print("students blocked:", blockers["student"].nunique() if not blockers.empty else 0)
