#!/usr/bin/env python3
"""
Test Case: Adolescent Patient (17y) with HTN + Heart Disease but NO Beta-blocker
Validates medication condition matching
"""

import sys
import json
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.ai_threshold_generator import ThresholdGenerator


def main():
    """Test adolescent patient case - Phúc Linh"""
    print("\n" + "="*80)
    print("TEST CASE: Adolescent (17y) + HTN + Heart Disease + NO Beta-blocker")
    print("="*80)
    
    patient_data = {
        'patient_id': 'patient_d4fa9f9c',
        'device_id': 'D001',
        'age': 17,
        'gender': 'M',
        'height': 176,
        'weight': 77,
        'blood_type': 'A+',
        'chronic_diseases': ['Huyết áp cao', 'Tim mạch'],  # HTN + Heart disease
        'medications': ['Hạ sốt'],  # Fever reducer - NOT beta-blocker
        'allergies': ['hải sản'],
        'family_history': ['không có'],
        'smoking_status': 'never',
        'alcohol_consumption': 'none',
        'exercise_frequency': 'rarely'
    }
    
    # Initialize generator
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
        # Generate thresholds
        print("\n📊 Generating thresholds...")
        result = generator.generate_thresholds(patient_data)
        
        # Display results
        print("\n✅ GENERATION SUCCESSFUL")
        print("\n🔹 Final Thresholds:")
        print(json.dumps(result['thresholds'], indent=2, ensure_ascii=False))
        
        print("\n🔹 Applied Rules:")
        if result.get('metadata', {}).get('applied_rules'):
            for rule in result['metadata']['applied_rules']:
                print(f"  - {rule['vital_sign']}: {rule['rule']} (priority: {rule['priority']})")
        
        print("\n🔹 Input Factors:")
        if result.get('metadata', {}).get('input_factors'):
            print(json.dumps(result['metadata']['input_factors'], indent=2, ensure_ascii=False))
        
        # Validate key expectations
        print("\n" + "="*80)
        print("VALIDATION CHECKS:")
        print("="*80)
        
        hr = result['thresholds']['heart_rate']
        applied_rules = result.get('metadata', {}).get('applied_rules', [])
        
        print(f"\n✓ Heart Rate: {hr['min_normal']}-{hr['max_normal']} BPM")
        
        # Check if beta-blocker rule was applied
        beta_blocker_applied = any('Beta-blocker' in r['rule'] for r in applied_rules)
        print(f"\n✓ Beta-blocker rule applied: {beta_blocker_applied}")
        
        if beta_blocker_applied:
            print("  ❌ FAIL: Beta-blocker rule should NOT apply - patient takes Hạ sốt (fever reducer), not beta-blocker")
        else:
            print("  ✅ PASS: Beta-blocker rule correctly NOT applied")
        
        # Check if adolescent rule was applied
        adolescent_applied = any('Children have higher' in r['rule'] for r in applied_rules)
        print(f"\n✓ Adolescent rule applied: {adolescent_applied}")
        
        if adolescent_applied:
            print("  ✅ PASS: Adolescent rule correctly applied")
            if hr['max_normal'] == 120.0:
                print("  ✅ PASS: max_normal = 120 BPM (adolescent standard)")
            else:
                print(f"  ⚠️  CHECK: max_normal = {hr['max_normal']} BPM (expected 120)")
        else:
            print("  ⚠️  CHECK: Adolescent rule not applied")
        
        print("\n" + "="*80)
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
