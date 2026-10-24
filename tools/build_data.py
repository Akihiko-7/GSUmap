"""Build data/places.json and data/paths.geojson for GSU Compass.

Positions come from the Gombe Life campus plan, which was built from OpenStreetMap (named points inside the mapped
university boundary) plus the owner's corrections. They are stored there as local metres around an origin
(x east, z south), so they are converted to latitude and longitude here.

Paths: every OSM road and footway within 350 m of the campus. Ways that cross the university wall anywhere other than
the two open gates (the main gate and gate 3) are cut at the wall, because people cannot walk through it.
Source: the cached Overpass extract from Gombe Life if it is on this machine, otherwise a fresh Overpass query.

Usage: python tools/build_data.py [path/to/osm_features.json]
"""
import json
import math
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
GOMBE_LIFE_OSM = Path.home() / "Desktop" / "Gombe-Life" / "data" / "raw" / "osm_features.json"

# ---------------------------------------------------------------- projection (same as Gombe Life)
ORIGIN = (10.2897, 11.1673)
_rad = math.radians(ORIGIN[0])
M_LAT = 111132.92 - 559.82 * math.cos(2 * _rad) + 1.175 * math.cos(4 * _rad)
M_LON = 111412.84 * math.cos(_rad) - 93.5 * math.cos(3 * _rad)


def unproject(x: float, z: float) -> tuple[float, float]:
    return round(ORIGIN[0] - z / M_LAT, 6), round(ORIGIN[1] + x / M_LON, 6)


def project(lat: float, lng: float) -> tuple[float, float]:
    return (lng - ORIGIN[1]) * M_LON, -(lat - ORIGIN[0]) * M_LAT


# the mapped university boundary (local metres), from Gombe Life data/world/campus.json
BOUNDARY_FILE = Path.home() / "Desktop" / "Gombe-Life" / "data" / "world" / "campus.json"
OPEN_GATES = [(368.55, -1584.07), (442.79, -1888.38)]

C = "photos/commons/"
# ---------------------------------------------------------------- places
# (id, name, category, x, z, source, aliases, description, hours, photos)
# source: osm = a named OSM point; owner = placed on the owner's word; estimate = my estimate, needs checking on the ground
P = [
    # gates
    ("main-gate", "Main Gate (Gate 1)", "gate", 368.55, -1584.07, "owner",
     ["main gate", "front gate", "gate 1", "main entrance", "babban kofa", "kofar jami'a", "kofar shiga", "get"],
     "The university's main entrance on the western boulevard: a wide canopy with the crest, gatehouses either side. The drive leads to the fountain roundabout, Senate and Registry. The university signboard stands to the left as you arrive.",
     "Open daily, 6:00 to 22:00 (security on duty 24 hours)",
     [C + "GOMBE_STATE_UNIVERSITY_ENTRANCE.jpg", C + "Main_Entrance_GSU.jpg", C + "Gombe_State_University.jpg", C + "Gombe_state_university.jpg"]),
    ("gate-3", "Gate 3 (West Gate)", "gate", 442.79, -1888.38, "owner",
     ["gate 3", "second gate", "west gate", "back gate", "law gate", "kofa ta biyu"],
     "The second open gate, on Gombe State University road by the Central Mosque. The quickest way in for the Faculty of Law, Education and the SBRS blocks.",
     "Open daily, 6:00 to 22:00", []),
    # admin
    ("senate", "Senate Building", "admin", 596, -1492, "osm",
     ["senate", "senate chamber", "council chamber", "vc office", "vice chancellor", "vice-chancellor", "ofishin vc", "majalisar jami'a"],
     "Senate and Council Chamber with the Vice-Chancellor's office nearby. Senate Office is just east of it.",
     "Mon to Fri, 8:00 to 16:00", []),
    ("registry", "Registry", "admin", 662, -1483, "osm",
     ["registry", "gsu registry", "admissions", "admission office", "academic office", "records", "rajista", "registrar", "course registration", "clearance"],
     "Admissions, student records, clearance, transcripts and registration problems. Bring your admission letter and JAMB documents.",
     "Mon to Fri, 8:00 to 16:00", []),
    ("bursary", "Bursary", "admin", 708, -1542, "osm",
     ["bursary", "gsu bursary", "bursar", "school fees", "fees office", "accounts", "payment", "kudin makaranta", "biyan kudi", "receipt"],
     "Fees, payment receipts, refunds and scholarship payments. School fees are paid online or at the bank, then the receipt is verified here.",
     "Mon to Fri, 8:00 to 16:00", []),
    ("admin-block", "Administrative Block", "admin", 653, -1189, "osm",
     ["admin block", "administrative block", "admin", "diploma site", "ofishin gudanarwa"],
     "Administrative Block on the south side by the Diploma site. Which building in the photographs is this one has not been confirmed.",
     "Mon to Fri, 8:00 to 16:00",
     [C + "Administrative_block_GSU.jpg", C + "Admin_Block_GSU.jpg", C + "The_on_going_construction_of_the_administrative_Building_of_the_Gombe_State_University_of_Nigeria.jpg"]),
    ("postgraduate", "School of Postgraduate Studies", "admin", 469, -1764, "osm",
     ["postgraduate", "pg school", "spgs", "masters", "phd"], "Postgraduate admissions and records.", "Mon to Fri, 8:00 to 16:00", []),
    ("alumni", "Alumni Office", "admin", 725, -1796, "osm", ["alumni", "alumni office"], "Alumni association office.", "Mon to Fri, 9:00 to 15:00", []),
    ("src-secretariat", "SRC Secretariat", "admin", 808, -1887, "osm",
     ["src", "sug", "students union", "student union", "src secretariat", "kungiyar dalibai"],
     "Students' Representative Council secretariat. The SRC garden, park and shop are beside it.", "Mon to Sat, 9:00 to 18:00", []),
    ("asuu", "ASUU Secretariat", "admin", 728, -1784, "osm", ["asuu", "lecturers union"], "Academic Staff Union of Universities secretariat.", "Mon to Fri, 9:00 to 15:00", []),
    ("asuu-board", "ASUU Board", "admin", 913, -2088, "owner", ["asuu board", "notice board"], "ASUU notice board in the north of the campus (the map wrongly called it a clinic). Amzee Restaurant is beside it.", "Always open", []),
    ("sbrs", "SBRS Administrative Block", "admin", 607, -1877, "osm",
     ["sbrs", "remedial", "school of basic and remedial studies", "pre-degree", "ijmb", "basic studies"],
     "School of Basic and Remedial Studies: pre-degree and remedial programmes. Its biology lab and the Department of SLT are next door.", "Mon to Fri, 8:00 to 16:00", []),
    # faculties and departments
    ("cs-dept", "Computer Science Department (ICT Centre)", "faculty", 615, -1463, "owner",
     ["computer science", "cs", "cs department", "ict centre", "ict center", "l1", "computing", "sashen kwamfuta"],
     "The ICT Centre, home of the Computer Science Department: pale yellow, two storeys, a canopy on four tall white columns. Close to the Registry. 'L1' is its lecture room (name as used by students; position inside the building not mapped).",
     "Mon to Fri, 8:00 to 17:00", []),
    ("ict-park", "ICT Park", "faculty", 410, -1477, "osm", ["ict park", "cbt centre", "cbt", "computer centre"], "ICT Park near the main gate, used for computer-based tests and online registration.", "Mon to Fri, 8:00 to 17:00", []),
    ("science", "Faculty of Science Complex", "faculty", 899.6, -1700.4, "estimate",
     ["science complex", "faculty of science", "fsc", "science", "sciences", "complex", "kimiyya"],
     "The biggest building on campus: a three-storey quadrangle holding Lecture Theatres A and B and SLT A and B, plus Geography and Geology offices. Footprint estimated from photographs.",
     "Mon to Fri, 7:30 to 18:00",
     [C + "Faculty_of_Science_Complex_GSU.jpg", C + "Science_complex_of_Gombe_State_University.jpg", C + "Faculty_of_Science_Complex_Gombe_State_University.jpg", C + "Faculty_of_Science_complex_in_Gombe_state_University.jpg", C + "A_side_view_of_science_complex_of_Gombe_State_university.jpg", C + "A_side_view_of_the_science_complex_of_Gombe_State_University_Nigeria.jpg"]),
    ("law", "Faculty of Law", "faculty", 593, -1951, "osm",
     ["law", "faculty of law", "law faculty", "shari'a", "lauyoyi"],
     "Faculty of Law: cream, three storeys, a dark glazed entrance over a porch. Near Gate 3; the University Clinic and day care are beside it.",
     "Mon to Fri, 8:00 to 17:00",
     [C + "Faculty_of_Law_GSU.jpg", C + "Law_Faculty_GSU.jpg", C + "Faculty_of_Law_Gombe_State_University.jpg", C + "Gombe_State_University_faculty_of_law_01.jpg", C + "Faculty_of_law_Gombe_State_University_03.jpg"]),
    ("law-old", "Old Faculty of Law", "faculty", 646, -1859, "estimate",
     ["old law", "old faculty of law", "law old site"], "The older Faculty of Law building. Position is the mapped 'faculty of law' label nearest the education blocks; not confirmed.", "Mon to Fri, 8:00 to 17:00",
     [C + "Old_Faculty_of_Law_GSU.jpg"]),
    ("moot-court", "Faculty of Law Moot Court", "lecture_hall", 728, -1755, "osm", ["moot court", "mock court"], "Practice courtroom used by law students.", "Mon to Fri, 8:00 to 17:00", []),
    ("education", "Faculty of Education", "faculty", 890, -1935, "owner",
     ["education", "faculty of education", "edu", "ilimi"],
     "Faculty of Education: peach, single storey, an arcade along the front and a terracotta roof. The Dean's office is in the western blocks.",
     "Mon to Fri, 8:00 to 16:00",
     [C + "Faculty_of_Education_GSU_.jpg", C + "Faculty_of_Education_GSU.jpg"]),
    ("education-dean", "Faculty of Education Dean's Office", "faculty", 592, -1801, "osm", ["education dean", "dean education", "block e"], "Dean's office of the Faculty of Education, among Blocks A to E.", "Mon to Fri, 8:00 to 16:00", []),
    ("pharmacy", "Faculty of Pharmaceutical Sciences", "faculty", 801, -1947, "owner",
     ["pharmacy", "pharmaceutical sciences", "pharm", "faculty of pharmacy", "magani"],
     "Faculty of Pharmaceutical Sciences complex: cream, three storeys.",
     "Mon to Fri, 8:00 to 17:00",
     [C + "Gombe_State_University_Faculty_of_Phamaceutical_Sciences_Complex_01.jpg", C + "Gombe_State_University_faculty_of_pharmaceutical_sciences_01.jpg", C + "Gombe_State_University_Faculty_of_Phamaceutical_Sciences_Complex_05.jpg"]),
    ("medical", "College of Medical Sciences", "faculty", 812, -1512, "osm",
     ["medicine", "medical college", "college of medicine", "mbbs", "medical sciences", "com", "likita"],
     "College of Medical Sciences: a cluster of beige two-storey blocks, including Medical Biochemistry, Anatomy and Physiology.",
     "Mon to Fri, 8:00 to 17:00",
     [C + "Pictures_of_medical_college_GSU_01.jpg", C + "Pictures_of_medical_college_GSU_02.jpg", C + "Medical_Biochemistry_Medical_College_Gombe_State_University_01.jpg", C + "Department_of_medical_biochemistry_GSU_01.jpg"]),
    ("biochem", "Biochemistry and Microbiology Department", "faculty", 862, -1564, "osm",
     ["biochemistry", "microbiology", "biochem", "micro"], "Biochemistry and Microbiology: cream, two storeys, a grey porch.", "Mon to Fri, 8:00 to 17:00",
     [C + "Biochemistry_Department_GSU.jpg"]),
    ("nursing", "Department of Nursing Science", "faculty", 900, -1475, "osm", ["nursing", "nursing science", "faculty of nursing", "nas"], "Nursing Science department and faculty offices.", "Mon to Fri, 8:00 to 17:00", []),
    ("english-history", "Department of English and History", "faculty", 470, -1722, "osm",
     ["english", "history", "arts", "english and history", "turanci", "tarihi"], "English and History: pale, two storeys, a red-framed glazed entrance.", "Mon to Fri, 8:00 to 16:00",
     [C + "History_And_English_Department_of_Gombe_State_University.jpg"]),
    ("geography", "Geography Department", "faculty", 945, -1677, "osm", ["geography", "geology", "geography room 3", "geography room 4"], "Geography Department rooms 3 and 4 and the Geology visiting lecturers' office, at the back of the Science Complex.", "Mon to Fri, 8:00 to 17:00", []),
    ("sociology", "Department of Sociology", "faculty", 757, -1811, "osm", ["sociology", "social sciences"], "Sociology department.", "Mon to Fri, 8:00 to 16:00", []),
    ("economics", "Economics Department", "faculty", 765, -1855, "osm", ["economics", "eco"], "Economics department.", "Mon to Fri, 8:00 to 16:00", []),
    ("polsci", "Political Science Department", "faculty", 790, -1845, "osm", ["political science", "pol sci", "polsci"], "Political Science department.", "Mon to Fri, 8:00 to 16:00", []),
    ("religious", "Religious Studies Department", "faculty", 794, -1801, "osm", ["religious studies", "islamic studies", "crs", "religion"], "Religious Studies department.", "Mon to Fri, 8:00 to 16:00", []),
    ("slt", "Department of SLT", "faculty", 586, -1884, "osm", ["slt", "science laboratory technology", "lab tech"], "Science Laboratory Technology department, beside the SBRS block.", "Mon to Fri, 8:00 to 16:00", []),
    ("islamic-institute", "International Institute for Islamic Research", "faculty", 621, -1890, "osm", ["islamic research", "iiird", "institute"], "International Institute for Islamic Research and Development.", "Mon to Fri, 8:00 to 16:00", []),
    ("entrepreneurship", "Centre for Entrepreneurship Development Studies", "faculty", 421, -1763, "osm", ["entrepreneurship", "ceds", "ent"], "Entrepreneurship courses and skills training.", "Mon to Fri, 8:00 to 16:00", []),
    # libraries and lecture halls
    ("library", "University Main Library", "lecture_hall", 643, -1718, "osm",
     ["library", "main library", "laburare", "dakin karatu", "lib", "reading room"],
     "Main Library: cream, a red-framed glazed front over a porch. Reading rooms, e-library and the reserve collection. Bring your ID card.",
     "Mon to Fri, 8:00 to 22:00; Sat, 9:00 to 17:00",
     [C + "Gombe_State_University_Library.jpg", C + "Gombe_State_University_Main_Library_2.jpg", C + "The_Gombe_State_University_Library_01.jpg"]),
    ("edu-library", "Faculty of Education Library", "lecture_hall", 518, -1829, "osm", ["education library", "faculty library"], "Faculty of Education Library: mustard, single storey.", "Mon to Fri, 8:00 to 18:00",
     [C + "Faculty_of_Education_Library_GSU_.jpg"]),
    ("ndic-elibrary", "NDIC E-Library", "lecture_hall", 484, -1830, "osm", ["e-library", "elibrary", "ndic"], "NDIC-sponsored e-library with computers.", "Mon to Fri, 9:00 to 17:00", []),
    ("lt-a", "Lecture Theatre A", "lecture_hall", 924, -1715, "osm", ["lt a", "lta", "lecture theatre a", "theatre a"], "Inside the Faculty of Science Complex.", "Lecture hours, 8:00 to 18:00", []),
    ("lt-b", "Lecture Theatre B", "lecture_hall", 906, -1718, "osm", ["lt b", "ltb", "lecture theatre b", "theatre b"], "Inside the Faculty of Science Complex.", "Lecture hours, 8:00 to 18:00", []),
    ("slt-a", "SLT A (Science Lecture Theatre A)", "lecture_hall", 869, -1729, "osm", ["slt a", "science lecture theatre a"], "Inside the Faculty of Science Complex.", "Lecture hours, 8:00 to 18:00", []),
    ("slt-b", "SLT B (Science Lecture Theatre B)", "lecture_hall", 917, -1710, "osm", ["slt b", "science lecture theatre b"], "Inside the Faculty of Science Complex.", "Lecture hours, 8:00 to 18:00", []),
    ("lt-7", "LT 7", "lecture_hall", 905, -1686, "osm", ["lt 7", "lt7", "lecture theatre 7"], "Lecture Theatre 7, at the front of the Science Complex.", "Lecture hours, 8:00 to 18:00", []),
    ("blocks-ae", "Blocks A to E (Education)", "lecture_hall", 560, -1830, "osm", ["a block", "b block", "block a", "block b", "block c", "block e", "blocks"], "Classroom blocks A, B, C and E around the Faculty of Education Dean's office.", "Lecture hours, 8:00 to 18:00", []),
    ("old-mph", "Old Multipurpose Hall", "lecture_hall", 761, -1741, "owner",
     ["old multipurpose hall", "old mph", "multipurpose", "exam hall", "mph"], "Old Multipurpose Hall: peach, two storeys, a red roof and a colonnade. Used for exams, convocation rehearsals and events.", "During events and exams",
     [C + "Old_Multipurpose_Hall_GSU.jpg", C + "Gombe_state_university_old_multipurpose_hall.jpg", C + "Historical_building_in_gsu.jpg"]),
    ("new-mph", "New Multipurpose Hall", "lecture_hall", 722, -1621, "estimate",
     ["new multipurpose hall", "new mph", "devfest", "events hall", "auditorium"], "The New Multipurpose Hall, used for big events such as Google DevFest Gombe. POSITION ESTIMATED: please correct it with Admin mode.", "During events",
     [C + "New_multi-purpose_hall_Gombe_state_university.jpg", C + "New_multi-purpose_hall_Gombe_state_universit.jpg", C + "New_multi-purpose_hall_Gombe_state_universi.jpg", C + "Devfest_google_developer_group_at_Gombe_state_university_multipurpose_hall_01.jpg", C + "Devfest_google_developer_group_at_Gombe_state_university_multipurpose_hall_02.jpg"]),
    # named blocks whose use is not confirmed
    ("blk-musa-babayo", "Musa Babayo Block", "lecture_hall", 454, -1810, "osm", ["musa babayo"], "Named block on the campus map; what it houses is not confirmed yet.", "Lecture hours", []),
    ("blk-rufai", "Rufai Ahmad Alkali Block", "lecture_hall", 521, -1752, "osm", ["rufai ahmad alkali", "rufai"], "Named block on the campus map; what it houses is not confirmed yet.", "Lecture hours", []),
    ("blk-lidani", "Sen. Joshua Lidani Block", "lecture_hall", 559, -1734, "osm", ["joshua lidani", "lidani"], "Named block on the campus map; what it houses is not confirmed yet.", "Lecture hours", []),
    ("blk-somasundara", "JWD Somasundara Block", "lecture_hall", 403, -1733, "osm", ["somasundara", "jwd"], "Named block on the campus map; what it houses is not confirmed yet.", "Lecture hours", []),
    ("blk-waziri", "Ibrahim Waziri Abubakar Block", "lecture_hall", 436, -1725, "osm", ["ibrahim waziri", "waziri"], "Named block on the campus map; what it houses is not confirmed yet.", "Lecture hours", []),
    ("blk-usman-shehu", "Usman Shehu Abubakar Block", "lecture_hall", 765, -1750, "osm", ["usman shehu abubakar"], "Named block on the campus map; what it houses is not confirmed yet.", "Lecture hours", []),
    ("blk-ibrahim-musa", "Ibrahim Musa Umar Block", "lecture_hall", 420, -1458, "osm", ["ibrahim musa umar"], "Large named building by the ICT Park; what it houses is not confirmed yet.", "Lecture hours", []),
    ("blk-haruna", "Haruna Kadir Rashid Block", "lecture_hall", 635, -2034, "osm", ["haruna kadir rashid"], "Named block in the north of the campus; what it houses is not confirmed yet.", "Lecture hours", []),
    ("blk-el-nafaty", "Aliyu Usman El-Nafaty Block", "lecture_hall", 813, -2046, "osm", ["el-nafaty", "el nafaty", "aliyu usman"], "Named block in the north of the campus; what it houses is not confirmed yet.", "Lecture hours", []),
    # hostels
    ("male-hostel", "Male Hostel (Mika Ismaila Jimeta)", "hostel", 1102, -1380, "osm",
     ["male hostel", "boys hostel", "boys' hostel", "mika ismaila jimeta", "dakin kwanan maza", "masaukin maza", "hostel"],
     "The boys' hostel: ochre, four storeys, green roof. The hostel mosque, eatery and shops are close by.", "Open 24 hours (residents)",
     []),
    ("timothy-shelpidi", "Timothy Shelpidi Hall (Male)", "hostel", 1119, -1319, "osm", ["timothy shelpidi", "shelpidi"], "Male hostel block south of Mika Ismaila Jimeta.", "Open 24 hours (residents)",
     [C + "The_frontal_view_of_Timothy_sheldipi_of_Gombe_State_University_male_hostel.jpg", C + "The_back_view_of_Timothy_sheldipi_of_Gombe_State_University_male_hostel.jpg"]),
    ("female-old", "Female Old Hostel", "hostel", 1019, -1828, "osm", ["female old hostel", "old female hostel", "girls hostel", "dakin kwanan mata", "masaukin mata"], "The original female hostel, near the Chapel of Joy.", "Open 24 hours (residents)", []),
    ("female-annex", "Female Annex Hostel", "hostel", 963, -1882, "osm", ["female annex", "annex hostel"], "Female annex hostel.", "Open 24 hours (residents)", []),
    ("female-hall-2", "Female Hostel Hall 2", "hostel", 1004, -1931, "owner", ["hall 2", "hall ii", "female new hostel", "new female hostel"], "Pink, four storeys, red roof. Which mapped building is Hall 2 is a guess.", "Open 24 hours (residents)", []),
    ("female-hall-3", "Female Hostel Hall 3 (Habiba Muda Lawal)", "hostel", 1017, -1753, "owner", ["hall 3", "hall iii", "habiba muda lawal"], "Cream, two storeys, a tall portico with terracotta bases. Which mapped building is Hall 3 is a guess.", "Open 24 hours (residents)", []),
    ("female-hall-4", "New Female Hostel IV", "hostel", 974, -1714, "osm", ["hall 4", "hall iv", "female hostel iv"], "New Female Hostel IV.", "Open 24 hours (residents)", []),
    ("halima-abba", "Halima Mohammed Abba Hall", "hostel", 1004, -1706, "osm", ["halima mohammed abba", "halima abba"], "Female hall beside Hostel IV.", "Open 24 hours (residents)", []),
    # health
    ("clinic", "University Clinic", "clinic", 626, -1967, "owner",
     ["clinic", "health centre", "health center", "sick bay", "hospital", "asibiti", "doctor", "likita", "medical centre", "first aid"],
     "University Clinic, beside the Faculty of Law and close to the day care. First aid, malaria tests, medical checks for freshers.", "Open 24 hours for emergencies; outpatients 8:00 to 16:00", []),
    ("old-clinic", "Old Clinic (Health Clinic)", "clinic", 790, -1890, "osm", ["old clinic", "gsu old clinic", "health clinic"], "The old university health clinic near the SRC area.", "Mon to Fri, 8:00 to 16:00", []),
    # worship
    ("central-mosque", "GSU Central Mosque", "worship", 492, -1940, "osm",
     ["central mosque", "mosque", "masallaci", "masallacin juma'a", "juma'at mosque", "friday mosque", "jumu'a", "pray", "sallah"],
     "The university's Friday mosque: white, a green dome and a tall round minaret. Near Gate 3.", "Open for all five daily prayers; Jumu'ah on Friday",
     [C + "ICentral_Mosque_Gombe_State_University.jpg", C + "Central_Mosque_Gombe_State_University.jpg"]),
    ("hostel-mosque", "Male Hostel Mosque", "worship", 1088, -1211, "osm", ["hostel mosque", "male hostel mosque", "masallacin hostel"], "Ochre mosque with battlements and pink columns, by the male hostels.", "Open for daily prayers",
     [C + "Gombe_State_University_male_hostel_mosque.jpg"]),
    ("science-mosque", "Male and Female Mosque (Science area)", "worship", 895, -1784, "osm", ["male mosque", "female mosque", "science mosque", "masallacin mata"], "Separate male and female prayer rooms with restrooms, beside the Science Complex.", "Open for daily prayers", []),
    ("registry-mosque", "Mosque near Registry", "worship", 683, -1443, "osm", ["registry mosque", "senate mosque"], "Small mosque by the Registry and Senate.", "Open for daily prayers", []),
    ("chapel", "Chapel of Joy", "worship", 1105, -1800, "osm",
     ["chapel", "chapel of joy", "church", "coci", "majami'a", "service", "fellowship", "protestant"], "Chapel of Joy, the campus chapel on the east side near the female hostels.", "Sunday services; fellowship in the week",
     []),
    ("catholic", "Catholic Church", "worship", 1097, -1854, "osm", ["catholic", "catholic church", "mass"], "Catholic chaplaincy, beside the Chapel of Joy.", "Sunday Mass; weekday Mass in the evening", []),
    # food
    ("food-court", "New Commercial Area (food and shops)", "cafeteria", 944, -1766, "osm",
     ["cafeteria", "canteen", "food", "restaurant", "eat", "buka", "mama put", "chop", "abinci", "wurin cin abinci", "commercial area", "ahwas", "lauwali", "jami'a shop", "shops"],
     "The busiest food spot: Ahwas restaurant, Lauwali restaurant, Mama Rice, Jami'a shop, cosmetics and provisions, all by the Science Complex.", "Daily, 7:00 to 21:00", []),
    ("mama-rice", "Mama Rice", "cafeteria", 925, -1765, "osm", ["mama rice", "rice", "shinkafa"], "Popular rice and stew spot in the new commercial area.", "Daily, 8:00 to 20:00", []),
    ("amzee", "Amzee Restaurant", "cafeteria", 935, -2082, "owner", ["amzee", "amzee restaurant"], "Restaurant beside the ASUU Board in the north (position estimated).", "Daily, 8:00 to 21:00", []),
    ("hostel-eatery", "Hostel Eatery", "cafeteria", 1023, -1368, "osm", ["eatery", "hostel eatery", "male hostel food"], "Eatery and provision shops by the male hostels.", "Daily, 7:00 to 22:00", []),
    ("src-shop", "SRC Shop", "cafeteria", 814, -1882, "osm", ["src shop", "stationery", "snacks", "drinks"], "Snacks, drinks and stationery at the SRC.", "Mon to Sat, 8:00 to 19:00", []),
    # money
    ("atm-west", "ATM Gallery (Education side)", "bank", 462, -1876, "osm", ["atm", "bank", "cash", "withdraw", "banki", "cire kudi", "pos"], "ATMs on the west side near the Faculty of Education blocks and Gate 3.", "ATMs 24 hours", []),
    ("atm-commercial", "ATMs at New Commercial Area", "bank", 940, -1778, "osm", ["atm", "bank", "pos", "transfer", "banki"], "ATMs and POS operators in the new commercial area.", "ATMs 24 hours; POS 8:00 to 20:00", []),
    ("atm-src", "Banks by the SRC", "bank", 780, -1905, "osm", ["bank", "atm", "school fees bank", "banki", "pay fees"], "Bank points and ATMs around the SRC area. School fees can be paid at the bank, then verified at the Bursary.", "Mon to Fri, 8:00 to 16:00; ATMs 24 hours", []),
    ("atm-hostel", "ATMs by Male Hostel", "bank", 985, -1325, "osm", ["atm", "bank", "pos"], "ATMs and POS by the male hostel commercial area.", "ATMs 24 hours", []),
    # sports and open places
    ("football", "Football Pitch", "sports", 882, -1222, "osm", ["football", "pitch", "field", "stadium", "filin kwallo", "sports", "ball"], "The main football pitch in the south of the campus, near the male hostels.", "Daily, 6:00 to 19:00", []),
    ("fountain", "Fountain Roundabout", "landmark", 593.5, -1539.3, "owner", ["fountain", "roundabout", "maɓuɓɓuga", "kewaye"], "The roundabout on the drive from the main gate, with a blue-tiled fountain and the crest on top. Senate, Registry and Bursary are around it.", "Always open", []),
    ("src-garden", "SRC Garden", "landmark", 834, -1842, "osm", ["src garden", "garden", "src park"], "Shaded garden by the SRC where students meet.", "Daily", []),
    ("love-garden", "Love Garden", "landmark", 724, -1680, "osm", ["love garden"], "Garden between the Main Library and the Science Complex.", "Daily", []),
    ("botanical", "Botanical Garden", "landmark", 660, -1886, "osm", ["botanical garden", "botany garden"], "Botanical Garden used by Biological Sciences.", "Daily, 7:00 to 18:00", []),
    ("zoo", "GSU Zoological Park", "landmark", 1040, -1588, "osm", ["zoo", "zoological park", "zoological garden", "gidan namun daji", "animals"], "The university zoological park on the east side.", "Daily, 9:00 to 18:00",
     [C + "GSU_Zoological_Garden_Gate.jpg", C + "Gombe_State_University_Zoological_Park.jpg"]),
    ("gsu-greens", "GSU Greens", "landmark", 676, -1559, "osm", ["greens", "gsu greens", "lawn"], "Lawns between the Bursary and the Senate.", "Daily", []),
    ("daycare", "University Day Care", "landmark", 654, -1990, "osm", ["day care", "creche", "nursery"], "Day care for staff and students' children, beside the clinic.", "Mon to Fri, 7:30 to 16:30", []),
    ("fire-service", "Fire Service", "landmark", 849, -2110, "osm", ["fire service", "fire station", "emergency", "kashe gobara"], "University fire service in the north.", "24 hours", []),
    ("met-station", "Meteorological Station", "landmark", 1135, -1745, "osm", ["weather station", "met station", "meteorological"], "Weather station on the east edge of the campus.", "By arrangement", []),
    ("filling-station", "GSU Filling Station", "landmark", 362, -1421, "osm", ["filling station", "petrol", "fuel", "mai"], "Filling station just inside the main gate area.", "Daily, 7:00 to 20:00", []),
    ("bus-park", "Bus Park", "gate", 372, -1409, "osm", ["bus park", "keke", "napep", "taxi", "bus", "motor park", "tasha"], "Where shuttle buses and kekes drop off by the main gate.", "Daily, 6:00 to 21:00", []),
]

CATEGORIES = ["faculty", "lecture_hall", "hostel", "admin", "bank", "clinic", "cafeteria", "worship", "sports", "gate", "landmark"]


def build_places() -> list[dict]:
    out, seen = [], set()
    for pid, name, cat, x, z, src, aliases, desc, hours, photos in P:
        assert pid not in seen, pid
        assert cat in CATEGORIES, cat
        seen.add(pid)
        for ph in photos:
            assert (ROOT / "static" / ph).exists(), "missing photo " + ph
        lat, lng = unproject(x, z)
        out.append({"id": pid, "name": name, "aliases": aliases, "category": cat, "lat": lat, "lng": lng,
                    "description": desc, "opening_hours": hours, "reference_photos": photos,
                    "approximate": True, "source": src})
    return out


# ---------------------------------------------------------------- paths
def load_boundary() -> list[tuple[float, float]]:
    ring = json.loads(BOUNDARY_FILE.read_text())[0]["ring"]
    return list(zip(ring[::2], ring[1::2]))


def inside(poly, x, z) -> bool:
    c, j = False, len(poly) - 1
    for i in range(len(poly)):
        xi, zi = poly[i]
        xj, zj = poly[j]
        if (zi > z) != (zj > z) and x < (xj - xi) * (z - zi) / (zj - zi) + xi:
            c = not c
        j = i
    return c


def dist_to_poly(poly, x, z) -> float:
    best = 1e9
    for i in range(len(poly)):
        ax, az = poly[i - 1]
        bx, bz = poly[i]
        dx, dz = bx - ax, bz - az
        t = max(0, min(1, ((x - ax) * dx + (z - az) * dz) / (dx * dx + dz * dz or 1)))
        best = min(best, math.hypot(x - ax - dx * t, z - az - dz * t))
    return best


WALKABLE = {"footway", "path", "pedestrian", "steps", "living_street", "residential", "service", "unclassified",
            "tertiary", "secondary", "primary", "trunk", "track", "road", "tertiary_link", "secondary_link", "primary_link"}


def load_ways(src: Path | None) -> list[dict]:
    if src and src.exists():
        print("paths from", src)
        return [e for e in json.loads(src.read_text())["elements"] if e["type"] == "way" and e.get("tags", {}).get("highway") in WALKABLE]
    s, w, n, e = 10.296, 11.166, 10.314, 11.186
    q = f'[out:json][timeout:60];way["highway"]({s},{w},{n},{e});out geom;'
    print("paths from Overpass")
    req = urllib.request.Request("https://overpass-api.de/api/interpreter", data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": "GSU-Compass"})
    els = json.loads(urllib.request.urlopen(req, timeout=120).read())["elements"]
    return [e for e in els if e.get("tags", {}).get("highway") in WALKABLE]


def build_paths(src: Path | None) -> dict:
    wall = load_boundary()
    feats = []
    for way in load_ways(src):
        pts = [project(g["lat"], g["lon"]) for g in way.get("geometry", [])]
        if len(pts) < 2:
            continue
        # keep points near the campus; split the way where it leaves that area or crosses the wall at a closed spot
        runs, cur = [], []
        for i, (x, z) in enumerate(pts):
            near = inside(wall, x, z) or dist_to_poly(wall, x, z) < 350
            if not near:
                if len(cur) > 1:
                    runs.append(cur)
                cur = []
                continue
            if cur:
                px, pz = cur[-1]
                crosses = inside(wall, px, pz) != inside(wall, x, z)
                at_gate = any(math.hypot(gx - (px + x) / 2, gz - (pz + z) / 2) < 40 for gx, gz in OPEN_GATES)
                if crosses and not at_gate:
                    if len(cur) > 1:
                        runs.append(cur)
                    cur = []
            cur.append((x, z))
        if len(cur) > 1:
            runs.append(cur)
        for run in runs:
            coords = [list(reversed(unproject(x, z))) for x, z in run]
            feats.append({"type": "Feature", "properties": {"highway": way["tags"]["highway"], "name": way["tags"].get("name", ""), "osm_id": way["id"]},
                          "geometry": {"type": "LineString", "coordinates": coords}})
    return {"type": "FeatureCollection", "features": feats}


def build_boundary() -> dict:
    ring = [list(reversed(unproject(x, z))) for x, z in load_boundary()]
    ring.append(ring[0])
    return {"type": "Feature", "properties": {"name": "Gombe State University"}, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def build_buildings() -> dict:
    """Campus building footprints from the Gombe Life world chunks, for the offline map. Wall segments are left out."""
    feats = []
    for f in (BOUNDARY_FILE.parent / "chunks").glob("*.json"):
        for b in json.loads(f.read_text()).get("b", []):
            if b.get("zn") != "gsu" or b.get("k") == "wall":
                continue
            p = b["p"]
            ring = [list(reversed(unproject(p[i], p[i + 1]))) for i in range(0, len(p), 2)]
            ring.append(ring[0])
            feats.append({"type": "Feature", "properties": {"name": b.get("n", "")}, "geometry": {"type": "Polygon", "coordinates": [ring]}})
    return {"type": "FeatureCollection", "features": feats}


if __name__ == "__main__":
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else GOMBE_LIFE_OSM
    places = build_places()
    (DATA / "places.json").write_text(json.dumps(places, indent=1, ensure_ascii=False) + "\n")
    paths = build_paths(src)
    (DATA / "paths.geojson").write_text(json.dumps(paths, separators=(",", ":")) + "\n")
    (DATA / "boundary.geojson").write_text(json.dumps(build_boundary(), separators=(",", ":")) + "\n")
    buildings = build_buildings()
    (DATA / "buildings.geojson").write_text(json.dumps(buildings, separators=(",", ":")) + "\n")
    print(f"{len(places)} places, {len(paths['features'])} path lines, {len(buildings['features'])} buildings")
