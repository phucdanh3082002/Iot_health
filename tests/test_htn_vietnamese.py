#!/usr/bin/env python3
"""
Test Case: Adolescent with Hypertension (Vietnamese naming)
Validates disease name translation in rule matching
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ai_threshold_generator import ThresholdGenerator


def main():
    print("\n" + "="*80)
    print("TEST CASE: Adolescent (17y) + Tăng huyết áp (Vietnamese HTN)")
    print("="*80)
    
    patient_data = {
        'patient_id': 'patient_76b4a1cc',
        'device_id': 'D001',
        'age': 17,
        'gender': 'M',
        'height': 177,
        'weight': 67,
        'blood_type': 'A+',
        'chronic_diseases': ['Tăng huyết áp'],  # Vietnamese for Hypertension
        'medications': ['Hạ sốt'],  # Fever reducer
        'allergies': [],
        'family_history': [],
        'smoking_status': 'never',
        'alcohol_consumption': 'none',
        'exercise_frequency': 'rarely'
    }
    
    generator = ThresholdGenerator(
        db_config={
            'host': 'database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com',
            'port': 3306,
            'user': 'pi_sync',
            'password': 'Danhsidoi123',
            'database': 'iot_health_cloud'
        },
        gemini_api_key='AIzaSyBbSHJX6xo8CaCQDkSLDdLd2sClGNOaUao'
    )
    
    try:
        print("\n📊 Generating thresholds...")
        result = generator.generate_thresholds(patient_data)
        
        print("\n✅ GENERATION SUCCESSFUL")
        print("\n🔹 Final Thresholds (Systolic BP):")
        sbp = result['thresholds']['systolic_bp']
        print(f"  min_normal: {sbp['min_normal']}, max_normal: {sbp['max_normal']}")
        
        print("\n🔹 Applied Rules:")
        for rule in result.get('metadata', {}).get('applied_rules', []):
            print(f"  - {rule['vital_sign']}: {rule['rule']} (priority: {rule['priority']})")
        
        # Validation
        print("\n" + "="*80)
        print("VALIDATION CHECKS:")
        print("="*80)
        
        htn_rule_applied = any('Hypertension' in r['rule'] for r in result.get('metadata', {}).get('applied_rules', []))
        print(f"\n✓ Hypertension rule applied: {htn_rule_applied}")
        
        if htn_rule_applied:
            print("  ✅ PASS: HTN rule correctly matched 'Tăng huyết áp' (Vietnamese)")
            if sbp['max_normal'] == 110.0:
                print(f"  ✅ PASS: max_normal reduced to 110 mmHg (stricter control)")
            else:
                print(f"  ⚠️  CHECK: max_normal = {sbp['max_normal']} (expected 110 after HTN rule)")
        else:
            print("  ❌ FAIL: HTN rule should be applied for 'Tăng huyết áp' patient")
        
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
