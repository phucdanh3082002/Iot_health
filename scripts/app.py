#!/usr/bin/env python3
"""
Flask API Implementation cho IoT Health Monitor (v2.1.0)
Triển khai trên AWS EC2 với AI Threshold Generation support
Compatible with Database Schema v2.1.0
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import mysql.connector
import os
import sys
from datetime import datetime, timedelta
import json
import secrets
import logging

# Add scripts directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts"))
from ai_threshold_generator import ThresholdGenerator

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for web dashboard and Android app

# Database configuration
DB_CONFIG = {
    'host': 'database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com',
    'user': os.getenv('DB_USER', 'admin'),
    'password': os.getenv('MYSQL_PASSWORD', 'your_mysql_password'),
    'database': 'iot_health_cloud',
    'port': 3306,
    'charset': 'utf8mb4'
}

# Initialize AI Threshold Generator
try:
    threshold_generator = ThresholdGenerator(
        db_config=DB_CONFIG,
        gemini_api_key=os.getenv('GOOGLE_GEMINI_API_KEY')
    )
    logger.info("✅ ThresholdGenerator initialized")
except Exception as e:
    logger.warning(f"⚠️ ThresholdGenerator initialization failed: {e}")
    threshold_generator = None

# ==================== Medical Data Translation Mappings ====================
# English to Vietnamese translation for medical data
MEDICAL_DATA_TRANSLATIONS = {
    # Chronic Diseases
    'chronic_diseases': {
        'Hypertension': 'Tăng huyết áp',
        'Diabetes': 'Tiểu đường',
        'COPD': 'Bệnh phổi tắc nghẽn mạn tính (COPD)',
        'Asthma': 'Hen suyễn',
        'Heart Failure': 'Suy tim',
        'Atrial Fibrillation': 'Rung nhĩ',
        'Chronic Kidney Disease': 'Bệnh thận mãn tính',
        'Coronary Artery Disease': 'Bệnh động mạch vành',
        'Obesity': 'Béo phì',
        'Hyperthyroidism': 'Cường giáp',
        'Hypothyroidism': 'Suy giáp',
        'Anemia': 'Thiếu máu',
        'Pneumonia': 'Viêm phổi',
        'ARDS': 'Hội chứng suy hô hấp cấp tính',
        'Sepsis': 'Nhiễm trùng huyết',
        'Stroke': 'Đột quỵ',
        'Cancer': 'Ung thư',
        'Liver Disease': 'Bệnh gan',
        'Arthritis': 'Viêm khớp',
        'Osteoporosis': 'Loãng xương',

        # Additional Cardiovascular Diseases
        'Congestive Heart Failure': 'Suy tim sung huyết',
        'CHF': 'Suy tim sung huyết (CHF)',
        'HF': 'Suy tim',
        'Heart Disease': 'Bệnh tim',
        'CAD': 'Bệnh động mạch vành (CAD)',
        'Cyanotic Heart Disease': 'Bệnh tim tím',
        'Congenital Heart Disease': 'Bệnh tim bẩm sinh',
        'CHD': 'Bệnh tim bẩm sinh (CHD)',
        'Marfan Syndrome': 'Hội chứng Marfan',
        'Long QT Syndrome': 'Hội chứng QT dài',
        'LQTS': 'Hội chứng QT dài (LQTS)',
        'Eisenmenger Syndrome': 'Hội chứng Eisenmenger',

        # Respiratory Diseases
        'COPD Severe': 'COPD nặng',
        'Severe COPD': 'COPD giai đoạn nặng',
        'COPD GOLD 3-4': 'COPD giai đoạn 3-4',
        'Emphysema': 'Khí phế thũng',
        'Severe Asthma': 'Hen suyễn nặng',
        'Asthma Severe': 'Hen suyễn nặng',
        'Interstitial Lung Disease': 'Bệnh phổi kẽ',
        'ILD': 'Bệnh phổi kẽ (ILD)',
        'Pulmonary Fibrosis': 'Xơ phổi',
        'Pulmonary Hypertension': 'Tăng áp phổi',
        'PAH': 'Tăng áp phổi (PAH)',
        'Sleep Apnea': 'Ngưng thở khi ngủ',
        'OSA': 'Ngưng thở khi ngủ tắc nghẽn (OSA)',
        'Obstructive Sleep Apnea': 'Ngưng thở khi ngủ tắc nghẽn',
        'Tuberculosis': 'Lao phổi',
        'TB': 'Lao',

        # Kidney & Liver Diseases
        'CKD': 'Bệnh thận mãn tính (CKD)',
        'Chronic Kidney Disease': 'Bệnh thận mãn tính',
        'Renal Disease': 'Bệnh thận',
        'Cirrhosis': 'Xơ gan',
        'Liver Cirrhosis': 'Xơ gan',
        'Hepatitis B': 'Viêm gan B',
        'Hepatitis C': 'Viêm gan C',
        'HBV': 'Viêm gan B (HBV)',
        'HCV': 'Viêm gan C (HCV)',

        # Neurological Diseases
        'Parkinson Disease': 'Bệnh Parkinson',
        'Parkinson': 'Bệnh Parkinson',
        'Dementia': 'Sa sút trí tuệ',
        'Alzheimer': 'Bệnh Alzheimer',

        # Endocrine & Metabolic
        'Type 1 Diabetes': 'Tiểu đường type 1',
        'Type 2 Diabetes': 'Tiểu đường type 2',
        'T1DM': 'Tiểu đường type 1',
        'Graves Disease': 'Bệnh Graves (cường giáp)',
        'Basedow': 'Bệnh Basedow (cường giáp)',
        'Thyroid Disease': 'Bệnh tuyến giáp',
        'Gout': 'Bệnh gút',

        # Blood Disorders
        'Sickle Cell Disease': 'Bệnh hồng cầu hình liềm',
        'Sickle Cell Anemia': 'Thiếu máu hồng cầu hình liềm',
        'Thalassemia': 'Thiếu máu Địa Trung Hải',
        'Thalassemia Major': 'Thiếu máu Địa Trung Hải nặng',
        'Thalassemia Minor': 'Thiếu máu Địa Trung Hải nhẹ',
        'G6PD Deficiency': 'Thiếu men G6PD',

        # Infectious Diseases
        'HIV': 'HIV',
        'AIDS': 'AIDS',
        'HIV/AIDS': 'HIV/AIDS',
        'Dengue': 'Sốt xuất huyết',
        'Dengue Fever': 'Sốt xuất huyết dengue',
        'Malaria': 'Sốt rét',

        # Rheumatic & Musculoskeletal
        'Rheumatoid Arthritis': 'Viêm khớp dạng thấp',
        'RA': 'Viêm khớp dạng thấp (RA)',
        'Osteoarthritis': 'Thoái hóa khớp',

        # Immunological
        'Immune Disorder': 'Rối loạn miễn dịch',
        'Immunosuppressed': 'Suy giảm miễn dịch',
        'Chemotherapy': 'Đang hóa trị (suy giảm miễn dịch)',
        'Transplant': 'Sau ghép tạng',

        # Geriatric Syndromes
        'Frailty': 'Suy nhược',
        'Frail Elderly': 'Người cao tuổi suy nhược',

        # Other
        'High Blood Pressure': 'Huyết áp cao'
    },

    # Medications
    'medications': {
        # Beta-blockers
        'Beta Blocker': 'Thuốc chẹn beta',
        'Beta-blocker': 'Thuốc chẹn beta',
        'Metoprolol': 'Metoprolol (thuốc chẹn beta)',
        'Atenolol': 'Atenolol (thuốc chẹn beta)',
        'Carvedilol': 'Carvedilol (thuốc chẹn beta)',
        'Bisoprolol': 'Bisoprolol (thuốc chẹn beta)',
        'Propranolol': 'Propranolol (thuốc chẹn beta)',

        # ACE Inhibitors
        'ACE Inhibitor': 'Thuốc ức chế ACE',
        'Lisinopril': 'Lisinopril (thuốc ức chế ACE)',
        'Enalapril': 'Enalapril (thuốc ức chế ACE)',
        'Ramipril': 'Ramipril (thuốc ức chế ACE)',
        'Perindopril': 'Perindopril (thuốc ức chế ACE)',
        'Captopril': 'Captopril (thuốc ức chế ACE)',

        # ARBs
        'ARB': 'Thuốc chẹn thụ thể angiotensin (ARB)',
        'Losartan': 'Losartan (thuốc chẹn thụ thể angiotensin)',
        'Valsartan': 'Valsartan (thuốc chẹn thụ thể angiotensin)',
        'Telmisartan': 'Telmisartan (thuốc chẹn thụ thể angiotensin)',
        'Irbesartan': 'Irbesartan (thuốc chẹn thụ thể angiotensin)',
        'Candesartan': 'Candesartan (thuốc chẹn thụ thể angiotensin)',

        # Calcium Channel Blockers
        'Calcium Channel Blocker': 'Thuốc chẹn kênh canxi',
        'CCB': 'Thuốc chẹn kênh canxi (CCB)',
        'Amlodipine': 'Amlodipine (thuốc chẹn kênh canxi)',
        'Diltiazem': 'Diltiazem (thuốc chẹn kênh canxi)',
        'Verapamil': 'Verapamil (thuốc chẹn kênh canxi)',
        'Nifedipine': 'Nifedipine (thuốc chẹn kênh canxi)',

        # Diuretics
        'Diuretic': 'Thuốc lợi tiểu',
        'Furosemide': 'Furosemide (thuốc lợi tiểu)',
        'Hydrochlorothiazide': 'Hydrochlorothiazide (thuốc lợi tiểu)',
        'Spironolactone': 'Spironolactone (thuốc lợi tiểu)',
        'Indapamide': 'Indapamide (thuốc lợi tiểu)',

        # Alpha Blockers
        'Alpha Blocker': 'Thuốc chẹn alpha',
        'Prazosin': 'Prazosin (thuốc chẹn alpha)',
        'Doxazosin': 'Doxazosin (thuốc chẹn alpha)',
        'Terazosin': 'Terazosin (thuốc chẹn alpha)',

        # Other Antihypertensives
        'Clonidine': 'Clonidine (thuốc hạ huyết áp)',
        'Catapres': 'Catapres (clonidine)',

        # Diabetes Medications
        'Metformin': 'Metformin (thuốc tiểu đường)',
        'Insulin': 'Insulin (thuốc tiểu đường)',
        'Glipizide': 'Glipizide (thuốc tiểu đường)',
        'Glyburide': 'Glyburide (thuốc tiểu đường)',

        # Anticoagulants & Antiplatelets
        'Warfarin': 'Warfarin (thuốc chống đông máu)',
        'Aspirin': 'Aspirin (thuốc chống đông máu)',
        'Clopidogrel': 'Clopidogrel (thuốc chống đông máu)',
        'Rivaroxaban': 'Rivaroxaban (thuốc chống đông máu mới)',
        'Apixaban': 'Apixaban (thuốc chống đông máu mới)',
        'Dabigatran': 'Dabigatran (thuốc chống đông máu mới)',

        # Cardiac Medications
        'Digoxin': 'Digoxin (thuốc cường tim)',
        'Digitalis': 'Digitalis (thuốc cường tim)',

        # Antiarrhythmics
        'Amiodarone': 'Amiodarone (thuốc chống loạn nhịp)',
        'Flecainide': 'Flecainide (thuốc chống loạn nhịp)',
        'Sotalol': 'Sotalol (thuốc chống loạn nhịp)',

        # Nitrates
        'Nitrate': 'Thuốc nitrat',
        'Nitroglycerin': 'Nitroglycerin (thuốc giãn mạch vành)',
        'Isosorbide': 'Isosorbide (thuốc nitrat)',

        # Respiratory Medications
        'Bronchodilator': 'Thuốc giãn phế quản',
        'Albuterol': 'Albuterol (thuốc giãn phế quản)',
        'Salbutamol': 'Salbutamol (thuốc giãn phế quản)',
        'Theophylline': 'Theophylline (thuốc giãn phế quản)',
        'Salmeterol': 'Salmeterol (thuốc giãn phế quản dài hạn)',
        'Formoterol': 'Formoterol (thuốc giãn phế quản dài hạn)',
        'LABA': 'Thuốc giãn phế quản dài hạn (LABA)',
        'Terbutaline': 'Terbutaline (thuốc giãn phế quản)',
        'Ventolin': 'Ventolin (salbutamol)',
        'Budesonide': 'Budesonide (corticosteroid dạng hít)',
        'Fluticasone': 'Fluticasone (corticosteroid dạng hít)',
        'Inhaled Corticosteroid': 'Corticosteroid dạng hít',

        # Corticosteroids (Systemic)
        'Corticosteroid': 'Corticosteroid',
        'Steroid': 'Steroid',
        'Prednisone': 'Prednisone (corticosteroid)',
        'Prednisolone': 'Prednisolone (corticosteroid)',
        'Dexamethasone': 'Dexamethasone (corticosteroid)',
        'Methylprednisolone': 'Methylprednisolone (corticosteroid)',
        'Hydrocortisone': 'Hydrocortisone (corticosteroid)',

        # Statins (Cholesterol)
        'Statin': 'Thuốc hạ cholesterol (statin)',
        'Atorvastatin': 'Atorvastatin (thuốc hạ cholesterol)',
        'Simvastatin': 'Simvastatin (thuốc hạ cholesterol)',
        'Rosuvastatin': 'Rosuvastatin (thuốc hạ cholesterol)',

        # NSAIDs
        'NSAID': 'Thuốc chống viêm không steroid (NSAID)',
        'Ibuprofen': 'Ibuprofen (thuốc giảm đau, kháng viêm)',
        'Naproxen': 'Naproxen (thuốc giảm đau, kháng viêm)',
        'Diclofenac': 'Diclofenac (thuốc kháng viêm)',
        'Celecoxib': 'Celecoxib (thuốc kháng viêm)',

        # Analgesics
        'Acetaminophen': 'Acetaminophen (thuốc giảm đau)',
        'Paracetamol': 'Paracetamol (thuốc giảm đau)',

        # Opioids
        'Opioid': 'Thuốc giảm đau gây nghiện (opioid)',
        'Morphine': 'Morphine (thuốc giảm đau mạnh)',
        'Codeine': 'Codeine (thuốc giảm đau)',
        'Tramadol': 'Tramadol (thuốc giảm đau)',
        'Fentanyl': 'Fentanyl (thuốc giảm đau mạnh)',

        # Thyroid Medications
        'Levothyroxine': 'Levothyroxine (thuốc giáp)',
        'Thyroxine': 'Thyroxine (thuốc giáp)',
        'T4': 'T4 (levothyroxine)',
        'Methimazole': 'Methimazole (thuốc giáp)',

        # Parkinson's Medications
        'Levodopa': 'Levodopa (thuốc Parkinson)',
        'Carbidopa': 'Carbidopa (thuốc Parkinson)',
        'Sinemet': 'Sinemet (levodopa + carbidopa)',
        'Madopar': 'Madopar (levodopa)',

        # Antidepressants
        'SSRI': 'Thuốc chống trầm cảm SSRI',
        'Fluoxetine': 'Fluoxetine (thuốc chống trầm cảm)',
        'Sertraline': 'Sertraline (thuốc chống trầm cảm)',
        'Escitalopram': 'Escitalopram (thuốc chống trầm cảm)',
        'Paroxetine': 'Paroxetine (thuốc chống trầm cảm)',
        'Citalopram': 'Citalopram (thuốc chống trầm cảm)',

        'TCA': 'Thuốc chống trầm cảm 3 vòng (TCA)',
        'Amitriptyline': 'Amitriptyline (thuốc chống trầm cảm)',
        'Nortriptyline': 'Nortriptyline (thuốc chống trầm cảm)',
        'Imipramine': 'Imipramine (thuốc chống trầm cảm)',

        # Antipsychotics
        'Antipsychotic': 'Thuốc chống loạn thần',
        'Haloperidol': 'Haloperidol (thuốc chống loạn thần)',
        'Risperidone': 'Risperidone (thuốc chống loạn thần)',
        'Olanzapine': 'Olanzapine (thuốc chống loạn thần)',
        'Quetiapine': 'Quetiapine (thuốc chống loạn thần)',
        'Aripiprazole': 'Aripiprazole (thuốc chống loạn thần)',

        # Anxiolytics & Sedatives
        'Benzodiazepine': 'Benzodiazepine (thuốc an thần)',
        'Diazepam': 'Diazepam (thuốc an thần)',
        'Lorazepam': 'Lorazepam (thuốc an thần)',
        'Alprazolam': 'Alprazolam (thuốc an thần)',
        'Clonazepam': 'Clonazepam (thuốc an thần)',

        # Antihistamines
        'Antihistamine': 'Thuốc kháng histamine',
        'Diphenhydramine': 'Diphenhydramine (thuốc dị ứng)',
        'Chlorpheniramine': 'Chlorpheniramine (thuốc dị ứng)',
        'Cetirizine': 'Cetirizine (thuốc dị ứng)',
        'Loratadine': 'Loratadine (thuốc dị ứng)',
        'Fexofenadine': 'Fexofenadine (thuốc dị ứng)',

        # Decongestants
        'Decongestant': 'Thuốc thông mũi',
        'Pseudoephedrine': 'Pseudoephedrine (thuốc thông mũi)',
        'Phenylephrine': 'Phenylephrine (thuốc thông mũi)',

        # Proton Pump Inhibitors
        'PPI': 'Thuốc ức chế bơm proton (PPI)',
        'Omeprazole': 'Omeprazole (thuốc giảm acid dạ dày)',

        # Emergency Medications
        'Epinephrine': 'Epinephrine (adrenaline)',
        'Adrenaline': 'Adrenaline',
        'EpiPen': 'EpiPen (bút tiêm adrenaline)'
    },

    # Allergies
    'allergies': {
        # Severe Allergic Reactions
        'Anaphylaxis History': 'Tiền sử phản vệ',
        'Severe Allergy': 'Dị ứng nặng',
        'Severe Food Allergy': 'Dị ứng thực phẩm nặng',
        'EpiPen User': 'Người dùng EpiPen',

        # Drug Allergies
        'Drug Allergy': 'Dị ứng thuốc',
        'Penicillin': 'Penicillin',
        'Penicillin Allergy': 'Dị ứng penicillin',
        'Antibiotic Allergy': 'Dị ứng kháng sinh',
        'Beta-lactam Allergy': 'Dị ứng beta-lactam',
        'Sulfa Drugs': 'Thuốc Sulfa',
        'Sulfa Allergy': 'Dị ứng thuốc Sulfa',
        'Aspirin': 'Aspirin',
        'Aspirin Allergy': 'Dị ứng aspirin',
        'NSAIDs': 'Thuốc chống viêm không steroid (NSAIDs)',
        'NSAID Allergy': 'Dị ứng NSAID',
        'Ibuprofen Allergy': 'Dị ứng ibuprofen',
        'Codeine': 'Codeine',
        'Morphine': 'Morphine',
        'Contrast Allergy': 'Dị ứng thuốc cản quang',
        'Iodine': 'Iốt',
        'Iodine Allergy': 'Dị ứng iốt',
        'Radiographic Contrast Allergy': 'Dị ứng thuốc cản quang X-quang',
        'Latex': 'Cao su (Latex)',
        'Latex Allergy': 'Dị ứng cao su',
        'Rubber Allergy': 'Dị ứng cao su',

        # Food Allergies - Nuts
        'Peanuts': 'Đậu phộng',
        'Peanut Allergy': 'Dị ứng đậu phộng',
        'Tree Nuts': 'Các loại hạt',
        'Tree Nut Allergy': 'Dị ứng các loại hạt',
        'Cashew Allergy': 'Dị ứng hạt điều',
        'Almond Allergy': 'Dị ứng hạt hạnh nhân',
        'Walnut Allergy': 'Dị ứng hạt óc chó',

        # Food Allergies - Seafood
        'Shellfish': 'Hải sản có vỏ (tôm, cua)',
        'Shellfish Allergy': 'Dị ứng hải sản có vỏ',
        'Shrimp Allergy': 'Dị ứng tôm',
        'Crab Allergy': 'Dị ứng cua',
        'Clam Allergy': 'Dị ứng nghêu',
        'Squid Allergy': 'Dị ứng mực',
        'Seafood Allergy': 'Dị ứng hải sản',
        'Fish': 'Cá',
        'Fish Allergy': 'Dị ứng cá',

        # Food Allergies - Common
        'Eggs': 'Trứng',
        'Egg Allergy': 'Dị ứng trứng',
        'Chicken Egg Allergy': 'Dị ứng trứng gà',
        'Milk': 'Sữa',
        'Milk Allergy': 'Dị ứng sữa',
        'Dairy Allergy': 'Dị ứng sản phẩm từ sữa',
        'Cow Milk Protein Allergy': 'Dị ứng protein sữa bò',
        'Soy': 'Đậu nành',
        'Soy Allergy': 'Dị ứng đậu nành',
        'Wheat': 'Lúa mì',
        'Wheat Allergy': 'Dị ứng lúa mì',
        'Gluten Allergy': 'Dị ứng gluten',
        'Food Allergy': 'Dị ứng thực phẩm',

        # Environmental Allergies
        'Pollen': 'Phấn hoa',
        'Dust Mites': 'Bụi',
        'Dust Allergy': 'Dị ứng bụi',
        'Mold': 'Nấm mốc',
        'Pet Dander': 'Lông thú cưng',

        # Insect Venom
        'Insect Stings': 'Nọc ong/côn trùng',
        'Insect Venom Allergy': 'Dị ứng nọc côn trùng',
        'Bee Venom Allergy': 'Dị ứng nọc ong',
        'Wasp Allergy': 'Dị ứng ong bắp cày',
        'Fire Ant Allergy': 'Dị ứng kiến lửa'
    },

    # Family History
    'family_history': {
        # Cardiovascular
        'Heart Disease': 'Bệnh tim mạch',
        'Coronary Artery Disease': 'Bệnh động mạch vành',
        'Heart Attack': 'Nhồi máu cơ tim',
        'Myocardial Infarction': 'Nhồi máu cơ tim',
        'Stroke': 'Đột quỵ',
        'Hypertension': 'Tăng huyết áp',
        'High Blood Pressure': 'Huyết áp cao',
        'Heart Failure': 'Suy tim',
        'Atrial Fibrillation': 'Rung nhĩ',

        # Metabolic & Endocrine
        'Diabetes': 'Tiểu đường',
        'Type 1 Diabetes': 'Tiểu đường type 1',
        'Type 2 Diabetes': 'Tiểu đường type 2',
        'Obesity': 'Béo phì',
        'Thyroid Disease': 'Bệnh tuyến giáp',
        'Hyperthyroidism': 'Cường giáp',
        'Hypothyroidism': 'Suy giáp',

        # Cancer
        'Cancer': 'Ung thư',
        'Breast Cancer': 'Ung thư vú',
        'Lung Cancer': 'Ung thư phổi',
        'Colon Cancer': 'Ung thư đại tràng',
        'Colorectal Cancer': 'Ung thư đại trực tràng',
        'Prostate Cancer': 'Ung thư tuyến tiền liệt',
        'Stomach Cancer': 'Ung thư dạ dày',
        'Liver Cancer': 'Ung thư gan',
        'Ovarian Cancer': 'Ung thư buồng trứng',

        # Kidney & Liver
        'Kidney Disease': 'Bệnh thận',
        'Chronic Kidney Disease': 'Bệnh thận mãn tính',
        'Kidney Failure': 'Suy thận',
        'Liver Disease': 'Bệnh gan',
        'Cirrhosis': 'Xơ gan',

        # Respiratory
        'Asthma': 'Hen suyễn',
        'COPD': 'Bệnh phổi tắc nghẽn mạn tính',
        'Lung Disease': 'Bệnh phổi',
        'Tuberculosis': 'Lao phổi',

        # Neurological & Mental Health
        'Alzheimer': 'Bệnh Alzheimer',
        'Dementia': 'Sa sút trí tuệ',
        'Parkinson Disease': 'Bệnh Parkinson',
        'Epilepsy': 'Động kinh',
        'Seizure Disorder': 'Rối loạn co giật',
        'Mental Illness': 'Bệnh tâm thần',
        'Depression': 'Trầm cảm',
        'Anxiety': 'Lo âu',
        'Bipolar Disorder': 'Rối loạn lưỡng cực',
        'Schizophrenia': 'Tâm thần phân liệt',

        # Blood Disorders
        'Anemia': 'Thiếu máu',
        'Sickle Cell Disease': 'Bệnh hồng cầu hình liềm',
        'Thalassemia': 'Thiếu máu Địa Trung Hải',
        'Hemophilia': 'Bệnh máu khó đông',
        'Blood Clotting Disorder': 'Rối loạn đông máu',

        # Autoimmune & Rheumatic
        'Rheumatoid Arthritis': 'Viêm khớp dạng thấp',
        'Lupus': 'Bệnh lupus ban đỏ',
        'Multiple Sclerosis': 'Xơ cứng rải rác',
        'Osteoporosis': 'Loãng xương',
        'Arthritis': 'Viêm khớp',
        'Gout': 'Bệnh gút',

        # Other
        'Alcoholism': 'Nghiện rượu',
        'Drug Addiction': 'Nghiện ma túy',
        'Sudden Death': 'Tử vong đột ngột',
        'Sudden Cardiac Death': 'Tử vong đột ngột do tim'
    }
}

def get_db_connection():
    """Get database connection"""
    return mysql.connector.connect(**DB_CONFIG)

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM devices")
        device_count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return jsonify({
            'status': 'ok',
            'database': 'connected',
            'timestamp': datetime.utcnow().isoformat(),
            'api_version': '2.0.0',
            'schema_version': '2.0.0',
            'device_count': device_count
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'database': 'disconnected',
            'error': str(e)
        }), 500

@app.route('/api/pair-device', methods=['POST'])
def pair_device():
    """
    Pair device endpoint - Patient info sẽ được thêm sau từ Android app
    Response trả về patient_info = null nếu chưa có thông tin
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        pairing_code = data.get('pairing_code')
        user_id = data.get('user_id')
        nickname = data.get('nickname')

        if not all([pairing_code, user_id, nickname]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: pairing_code, user_id, nickname'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # 1. Verify pairing code exists and get device info
        cursor.execute("""
            SELECT d.*, p.patient_id, p.name as patient_name, p.age, p.gender
            FROM devices d
            LEFT JOIN patients p ON d.device_id = p.device_id
            WHERE d.pairing_code = %s AND d.is_active = 1
        """, (pairing_code,))

        device_result = cursor.fetchone()

        if not device_result:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Invalid pairing code or device not active'
            }), 400

        # Check pairing code expiry (10 minutes from creation)
        if device_result.get('pairing_qr_data'):
            try:
                qr_data = json.loads(device_result['pairing_qr_data'])
                expires_at = datetime.fromisoformat(qr_data.get('expires_at', ''))
                if datetime.utcnow() > expires_at:
                    cursor.close()
                    conn.close()
                    return jsonify({
                        'status': 'error',
                        'message': 'Pairing code expired. Please generate a new code.'
                    }), 400
            except (json.JSONDecodeError, ValueError, KeyError):
                pass  # Continue if QR data is invalid or missing expiry

        device_id = device_result['device_id']

        # 2. Check if device already paired with this user
        cursor.execute("""
            SELECT * FROM device_ownership
            WHERE device_id = %s AND user_id = %s
        """, (device_id, user_id))

        existing_pairing = cursor.fetchone()

        if existing_pairing:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Device already paired with this user'
            }), 409

        # 3. Check if device already paired with another user
        cursor.execute("""
            SELECT * FROM device_ownership
            WHERE device_id = %s
        """, (device_id,))

        other_pairing = cursor.fetchone()

        if other_pairing and other_pairing['user_id'] != user_id:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Device already paired with another user'
            }), 409

        # 4. Insert/update device ownership
        cursor.execute("""
            INSERT INTO device_ownership (user_id, device_id, role, nickname, added_at, last_accessed)
            VALUES (%s, %s, 'owner', %s, NOW(), NOW())
            ON DUPLICATE KEY UPDATE
                nickname = VALUES(nickname),
                last_accessed = NOW()
        """, (user_id, device_id, nickname))

        # 5. Update device paired status and clear pairing code
        cursor.execute("""
            UPDATE devices
            SET paired_by = %s,
                paired_at = NOW(),
                pairing_code = NULL,
                pairing_qr_data = NULL,
                last_seen = NOW()
            WHERE device_id = %s
        """, (user_id, device_id))

        # 6. Get patient thresholds (nếu patient_id có sẵn)
        thresholds = {}
        if device_result.get('patient_id'):
            cursor.execute("""
                SELECT vital_sign, min_normal, max_normal, min_critical, max_critical
                FROM patient_thresholds
                WHERE patient_id = %s
                ORDER BY vital_sign
            """, (device_result['patient_id'],))

            thresholds_result = cursor.fetchall()

            # Convert thresholds to dict format
            for threshold in thresholds_result:
                thresholds[threshold['vital_sign']] = {
                    'min_normal': float(threshold['min_normal']),
                    'max_normal': float(threshold['max_normal']),
                    'min_critical': float(threshold['min_critical']),
                    'max_critical': float(threshold['max_critical'])
                }

        conn.commit()
        cursor.close()
        conn.close()

        # 7. Build response - patient_info = null nếu chưa có
        patient_info = None
        commands_topic = None

        if device_result.get('patient_id'):
            patient_info = {
                'patient_id': device_result['patient_id'],
                'name': device_result['patient_name'],
                'age': device_result['age'],
                'gender': device_result['gender']
            }
            commands_topic = f'iot_health/patient/{device_result["patient_id"]}/commands'

        response_data = {
            'device_info': {
                'device_id': device_result['device_id'],
                'device_name': device_result['device_name'],
                'device_type': device_result['device_type'],
                'location': device_result['location'],
                'nickname': nickname
            },
            'patient_info': patient_info,
            'mqtt_topics': {
                'vitals': f'iot_health/device/{device_id}/vitals',
                'alerts': f'iot_health/device/{device_id}/alerts',
                'status': f'iot_health/device/{device_id}/status',
                'commands': commands_topic
            },
            'thresholds': thresholds
        }

        return jsonify({
            'status': 'success',
            'message': 'Device paired successfully',
            'data': response_data
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/devices/<user_id>', methods=['GET'])
def get_user_devices(user_id):
    """Get all devices paired with a user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                d.device_id,
                d.device_name,
                d.device_type,
                d.location,
                d.firmware_version,
                d.os_version,
                do.nickname,
                do.role,
                do.added_at,
                do.last_accessed,
                d.last_seen,
                d.is_active,
                p.patient_id,
                p.name as patient_name,
                p.age,
                p.gender,
                p.is_active as patient_active
            FROM devices d
            JOIN device_ownership do ON d.device_id = do.device_id
            LEFT JOIN patients p ON d.device_id = p.device_id AND p.is_active = 1
            WHERE do.user_id = %s
            ORDER BY do.added_at DESC
        """, (user_id,))

        devices = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'devices': devices
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/patients', methods=['POST'])
def create_patient():
    """
    Tạo patient mới với đầy đủ medical information
    Hỗ trợ AI threshold generation
    Owner và Caregiver đều có quyền tạo
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        # Required fields
        user_id = data.get('user_id')
        name = data.get('name')

        # Basic info
        age = data.get('age')
        gender = data.get('gender')
        height = data.get('height')
        weight = data.get('weight')
        blood_type = data.get('blood_type')

        # Medical history (new fields)
        medical_conditions = data.get('medical_conditions')  # Legacy field
        chronic_diseases = data.get('chronic_diseases')
        medications = data.get('medications')
        allergies = data.get('allergies')
        family_history = data.get('family_history')

        # Lifestyle factors
        smoking_status = data.get('smoking_status')
        alcohol_consumption = data.get('alcohol_consumption')
        exercise_frequency = data.get('exercise_frequency')

        # Contact info
        emergency_contact = data.get('emergency_contact')

        # Optional
        patient_id = data.get('patient_id')
        generate_ai_thresholds = data.get('generate_ai_thresholds', False)  # Auto-generate AI thresholds
        threshold_method = data.get('threshold_method', 'hybrid')  # rule_based, ai_generated, hybrid

        if not all([user_id, name]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: user_id, name'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Generate patient_id if not provided
        if not patient_id:
            import hashlib
            patient_id = f"patient_{hashlib.md5((user_id + name + str(datetime.utcnow())).encode()).hexdigest()[:12]}"

        # Convert JSON fields to string
        medical_conditions_json = json.dumps(medical_conditions, ensure_ascii=False) if medical_conditions else None
        chronic_diseases_json = json.dumps(chronic_diseases, ensure_ascii=False) if chronic_diseases else None
        medications_json = json.dumps(medications, ensure_ascii=False) if medications else None
        allergies_json = json.dumps(allergies, ensure_ascii=False) if allergies else None
        family_history_json = json.dumps(family_history, ensure_ascii=False) if family_history else None
        emergency_contact_json = json.dumps(emergency_contact, ensure_ascii=False) if emergency_contact else None

        # Create new patient (device_id = NULL ban đầu)
        cursor.execute("""
            INSERT INTO patients (
                patient_id, device_id, name, age, gender,
                height, weight, blood_type,
                medical_conditions, chronic_diseases, medications,
                allergies, family_history,
                smoking_status, alcohol_consumption, exercise_frequency,
                emergency_contact, is_active, created_at
            )
            VALUES (%s, NULL, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1, NOW())
        """, (
            patient_id, name, age, gender,
            height, weight, blood_type,
            medical_conditions_json, chronic_diseases_json, medications_json,
            allergies_json, family_history_json,
            smoking_status, alcohol_consumption, exercise_frequency,
            emergency_contact_json
        ))

        # Generate thresholds
        ai_result = None  # Initialize variable to avoid reference error
        if generate_ai_thresholds and threshold_generator:
            # Use AI to generate personalized thresholds
            logger.info(f"🤖 Generating AI thresholds for new patient {patient_id}")

            patient_data = {
                'age': age, 'gender': gender, 'height': height, 'weight': weight,
                'blood_type': blood_type, 'chronic_diseases': chronic_diseases or [],
                'medications': medications or [], 'allergies': allergies or [],
                'family_history': family_history or [],
                'smoking_status': smoking_status,
                'alcohol_consumption': alcohol_consumption,
                'exercise_frequency': exercise_frequency
            }

            ai_result = threshold_generator.generate_thresholds(patient_data)
            metadata_json = json.dumps(ai_result['metadata'], ensure_ascii=False)

            for vital_sign, thresholds in ai_result['thresholds'].items():
                cursor.execute("""
                    INSERT INTO patient_thresholds (
                        patient_id, vital_sign,
                        min_normal, max_normal, min_warning, max_warning,
                        min_critical, max_critical,
                        generation_method, ai_confidence, ai_model,
                        generation_timestamp, metadata, is_active
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, 1)
                """, (
                    patient_id, vital_sign,
                    thresholds['min_normal'], thresholds['max_normal'],
                    thresholds.get('min_warning'), thresholds.get('max_warning'),
                    thresholds['min_critical'], thresholds['max_critical'],
                    ai_result['metadata']['generation_method'],
                    ai_result['metadata']['ai_confidence'],
                    ai_result['metadata']['ai_model'],
                    metadata_json
                ))
        else:
            # Use default manual thresholds
            default_thresholds = [
                (patient_id, 'heart_rate', 60, 100, 55, 110, 40, 120, 'manual'),
                (patient_id, 'spo2', 95, 100, 92, 100, 85, 100, 'manual'),
                (patient_id, 'temperature', 36.1, 37.2, 35.5, 37.8, 35.0, 40.0, 'manual'),
                (patient_id, 'systolic_bp', 90, 120, 85, 135, 70, 180, 'manual'),
                (patient_id, 'diastolic_bp', 60, 80, 55, 90, 40, 110, 'manual')
            ]

            cursor.executemany("""
                INSERT INTO patient_thresholds (
                    patient_id, vital_sign,
                    min_normal, max_normal, min_warning, max_warning,
                    min_critical, max_critical, generation_method
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, default_thresholds)

        conn.commit()

        # Get created patient info with all new fields
        cursor.execute("""
            SELECT patient_id, device_id, name, age, gender,
                   height, weight, blood_type,
                   medical_conditions, chronic_diseases, medications,
                   allergies, family_history,
                   smoking_status, alcohol_consumption, exercise_frequency,
                   emergency_contact, is_active
            FROM patients
            WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        cursor.close()
        conn.close()

        # Parse JSON fields for response
        response_data = {
            'patient_id': patient['patient_id'],
            'device_id': patient['device_id'],
            'name': patient['name'],
            'age': patient['age'],
            'gender': patient['gender'],
            'height': patient['height'],
            'weight': patient['weight'],
            'blood_type': patient['blood_type'],
            'is_active': bool(patient['is_active'])
        }

        # Parse JSON fields
        for field in ['medical_conditions', 'chronic_diseases', 'medications',
                      'allergies', 'family_history', 'emergency_contact']:
            if patient.get(field):
                try:
                    response_data[field] = json.loads(patient[field]) if isinstance(patient[field], str) else patient[field]
                except:
                    response_data[field] = patient[field]
            else:
                response_data[field] = None

        # Add lifestyle fields
        response_data['smoking_status'] = patient['smoking_status']
        response_data['alcohol_consumption'] = patient['alcohol_consumption']
        response_data['exercise_frequency'] = patient['exercise_frequency']

        # Add threshold generation info for Android app
        if generate_ai_thresholds:
            # Count how many thresholds were generated
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM patient_thresholds WHERE patient_id = %s", (patient_id,))
            thresholds_count = cursor.fetchone()[0]
            cursor.close()

            response_data['thresholds_generated'] = thresholds_count
            response_data['generation_method'] = threshold_method
            response_data['confidence_score'] = ai_result.get('metadata', {}).get('ai_confidence', 0.0) if ai_result else 0.0
        else:
            response_data['thresholds_generated'] = 5  # Default thresholds count
            response_data['generation_method'] = 'manual'
            response_data['confidence_score'] = None

        return jsonify({
            'status': 'success',
            'message': 'Patient created successfully',
            'data': response_data
        })

    except mysql.connector.IntegrityError as e:
        return jsonify({
            'status': 'error',
            'message': f'Patient ID already exists or constraint violation: {str(e)}'
        }), 409
    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        logger.error(f"❌ Error creating patient: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

    except mysql.connector.IntegrityError as e:
        return jsonify({
            'status': 'error',
            'message': f'Patient ID already exists or constraint violation: {str(e)}'
        }), 409
    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/patients/<patient_id>', methods=['PUT'])
def update_patient(patient_id):
    """
    Cập nhật thông tin patient
    Owner và Caregiver có quyền sửa
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        user_id = data.get('user_id')
        name = data.get('name')
        age = data.get('age')
        gender = data.get('gender')
        phone = data.get('phone')
        email = data.get('email')
        address = data.get('address')
        emergency_contact = data.get('emergencyContact')  # Android uses camelCase
        medical_history = data.get('medicalHistory')  # Android uses camelCase
        medical_conditions = data.get('medical_conditions')


        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get patient's device_id (nếu có)
        cursor.execute("""
            SELECT device_id FROM patients WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        if not patient:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Patient not found'
            }), 404

        # Verify user có quyền (owner hoặc caregiver)
        # If patient has device_id, check ownership. If not, allow update (patient not yet linked)
        if patient['device_id']:
            cursor.execute("""
                SELECT role FROM device_ownership
                WHERE device_id = %s AND user_id = %s
                AND role IN ('owner', 'caregiver')
            """, (patient['device_id'], user_id))

            ownership = cursor.fetchone()

            if not ownership:
                cursor.close()
                conn.close()
                return jsonify({
                    'status': 'error',
                    'message': 'User does not have permission to update this patient'
                }), 403
        else:
            # Patient not linked to device yet - allow update for any user
            # (In production, you should check if user_id matches patient creator)
            pass

        # Update patient info
        update_fields = []
        update_values = []

        if name is not None:
            update_fields.append('name = %s')
            update_values.append(name)
        if age is not None:
            update_fields.append('age = %s')
            update_values.append(age)
        if gender is not None:
            update_fields.append('gender = %s')
            update_values.append(gender)
        if medical_conditions is not None:
            update_fields.append('medical_conditions = %s')
            update_values.append(json.dumps(medical_conditions))
        if emergency_contact is not None:
            update_fields.append('emergency_contact = %s')
            update_values.append(json.dumps(emergency_contact))

        update_fields.append('updated_at = NOW()')
        update_values.append(patient_id)

        cursor.execute(f"""
            UPDATE patients
            SET {', '.join(update_fields)}
            WHERE patient_id = %s
        """, tuple(update_values))

        conn.commit()

        # Get updated patient info
        cursor.execute("""
            SELECT patient_id, device_id, name, age, gender, medical_conditions, emergency_contact, is_active
            FROM patients
            WHERE patient_id = %s
        """, (patient_id,))

        updated_patient = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Patient updated successfully',
            'data': {
                'patient_id': updated_patient['patient_id'],
                'device_id': updated_patient['device_id'],
                'name': updated_patient['name'],
                'age': updated_patient['age'],
                'gender': updated_patient['gender'],
                'medical_conditions': json.loads(updated_patient['medical_conditions']) if updated_patient['medical_conditions'] else None,
                'emergency_contact': json.loads(updated_patient['emergency_contact']) if updated_patient['emergency_contact'] else None,
                'is_active': bool(updated_patient['is_active'])
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/patients/<patient_id>/assign-device', methods=['POST'])
def assign_device_to_patient(patient_id):
    """
    Gán device cho patient (sau khi đã pair device)
    Owner và Caregiver có quyền gán
    1 device = 1 patient (1:1 relationship)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        user_id = data.get('user_id')
        device_id = data.get('device_id')

        if not all([user_id, device_id]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: user_id, device_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify user owns/manages this device (owner hoặc caregiver)
        cursor.execute("""
            SELECT role FROM device_ownership
            WHERE device_id = %s AND user_id = %s
            AND role IN ('owner', 'caregiver')
        """, (device_id, user_id))

        ownership = cursor.fetchone()

        if not ownership:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'User does not have permission for this device'
            }), 403

        # Verify patient exists
        cursor.execute("""
            SELECT patient_id, device_id, name FROM patients WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        if not patient:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Patient not found'
            }), 404

        # Check if device already assigned to another patient
        cursor.execute("""
            SELECT patient_id, name FROM patients
            WHERE device_id = %s AND patient_id != %s AND is_active = 1
        """, (device_id, patient_id))

        existing_assignment = cursor.fetchone()

        if existing_assignment:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': f'Device already assigned to patient: {existing_assignment["name"]} ({existing_assignment["patient_id"]})'
            }), 409

        # Assign device to patient
        cursor.execute("""
            UPDATE patients
            SET device_id = %s,
                updated_at = NOW()
            WHERE patient_id = %s
        """, (device_id, patient_id))

        conn.commit()

        # Get updated info
        cursor.execute("""
            SELECT p.patient_id, p.device_id, p.name, p.age, p.gender,
                   d.device_name, do.nickname
            FROM patients p
            JOIN devices d ON p.device_id = d.device_id
            LEFT JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = %s
            WHERE p.patient_id = %s
        """, (user_id, patient_id))

        result = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Device assigned to patient successfully',
            'data': {
                'patient_id': result['patient_id'],
                'patient_name': result['name'],
                'device_id': result['device_id'],
                'device_name': result['device_name'],
                'device_nickname': result['nickname'],
                'mqtt_commands_topic': f'iot_health/patient/{patient_id}/commands'
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/patients', methods=['GET'])
def get_patients():
    """
    Lấy danh sách patients của user (dựa trên devices đã pair)
    """
    try:
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get all patients associated with user's devices
        cursor.execute("""
            SELECT
                p.patient_id,
                p.device_id,
                p.name,
                p.age,
                p.gender,
                p.medical_conditions,
                p.emergency_contact,
                p.is_active,
                p.created_at,
                p.updated_at,
                d.device_name,
                do.nickname as device_nickname,
                do.role as user_role
            FROM patients p
            LEFT JOIN devices d ON p.device_id = d.device_id
            LEFT JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = %s
            WHERE p.is_active = 1
            ORDER BY p.created_at DESC
        """, (user_id,))

        patients = cursor.fetchall()

        cursor.close()
        conn.close()

        # Format response
        result = []
        for patient in patients:
            result.append({
                'patient_id': patient['patient_id'],
                'device_id': patient['device_id'],
                'name': patient['name'],
                'age': patient['age'],
                'gender': patient['gender'],
                'medical_conditions': json.loads(patient['medical_conditions']) if patient['medical_conditions'] else None,
                'emergency_contact': json.loads(patient['emergency_contact']) if patient['emergency_contact'] else None,
                'is_active': bool(patient['is_active']),
                'created_at': patient['created_at'].isoformat() if patient['created_at'] else None,
                'updated_at': patient['updated_at'].isoformat() if patient['updated_at'] else None,
                'device_name': patient['device_name'],
                'device_nickname': patient['device_nickname'],
                'user_role': patient['user_role']
            })

        return jsonify({
            'status': 'success',
            'count': len(result),
            'patients': result
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/patients/<patient_id>', methods=['DELETE'])
def delete_patient(patient_id):
    """
    Xóa patient vĩnh viễn (DELETE)
    Chỉ owner và caregiver có quyền xóa
    """
    try:
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get patient's device_id
        cursor.execute("""
            SELECT device_id, name FROM patients WHERE patient_id = %s
        """, (patient_id,))

        patient = cursor.fetchone()

        if not patient:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Patient not found'
            }), 404

        # Verify user có quyền (owner hoặc caregiver)
        # If patient has device_id, check ownership. If not, allow delete (patient not yet linked)
        if patient['device_id']:
            cursor.execute("""
                SELECT role FROM device_ownership
                WHERE device_id = %s AND user_id = %s
                AND role IN ('owner', 'caregiver')
            """, (patient['device_id'], user_id))

            ownership = cursor.fetchone()

            if not ownership:
                cursor.close()
                conn.close()
                return jsonify({
                    'status': 'error',
                    'message': 'User does not have permission to delete this patient'
                }), 403
        else:
            # Patient not linked to device yet - allow delete for any user
            # (In production, you should check if user_id matches patient creator)
            pass

        # Delete patient (CASCADE sẽ xóa health_records, alerts, thresholds)
        cursor.execute("""
            DELETE FROM patients WHERE patient_id = %s
        """, (patient_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': f'Patient {patient["name"]} deleted successfully'
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/patients/<patient_id>/ai-thresholds', methods=['GET'])
def get_patient_ai_thresholds(patient_id):
    """
    Get AI-generated thresholds for a specific patient
    Returns personalized thresholds from patient_thresholds table
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # First verify patient exists
        cursor.execute("SELECT patient_id, name FROM patients WHERE patient_id = %s", (patient_id,))
        patient = cursor.fetchone()

        if not patient:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Patient not found'
            }), 404

        # Query patient_thresholds table for AI-generated thresholds
        cursor.execute("""
            SELECT
                vital_sign,
                min_normal,
                max_normal,
                min_warning,
                max_warning,
                min_critical,
                max_critical,
                generation_method,
                ai_confidence,
                ai_model,
                generation_timestamp,
                metadata
            FROM patient_thresholds
            WHERE patient_id = %s AND is_active = 1
            ORDER BY generation_timestamp DESC
        """, (patient_id,))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        if not rows:
            return jsonify({
                'status': 'error',
                'message': 'No AI thresholds found for this patient'
            }), 404

        # Transform data into expected format for Android app
        thresholds = {}
        metadata = None

        for row in rows:
            vital_sign = row['vital_sign']

            # Debug: Log raw values from database
            logger.info(f"Processing threshold: {vital_sign}")
            logger.info(f"  Raw min_normal: {row['min_normal']} (type: {type(row['min_normal'])})")
            logger.info(f"  Raw max_normal: {row['max_normal']} (type: {type(row['max_normal'])})")

            # Ensure proper conversion from Decimal to float
            # Use 0.0 only if value is actually None/NULL
            min_normal_val = float(row['min_normal']) if row['min_normal'] is not None else 0.0
            max_normal_val = float(row['max_normal']) if row['max_normal'] is not None else 0.0
            min_warning_val = float(row['min_warning']) if row['min_warning'] is not None else 0.0
            max_warning_val = float(row['max_warning']) if row['max_warning'] is not None else 0.0
            min_critical_val = float(row['min_critical']) if row['min_critical'] is not None else 0.0
            max_critical_val = float(row['max_critical']) if row['max_critical'] is not None else 0.0

            logger.info(f"  Converted min_normal: {min_normal_val}")
            logger.info(f"  Converted max_normal: {max_normal_val}")

            thresholds[vital_sign] = {
                'minNormal': min_normal_val,
                'maxNormal': max_normal_val,
                'minWarning': min_warning_val,
                'maxWarning': max_warning_val,
                'minCritical': min_critical_val,
                'maxCritical': max_critical_val
            }

            # Use metadata from first row (all thresholds share same generation metadata)
            if metadata is None:
                metadata = {
                    'generationMethod': row['generation_method'] if row['generation_method'] else 'baseline',
                    'aiModel': row['ai_model'] if row['ai_model'] else 'baseline',
                    'aiConfidence': float(row['ai_confidence']) if row['ai_confidence'] else 0.0,
                    'generationTimestamp': str(row['generation_timestamp']) if row['generation_timestamp'] else '',
                    'appliedRules': [],
                    'inputFactors': {}
                }

                # Parse metadata JSON if available
                if row['metadata']:
                    try:
                        meta_json = json.loads(row['metadata'])
                        if 'applied_rules' in meta_json:
                            metadata['appliedRules'] = meta_json['applied_rules']
                        if 'input_factors' in meta_json:
                            metadata['inputFactors'] = meta_json['input_factors']
                    except Exception as e:
                        print(f"Warning: Could not parse metadata JSON: {e}")

        return jsonify({
            'status': 'success',
            'data': {
                'patient_id': patient_id,  # Use snake_case to match Android @SerializedName
                'thresholds': thresholds,
                'metadata': metadata
            }
        }), 200

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/generate-pairing-code', methods=['POST'])
def generate_pairing_code():
    """
    Generate new pairing code for device (called from Pi GUI)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        device_id = data.get('device_id')

        if not device_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: device_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify device exists
        cursor.execute("SELECT * FROM devices WHERE device_id = %s", (device_id,))
        device = cursor.fetchone()

        if not device:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Device not found'
            }), 404

        # Generate 8-character pairing code
        pairing_code = secrets.token_hex(4).upper()

        # Create QR data with expiry (10 minutes)
        qr_data = {
            'device_id': device_id,
            'pairing_code': pairing_code,
            'timestamp': datetime.utcnow().isoformat(),
            'expires_at': (datetime.utcnow() + timedelta(minutes=10)).isoformat()
        }

        # Update device with new pairing code
        cursor.execute("""
            UPDATE devices
            SET pairing_code = %s,
                pairing_qr_data = %s
            WHERE device_id = %s
        """, (pairing_code, json.dumps(qr_data), device_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Pairing code generated successfully',
            'data': {
                'pairing_code': pairing_code,
                'qr_data': qr_data,
                'expires_in_minutes': 10
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/devices/<device_id>/nickname', methods=['PUT'])
def update_device_nickname(device_id):
    """
    Update device nickname sau khi đã pair
    Cho phép user đổi tên device theo ý muốn
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        user_id = data.get('user_id')
        nickname = data.get('nickname')

        if not all([user_id, nickname]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields: user_id, nickname'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify user owns this device
        cursor.execute("""
            SELECT * FROM device_ownership
            WHERE device_id = %s AND user_id = %s
        """, (device_id, user_id))

        ownership = cursor.fetchone()

        if not ownership:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'User does not own this device'
            }), 403

        # Update nickname
        cursor.execute("""
            UPDATE device_ownership
            SET nickname = %s,
                last_accessed = NOW()
            WHERE device_id = %s AND user_id = %s
        """, (nickname, device_id, user_id))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Device nickname updated successfully',
            'data': {
                'device_id': device_id,
                'nickname': nickname
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/devices/<device_id>/status', methods=['GET'])
def get_device_status(device_id):
    """
    Get device online status and health metrics
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT
                d.device_id,
                d.device_name,
                d.is_active,
                d.last_seen,
                TIMESTAMPDIFF(SECOND, d.last_seen, NOW()) as seconds_offline,
                COUNT(hr.id) as records_24h,
                AVG(hr.data_quality) as avg_quality_24h
            FROM devices d
            LEFT JOIN health_records hr ON d.device_id = hr.device_id
                AND hr.timestamp >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
            WHERE d.device_id = %s
            GROUP BY d.device_id
        """, (device_id,))

        device = cursor.fetchone()

        if not device:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Device not found'
            }), 404

        # Determine online status (offline if no heartbeat in 5 minutes)
        is_online = device['seconds_offline'] < 300 if device['last_seen'] else False

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'data': {
                'device_id': device['device_id'],
                'device_name': device['device_name'],
                'is_online': is_online,
                'is_active': bool(device['is_active']),
                'last_seen': device['last_seen'].isoformat() if device['last_seen'] else None,
                'seconds_offline': device['seconds_offline'],
                'records_24h': device['records_24h'],
                'avg_data_quality': float(device['avg_quality_24h']) if device['avg_quality_24h'] else None
            }
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/api/health-records', methods=['GET'])
def get_health_records():
    """
    Get health records (vitals history) với filter và pagination
    DEVICE-CENTRIC APPROACH: Query theo device_id (primary), patient_id optional

    Query params:
    - user_id: User ID (required for authorization)
    - device_id: Filter by device (optional but recommended)
    - patient_id: Filter by patient (optional, auto-resolved từ device nếu không có)
    - start_date: ISO format datetime (optional, default: 7 days ago)
    - end_date: ISO format datetime (optional, default: now)
    - vital_sign: Filter by vital type (heart_rate, spo2, temperature, blood_pressure) (optional)
    - page: Page number (default: 1)
    - limit: Records per page (default: 50, max: 500)
    - sort_order: asc or desc (default: desc)

    Returns:
    - Paginated list of health records với metadata
    - Records có thể có patient_id = NULL nếu device chưa assign patient
    """
    try:
        # Get query parameters
        user_id = request.args.get('user_id')
        device_id = request.args.get('device_id')
        patient_id = request.args.get('patient_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        vital_sign = request.args.get('vital_sign')
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 50)), 500)  # Max 500 records
        sort_order = request.args.get('sort_order', 'desc').upper()

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'

        # Set default date range (7 days)
        if not start_date:
            start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        if not end_date:
            end_date = datetime.utcnow().isoformat()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify user has access to requested device/patient
        if device_id:
            cursor.execute("""
                SELECT device_id FROM device_ownership
                WHERE device_id = %s AND user_id = %s
            """, (device_id, user_id))

            if not cursor.fetchone():
                cursor.close()
                conn.close()
                return jsonify({
                    'status': 'error',
                    'message': 'User does not have access to this device'
                }), 403

        # Build dynamic query
        query = """
            SELECT
                hr.id,
                hr.device_id,
                hr.patient_id,
                hr.timestamp,
                hr.heart_rate,
                hr.spo2,
                hr.temperature,
                hr.systolic_bp,
                hr.diastolic_bp,
                hr.mean_arterial_pressure,
                hr.data_quality,
                hr.measurement_context,
                hr.sensor_data,
                d.device_name,
                do.nickname as device_nickname,
                p.name as patient_name
            FROM health_records hr
            JOIN devices d ON hr.device_id = d.device_id
            JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = %s
            LEFT JOIN patients p ON hr.patient_id = p.patient_id
            WHERE hr.timestamp BETWEEN %s AND %s
        """

        params = [user_id, start_date, end_date]

        # Add filters
        if device_id:
            query += " AND hr.device_id = %s"
            params.append(device_id)

        if patient_id:
            query += " AND hr.patient_id = %s"
            params.append(patient_id)

        # Filter by vital sign (có giá trị khác NULL)
        if vital_sign:
            vital_map = {
                'heart_rate': 'hr.heart_rate IS NOT NULL',
                'spo2': 'hr.spo2 IS NOT NULL',
                'temperature': 'hr.temperature IS NOT NULL',
                'blood_pressure': '(hr.systolic_bp IS NOT NULL AND hr.diastolic_bp IS NOT NULL)'
            }
            if vital_sign in vital_map:
                query += f" AND {vital_map[vital_sign]}"

        # Count total records
        count_query = f"SELECT COUNT(*) as total FROM ({query}) as subquery"
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()['total']

        # Add pagination
        offset = (page - 1) * limit
        query += f" ORDER BY hr.timestamp {sort_order} LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        # Execute query
        cursor.execute(query, params)
        records = cursor.fetchall()

        cursor.close()
        conn.close()

        # Format response
        result = []
        for record in records:
            result.append({
                'id': record['id'],
                'device_id': record['device_id'],
                'device_name': record['device_name'],
                'device_nickname': record['device_nickname'],
                'patient_id': record['patient_id'],
                'patient_name': record['patient_name'],
                'timestamp': record['timestamp'].isoformat() if record['timestamp'] else None,
                'vitals': {
                    'heart_rate': record['heart_rate'],
                    'spo2': record['spo2'],
                    'temperature': float(record['temperature']) if record['temperature'] else None,
                    'systolic_bp': record['systolic_bp'],
                    'diastolic_bp': record['diastolic_bp'],
                    'mean_arterial_pressure': record['mean_arterial_pressure']
                },
                'data_quality': float(record['data_quality']) if record['data_quality'] else None,
                'measurement_context': record['measurement_context'],
                'sensor_data': json.loads(record['sensor_data']) if record['sensor_data'] else None
            })

        total_pages = (total_records + limit - 1) // limit

        return jsonify({
            'status': 'success',
            'data': result,
            'pagination': {
                'page': page,
                'limit': limit,
                'total_records': total_records,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'filters': {
                'device_id': device_id,
                'patient_id': patient_id,
                'start_date': start_date,
                'end_date': end_date,
                'vital_sign': vital_sign,
                'sort_order': sort_order
            }
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'Invalid parameter: {str(e)}'
        }), 400
    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/health-records/<int:record_id>', methods=['GET'])
def get_health_record_detail(record_id):
    """
    Get chi tiết single health record với full sensor data

    Query params:
    - user_id: User ID (required for authorization)
    """
    try:
        user_id = request.args.get('user_id')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get record với authorization check
        cursor.execute("""
            SELECT
                hr.*,
                d.device_name,
                do.nickname as device_nickname,
                p.name as patient_name,
                p.age,
                p.gender
            FROM health_records hr
            JOIN devices d ON hr.device_id = d.device_id
            JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = %s
            LEFT JOIN patients p ON hr.patient_id = p.patient_id
            WHERE hr.id = %s
        """, (user_id, record_id))

        record = cursor.fetchone()

        if not record:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Record not found or access denied'
            }), 404

        cursor.close()
        conn.close()

        # Format response
        return jsonify({
            'status': 'success',
            'data': {
                'id': record['id'],
                'device_id': record['device_id'],
                'device_name': record['device_name'],
                'device_nickname': record['device_nickname'],
                'patient_id': record['patient_id'],
                'patient_name': record['patient_name'],
                'patient_age': record['age'],
                'patient_gender': record['gender'],
                'timestamp': record['timestamp'].isoformat() if record['timestamp'] else None,
                'vitals': {
                    'heart_rate': record['heart_rate'],
                    'spo2': record['spo2'],
                    'temperature': float(record['temperature']) if record['temperature'] else None,
                    'systolic_bp': record['systolic_bp'],
                    'diastolic_bp': record['diastolic_bp'],
                    'mean_arterial_pressure': record['mean_arterial_pressure']
                },
                'data_quality': float(record['data_quality']) if record['data_quality'] else None,
                'measurement_context': record['measurement_context'],
                'sensor_data': json.loads(record['sensor_data']) if record['sensor_data'] else None,
                'synced_at': record['synced_at'].isoformat() if record['synced_at'] else None,
                'sync_status': record['sync_status']
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """
    Get alerts history với filter và pagination
    DEVICE-CENTRIC APPROACH: Query theo device_id (primary), patient_id optional

    Query params:
    - user_id: User ID (required for authorization)
    - device_id: Filter by device (optional but recommended)
    - patient_id: Filter by patient (optional, auto-resolved từ device nếu không có)
    - severity: Filter by severity (low, medium, high, critical) (optional)
    - alert_type: Filter by alert type (optional)
    - start_date: ISO format datetime (optional, default: 30 days ago)
    - end_date: ISO format datetime (optional, default: now)
    - acknowledged: Filter by acknowledged status (true/false) (optional)
    - page: Page number (default: 1)
    - limit: Records per page (default: 50, max: 200)
    - sort_order: asc or desc (default: desc)

    Returns:
    - Paginated list of alerts với metadata
    - Alerts có thể có patient_id = NULL nếu device chưa assign patient
    """
    try:
        # Get query parameters
        user_id = request.args.get('user_id')
        device_id = request.args.get('device_id')
        patient_id = request.args.get('patient_id')
        severity = request.args.get('severity')
        alert_type = request.args.get('alert_type')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        acknowledged = request.args.get('acknowledged')
        page = int(request.args.get('page', 1))
        limit = min(int(request.args.get('limit', 50)), 200)  # Max 200 records
        sort_order = request.args.get('sort_order', 'desc').upper()

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        if sort_order not in ['ASC', 'DESC']:
            sort_order = 'DESC'

        # Set default date range (30 days) using UTC+7 Vietnam timezone
        from datetime import timezone, timedelta as td
        vietnam_tz = timezone(td(hours=7))
        now_vietnam = datetime.now(vietnam_tz)

        if not start_date:
            start_date = (now_vietnam - timedelta(days=30)).isoformat()
        if not end_date:
            end_date = now_vietnam.isoformat()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Build dynamic query
        query = """
            SELECT
                a.id,
                a.device_id,
                a.patient_id,
                a.alert_type,
                a.severity,
                a.message,
                a.vital_sign,
                a.current_value,
                a.threshold_value,
                a.timestamp,
                a.acknowledged,
                a.resolved,
                a.notification_sent,
                a.notification_method,
                d.device_name,
                do.nickname as device_nickname,
                p.name as patient_name
            FROM alerts a
            JOIN devices d ON a.device_id = d.device_id
            JOIN device_ownership do ON d.device_id = do.device_id AND do.user_id = %s
            LEFT JOIN patients p ON a.patient_id = p.patient_id
            WHERE a.timestamp BETWEEN %s AND %s
        """

        params = [user_id, start_date, end_date]

        # Add filters
        if device_id:
            query += " AND a.device_id = %s"
            params.append(device_id)

        if patient_id:
            query += " AND a.patient_id = %s"
            params.append(patient_id)

        if severity:
            query += " AND a.severity = %s"
            params.append(severity)

        if alert_type:
            query += " AND a.alert_type = %s"
            params.append(alert_type)

        if acknowledged is not None:
            ack_value = acknowledged.lower() in ['true', '1', 'yes']
            query += " AND a.acknowledged = %s"
            params.append(ack_value)

        # Count total records
        count_query = f"SELECT COUNT(*) as total FROM ({query}) as subquery"
        cursor.execute(count_query, params)
        total_records = cursor.fetchone()['total']

        # Add pagination
        offset = (page - 1) * limit
        query += f" ORDER BY a.timestamp {sort_order} LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        # Execute query
        cursor.execute(query, params)
        alerts = cursor.fetchall()

        cursor.close()
        conn.close()

        # Format response
        result = []
        for alert in alerts:
            # Generate summary for mobile app list view
            summary = ""
            if alert['alert_type'] == 'high_heart_rate':
                summary = f"Nhịp tim cao: {alert['current_value']} BPM"
            elif alert['alert_type'] == 'low_temperature':
                summary = f"Nhiệt độ thấp: {alert['current_value']}°C"
            elif alert['alert_type'] == 'high_temperature':
                summary = f"Nhiệt độ cao: {alert['current_value']}°C"
            elif alert['alert_type'] == 'low_spo2':
                summary = f"SpO2 thấp: {alert['current_value']}%"
            else:
                # Generic summary from message
                summary = alert['message'][:50] + "..." if len(alert['message']) > 50 else alert['message']

            result.append({
                'id': alert['id'],
                'device_id': alert['device_id'],
                'device_name': alert['device_name'],
                'device_nickname': alert['device_nickname'],
                'patient_id': alert['patient_id'],
                'patient_name': alert['patient_name'],
                'alert_type': alert['alert_type'],
                'severity': alert['severity'],
                'summary': summary,  # ✅ THÊM TRƯỜNG SUMMARY
                'message': alert['message'],
                'vital_sign': alert['vital_sign'],
                'current_value': float(alert['current_value']) if alert['current_value'] else None,
                'threshold_value': float(alert['threshold_value']) if alert['threshold_value'] else None,
                'timestamp': alert['timestamp'].isoformat() if alert['timestamp'] else None,
                'acknowledged': bool(alert['acknowledged']),
                'resolved': bool(alert['resolved']),
                'notification_sent': bool(alert['notification_sent']),
                'notification_method': alert['notification_method']
            })

        total_pages = (total_records + limit - 1) // limit

        return jsonify({
            'status': 'success',
            'data': result,
            'pagination': {
                'page': page,
                'limit': limit,
                'total_records': total_records,
                'total_pages': total_pages,
                'has_next': page < total_pages,
                'has_prev': page > 1
            },
            'filters': {
                'device_id': device_id,
                'patient_id': patient_id,
                'severity': severity,
                'alert_type': alert_type,
                'start_date': start_date,
                'end_date': end_date,
                'acknowledged': acknowledged,
                'sort_order': sort_order
            }
        })

    except ValueError as e:
        return jsonify({
            'status': 'error',
            'message': f'Invalid parameter: {str(e)}'
        }), 400
    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/alerts/<int:alert_id>/acknowledge', methods=['PUT'])
def acknowledge_alert(alert_id):
    """
    Mark alert as acknowledged

    Body params:
    - user_id: User ID (required for authorization)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        user_id = data.get('user_id')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify user has access to this alert
        cursor.execute("""
            SELECT a.id, a.device_id
            FROM alerts a
            JOIN device_ownership do ON a.device_id = do.device_id AND do.user_id = %s
            WHERE a.id = %s
        """, (user_id, alert_id))

        alert = cursor.fetchone()

        if not alert:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Alert not found or access denied'
            }), 404

        # Update alert
        cursor.execute("""
            UPDATE alerts
            SET acknowledged = 1
            WHERE id = %s
        """, (alert_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Alert acknowledged successfully',
            'data': {
                'alert_id': alert_id,
                'acknowledged': True
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/alerts/<int:alert_id>/resolve', methods=['PUT'])
def resolve_alert(alert_id):
    """
    Mark alert as resolved

    Body params:
    - user_id: User ID (required for authorization)
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        user_id = data.get('user_id')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: user_id'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Verify user has access to this alert (owner or caregiver)
        cursor.execute("""
            SELECT a.id, a.device_id
            FROM alerts a
            JOIN device_ownership do ON a.device_id = do.device_id
            WHERE a.id = %s AND do.user_id = %s
            AND do.role IN ('owner', 'caregiver')
        """, (alert_id, user_id))

        alert = cursor.fetchone()

        if not alert:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': 'Alert not found or access denied'
            }), 404

        # Update alert
        cursor.execute("""
            UPDATE alerts
            SET resolved = 1,
                acknowledged = 1
            WHERE id = %s
        """, (alert_id,))

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'message': 'Alert resolved successfully',
            'data': {
                'alert_id': alert_id,
                'resolved': True,
                'acknowledged': True
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/alerts/statistics', methods=['GET'])
def get_alerts_statistics():
    """
    Get alerts statistics cho dashboard mobile app

    Query params:
    - user_id: User ID (required)
    - device_id: Device ID (optional)
    - patient_id: Patient ID (optional)
    - days: Number of days to look back (default: 7)

    Returns:
    - Alert counts by severity, status
    - Recent alerts summary
    """
    try:
        user_id = request.args.get('user_id')
        device_id = request.args.get('device_id')
        patient_id = request.args.get('patient_id')
        days = int(request.args.get('days', 7))

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        # Use UTC+7 Vietnam timezone
        from datetime import timezone, timedelta as td
        vietnam_tz = timezone(td(hours=7))
        now_vietnam = datetime.now(vietnam_tz)
        start_date = (now_vietnam - timedelta(days=days)).isoformat()
        end_date = now_vietnam.isoformat()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Build base query
        base_query = """
            FROM alerts a
            JOIN device_ownership do ON a.device_id = do.device_id AND do.user_id = %s
            WHERE a.timestamp BETWEEN %s AND %s
        """

        params = [user_id, start_date, end_date]

        if device_id:
            base_query += " AND a.device_id = %s"
            params.append(device_id)

        if patient_id:
            base_query += " AND a.patient_id = %s"
            params.append(patient_id)

        # Get severity counts
        severity_query = f"""
            SELECT
                a.severity,
                COUNT(*) as count
            {base_query}
            GROUP BY a.severity
        """

        cursor.execute(severity_query, params)
        severity_stats = cursor.fetchall()

        # Get status counts
        status_query = f"""
            SELECT
                CASE
                    WHEN a.resolved = 1 THEN 'resolved'
                    WHEN a.acknowledged = 1 THEN 'acknowledged'
                    ELSE 'active'
                END as status,
                COUNT(*) as count
            {base_query}
            GROUP BY
                CASE
                    WHEN a.resolved = 1 THEN 'resolved'
                    WHEN a.acknowledged = 1 THEN 'acknowledged'
                    ELSE 'active'
                END
        """

        cursor.execute(status_query, params)
        status_stats = cursor.fetchall()

        # Get recent alerts (last 10)
        recent_query = f"""
            SELECT
                a.id,
                a.alert_type,
                a.severity,
                a.message,
                a.timestamp,
                d.device_name,
                do.nickname as device_nickname
            {base_query.replace('FROM alerts a', 'FROM alerts a JOIN devices d ON a.device_id = d.device_id')}
            ORDER BY a.timestamp DESC
            LIMIT 10
        """

        cursor.execute(recent_query, params)
        recent_alerts = cursor.fetchall()

        cursor.close()
        conn.close()

        # Format severity stats
        severity_dict = {'low': 0, 'medium': 0, 'high': 0, 'critical': 0}
        for stat in severity_stats:
            severity_dict[stat['severity']] = stat['count']

        # Format status stats
        status_dict = {'active': 0, 'acknowledged': 0, 'resolved': 0}
        for stat in status_stats:
            status_dict[stat['status']] = stat['count']

        # Format recent alerts
        recent_list = []
        for alert in recent_alerts:
            recent_list.append({
                'id': alert['id'],
                'alert_type': alert['alert_type'],
                'severity': alert['severity'],
                'message': alert['message'][:100] + "..." if len(alert['message']) > 100 else alert['message'],
                'timestamp': alert['timestamp'].isoformat() if alert['timestamp'] else None,
                'device_name': alert['device_name'],
                'device_nickname': alert['device_nickname']
            })

        return jsonify({
            'status': 'success',
            'data': {
                'time_range': {
                    'days': days,
                    'start': start_date,
                    'end': end_date
                },
                'severity_counts': severity_dict,
                'status_counts': status_dict,
                'total_alerts': sum(severity_dict.values()),
                'recent_alerts': recent_list
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/vitals/statistics', methods=['GET'])
def get_vitals_statistics():
    """
    Get vitals statistics (min, max, avg) cho time range

    Query params:
    - user_id: User ID (required)
    - device_id: Device ID (optional)
    - patient_id: Patient ID (optional)
    - start_date: ISO format (default: 7 days ago)
    - end_date: ISO format (default: now)

    Returns:
    - Statistics for each vital sign
    """
    try:
        user_id = request.args.get('user_id')
        device_id = request.args.get('device_id')
        patient_id = request.args.get('patient_id')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        if not user_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required parameter: user_id'
            }), 400

        # Set default date range (7 days)
        if not start_date:
            start_date = (datetime.utcnow() - timedelta(days=7)).isoformat()
        if not end_date:
            end_date = datetime.utcnow().isoformat()

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Build query
        query = """
            SELECT
                COUNT(*) as total_records,
                AVG(heart_rate) as avg_heart_rate,
                MIN(heart_rate) as min_heart_rate,
                MAX(heart_rate) as max_heart_rate,
                AVG(spo2) as avg_spo2,
                MIN(spo2) as min_spo2,
                MAX(spo2) as max_spo2,
                AVG(temperature) as avg_temperature,
                MIN(temperature) as min_temperature,
                MAX(temperature) as max_temperature,
                AVG(systolic_bp) as avg_systolic,
                MIN(systolic_bp) as min_systolic,
                MAX(systolic_bp) as max_systolic,
                AVG(diastolic_bp) as avg_diastolic,
                MIN(diastolic_bp) as min_diastolic,
                MAX(diastolic_bp) as max_diastolic
            FROM health_records hr
            JOIN device_ownership do ON hr.device_id = do.device_id AND do.user_id = %s
            WHERE hr.timestamp BETWEEN %s AND %s
        """

        params = [user_id, start_date, end_date]

        if device_id:
            query += " AND hr.device_id = %s"
            params.append(device_id)

        if patient_id:
            query += " AND hr.patient_id = %s"
            params.append(patient_id)

        cursor.execute(query, params)
        stats = cursor.fetchone()

        cursor.close()
        conn.close()

        return jsonify({
            'status': 'success',
            'data': {
                'total_records': stats['total_records'],
                'date_range': {
                    'start': start_date,
                    'end': end_date
                },
                'heart_rate': {
                    'avg': float(stats['avg_heart_rate']) if stats['avg_heart_rate'] else None,
                    'min': stats['min_heart_rate'],
                    'max': stats['max_heart_rate']
                },
                'spo2': {
                    'avg': float(stats['avg_spo2']) if stats['avg_spo2'] else None,
                    'min': stats['min_spo2'],
                    'max': stats['max_spo2']
                },
                'temperature': {
                    'avg': float(stats['avg_temperature']) if stats['avg_temperature'] else None,
                    'min': float(stats['min_temperature']) if stats['min_temperature'] else None,
                    'max': float(stats['max_temperature']) if stats['max_temperature'] else None
                },
                'blood_pressure': {
                    'systolic': {
                        'avg': float(stats['avg_systolic']) if stats['avg_systolic'] else None,
                        'min': stats['min_systolic'],
                        'max': stats['max_systolic']
                    },
                    'diastolic': {
                        'avg': float(stats['avg_diastolic']) if stats['avg_diastolic'] else None,
                        'min': stats['min_diastolic'],
                        'max': stats['max_diastolic']
                    }
                }
            }
        })

    except mysql.connector.Error as e:
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500

@app.route('/api/ai/generate-thresholds', methods=['POST'])
def generate_ai_thresholds():
    """
    Generate personalized thresholds using AI

    Request body:
    {
        "patient_id": "patient_001",
        "method": "hybrid"  // "rule_based", "ai_generated", or "hybrid"
    }

    Response:
    {
        "status": "success",
        "data": {
            "patient_id": "patient_001",
            "thresholds": {
                "heart_rate": {"min_normal": 60, "max_normal": 100, ...},
                "spo2": {...},
                ...
            },
            "metadata": {
                "generation_method": "hybrid",
                "ai_model": "rule_based + gemini-1.5-pro",
                "ai_confidence": 0.95,
                "generation_timestamp": "2025-12-15T18:30:00",
                "applied_rules": [...],
                "input_factors": {...}
            }
        }
    }
    """
    try:
        if not threshold_generator:
            return jsonify({
                'status': 'error',
                'message': 'Threshold generator not available'
            }), 503

        data = request.get_json()

        if not data:
            return jsonify({
                'status': 'error',
                'message': 'No JSON data provided'
            }), 400

        patient_id = data.get('patient_id')
        method = data.get('method', 'hybrid')  # Default to hybrid

        if not patient_id:
            return jsonify({
                'status': 'error',
                'message': 'Missing required field: patient_id'
            }), 400

        # Validate method
        if method not in ['rule_based', 'ai_generated', 'hybrid']:
            return jsonify({
                'status': 'error',
                'message': f'Invalid method: {method}. Use rule_based, ai_generated, or hybrid'
            }), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Get patient data
        cursor.execute("""
            SELECT patient_id, name, age, gender, height, weight, blood_type,
                   medical_conditions, chronic_diseases, medications, allergies,
                   family_history, smoking_status, alcohol_consumption,
                   exercise_frequency, risk_factors
            FROM patients
            WHERE patient_id = %s AND is_active = 1
        """, (patient_id,))

        patient = cursor.fetchone()

        if not patient:
            cursor.close()
            conn.close()
            return jsonify({
                'status': 'error',
                'message': f'Patient not found: {patient_id}'
            }), 404

        # Parse JSON fields
        for field in ['chronic_diseases', 'medications', 'allergies', 'family_history', 'risk_factors']:
            if patient.get(field):
                try:
                    patient[field] = json.loads(patient[field]) if isinstance(patient[field], str) else patient[field]
                except:
                    patient[field] = []

        # Generate thresholds
        logger.info(f"🔧 Generating thresholds for {patient_id} using hybrid method")
        result = threshold_generator.generate_thresholds(patient)

        # Save thresholds to database
        metadata_json = json.dumps(result['metadata'], ensure_ascii=False)

        for vital_sign, thresholds in result['thresholds'].items():
            cursor.execute("""
                INSERT INTO patient_thresholds (
                    patient_id, vital_sign,
                    min_normal, max_normal,
                    min_warning, max_warning,
                    min_critical, max_critical,
                    generation_method, ai_confidence, ai_model,
                    generation_timestamp, metadata, is_active
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s, 1)
                ON DUPLICATE KEY UPDATE
                    min_normal = VALUES(min_normal),
                    max_normal = VALUES(max_normal),
                    min_warning = VALUES(min_warning),
                    max_warning = VALUES(max_warning),
                    min_critical = VALUES(min_critical),
                    max_critical = VALUES(max_critical),
                    generation_method = VALUES(generation_method),
                    ai_confidence = VALUES(ai_confidence),
                    ai_model = VALUES(ai_model),
                    generation_timestamp = NOW(),
                    metadata = VALUES(metadata),
                    updated_at = NOW()
            """, (
                patient_id, vital_sign,
                thresholds['min_normal'], thresholds['max_normal'],
                thresholds.get('min_warning'), thresholds.get('max_warning'),
                thresholds['min_critical'], thresholds['max_critical'],
                result['metadata']['generation_method'],
                result['metadata']['ai_confidence'],
                result['metadata']['ai_model'],
                metadata_json
            ))

        conn.commit()
        cursor.close()
        conn.close()

        logger.info(f"✅ Thresholds saved for {patient_id}")

        return jsonify({
            'status': 'success',
            'message': 'Thresholds generated successfully',
            'data': {
                'patient_id': patient_id,
                'thresholds': result['thresholds'],
                'metadata': result['metadata']
            }
        })

    except mysql.connector.Error as e:
        logger.error(f"❌ Database error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Database error: {str(e)}'
        }), 500
    except Exception as e:
        logger.error(f"❌ Server error: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Server error: {str(e)}'
        }), 500


# ==================== Medical Data Selection Endpoints ====================

@app.route('/api/medical-data/chronic-diseases', methods=['GET'])
def get_chronic_diseases():
    """
    Get list of chronic diseases from threshold_generation_rules
    Returns both English (for backend) and Vietnamese (for UI display)

    Response:
    {
        "status": "success",
        "data": [
            {
                "nameEn": "COPD",
                "nameVi": "Bệnh phổi tắc nghẽn mạn tính (COPD)",
                "category": "chronic_diseases"
            },
            ...
        ]
    }
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Query unique chronic diseases from threshold_generation_rules
        cursor.execute("""
            SELECT DISTINCT conditions
            FROM threshold_generation_rules
            WHERE is_active = TRUE
            AND JSON_CONTAINS_PATH(conditions, 'one', '$.chronic_diseases')
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Extract unique diseases
        diseases_set = set()
        for row in rows:
            try:
                conditions = json.loads(row['conditions']) if isinstance(row['conditions'], str) else row['conditions']
                if 'chronic_diseases' in conditions:
                    diseases_list = conditions['chronic_diseases']
                    if isinstance(diseases_list, list):
                        for disease in diseases_list:
                            diseases_set.add(disease.strip())
            except Exception as e:
                logger.warning(f"Failed to parse conditions: {e}")
                continue

        # Build response with translations
        result = []
        translations = MEDICAL_DATA_TRANSLATIONS['chronic_diseases']

        for disease_en in sorted(diseases_set):
            result.append({
                'nameEn': disease_en,
                'nameVi': translations.get(disease_en, disease_en),  # Fallback to English if no translation
                'category': 'chronic_diseases'
            })

        logger.info(f"✅ Returned {len(result)} chronic diseases")
        return jsonify({
            'status': 'success',
            'data': result
        })

    except Exception as e:
        logger.error(f"❌ Error fetching chronic diseases: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to fetch chronic diseases: {str(e)}'
        }), 500


@app.route('/api/medical-data/medications', methods=['GET'])
def get_medications():
    """
    Get list of medications from threshold_generation_rules
    Returns both English (for backend) and Vietnamese (for UI display)

    Response:
    {
        "status": "success",
        "data": [
            {
                "nameEn": "Metoprolol",
                "nameVi": "Metoprolol (thuốc chẹn beta)",
                "category": "medications"
            },
            ...
        ]
    }
    """
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        # Query unique medications from threshold_generation_rules
        cursor.execute("""
            SELECT DISTINCT conditions
            FROM threshold_generation_rules
            WHERE is_active = TRUE
            AND JSON_CONTAINS_PATH(conditions, 'one', '$.medications')
        """)

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Extract unique medications
        medications_set = set()
        for row in rows:
            try:
                conditions = json.loads(row['conditions']) if isinstance(row['conditions'], str) else row['conditions']
                if 'medications' in conditions:
                    meds_list = conditions['medications']
                    if isinstance(meds_list, list):
                        for med in meds_list:
                            medications_set.add(med.strip())
            except Exception as e:
                logger.warning(f"Failed to parse conditions: {e}")
                continue

        # Build response with translations
        result = []
        translations = MEDICAL_DATA_TRANSLATIONS['medications']

        for med_en in sorted(medications_set):
            result.append({
                'nameEn': med_en,
                'nameVi': translations.get(med_en, med_en),
                'category': 'medications'
            })

        logger.info(f"✅ Returned {len(result)} medications")
        return jsonify({
            'status': 'success',
            'data': result
        })

    except Exception as e:
        logger.error(f"❌ Error fetching medications: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to fetch medications: {str(e)}'
        }), 500


@app.route('/api/medical-data/allergies', methods=['GET'])
def get_allergies():
    """
    Get list of common allergies
    Returns both English (for backend) and Vietnamese (for UI display)

    Response:
    {
        "status": "success",
        "data": [
            {
                "nameEn": "Penicillin",
                "nameVi": "Penicillin",
                "category": "allergies"
            },
            ...
        ]
    }
    """
    try:
        # Use predefined list from MEDICAL_DATA_TRANSLATIONS
        result = []
        translations = MEDICAL_DATA_TRANSLATIONS['allergies']

        for allergy_en, allergy_vi in sorted(translations.items()):
            result.append({
                'nameEn': allergy_en,
                'nameVi': allergy_vi,
                'category': 'allergies'
            })

        logger.info(f"✅ Returned {len(result)} allergies")
        return jsonify({
            'status': 'success',
            'data': result
        })

    except Exception as e:
        logger.error(f"❌ Error fetching allergies: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to fetch allergies: {str(e)}'
        }), 500


@app.route('/api/medical-data/family-history', methods=['GET'])
def get_family_history():
    """
    Get list of common family history conditions
    Returns both English (for backend) and Vietnamese (for UI display)

    Response:
    {
        "status": "success",
        "data": [
            {
                "nameEn": "Heart Disease",
                "nameVi": "Bệnh tim mạch",
                "category": "family_history"
            },
            ...
        ]
    }
    """
    try:
        # Use predefined list from MEDICAL_DATA_TRANSLATIONS
        result = []
        translations = MEDICAL_DATA_TRANSLATIONS['family_history']

        for condition_en, condition_vi in sorted(translations.items()):
            result.append({
                'nameEn': condition_en,
                'nameVi': condition_vi,
                'category': 'family_history'
            })

        logger.info(f"✅ Returned {len(result)} family history conditions")
        return jsonify({
            'status': 'success',
            'data': result
        })

    except Exception as e:
        logger.error(f"❌ Error fetching family history: {e}")
        return jsonify({
            'status': 'error',
            'message': f'Failed to fetch family history: {str(e)}'
        }), 500


if __name__ == '__main__':
    # Production: Use gunicorn instead
    # gunicorn -w 4 -b 0.0.0.0:8000 flask_api_pairing:app
    app.run(host='0.0.0.0', port=8000, debug=False)
