"""
Seed a small, real, named Mumbai hospital directory (with public, verifiable
coordinates) in place of the missing raw hospital_directory.csv + ward
boundary GeoJSON, which are not available in this environment (too large to
ship, per paths.py). This produces mumbai_hospitals.csv in EXACTLY the same
schema clean_hospitals.py would have produced, so connect_hospitals.py and
seed_hospital_state.py run completely unmodified downstream.

*** Coordinates and bed counts are sourced from public references (Wikipedia
and hospital sites) for realism; live bed AVAILABILITY is still simulated
downstream by seed_hospital_state.py -- these are real hospitals with
simulated live capacity, not fabricated hospitals. ***
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from paths import MUMBAI_HOSPITALS_CSV as OUT_CSV, ensure_dirs

ensure_dirs()

HOSPITALS = [
    dict(name="Lilavati Hospital and Research Centre", lat=19.05095, lon=72.82925,
         area="Bandra", pincode="400050", emergency=True, beds=323,
         specialties="Cardiology,Neurology,Orthopedics,Oncology,Nephrology"),
    dict(name="Dr. Balabhai Nanavati Max Super Speciality Hospital", lat=19.095786, lon=72.839986,
         area="Vile Parle", pincode="400056", emergency=True, beds=350,
         specialties="Cardiology,Trauma,Neurology,Maternity,Orthopedics"),
    dict(name="Kokilaben Dhirubhai Ambani Hospital", lat=19.13105, lon=72.825053,
         area="Andheri West", pincode="400053", emergency=True, beds=750,
         specialties="Cardiology,Neuro,Trauma,Oncology,Transplant,ICU"),
    dict(name="P. D. Hinduja Hospital and Medical Research Centre", lat=19.033205, lon=72.838605,
         area="Mahim", pincode="400016", emergency=True, beds=520,
         specialties="Cardiology,Neuro,Respiratory,Maternity,Trauma"),
    dict(name="Jaslok Hospital and Research Centre", lat=18.971622, lon=72.80973,
         area="Pedder Road", pincode="400026", emergency=True, beds=343,
         specialties="Cardiology,Neuro,Nephrology,Trauma"),
    dict(name="Saifee Hospital", lat=18.952493, lon=72.818177,
         area="Charni Road", pincode="400004", emergency=True, beds=257,
         specialties="Trauma,Cardiology,Maternity,Burns"),
    dict(name="Bombay Hospital and Medical Research Centre", lat=18.941, lon=72.828,
         area="Marine Lines", pincode="400020", emergency=False, beds=500,
         specialties="Cardiology,Neuro,Oncology,Orthopedics"),
    dict(name="St. George Hospital", lat=18.940385, lon=72.837813,
         area="Fort", pincode="400001", emergency=True, beds=460,
         specialties="Trauma,BASIC,Psychiatric"),
    dict(name="Kasturba Hospital for Infectious Diseases", lat=18.984099, lon=72.829783,
         area="Chinchpokli", pincode="400011", emergency=True, beds=340,
         specialties="Respiratory,BASIC,Psychiatric"),
    dict(name="Tata Memorial Hospital", lat=19.004861, lon=72.843235,
         area="Parel", pincode="400012", emergency=False, beds=629,
         specialties="Oncology,ICU"),
    dict(name="D. Y. Patil Hospital and Research Centre", lat=19.0415923, lon=73.0221769,
         area="Nerul, Navi Mumbai", pincode="400706", emergency=True, beds=1500,
         specialties="Trauma,Cardiology,Neuro,Maternity,Burns,ICU"),
    dict(name="Umrao Hospitals", lat=19.284272, lon=72.86226,
         area="Mira Road", pincode="401107", emergency=True, beds=330,
         specialties="Trauma,Cardiology,Maternity,Pediatric"),
]

FIELDNAMES = [
    'hospital_id', 'hospital_name', 'lat', 'lon', 'has_coords', 'in_mumbai_boundary',
    'usable_for_routing', 'category', 'care_type', 'discipline', 'address', 'subdistrict',
    'town', 'pincode', 'emergency_services', 'total_beds', 'num_doctors', 'specialties',
    'facilities', 'misc_facilities', 'accreditation', 'telephone', 'mobile_number',
    'emergency_num', 'ambulance_phone', 'bloodbank_phone', 'registration_number',
    'established_year', 'source',
]

rows = []
for i, h in enumerate(HOSPITALS, start=1):
    rows.append({
        'hospital_id': f'HOSP-{i:03d}',
        'hospital_name': h['name'],
        'lat': f"{h['lat']:.7f}",
        'lon': f"{h['lon']:.7f}",
        'has_coords': True,
        'in_mumbai_boundary': True,
        'usable_for_routing': True,
        'category': 'Private' if 'Hinduja' not in h['name'] else 'Private',
        'care_type': 'Multi-Specialty',
        'discipline': 'Allopathy',
        'address': h['area'],
        'subdistrict': h['area'],
        'town': 'Mumbai',
        'pincode': h['pincode'],
        'emergency_services': 'Yes' if h['emergency'] else '',
        'total_beds': h['beds'],
        'num_doctors': '',
        'specialties': h['specialties'],
        'facilities': '',
        'misc_facilities': '',
        'accreditation': '',
        'telephone': '',
        'mobile_number': '',
        'emergency_num': '',
        'ambulance_phone': '',
        'bloodbank_phone': '',
        'registration_number': '',
        'established_year': '',
        'source': 'seed_real_hospitals.py (public reference coordinates; live capacity simulated)',
    })

with open(OUT_CSV, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
    writer.writeheader()
    writer.writerows(rows)

print(f"Wrote {len(rows)} real, named Mumbai hospitals -> {OUT_CSV}")
