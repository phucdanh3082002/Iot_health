#!/usr/bin/env python3
"""
AI Threshold Generator
Generates personalized vital sign thresholds using rule-based logic + Google Gemini API
Compatible with Database Schema v2.1.0 (AI Threshold Support)
"""

import os
import json
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import mysql.connector

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ThresholdGenerator:
    """
    Hybrid AI-powered threshold generator with comprehensive medical rule-based system

    This system combines evidence-based medical guidelines with AI refinement to generate
    personalized vital sign thresholds. It follows international standards including:
    - AHA (American Heart Association) Guidelines for Heart Rate
    - JNC8 (Eighth Joint National Committee) for Blood Pressure
    - ADA (American Diabetes Association) Standards
    - WHO (World Health Organization) Guidelines
    - ATS/ERS (American Thoracic Society/European Respiratory Society) for SpO2
    - NICE (National Institute for Health and Care Excellence) Guidelines

    Method: HYBRID ONLY (Rule-based foundation + AI refinement)
    - Phase 1: Apply comprehensive medical rules from database
    - Phase 2: AI (Gemini 2.0) refines based on patient context
    - Phase 3: Validate against safety bounds
    """

    # Baseline thresholds based on international medical standards
    # Sources: AHA 2020, JNC8, WHO 2021, ATS/ERS 2019
    BASELINE_THRESHOLDS = {
        'heart_rate': {  # AHA Guidelines 2020
            'min_normal': 60.0,   # Bradycardia threshold
            'max_normal': 100.0,  # Tachycardia threshold
            'min_warning': 55.0,  # Pre-bradycardia
            'max_warning': 110.0, # Pre-tachycardia
            'min_critical': 40.0, # Severe bradycardia (emergency)
            'max_critical': 120.0 # Severe tachycardia (emergency)
        },
        'spo2': {  # ATS/ERS Guidelines 2019
            'min_normal': 95.0,   # Normal oxygen saturation
            'max_normal': 100.0,  # Upper physiological limit
            'min_warning': 92.0,  # Mild hypoxemia
            'max_warning': 100.0,
            'min_critical': 85.0, # Severe hypoxemia (emergency)
            'max_critical': 100.0
        },
        'temperature': {  # WHO/NICE Guidelines 2021
            'min_normal': 36.1,   # Normal body temp (Celsius)
            'max_normal': 37.2,   # Normal upper limit
            'min_warning': 35.5,  # Mild hypothermia warning
            'max_warning': 37.8,  # Mild fever warning
            'min_critical': 35.0, # Hypothermia (emergency)
            'max_critical': 40.0  # Hyperthermia (emergency)
        },
        'systolic_bp': {  # JNC8 Guidelines 2014
            'min_normal': 90.0,   # Hypotension threshold
            'max_normal': 120.0,  # Pre-hypertension threshold
            'min_warning': 85.0,  # Severe hypotension warning
            'max_warning': 135.0, # Stage 1 hypertension
            'min_critical': 70.0, # Shock range (emergency)
            'max_critical': 180.0 # Hypertensive crisis (emergency)
        },
        'diastolic_bp': {  # JNC8 Guidelines 2014
            'min_normal': 60.0,   # Hypotension threshold
            'max_normal': 80.0,   # Pre-hypertension threshold
            'min_warning': 55.0,  # Severe hypotension warning
            'max_warning': 90.0,  # Stage 1 hypertension
            'min_critical': 40.0, # Shock range (emergency)
            'max_critical': 110.0 # Hypertensive crisis (emergency)
        }
    }

    # Safety bounds - absolute limits that cannot be exceeded
    # These protect against erroneous adjustments
    SAFETY_BOUNDS = {
        'heart_rate': {'absolute_min': 30.0, 'absolute_max': 200.0},
        'spo2': {'absolute_min': 70.0, 'absolute_max': 100.0},
        'temperature': {'absolute_min': 32.0, 'absolute_max': 42.0},
        'systolic_bp': {'absolute_min': 50.0, 'absolute_max': 250.0},
        'diastolic_bp': {'absolute_min': 30.0, 'absolute_max': 150.0}
    }

    def __init__(self, db_config: Dict[str, Any], gemini_api_key: Optional[str] = None):
        """
        Initialize threshold generator

        Args:
            db_config: MySQL database configuration
            gemini_api_key: Google Gemini API key (optional, for AI mode)
        """
        self.db_config = db_config
        self.gemini_api_key = gemini_api_key or os.getenv('GOOGLE_GEMINI_API_KEY')
        self.gemini_client = None

        # Initialize Gemini client if API key available
        if self.gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=self.gemini_api_key)
                self.gemini_client = genai.GenerativeModel('gemini-2.0-flash')
                logger.info("✅ Google Gemini API initialized (gemini-2.0-flash)")
            except ImportError:
                logger.warning("⚠️ google-generativeai package not installed, using rule-based only")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize Gemini API: {e}")
        else:
            logger.info("ℹ️ No Gemini API key, using rule-based mode only")

    def generate_thresholds(
        self,
        patient_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Generate personalized thresholds for a patient using HYBRID method only

        Process:
        1. Apply comprehensive rule-based adjustments from database
        2. Refine with AI (Gemini) for edge cases and interactions
        3. Validate against safety bounds
        4. Return complete threshold set with metadata

        Args:
            patient_data: Patient information including medical history

        Returns:
            Dictionary with thresholds for all vital signs + metadata
        """
        try:
            logger.info("🔄 Generating HYBRID thresholds (Rule-based + AI)...")

            # Phase 1: Apply rule-based logic
            rule_thresholds = self._generate_rule_based(patient_data)

            # Phase 2: Refine with AI if available
            if self.gemini_client:
                hybrid_result = self._refine_with_ai(rule_thresholds, patient_data)
            else:
                logger.warning("⚠️ AI not available, using rule-based only")
                hybrid_result = rule_thresholds
                hybrid_result['metadata']['generation_method'] = 'rule_based_only'

            # Phase 3: Validate safety bounds
            validated_result = self._validate_safety_bounds(hybrid_result)

            return validated_result

        except Exception as e:
            logger.error(f"❌ Threshold generation failed: {e}")
            # Return baseline thresholds as fallback
            return self._get_baseline_thresholds('baseline_fallback', 0.5)

    def _generate_rule_based(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate thresholds using rule-based approach
        Apply medical guidelines from threshold_generation_rules table
        """
        logger.info("🔧 Generating rule-based thresholds...")

        # Start with baseline
        thresholds = {}
        for vital_sign, baseline in self.BASELINE_THRESHOLDS.items():
            thresholds[vital_sign] = baseline.copy()

        # Get applicable rules from database
        try:
            conn = mysql.connector.connect(**self.db_config)
        except mysql.connector.Error as e:
            logger.error(f"❌ Database connection failed: {e}")
            # Return baseline thresholds if database unavailable
            return self._get_baseline_thresholds('rule_based_fallback', 0.5)

        cursor = conn.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT vital_sign, conditions,
                       min_normal_adjustment, max_normal_adjustment,
                       min_critical_adjustment, max_critical_adjustment,
                       justification, priority
                FROM threshold_generation_rules
                WHERE is_active = TRUE
                ORDER BY priority ASC
            """)

            rules = cursor.fetchall() or []
            applied_rules = []

            # Track highest priority rule per vital_sign per condition_type to avoid double-counting
            # Example: COPD rule (priority 1) + COPD/Asthma rule (priority 2) should NOT stack
            vital_sign_condition_tracker = {}

            # Apply rules based on patient conditions
            for rule in rules:
                if self._rule_matches_patient(rule['conditions'], patient_data):
                    vital_sign = rule['vital_sign']
                    conditions_parsed = json.loads(rule['conditions']) if isinstance(rule['conditions'], str) else rule['conditions']

                    # Identify condition type (chronic_diseases, age_range, smoking_status, etc.)
                    condition_type = list(conditions_parsed.keys())[0] if conditions_parsed else 'unknown'

                    # Create tracking key: vital_sign + condition_type
                    track_key = f"{vital_sign}_{condition_type}"

                    # Only apply if this is the FIRST rule for this vital_sign + condition_type
                    # (rules are sorted by priority ASC, so first match = highest priority)
                    if track_key not in vital_sign_condition_tracker:
                        vital_sign_condition_tracker[track_key] = True

                        if vital_sign in thresholds:
                            # Apply adjustments
                            thresholds[vital_sign]['min_normal'] += rule['min_normal_adjustment']
                            thresholds[vital_sign]['max_normal'] += rule['max_normal_adjustment']
                            thresholds[vital_sign]['min_critical'] += rule['min_critical_adjustment']
                            thresholds[vital_sign]['max_critical'] += rule['max_critical_adjustment']

                            # Recalculate warning thresholds (ensure they're between normal and critical)
                            thresholds[vital_sign]['min_warning'] = max(
                                thresholds[vital_sign]['min_critical'],
                                thresholds[vital_sign]['min_normal'] - 5
                            )
                            thresholds[vital_sign]['max_warning'] = min(
                                thresholds[vital_sign]['max_critical'],
                                thresholds[vital_sign]['max_normal'] + 10
                            )

                            applied_rules.append({
                                'vital_sign': vital_sign,
                                'rule': rule['justification'],
                                'priority': rule['priority']
                            })

                            logger.info(f"  ✓ Applied rule for {vital_sign}: {rule['justification']}")
                    else:
                        logger.debug(f"  ⊗ Skipped overlapping rule for {vital_sign} ({condition_type} already covered by higher priority rule)")

            # Calculate confidence score based on rules applied
            if applied_rules and len(applied_rules) > 0:
                confidence = min(0.7 + (len(applied_rules) * 0.05), 0.95)
            else:
                confidence = 0.7  # Baseline confidence if no rules applied

            result = {
                'thresholds': thresholds,
                'metadata': {
                    'generation_method': 'rule_based',
                    'ai_model': 'rule_based',
                    'ai_confidence': confidence,
                    'generation_timestamp': datetime.utcnow().isoformat(),
                    'applied_rules': applied_rules,
                    'input_factors': self._extract_input_factors(patient_data)
                }
            }

            logger.info(f"✅ Rule-based generation completed (confidence: {confidence:.2f})")
            return result

        finally:
            cursor.close()
            conn.close()


    def _refine_with_ai(
        self,
        rule_thresholds: Dict[str, Any],
        patient_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Refine rule-based thresholds with AI suggestions
        """
        logger.info("🔄 Refining rule-based thresholds with AI...")

        try:
            # Create refinement prompt
            prompt = self._create_refinement_prompt(rule_thresholds, patient_data)

            # Get AI suggestions
            response = self.gemini_client.generate_content(prompt)

            # Parse and apply refinements
            refined_thresholds = self._apply_refinements(
                rule_thresholds['thresholds'],
                response.text
            )

            # Validate refinements are reasonable (max adjustment ±30%)
            refined_thresholds = self._validate_refinement_bounds(
                rule_thresholds['thresholds'],
                refined_thresholds
            )

            result = {
                'thresholds': refined_thresholds,
                'metadata': {
                    'generation_method': 'hybrid',
                    'ai_model': 'rule_based + gemini-2.0-flash',
                    'ai_confidence': 0.95,
                    'generation_timestamp': datetime.utcnow().isoformat(),
                    'applied_rules': rule_thresholds['metadata'].get('applied_rules', []),
                    'ai_refinements': response.text,
                    'input_factors': self._extract_input_factors(patient_data)
                }
            }

            logger.info("✅ Hybrid generation completed")
            return result

        except Exception as e:
            logger.error(f"❌ AI refinement failed: {e}, using rule-based only")
            return rule_thresholds

    def _rule_matches_patient(self, conditions_json: str, patient_data: Dict[str, Any]) -> bool:
        """
        Check if a rule's conditions match patient data

        NOTE: No translation needed anymore!
        - Android app now uses SearchBox + Multi-select
        - Stores English names directly (e.g., "Hypertension" not "tăng huyết áp")
        - Medications, allergies, family history also stored in English
        - Direct matching with database rules without translation
        """
        try:
            conditions = json.loads(conditions_json) if isinstance(conditions_json, str) else conditions_json

            # Check age range
            if 'age_range' in conditions:
                age = patient_data.get('age')
                if age:
                    min_age, max_age = conditions['age_range']
                    if not (min_age <= age <= max_age):
                        return False

            # Check gender
            if 'gender' in conditions:
                if patient_data.get('gender') != conditions['gender']:
                    return False

            # Check chronic diseases
            # NOTE: Android app stores English names directly (e.g., "Hypertension", "Diabetes")
            # No translation needed - direct matching with database rules
            if 'chronic_diseases' in conditions:
                patient_diseases = patient_data.get('chronic_diseases', [])
                if isinstance(patient_diseases, str):
                    try:
                        patient_diseases = json.loads(patient_diseases)
                    except (json.JSONDecodeError, TypeError):
                        patient_diseases = []

                # Handle None case
                if patient_diseases is None:
                    patient_diseases = []

                # Extract disease names (normalize to lowercase for case-insensitive matching)
                disease_names = []
                if isinstance(patient_diseases, list):
                    for disease in patient_diseases:
                        if isinstance(disease, dict):
                            disease_name = disease.get('name', '').strip().lower()
                            if disease_name:
                                disease_names.append(disease_name)
                        elif disease:  # Non-empty string
                            disease_name = str(disease).strip().lower()
                            disease_names.append(disease_name)

                # Check if ALL required diseases match (rule requires complete match)
                # For example: Rule needs "Diabetes + Hypertension" = patient must have BOTH
                required_diseases = conditions.get('chronic_diseases', [])
                required_diseases_lower = [req.strip().lower() for req in required_diseases]
                if required_diseases:
                    # Ensure patient has ALL required diseases
                    if not all(req in disease_names for req in required_diseases_lower):
                        return False  # Patient missing at least one required disease

            # Check medications (CRITICAL: rules requiring specific drugs must validate presence)
            # NOTE: Android app stores English names directly (e.g., "Metoprolol", "Aspirin")
            # No translation needed - direct matching with database rules
            if 'medications' in conditions:
                patient_meds = patient_data.get('medications', [])
                if isinstance(patient_meds, str):
                    try:
                        patient_meds = json.loads(patient_meds)
                    except (json.JSONDecodeError, TypeError):
                        patient_meds = []

                if patient_meds is None:
                    patient_meds = []

                # Extract medication names (normalize to lowercase for case-insensitive matching)
                med_names = []
                if isinstance(patient_meds, list):
                    for med in patient_meds:
                        if isinstance(med, dict):
                            med_name = med.get('name', '').strip().lower()
                            if med_name:
                                med_names.append(med_name)
                        elif med:
                            med_name = str(med).strip().lower()
                            med_names.append(med_name)

                # Check if any required medication matches
                required_meds = conditions.get('medications', [])
                required_meds_lower = [req.strip().lower() for req in required_meds]
                if required_meds and not any(req in med_names for req in required_meds_lower):
                    return False  # Rule requires medication but patient doesn't have it

            # Check BMI range
            if 'bmi_range' in conditions:
                bmi = self._calculate_bmi(patient_data)
                if bmi is None:
                    return False  # Rule requires BMI but patient data doesn't have height/weight
                min_bmi, max_bmi = conditions['bmi_range']
                if not (min_bmi <= bmi <= max_bmi):
                    return False

            # Check lifestyle factors
            if 'smoking_status' in conditions:
                if patient_data.get('smoking_status') != conditions['smoking_status']:
                    return False

            if 'exercise_frequency' in conditions:
                if patient_data.get('exercise_frequency') != conditions['exercise_frequency']:
                    return False

            # Check altitude (MUST be explicitly provided in patient_data)
            if 'altitude_meters' in conditions:
                patient_altitude = patient_data.get('altitude_meters')
                if patient_altitude is None:
                    return False  # Rule requires altitude but patient doesn't have it
                min_alt, max_alt = conditions['altitude_meters']
                if not (min_alt <= patient_altitude <= max_alt):
                    return False

            # Check medical_conditions (e.g., Post-Surgical, ICU Patient)
            if 'medical_conditions' in conditions:
                patient_conditions = patient_data.get('medical_conditions', [])
                if isinstance(patient_conditions, str):
                    try:
                        patient_conditions = json.loads(patient_conditions)
                    except (json.JSONDecodeError, TypeError):
                        patient_conditions = []

                if patient_conditions is None:
                    patient_conditions = []

                # Normalize to lowercase list
                condition_names = []
                if isinstance(patient_conditions, list):
                    for cond in patient_conditions:
                        if isinstance(cond, dict):
                            cond_name = cond.get('name', '').strip().lower()
                            if cond_name:
                                condition_names.append(cond_name)
                        elif cond:
                            condition_names.append(str(cond).strip().lower())

                # Check if any required condition matches
                required_conditions = conditions.get('medical_conditions', [])
                required_conditions_lower = [req.strip().lower() for req in required_conditions]
                if required_conditions and not any(req in condition_names for req in required_conditions_lower):
                    return False

            # Check risk_factors (e.g., Sepsis Risk, ICU Patient)
            if 'risk_factors' in conditions:
                patient_risk_factors = patient_data.get('risk_factors', [])
                if isinstance(patient_risk_factors, str):
                    try:
                        patient_risk_factors = json.loads(patient_risk_factors)
                    except (json.JSONDecodeError, TypeError):
                        patient_risk_factors = []

                if patient_risk_factors is None:
                    patient_risk_factors = []

                # Normalize to lowercase list
                risk_factor_names = []
                if isinstance(patient_risk_factors, list):
                    for risk in patient_risk_factors:
                        if isinstance(risk, dict):
                            risk_name = risk.get('name', '').strip().lower()
                            if risk_name:
                                risk_factor_names.append(risk_name)
                        elif risk:
                            risk_factor_names.append(str(risk).strip().lower())

                # Check if any required risk factor matches
                required_risks = conditions.get('risk_factors', [])
                required_risks_lower = [req.strip().lower() for req in required_risks]
                if required_risks and not any(req in risk_factor_names for req in required_risks_lower):
                    return False

            # Check allergies (CRITICAL for anaphylaxis risk monitoring)
            # NOTE: Android app stores English names directly (e.g., "Penicillin", "Shellfish")
            # No translation needed - direct matching with database rules
            if 'allergies' in conditions:
                patient_allergies = patient_data.get('allergies', [])
                if isinstance(patient_allergies, str):
                    try:
                        patient_allergies = json.loads(patient_allergies)
                    except (json.JSONDecodeError, TypeError):
                        patient_allergies = []

                if patient_allergies is None:
                    patient_allergies = []

                # Extract allergy names (normalize to lowercase for case-insensitive matching)
                allergy_names = []
                if isinstance(patient_allergies, list):
                    for allergy in patient_allergies:
                        if isinstance(allergy, dict):
                            allergy_name = allergy.get('name', '').strip().lower()
                            if allergy_name:
                                allergy_names.append(allergy_name)
                        elif allergy:
                            allergy_name = str(allergy).strip().lower()
                            allergy_names.append(allergy_name)

                # Check if any required allergy matches
                required_allergies = conditions.get('allergies', [])
                required_allergies_lower = [req.strip().lower() for req in required_allergies]
                if required_allergies and not any(req in allergy_names for req in required_allergies_lower):
                    return False  # Rule requires allergy but patient doesn't have it

            return True

        except Exception as e:
            logger.warning(f"⚠️ Error matching rule conditions: {e}")
            return False

    def _create_gemini_prompt(self, patient_data: Dict[str, Any]) -> str:
        """Create prompt for Gemini API to generate thresholds"""
        return f"""You are a medical AI assistant specializing in vital sign monitoring thresholds.

Generate personalized vital sign thresholds for the following patient following evidence-based medical guidelines.

**Patient Profile:**
- Age: {patient_data.get('age', 'Unknown')}
- Gender: {patient_data.get('gender', 'Unknown')}
- Height: {patient_data.get('height', 'Unknown')} cm
- Weight: {patient_data.get('weight', 'Unknown')} kg
- Blood Type: {patient_data.get('blood_type', 'Unknown')}

**Medical History:**
- Chronic Diseases: {json.dumps(patient_data.get('chronic_diseases', []), ensure_ascii=False)}
- Medications: {json.dumps(patient_data.get('medications', []), ensure_ascii=False)}
- Allergies: {json.dumps(patient_data.get('allergies', []), ensure_ascii=False)}
- Family History: {json.dumps(patient_data.get('family_history', []), ensure_ascii=False)}

**Lifestyle:**
- Smoking: {patient_data.get('smoking_status', 'Unknown')}
- Alcohol: {patient_data.get('alcohol_consumption', 'Unknown')}
- Exercise: {patient_data.get('exercise_frequency', 'Unknown')}

**MEDICAL GUIDELINES TO FOLLOW:**

1. **Heart Rate (BPM)** - AHA 2020 + ESC 2022:
   - Normal: 60-100 BPM (adults at rest, measured after 5 min rest)
   - Bradycardia: <60 BPM; Tachycardia: >100 BPM
   - Critical: <40 BPM (severe bradycardia) or >120 BPM (severe tachycardia)

   **CRITICAL ADJUSTMENTS:**
     * Beta-blockers (metoprolol, atenolol, carvedilol) + Digoxin: LOWER max_normal by 15-20 BPM (additive effect)
     * Beta-blockers + CCB (verapamil/diltiazem): HIGH RISK - LOWER by 15-20 BPM, RAISE min_critical to 45 BPM (severe bradycardia risk per ESC 2021)
     * Atrial Fibrillation (rate-controlled): ACCEPT 60-110 BPM as TARGET range (ESC AFib 2020)
     * Heart Failure with reduced EF: TARGET 55-70 BPM as OPTIMAL (ESC 2021 HF guidelines)
     * Elderly (>65y): LOWER max_normal by 5-10 BPM (normal resting HR decreases with age)
     * Athletes: LOWER min_normal to 40-50 BPM (athletic heart syndrome)
     * Hyperthyroidism: RAISE max_normal by 10-20 BPM (increased metabolic rate)
     * Hypothyroidism: LOWER max_normal by 5-10 BPM (decreased metabolic rate)

2. **SpO2 (%)** - ATS/ERS 2019 + BTS 2017 Oxygen Guidelines:
   - Normal: 95-100% (healthy adults, sea level)
   - Mild hypoxemia: 90-94%; Moderate: 85-89%; Severe: <85%
   - Critical: <85% (requires immediate intervention)

   **CRITICAL ADJUSTMENTS:**
     * COPD (all stages): ACCEPT 88-92% as TARGET range (BTS 2017 - avoid hyperoxia-induced hypercapnia)
     * Carbon Monoxide Poisoning: SpO2 may appear NORMAL (pulse oximeter cannot distinguish COHb - use arterial blood gas)
     * High Altitude (>2400m): ACCEPT 90-95% as normal (Wilderness Medical Society - physiological adaptation)
     * Methemoglobinemia: SpO2 plateaus at ~85% regardless of true saturation (use co-oximetry)
     * Pneumonia/ARDS: TARGET >90% SpO2 (ARDSNet protocol - lung protective ventilation)
     * Sepsis: TARGET 94-98% SpO2 (Surviving Sepsis Campaign 2021 - avoid hyperoxia)
     * Pregnancy: TARGET ≥95% SpO2 (fetal oxygenation dependency)
     * Smokers: May show 92-94% baseline (chronic carbon monoxide binding)
     * Severe anemia (Hb <7 g/dL): SpO2 may appear normal but low oxygen delivery (monitor hemoglobin)

3. **Body Temperature (°C)** - WHO/NICE Guidelines 2021:
   - Normal: 36.1-37.2°C (oral/tympanic measurement)
   - Fever: >37.5°C; High fever: >38.5°C; Hyperpyrexia: >40°C
   - Hypothermia: <35°C (moderate), <32°C (severe)
   - Critical: <35°C or >40°C (emergency intervention required)
   - ADJUSTMENTS:
     * Elderly (>65y): LOWER baseline by 0.2-0.5°C (reduced thermoregulation)
     * Immunosuppressed: LOWER fever threshold to 37.8°C (infections may not show high fever)
     * Antipyretics (acetaminophen, NSAIDs): May mask fever (consider medication timing)

4. **Systolic Blood Pressure (mmHg)** - AHA/ACC Guidelines 2017-2025 (Updated Aug 2025):
   - NORMAL: <120 mmHg (healthy adults)
   - ELEVATED: 120-129 mmHg AND Diastolic <80 mmHg (pre-hypertension)
   - STAGE 1 HYPERTENSION: 130-139 mmHg OR Diastolic 80-89 mmHg
   - STAGE 2 HYPERTENSION: ≥140 mmHg OR Diastolic ≥90 mmHg
   - SEVERE HYPERTENSION: >180 mmHg (without symptoms - call healthcare professional immediately)
   - HYPERTENSIVE EMERGENCY: >180 mmHg WITH SYMPTOMS (chest pain, shortness of breath, back pain,
     numbness, weakness, vision changes, difficulty speaking - CALL 911 IMMEDIATELY)

   **CRITICAL ADJUSTMENTS:**
     * Diabetes + Hypertension: TARGET <130/80 mmHg (ADA 2024 - 20-30% CVD risk reduction, microvascular protection)
     * CKD Stages 3-5: TARGET <130/80 mmHg (KDIGO 2021 - slow GFR decline, reduce proteinuria)
     * Elderly (>65y): INDIVIDUALIZE 130-150 mmHg systolic (SPRINT 2015 - balance benefits vs. frailty/falls risk)
     * Hypotension: <90 mmHg systolic (symptomatic)
     * Critical: <70 mmHg (shock risk) or >180 mmHg (stroke/MI risk)
     * ACE inhibitors/ARBs: May allow slightly lower thresholds (renal/cardiac protective effect)
     * Beta-blockers + Calcium channel blockers: MONITOR for bradycardia + hypotension interaction

5. **Diastolic Blood Pressure (mmHg)** - AHA/ACC Guidelines 2017-2025 (Updated Aug 2025):
   - NORMAL: <80 mmHg (healthy adults)
   - ELEVATED: 80-89 mmHg (with Systolic 120-129 = pre-hypertension)
   - STAGE 1 HYPERTENSION: 80-89 mmHg (with Systolic 130-139)
   - STAGE 2 HYPERTENSION: ≥90 mmHg
   - SEVERE HYPERTENSION: >120 mmHg (without symptoms - call healthcare professional)
   - HYPERTENSIVE EMERGENCY: >120 mmHg WITH SYMPTOMS → CALL 911

   **CRITICAL ADJUSTMENTS:**
     * Diabetes: TARGET <80 mmHg (ADA 2024 - microvascular protection)
     * CKD Stages 3-5: TARGET <80 mmHg (KDIGO 2021 - slow progression)
     * Elderly (>65y): ACCEPT 85-90 mmHg (isolated systolic hypertension common with age)
     * Hypotension: <60 mmHg (symptomatic - dizziness, fatigue)
     * Critical: <40 mmHg (shock risk) or >120 mmHg (stroke risk)

**CRITICAL DRUG INTERACTIONS TO CONSIDER:**
- Beta-blockers + Calcium channel blockers (verapamil/diltiazem): Risk of severe bradycardia and hypotension
- ACE inhibitors + ARBs: Increased hypotension risk (dual RAAS blockade)
- NSAIDs + Antihypertensives: NSAIDs may reduce BP medication effectiveness
- Diuretics + Beta-blockers: Increased hypotension and bradycardia risk
- Corticosteroids + Antihypertensives: Steroids may increase BP (counteract BP meds)

**COMORBIDITY PATTERNS:**
- Diabetes + Hypertension: Stricter BP targets (<130/80 mmHg) per ADA 2021
- COPD + Beta-blockers: AVOID non-selective beta-blockers (bronchospasm risk)
- Heart Failure + Beta-blockers: LOWER HR targets acceptable (target 50-60 BPM in stable HF)
- CKD + Hypertension: Monitor for hyperkalemia with ACE/ARBs (KDIGO 2021)
- Atrial Fibrillation: ACCEPT HR 60-110 BPM (rate-controlled AFib targets)

**OUTPUT REQUIREMENTS:**
1. ALL thresholds must include min_normal, max_normal, min_warning, max_warning, min_critical, max_critical
2. Provide SPECIFIC medical justification citing guidelines (e.g., "Per JNC8 2014, diabetes requires tighter BP control")
3. Mention ALL relevant drug adjustments applied
4. Ensure logical ordering: min_critical < min_warning < min_normal < max_normal < max_warning < max_critical
5. Validate against safety bounds: HR (30-200), SpO2 (70-100), Temp (32-42°C), SBP (50-250), DBP (30-150)

Please provide personalized thresholds in STRICT JSON format:
{{
  "heart_rate": {{
    "min_normal": X,
    "max_normal": Y,
    "min_warning": Z,
    "max_warning": W,
    "min_critical": A,
    "max_critical": B
  }},
  "spo2": {{...}},
  "temperature": {{...}},
  "systolic_bp": {{...}},
  "diastolic_bp": {{...}},
  "justification": "Detailed medical reasoning with guideline citations (AHA/JNC8/WHO/ATS/KDIGO), drug interaction considerations, and comorbidity adjustments applied"
}}
"""

    def _create_refinement_prompt(
        self,
        rule_thresholds: Dict[str, Any],
        patient_data: Dict[str, Any]
    ) -> str:
        """Create prompt for AI to refine rule-based thresholds"""
        return f"""You are a medical AI specialist conducting a comprehensive review of vital sign thresholds.

**PATIENT COMPLETE PROFILE:**
{json.dumps(self._extract_input_factors(patient_data), indent=2, ensure_ascii=False)}

**CURRENT RULE-BASED THRESHOLDS:**
{json.dumps(rule_thresholds['thresholds'], indent=2)}

**APPLIED MEDICAL RULES:**
{json.dumps(rule_thresholds['metadata'].get('applied_rules', []), indent=2, ensure_ascii=False)}

**YOUR TASK:**
Review these rule-based thresholds and identify EDGE CASES or COMPLEX INTERACTIONS that automated rules may have missed.
Focus on multi-drug interactions, rare comorbidity patterns, and conflicting therapeutic targets.

**CRITICAL REVIEW CHECKLIST:**

1. **DRUG-DRUG INTERACTIONS:**
   - Beta-blockers + Calcium channel blockers (verapamil/diltiazem):
     * Risk: Severe bradycardia (<50 BPM) and hypotension
     * Action: LOWER max_normal HR by additional 5-10 BPM if both present

   - ACE inhibitors + ARBs (dual RAAS blockade):
     * Risk: Excessive hypotension, hyperkalemia
     * Action: RAISE min_critical SBP by 5-10 mmHg (avoid <85 mmHg)

   - NSAIDs + Antihypertensives:
     * Risk: NSAIDs reduce BP medication effectiveness
     * Action: TIGHTEN max_warning BP by 5 mmHg (earlier intervention)

   - Diuretics + Beta-blockers:
     * Risk: Synergistic bradycardia and orthostatic hypotension
     * Action: ADJUST both HR (lower by 5 BPM) and BP (raise min_critical SBP by 5 mmHg)

   - Corticosteroids + Antihypertensives:
     * Risk: Steroids counteract BP medications (fluid retention)
     * Action: TIGHTEN max_warning BP by 5-10 mmHg (compensate for steroid effect)

   - Theophylline + Beta-agonists (in COPD):
     * Risk: Increased tachycardia
     * Action: RAISE max_warning HR by 10 BPM (expect higher baseline)

2. **COMORBIDITY CONFLICT PATTERNS:**
   - Diabetes + CKD + Hypertension (common triad):
     * Conflict: Tight BP control vs. CKD progression risk
     * Resolution: TARGET SBP 120-130 mmHg (ADA/KDIGO 2021 consensus)
     * Action: ADJUST max_normal SBP to 130 mmHg, max_warning to 140 mmHg

   - COPD + Heart Failure:
     * Conflict: Beta-blockers beneficial for HF but risky in COPD
     * Resolution: Use cardioselective beta-blockers (bisoprolol, metoprolol succinate)
     * Action: If beta-blocker present, ACCEPT HR 50-60 BPM as normal (HF target)

   - Atrial Fibrillation + Hypertension:
     * Conflict: Rate control vs. BP control
     * Resolution: Rate-controlled AFib targets 60-110 BPM (ESC 2020)
     * Action: ADJUST max_normal HR to 110 BPM if AFib documented

   - Hyperthyroidism + Hypertension:
     * Conflict: High HR from thyroid vs. beta-blocker for BP
     * Resolution: Beta-blockers treat both conditions
     * Action: MONITOR but do NOT over-adjust HR (expect gradual normalization)

   - CKD Stage 4-5 + Heart Failure:
     * Conflict: Fluid management complexity
     * Resolution: Stricter BP monitoring, avoid hypotension
     * Action: RAISE min_critical SBP to 90 mmHg (protect kidney perfusion)

3. **AGE + GENDER + ETHNICITY INTERACTIONS:**
   - Elderly (>75y) + Multiple Medications (polypharmacy):
     * Risk: Increased adverse drug reactions, falls
     * Action: WIDEN normal ranges (tolerate SBP 130-150 mmHg to avoid falls)

   - Elderly + CKD:
     * Risk: Renal function decline with tight BP control
     * Action: ACCEPT SBP 140-150 mmHg (avoid over-treatment)

   - Premenopausal women + Hypertension:
     * Consideration: Avoid ACE/ARBs if pregnancy possible (teratogenic)
     * Action: NO threshold adjustment but NOTE in justification

   - African American + Hypertension:
     * Evidence: Better response to diuretics + CCBs than ACE/ARBs (JNC8)
     * Action: NO threshold adjustment (medication choice, not targets)

4. **LIFESTYLE + CHRONIC DISEASE INTERACTIONS:**
   - Current smoker + COPD:
     * SpO2 Adjustment (CRITICAL - BTS 2017 Guidelines):
       - COPD patients target SpO2 88-92% to avoid CO2 retention
       - If rule-based SpO2 min_normal is already 88%, DO NOT raise it
       - Action: ACCEPT or SLIGHTLY LOWER min_normal if rule set it too high (e.g., 90% → 88%)
       - NEVER suggest raising SpO2 threshold for COPD patients
       - Example: If min_normal=88%, suggest min_normal_adj=0 (already correct)
       - Example: If min_normal=92%, suggest min_normal_adj=-4 (lower to 88%)
     * HR Monitoring: TIGHTEN max_warning HR by 5 BPM (increased CVD risk from smoking)

   - Alcohol abuse + Hypertension:
     * Risk: Alcohol-induced hypertension, medication non-compliance
     * Action: TIGHTEN max_warning BP by 5 mmHg (earlier intervention)

   - Sedentary + Obesity + Diabetes:
     * Risk: Metabolic syndrome cluster (high CVD risk)
     * Action: STRICTER BP targets (max_normal SBP 120 mmHg per ADA)

5. **RARE BUT CRITICAL CONDITIONS:**
   - Hypothyroidism + Beta-blockers:
     * Risk: Excessive bradycardia (both lower HR)
     * Action: LOWER max_normal HR by additional 5 BPM, RAISE min_critical to 45 BPM

   - Severe obesity (BMI >40) + Hypertension:
     * Consideration: BP measurement accuracy issues
     * Action: NOTE in justification (use large cuff, consider ambulatory BP monitoring)

   - Pregnancy (if female, childbearing age):
     * CRITICAL: Different thresholds apply (BP >140/90 = gestational HTN)
     * Action: If pregnancy documented, ADJUST SBP max_normal to 140 mmHg

**BASELINE THRESHOLD VALIDATION (Check BEFORE suggesting adjustments):**
Verify rule-based thresholds are within acceptable medical ranges:

1. **Temperature Baselines (WHO/NICE 2021: Normal 36.1-37.2°C):**
   - If min_normal < 36.0°C: RAISE to 36.1°C (likely rule error)
   - If max_normal > 37.5°C: LOWER to 37.2°C (avoid missing fever)
   - Example: min_normal=35.6°C → suggest min_normal_adj=+0.5°C (correct to 36.1°C)

2. **Heart Rate Baselines (ESC 2021: Normal 60-100 BPM):**
   - If min_normal < 40 BPM (without pacemaker): RAISE to 45 BPM
   - If max_normal > 120 BPM (without specific condition): LOWER to 100 BPM

3. **SpO2 Baselines (WHO 2021: Normal ≥95%, BTS 2017 COPD: 88-92%):**
   - Healthy patients: min_normal should be ≥95%
   - COPD patients: min_normal should be 88-92% (NOT higher)
   - If COPD with min_normal=90-94%, consider LOWERING to 88%

4. **Blood Pressure Baselines (AHA/ACC 2017-2025):**
   - SBP: Normal <120 mmHg, Elevated 120-129 mmHg
   - DBP: Normal <80 mmHg
   - Validate critical bounds: min_critical SBP should be 80-90 mmHg

**ADJUSTMENT GUIDELINES:**
- **FIRST**: Check baseline validation above - fix rule errors before complex adjustments
- Adjustments should be SMALL (±5-10 units) and JUSTIFIED by specific interactions
- If rules already handled a condition well, suggest 0 adjustment
- **CRITICAL**: For COPD SpO2, NEVER raise thresholds (accept lower values per BTS 2017)
- Prioritize PATIENT SAFETY over aggressive control (e.g., avoid hypotension in elderly)
- Cite SPECIFIC guidelines when suggesting changes (e.g., "Per ESC 2020 AFib guidelines")
- If no complex interactions found, state "No additional adjustments needed - rule-based thresholds are appropriate"

**OUTPUT FORMAT (STRICT JSON):**
{{
  "heart_rate": {{
    "min_normal_adj": 0,      // Adjustment to min_normal (can be negative)
    "max_normal_adj": -5,     // Example: lower by 5 BPM
    "min_warning_adj": 0,
    "max_warning_adj": -5,
    "min_critical_adj": 0,
    "max_critical_adj": 0
  }},
  "spo2": {{
    "min_normal_adj": 0,
    "max_normal_adj": 0,
    "min_warning_adj": 0,
    "max_warning_adj": 0,
    "min_critical_adj": 0,
    "max_critical_adj": 0
  }},
  "temperature": {{...}},
  "systolic_bp": {{...}},
  "diastolic_bp": {{...}},
  "justification": "DETAILED medical reasoning explaining EACH non-zero adjustment with:
    1. Baseline validation check (if any thresholds corrected due to rule errors)
    2. Specific drug interaction or comorbidity pattern identified
    3. Medical guideline citation (e.g., JNC8, ADA 2021, ESC 2020, BTS 2017)
    4. Rationale for adjustment magnitude
    5. Any warnings or monitoring recommendations

    Example for baseline correction: 'Temperature baseline validation: Rule-based min_normal=35.6°C is below WHO/NICE 2021 standard (36.1°C). Corrected min_normal to 36.1°C (+0.5°C adjustment) to align with international standards.'

    Example for complex interaction: 'Beta-blocker (metoprolol) + calcium channel blocker (diltiazem) detected: Per ACC/AHA guidelines, this combination increases bradycardia risk. Adjusted max_normal HR from 90 to 85 BPM to account for synergistic effect. Monitor for symptomatic bradycardia (<50 BPM).'

    Example for COPD SpO2: 'COPD patient with rule-based SpO2 min_normal=88%: Per BTS 2017 guidelines, target SpO2 88-92% to avoid CO2 retention. Current threshold already appropriate - no adjustment needed (min_normal_adj=0).'

    If no adjustments: 'Baseline validation passed - all thresholds within acceptable ranges per WHO/AHA/ESC standards. No complex drug interactions requiring additional adjustments. Rule-based thresholds appropriately address patient conditions per AHA/JNC8/WHO guidelines.'"
}}

**IMPORTANT - DIRECTIONAL LOGIC:**
- **WIDEN ranges** = Accept more values as normal (LOWER min_normal OR RAISE max_normal)
  * Example: COPD SpO2 88% is acceptable → LOWER min_normal to 88% (WIDEN acceptance)
- **TIGHTEN ranges** = Trigger alerts earlier (RAISE min_normal OR LOWER max_normal)
  * Example: High CVD risk → LOWER max_normal BP to catch hypertension earlier
- Do NOT confuse "avoid false alarms" with "tighten thresholds" - they are OPPOSITE actions
  * Avoid false alarms for COPD = ACCEPT lower SpO2 (WIDEN range, don't tighten)
- Do NOT suggest large adjustments (>±15 units) without strong evidence
- Do NOT contradict established guidelines without citing newer evidence
- If uncertain, err on the side of SAFETY (wider ranges for elderly, tighter for high-risk patients)
- ALL non-zero adjustments MUST be explained in justification with guideline citations
"""

    def _parse_gemini_response(self, response_text: str) -> Dict[str, Dict[str, float]]:
        """Parse Gemini API response to extract thresholds"""
        try:
            # Extract JSON from response (handle markdown code blocks)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")

            json_text = response_text[json_start:json_end]
            parsed = json.loads(json_text)

            # Extract thresholds (remove justification key)
            thresholds = {k: v for k, v in parsed.items() if k != 'justification'}

            return thresholds

        except Exception as e:
            logger.error(f"❌ Failed to parse Gemini response: {e}")
            # Return baseline
            return self.BASELINE_THRESHOLDS

    def _apply_refinements(
        self,
        base_thresholds: Dict[str, Dict[str, float]],
        refinement_text: str
    ) -> Dict[str, Dict[str, float]]:
        """Apply AI refinement suggestions to base thresholds"""
        try:
            # Try to find JSON code block first (```json ... ```)
            json_block_start = refinement_text.find('```json')
            json_block_end = refinement_text.find('```', json_block_start + 7)

            if json_block_start != -1 and json_block_end != -1:
                json_text = refinement_text[json_block_start + 7:json_block_end].strip()
            else:
                # Fallback to finding first complete JSON object
                json_start = refinement_text.find('{')
                if json_start == -1:
                    raise ValueError("No JSON found in refinement text")

                # Find matching closing brace
                brace_count = 0
                json_end = json_start
                for i in range(json_start, len(refinement_text)):
                    if refinement_text[i] == '{':
                        brace_count += 1
                    elif refinement_text[i] == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = i + 1
                            break

                if brace_count != 0:
                    raise ValueError("Unmatched braces in JSON")

                json_text = refinement_text[json_start:json_end]

            refinements = json.loads(json_text)

            refined = {}
            for vital_sign, base_vals in base_thresholds.items():
                refined[vital_sign] = base_vals.copy()

                if vital_sign in refinements:
                    adjustments = refinements[vital_sign]
                    for key, adj in adjustments.items():
                        if key.endswith('_adj'):
                            threshold_key = key[:-4]  # Remove '_adj'
                            if threshold_key in refined[vital_sign]:
                                refined[vital_sign][threshold_key] += adj

            return refined

        except Exception as e:
            logger.warning(f"⚠️ Failed to apply refinements: {e}, using base thresholds")
            return base_thresholds

    def _validate_refinement_bounds(
        self,
        base_thresholds: Dict[str, Dict[str, float]],
        refined_thresholds: Dict[str, Dict[str, float]]
    ) -> Dict[str, Dict[str, float]]:
        """
        Validate that AI refinements are reasonable (within ±30% of base)
        This prevents AI from making extreme adjustments
        """
        validated = {}
        corrections = []

        for vital_sign in base_thresholds:
            if vital_sign not in refined_thresholds:
                validated[vital_sign] = base_thresholds[vital_sign].copy()
                continue

            validated[vital_sign] = {}
            base = base_thresholds[vital_sign]
            refined = refined_thresholds[vital_sign]

            for key in base:
                base_val = base[key]
                refined_val = refined.get(key, base_val)

                # Calculate allowed range (±30%)
                max_adjustment = abs(base_val * 0.3)
                min_allowed = base_val - max_adjustment
                max_allowed = base_val + max_adjustment

                # Clip to allowed range
                if refined_val < min_allowed:
                    corrections.append(f"{vital_sign}.{key}: {refined_val:.1f} → {min_allowed:.1f} (too low)")
                    validated[vital_sign][key] = min_allowed
                elif refined_val > max_allowed:
                    corrections.append(f"{vital_sign}.{key}: {refined_val:.1f} → {max_allowed:.1f} (too high)")
                    validated[vital_sign][key] = max_allowed
                else:
                    validated[vital_sign][key] = refined_val

        if corrections:
            logger.warning(f"⚠️ AI refinements clipped to ±30%: {corrections}")

        return validated

    def _validate_safety_bounds(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate and enforce safety bounds on generated thresholds
        This prevents dangerous threshold values that could miss critical conditions
        """
        logger.info("🔒 Validating safety bounds...")

        thresholds = result['thresholds']
        violations = []

        for vital_sign, bounds in self.SAFETY_BOUNDS.items():
            if vital_sign not in thresholds:
                continue

            vital_thresholds = thresholds[vital_sign]

            # Check and enforce absolute minimum
            for key in ['min_normal', 'min_warning', 'min_critical']:
                if key in vital_thresholds:
                    if vital_thresholds[key] < bounds['absolute_min']:
                        violations.append(f"{vital_sign}.{key}: {vital_thresholds[key]} < {bounds['absolute_min']}")
                        vital_thresholds[key] = bounds['absolute_min']

            # Check and enforce absolute maximum
            for key in ['max_normal', 'max_warning', 'max_critical']:
                if key in vital_thresholds:
                    if vital_thresholds[key] > bounds['absolute_max']:
                        violations.append(f"{vital_sign}.{key}: {vital_thresholds[key]} > {bounds['absolute_max']}")
                        vital_thresholds[key] = bounds['absolute_max']

        if violations:
            logger.warning(f"⚠️ Safety bound violations corrected: {violations}")
            result['metadata']['safety_corrections'] = violations
        else:
            logger.info("✅ All thresholds within safety bounds")

        return result

    def _extract_input_factors(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key factors used for threshold generation"""
        chronic_diseases = patient_data.get('chronic_diseases') or []
        medications = patient_data.get('medications') or []

        # Normalize chronic_diseases to list of strings
        disease_names = []
        if isinstance(chronic_diseases, list):
            for d in chronic_diseases:
                if isinstance(d, dict):
                    disease_names.append(d.get('name', ''))
                else:
                    disease_names.append(str(d))
        elif isinstance(chronic_diseases, str):
            try:
                parsed = json.loads(chronic_diseases)
                if isinstance(parsed, list):
                    disease_names = [d if isinstance(d, str) else d.get('name', '') for d in parsed]
            except:
                disease_names = []

        # Normalize medications to list of strings
        med_names = []
        if isinstance(medications, list):
            for m in medications:
                if isinstance(m, dict):
                    med_names.append(m.get('name', ''))
                else:
                    med_names.append(str(m))
        elif isinstance(medications, str):
            try:
                parsed = json.loads(medications)
                if isinstance(parsed, list):
                    med_names = [m if isinstance(m, str) else m.get('name', '') for m in parsed]
            except:
                med_names = []

        return {
            'age': patient_data.get('age'),
            'gender': patient_data.get('gender'),
            'bmi': self._calculate_bmi(patient_data),
            'chronic_diseases': disease_names,  # Add actual list
            'medications': med_names,  # Add actual list (CRITICAL for rule matching)
            'chronic_disease_count': len(disease_names),
            'medication_count': len(med_names),
            'smoking_status': patient_data.get('smoking_status'),
            'exercise_frequency': patient_data.get('exercise_frequency')
        }

    def _calculate_bmi(self, patient_data: Dict[str, Any]) -> Optional[float]:
        """Calculate BMI if height and weight available"""
        try:
            height = patient_data.get('height')
            weight = patient_data.get('weight')

            # Validate inputs
            if not height or not weight:
                return None

            # Convert to float and validate range
            height = float(height)
            weight = float(weight)

            if height <= 0 or height > 300:  # Unrealistic height (cm)
                logger.warning(f"⚠️ Invalid height: {height} cm")
                return None

            if weight <= 0 or weight > 500:  # Unrealistic weight (kg)
                logger.warning(f"⚠️ Invalid weight: {weight} kg")
                return None

            height_m = height / 100.0  # Convert cm to m
            bmi = weight / (height_m ** 2)

            # Validate BMI range
            if bmi < 10 or bmi > 100:  # Unrealistic BMI
                logger.warning(f"⚠️ Calculated BMI out of range: {bmi:.1f}")
                return None

            return round(bmi, 1)

        except (TypeError, ValueError, ZeroDivisionError) as e:
            logger.warning(f"⚠️ BMI calculation failed: {e}")
            return None

    def _get_baseline_thresholds(
        self,
        method: str,
        confidence: float
    ) -> Dict[str, Any]:
        """Get baseline thresholds as fallback"""
        return {
            'thresholds': self.BASELINE_THRESHOLDS,
            'metadata': {
                'generation_method': method,
                'ai_model': 'baseline',
                'ai_confidence': confidence,
                'generation_timestamp': datetime.utcnow().isoformat(),
                'input_factors': {},
                'justification': 'Using baseline thresholds (fallback)'
            }
        }


# CLI for testing
if __name__ == '__main__':
    import sys

    # Test configuration
    db_config = {
        'host': 'database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com',
        'user': os.getenv('DB_USER', 'admin'),
        'password': os.getenv('MYSQL_PASSWORD'),
        'database': 'iot_health_cloud',
        'port': 3306
    }

    # Sample patient data
    test_patient = {
        'age': 65,
        'gender': 'M',
        'height': 170,
        'weight': 75,
        'blood_type': 'A+',
        'chronic_diseases': [
            {'name': 'Hypertension', 'diagnosed_date': '2020-01-01', 'severity': 'moderate'}
        ],
        'medications': [
            {'name': 'Aspirin', 'dosage': '100mg', 'frequency': 'daily'}
        ],
        'allergies': [],
        'family_history': [
            {'condition': 'Heart Disease', 'relation': 'father'}
        ],
        'smoking_status': 'former',
        'alcohol_consumption': 'light',
        'exercise_frequency': 'weekly'
    }

    # Initialize generator
    generator = ThresholdGenerator(db_config)

    # Generate thresholds (always uses hybrid method)
    print("\n" + "="*60)
    print("AI Threshold Generator - Hybrid Method")
    print("="*60)

    result = generator.generate_thresholds(test_patient)

    print("\n📊 Generated Thresholds:")
    for vital_sign, thresholds in result['thresholds'].items():
        print(f"\n{vital_sign.upper()}:")
        print(f"  Normal:   {thresholds['min_normal']:.1f} - {thresholds['max_normal']:.1f}")
        print(f"  Warning:  {thresholds['min_warning']:.1f} - {thresholds['max_warning']:.1f}")
        print(f"  Critical: {thresholds['min_critical']:.1f} - {thresholds['max_critical']:.1f}")

    print(f"\n📋 Metadata:")
    print(f"  Method: {result['metadata']['generation_method']}")
    print(f"  Model: {result['metadata']['ai_model']}")
    print(f"  Confidence: {result['metadata']['ai_confidence']:.2f}")
    print(f"  Rules Applied: {len(result['metadata'].get('applied_rules', []))}")
