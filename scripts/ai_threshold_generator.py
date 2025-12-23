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
    AI-powered threshold generator with rule-based fallback
    
    Methods:
        - Rule-based: Apply medical guidelines from threshold_generation_rules table
        - AI-powered: Use Google Gemini API for personalized adjustments
        - Hybrid: Combine both approaches for optimal results
    """
    
    # Baseline thresholds (used as starting point)
    BASELINE_THRESHOLDS = {
        'heart_rate': {
            'min_normal': 60.0,
            'max_normal': 100.0,
            'min_warning': 55.0,
            'max_warning': 110.0,
            'min_critical': 40.0,
            'max_critical': 120.0
        },
        'spo2': {
            'min_normal': 95.0,
            'max_normal': 100.0,
            'min_warning': 92.0,
            'max_warning': 100.0,
            'min_critical': 85.0,
            'max_critical': 100.0
        },
        'temperature': {
            'min_normal': 36.1,
            'max_normal': 37.2,
            'min_warning': 35.5,
            'max_warning': 37.8,
            'min_critical': 35.0,
            'max_critical': 40.0
        },
        'systolic_bp': {
            'min_normal': 90.0,
            'max_normal': 120.0,
            'min_warning': 85.0,
            'max_warning': 135.0,
            'min_critical': 70.0,
            'max_critical': 180.0
        },
        'diastolic_bp': {
            'min_normal': 60.0,
            'max_normal': 80.0,
            'min_warning': 55.0,
            'max_warning': 90.0,
            'min_critical': 40.0,
            'max_critical': 110.0
        }
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
        patient_data: Dict[str, Any],
        method: str = 'hybrid'
    ) -> Dict[str, Any]:
        """
        Generate personalized thresholds for a patient
        
        Args:
            patient_data: Patient information including medical history
            method: 'rule_based', 'ai_generated', or 'hybrid'
        
        Returns:
            Dictionary with thresholds for all vital signs + metadata
        """
        try:
            if method == 'rule_based':
                return self._generate_rule_based(patient_data)
            elif method == 'ai_generated' and self.gemini_client:
                return self._generate_ai_powered(patient_data)
            elif method == 'hybrid':
                # Start with rule-based, then refine with AI
                rule_thresholds = self._generate_rule_based(patient_data)
                if self.gemini_client:
                    return self._refine_with_ai(rule_thresholds, patient_data)
                return rule_thresholds
            else:
                # Fallback to rule-based
                logger.warning(f"Unknown method '{method}' or AI not available, using rule-based")
                return self._generate_rule_based(patient_data)
                
        except Exception as e:
            logger.error(f"❌ Threshold generation failed: {e}")
            # Return baseline thresholds as fallback
            return self._get_baseline_thresholds('manual', 0.0)
    
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
        conn = mysql.connector.connect(**self.db_config)
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
            
            # Apply rules based on patient conditions
            for rule in rules:
                if self._rule_matches_patient(rule['conditions'], patient_data):
                    vital_sign = rule['vital_sign']
                    
                    if vital_sign in thresholds:
                        # Apply adjustments
                        thresholds[vital_sign]['min_normal'] += rule['min_normal_adjustment']
                        thresholds[vital_sign]['max_normal'] += rule['max_normal_adjustment']
                        thresholds[vital_sign]['min_critical'] += rule['min_critical_adjustment']
                        thresholds[vital_sign]['max_critical'] += rule['max_critical_adjustment']
                        
                        # Recalculate warning thresholds
                        thresholds[vital_sign]['min_warning'] = thresholds[vital_sign]['min_normal'] - 5
                        thresholds[vital_sign]['max_warning'] = thresholds[vital_sign]['max_normal'] + 10
                        
                        applied_rules.append({
                            'vital_sign': vital_sign,
                            'rule': rule['justification'],
                            'priority': rule['priority']
                        })
                        
                        logger.info(f"  ✓ Applied rule for {vital_sign}: {rule['justification']}")
            
            # Calculate confidence score based on rules applied
            try:
                confidence = min(0.7 + (len(applied_rules) * 0.05), 0.95)
            except (TypeError, AttributeError):
                confidence = 0.7
            
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
    
    def _generate_ai_powered(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate thresholds using Google Gemini API
        """
        logger.info("🤖 Generating AI-powered thresholds with Gemini...")
        
        try:
            # Prepare prompt for Gemini
            prompt = self._create_gemini_prompt(patient_data)
            
            # Call Gemini API
            response = self.gemini_client.generate_content(prompt)
            
            # Parse response
            thresholds = self._parse_gemini_response(response.text)
            
            result = {
                'thresholds': thresholds,
                'metadata': {
                    'generation_method': 'ai_generated',
                    'ai_model': 'gemini-1.5-pro',
                    'ai_confidence': 0.9,
                    'generation_timestamp': datetime.utcnow().isoformat(),
                    'input_factors': self._extract_input_factors(patient_data),
                    'justification': response.text
                }
            }
            
            logger.info("✅ AI-powered generation completed")
            return result
            
        except Exception as e:
            logger.error(f"❌ Gemini API error: {e}, falling back to rule-based")
            return self._generate_rule_based(patient_data)
    
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
                
                # Extract disease names
                disease_names = []
                if isinstance(patient_diseases, list):
                    for disease in patient_diseases:
                        if isinstance(disease, dict):
                            disease_names.append(disease.get('name', ''))
                        else:
                            disease_names.append(str(disease))
                
                # Check if any required disease matches
                required_diseases = conditions.get('chronic_diseases', [])
                if required_diseases and not any(req in disease_names for req in required_diseases):
                    return False
            
            # Check lifestyle factors
            if 'smoking_status' in conditions:
                if patient_data.get('smoking_status') != conditions['smoking_status']:
                    return False
            
            if 'exercise_frequency' in conditions:
                if patient_data.get('exercise_frequency') != conditions['exercise_frequency']:
                    return False
            
            return True
            
        except Exception as e:
            logger.warning(f"⚠️ Error matching rule conditions: {e}")
            return False
    
    def _create_gemini_prompt(self, patient_data: Dict[str, Any]) -> str:
        """Create prompt for Gemini API to generate thresholds"""
        return f"""You are a medical AI assistant specializing in vital sign monitoring thresholds.

Generate personalized vital sign thresholds for the following patient:

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

Please provide personalized thresholds for:
1. Heart Rate (BPM)
2. SpO2 (%)
3. Body Temperature (°C)
4. Systolic Blood Pressure (mmHg)
5. Diastolic Blood Pressure (mmHg)

For each vital sign, specify:
- min_normal, max_normal (normal range)
- min_warning, max_warning (warning range)
- min_critical, max_critical (critical range)
- Brief medical justification

Format your response as JSON:
{{
  "heart_rate": {{"min_normal": X, "max_normal": Y, ...}},
  "spo2": {{...}},
  ...
  "justification": "Medical reasoning here"
}}
"""
    
    def _create_refinement_prompt(
        self,
        rule_thresholds: Dict[str, Any],
        patient_data: Dict[str, Any]
    ) -> str:
        """Create prompt for AI to refine rule-based thresholds"""
        return f"""You are a medical AI assistant reviewing vital sign thresholds.

**Patient Profile:**
{json.dumps(self._extract_input_factors(patient_data), indent=2, ensure_ascii=False)}

**Current Rule-Based Thresholds:**
{json.dumps(rule_thresholds['thresholds'], indent=2)}

**Applied Rules:**
{json.dumps(rule_thresholds['metadata'].get('applied_rules', []), indent=2, ensure_ascii=False)}

Review these thresholds and suggest any necessary adjustments based on the patient's complete medical profile. 
Focus on edge cases or interactions between conditions that rules might miss.

Respond in JSON format with suggested adjustments (use 0 if no change needed):
{{
  "heart_rate": {{"min_normal_adj": 0, "max_normal_adj": -5, ...}},
  "justification": "Reasoning for adjustments"
}}
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
            # Parse refinement JSON
            json_start = refinement_text.find('{')
            json_end = refinement_text.rfind('}') + 1
            refinements = json.loads(refinement_text[json_start:json_end])
            
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
    
    def _extract_input_factors(self, patient_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key factors used for threshold generation"""
        chronic_diseases = patient_data.get('chronic_diseases') or []
        medications = patient_data.get('medications') or []
        
        return {
            'age': patient_data.get('age'),
            'gender': patient_data.get('gender'),
            'bmi': self._calculate_bmi(patient_data),
            'chronic_disease_count': len(chronic_diseases) if isinstance(chronic_diseases, list) else 0,
            'medication_count': len(medications) if isinstance(medications, list) else 0,
            'smoking_status': patient_data.get('smoking_status'),
            'exercise_frequency': patient_data.get('exercise_frequency')
        }
    
    def _calculate_bmi(self, patient_data: Dict[str, Any]) -> Optional[float]:
        """Calculate BMI if height and weight available"""
        try:
            height = patient_data.get('height')
            weight = patient_data.get('weight')
            
            if height and weight:
                height_m = height / 100.0  # Convert cm to m
                bmi = weight / (height_m ** 2)
                return round(bmi, 1)
            
            return None
        except:
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
    
    # Generate thresholds
    print("\n" + "="*60)
    print("AI Threshold Generator - Test")
    print("="*60)
    
    result = generator.generate_thresholds(test_patient, method='rule_based')
    
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
