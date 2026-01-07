#!/usr/bin/env python3
"""
Health Analysis Service - AI-powered health trend analysis
Uses Google Gemini 2.0 Flash for comprehensive health assessment

Research-based implementation:
- AHA Blood Pressure Guidelines (2017/2023)
- WHO Health Scoring Methodology
- Evidence-based vital signs assessment

Health Score Formula (0-100):
- Vital Sign Compliance (40%): How well vitals stay within personalized thresholds
- Trend Stability (30%): Consistency and predictability of vital signs
- Risk Factors (20%): Impact of chronic diseases, medications, age
- Alert Frequency (10%): Number and severity of alerts

Author: IoT Health Monitoring System
Version: 1.0.0
"""

import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import mysql.connector
import google.generativeai as genai
from statistics import mean, stdev
import math
import os

logger = logging.getLogger(__name__)

# ==================== Medical Guidelines Constants ====================
# Based on AHA 2017/2023 Blood Pressure Guidelines

BLOOD_PRESSURE_CATEGORIES = {
    'normal': {'sys_max': 120, 'dia_max': 80},
    'elevated': {'sys_min': 120, 'sys_max': 129, 'dia_max': 80},
    'stage1_hypertension': {'sys_min': 130, 'sys_max': 139, 'dia_min': 80, 'dia_max': 89},
    'stage2_hypertension': {'sys_min': 140, 'dia_min': 90},
    'hypertensive_crisis': {'sys_min': 180, 'dia_min': 120}
}

# Heart Rate Normal Ranges by Age (resting)
HEART_RATE_RANGES = {
    'adult': {'min': 60, 'max': 100},
    'elderly': {'min': 60, 'max': 100},  # >65 years
    'bradycardia': {'max': 60},
    'tachycardia': {'min': 100}
}

# SpO2 Guidelines
SPO2_RANGES = {
    'normal': {'min': 95, 'max': 100},
    'mild_hypoxemia': {'min': 91, 'max': 94},
    'moderate_hypoxemia': {'min': 86, 'max': 90},
    'severe_hypoxemia': {'max': 85},
    'copd_acceptable': {'min': 88, 'max': 92}  # For COPD patients
}

# Temperature Ranges (Celsius)
TEMPERATURE_RANGES = {
    'normal': {'min': 36.1, 'max': 37.2},
    'low_grade_fever': {'min': 37.3, 'max': 38.0},
    'fever': {'min': 38.1, 'max': 39.0},
    'high_fever': {'min': 39.1},
    'hypothermia': {'max': 35.0}
}


class HealthAnalysisService:
    """
    AI-powered health analysis service

    Health Score Formula (0-100):
    - Vital Sign Compliance (40%): How well vitals stay within personalized thresholds
    - Trend Stability (30%): Consistency and predictability of vital signs
    - Risk Factors (20%): Impact of chronic diseases, medications, age
    - Alert Frequency (10%): Number and severity of alerts
    """

    # Weight factors for health score calculation
    SCORE_WEIGHTS = {
        'vital_compliance': 0.40,    # 40% - Most important
        'trend_stability': 0.30,     # 30% - Second most important
        'risk_factors': 0.20,        # 20% - Chronic diseases, meds
        'alert_frequency': 0.10      # 10% - Alert severity
    }

    # Risk factor scores (based on medical evidence)
    DISEASE_RISK_SCORES = {
        # Cardiovascular
        'Heart Disease': 15, 'CAD': 15, 'Coronary Artery Disease': 15,
        'Heart Failure': 18, 'CHF': 18, 'Congestive Heart Failure': 18,
        'Hypertension': 10, 'High Blood Pressure': 10,
        'Atrial Fibrillation': 12, 'AFib': 12,
        'Arrhythmia': 10,

        # Respiratory
        'COPD': 13, 'Severe COPD': 16, 'Emphysema': 14,
        'Asthma': 5, 'Severe Asthma': 8,
        'Pulmonary Fibrosis': 15,
        'Sleep Apnea': 8, 'OSA': 8,

        # Metabolic
        'Diabetes': 12, 'Type 1 Diabetes': 14, 'Type 2 Diabetes': 12,
        'Hyperthyroidism': 6, 'Hypothyroidism': 5,
        'Obesity': 7,

        # Renal
        'CKD': 14, 'Chronic Kidney Disease': 14,
        'Renal Disease': 12,

        # Neurological
        'Stroke': 16, 'Parkinson Disease': 10,

        # Blood Disorders
        'Anemia': 8, 'Thalassemia': 10,

        # Hepatic
        'Cirrhosis': 12, 'Liver Disease': 10,

        # Infectious
        'HIV': 8, 'Hepatitis B': 6, 'Hepatitis C': 6
    }

    def __init__(self, db_config: Dict, gemini_api_key: str):
        """Initialize service with database and Gemini API"""
        self.db_config = db_config
        genai.configure(api_key=gemini_api_key)
        self.model = genai.GenerativeModel('gemini-2.0-flash')
        logger.info("✅ HealthAnalysisService initialized")

    def analyze_patient_health(
        self,
        patient_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        Main analysis method - Comprehensive health assessment

        Returns:
        {
            'health_score': 85.5,
            'overall_status': 'good',
            'trends': {...},
            'insights': [...],
            'recommendations': [...],
            'anomalies': [...],
            'ai_confidence': 0.92,
            'data_summary': {...},
            'score_breakdown': {...}
        }
        """
        try:
            logger.info(f"🔍 Starting health analysis for patient: {patient_id}")

            # Step 1: Collect comprehensive patient data
            data = self._collect_patient_data(patient_id, days)

            if data['total_records'] < 10:
                logger.warning(f"⚠️ Insufficient data: {data['total_records']} records")
                return self._create_insufficient_data_response(data)

            # Step 2: Calculate health score (before AI analysis)
            health_score_components = self._calculate_health_score_components(data)
            health_score = self._aggregate_health_score(health_score_components)

            # Step 3: Generate optimized Gemini prompt
            prompt = self._generate_analysis_prompt(data, health_score_components)

            # Step 4: Call Gemini API
            logger.info("🤖 Calling Gemini API for analysis...")
            response = self.model.generate_content(prompt)

            # Step 5: Parse and validate response
            ai_result = self._parse_gemini_response(response.text)

            # Step 6: Merge with calculated metrics
            final_result = {
                'patient_id': patient_id,  # Add patient_id to response
                'health_score': health_score,
                'overall_status': self._determine_status(health_score, data),
                'trends': ai_result.get('trends', {}),
                'insights': ai_result.get('insights', []),
                'recommendations': ai_result.get('recommendations', []),
                'anomalies': ai_result.get('anomalies', []),
                'ai_confidence': self._calculate_confidence(data, ai_result),
                'data_summary': data['summary'],
                'score_breakdown': health_score_components,
                'overall_assessment': ai_result.get('overall_assessment', '')
            }

            # Step 7: Save to database
            self._save_analysis(patient_id, data, final_result, response.text)

            logger.info(f"✅ Analysis completed: score={health_score:.1f}, status={final_result['overall_status']}")
            return final_result

        except Exception as e:
            logger.error(f"❌ Analysis failed: {e}", exc_info=True)
            raise

    def get_latest_analysis(self, patient_id: str) -> Optional[Dict[str, Any]]:
        """Get latest valid analysis from cache (24h)"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT * FROM health_analysis
                WHERE patient_id = %s
                AND expires_at > NOW()
                ORDER BY analysis_date DESC
                LIMIT 1
            """, (patient_id,))

            result = cursor.fetchone()
            cursor.close()
            conn.close()

            if result:
                # Parse JSON fields
                for field in ['trends', 'insights', 'recommendations', 'anomalies', 'data_summary', 'score_breakdown']:
                    if result.get(field):
                        result[field] = json.loads(result[field]) if isinstance(result[field], str) else result[field]

                logger.info(f"✅ Found cached analysis for {patient_id}")
                return result

            logger.info(f"ℹ️ No cached analysis found for {patient_id}")
            return None

        except Exception as e:
            logger.error(f"❌ Error fetching analysis: {e}")
            return None

    def _collect_patient_data(self, patient_id: str, days: int) -> Dict[str, Any]:
        """
        Collect comprehensive patient data for analysis

        Returns:
        {
            'patient': {...},
            'thresholds': {...},
            'records': [...],
            'alerts': [...],
            'total_records': int,
            'date_range': {...},
            'summary': {...}
        }
        """
        conn = mysql.connector.connect(**self.db_config)
        cursor = conn.cursor(dictionary=True)

        try:
            # 1. Get patient info
            cursor.execute("""
                SELECT * FROM patients
                WHERE patient_id = %s
            """, (patient_id,))

            patient = cursor.fetchone()
            if not patient:
                raise ValueError(f"Patient {patient_id} not found")

            # 2. Get personalized thresholds
            cursor.execute("""
                SELECT * FROM patient_thresholds
                WHERE patient_id = %s
                ORDER BY updated_at DESC
                LIMIT 1
            """, (patient_id,))

            thresholds = cursor.fetchone()

            # Parse JSON fields in thresholds
            if thresholds:
                for field in ['chronic_diseases', 'medications', 'allergies']:
                    if thresholds.get(field):
                        try:
                            thresholds[field] = json.loads(thresholds[field]) if isinstance(thresholds[field], str) else thresholds[field]
                        except:
                            thresholds[field] = []

            # 3. Get health records (last N days)
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            cursor.execute("""
                SELECT * FROM health_records
                WHERE device_id = (
                    SELECT device_id FROM patients WHERE patient_id = %s
                )
                AND timestamp BETWEEN %s AND %s
                ORDER BY timestamp ASC
            """, (patient_id, start_date, end_date))

            records = cursor.fetchall()

            # 4. Get alerts in period
            cursor.execute("""
                SELECT * FROM alerts
                WHERE patient_id = %s
                AND timestamp BETWEEN %s AND %s
                ORDER BY timestamp DESC
            """, (patient_id, start_date, end_date))

            alerts = cursor.fetchall()

            # 5. Calculate summary statistics
            summary = self._calculate_data_summary(records, alerts, thresholds)

            return {
                'patient': patient,
                'thresholds': thresholds,
                'records': records,
                'alerts': alerts,
                'total_records': len(records),
                'date_range': {
                    'start': start_date,
                    'end': end_date,
                    'days': days
                },
                'summary': summary
            }

        finally:
            cursor.close()
            conn.close()

    def _calculate_data_summary(
        self,
        records: List[Dict],
        alerts: List[Dict],
        thresholds: Optional[Dict]
    ) -> Dict[str, Any]:
        """Calculate statistical summary of health data"""

        if not records:
            return {'total_records': 0, 'data_completeness': 0}

        # Extract vital signs
        hrs = [r['heart_rate'] for r in records if r.get('heart_rate')]
        spo2s = [r['spo2'] for r in records if r.get('spo2')]
        sys_bps = [r['systolic_bp'] for r in records if r.get('systolic_bp')]
        dia_bps = [r['diastolic_bp'] for r in records if r.get('diastolic_bp')]
        temps = [r['temperature'] for r in records if r.get('temperature')]

        # Calculate violations if thresholds exist
        violations = {'hr': 0, 'spo2': 0, 'bp': 0, 'temp': 0}
        if thresholds:
            hr_min = thresholds.get('hr_min', 60)
            hr_max = thresholds.get('hr_max', 100)
            spo2_min = thresholds.get('spo2_min', 95)
            sys_min = thresholds.get('sys_min', 90)
            sys_max = thresholds.get('sys_max', 120)
            dia_min = thresholds.get('dia_min', 60)
            dia_max = thresholds.get('dia_max', 80)
            temp_min = thresholds.get('temp_min', 36.1)
            temp_max = thresholds.get('temp_max', 37.2)

            for r in records:
                if r.get('heart_rate'):
                    if r['heart_rate'] < hr_min or r['heart_rate'] > hr_max:
                        violations['hr'] += 1
                if r.get('spo2'):
                    if r['spo2'] < spo2_min:
                        violations['spo2'] += 1
                if r.get('systolic_bp') and r.get('diastolic_bp'):
                    if (r['systolic_bp'] < sys_min or r['systolic_bp'] > sys_max or
                        r['diastolic_bp'] < dia_min or r['diastolic_bp'] > dia_max):
                        violations['bp'] += 1
                if r.get('temperature'):
                    if r['temperature'] < temp_min or r['temperature'] > temp_max:
                        violations['temp'] += 1

        # Alert breakdown
        alert_counts = {
            'total': len(alerts),
            'critical': len([a for a in alerts if a.get('severity') == 'critical']),
            'warning': len([a for a in alerts if a.get('severity') == 'warning']),
            'info': len([a for a in alerts if a.get('severity') == 'info'])
        }

        return {
            'total_records': len(records),
            'data_completeness': (
                (len(hrs) + len(spo2s) + len(sys_bps) + len(temps)) /
                (len(records) * 4)
            ) if records else 0,

            # Heart Rate
            'hr_avg': round(mean(hrs), 1) if hrs else 0,
            'hr_min': min(hrs) if hrs else 0,
            'hr_max': max(hrs) if hrs else 0,
            'hr_stdev': round(stdev(hrs), 1) if len(hrs) > 1 else 0,
            'hr_violations': violations['hr'],

            # SpO2
            'spo2_avg': round(mean(spo2s), 1) if spo2s else 0,
            'spo2_min': min(spo2s) if spo2s else 0,
            'spo2_max': max(spo2s) if spo2s else 0,
            'spo2_violations': violations['spo2'],

            # Blood Pressure
            'bp_sys_avg': round(mean(sys_bps), 1) if sys_bps else 0,
            'bp_dia_avg': round(mean(dia_bps), 1) if dia_bps else 0,
            'bp_sys_min': min(sys_bps) if sys_bps else 0,
            'bp_sys_max': max(sys_bps) if sys_bps else 0,
            'bp_violations': violations['bp'],

            # Temperature
            'temp_avg': round(mean(temps), 2) if temps else 0,
            'temp_min': min(temps) if temps else 0,
            'temp_max': max(temps) if temps else 0,
            'temp_violations': violations['temp'],

            # Alerts
            **alert_counts
        }

    def _calculate_health_score_components(self, data: Dict) -> Dict[str, float]:
        """
        Calculate health score components (0-100 each)

        Research-based scoring:
        1. Vital Compliance: % of readings within personalized thresholds
        2. Trend Stability: Coefficient of variation (lower = more stable)
        3. Risk Factors: Disease severity + age + medication interactions
        4. Alert Frequency: Alert rate and severity weighted
        """
        summary = data['summary']
        patient = data['patient']
        thresholds = data['thresholds'] or {}
        total_records = data['total_records']

        if total_records == 0:
            return {k: 0.0 for k in ['vital_compliance', 'trend_stability', 'risk_factors', 'alert_frequency']}

        # 1. Vital Sign Compliance Score (0-100)
        # Higher is better - more readings within thresholds
        total_violations = (
            summary['hr_violations'] +
            summary['spo2_violations'] +
            summary['bp_violations'] +
            summary['temp_violations']
        )
        max_possible_violations = total_records * 4  # 4 vital signs
        compliance_rate = 1 - (total_violations / max_possible_violations) if max_possible_violations > 0 else 0
        vital_compliance = max(0, min(100, compliance_rate * 100))

        # 2. Trend Stability Score (0-100)
        # Lower coefficient of variation = more stable = higher score
        cv_scores = []

        if summary['hr_avg'] > 0 and summary['hr_stdev'] > 0:
            hr_cv = (summary['hr_stdev'] / summary['hr_avg']) * 100
            # Good CV for HR: < 10%, Poor: > 20%
            hr_stability = max(0, min(100, 100 - (hr_cv * 5)))
            cv_scores.append(hr_stability)

        # SpO2 should be very stable (CV < 2% is excellent)
        if summary['spo2_avg'] > 0 and summary['spo2_max'] > 0:
            spo2_range = summary['spo2_max'] - summary['spo2_min']
            spo2_stability = max(0, min(100, 100 - (spo2_range * 10)))
            cv_scores.append(spo2_stability)

        # BP stability
        if summary['bp_sys_avg'] > 0 and summary['bp_sys_max'] > 0:
            bp_range = summary['bp_sys_max'] - summary['bp_sys_min']
            # Good: < 20 mmHg range
            bp_stability = max(0, min(100, 100 - (bp_range / 20 * 50)))
            cv_scores.append(bp_stability)

        trend_stability = mean(cv_scores) if cv_scores else 50.0

        # 3. Risk Factors Score (0-100)
        # Lower risk = higher score
        risk_score = 0

        # Age risk (exponential after 60)
        age = patient.get('age', 50)
        if age >= 60:
            age_risk = min(20, (age - 60) * 0.8)
            risk_score += age_risk
        elif age < 18:
            risk_score += 5  # Pediatric considerations

        # Chronic disease risk
        diseases = thresholds.get('chronic_diseases', [])
        if diseases:
            for disease in diseases:
                risk_score += self.DISEASE_RISK_SCORES.get(disease, 3)

        # Medication count (polypharmacy risk)
        medications = thresholds.get('medications', [])
        if len(medications) >= 5:
            risk_score += 8
        elif len(medications) >= 3:
            risk_score += 4

        # Convert to 0-100 (higher is better)
        # Max risk score ~= 100, so invert
        risk_factors = max(0, min(100, 100 - risk_score))

        # 4. Alert Frequency Score (0-100)
        # Fewer alerts = better score
        alert_rate = (
            (summary['critical'] * 3 +  # Weight critical 3x
             summary['warning'] * 1.5) /  # Weight warning 1.5x
            total_records * 100
        ) if total_records > 0 else 0
        # Good: < 5% critical/warning rate
        alert_frequency = max(0, min(100, 100 - (alert_rate * 10)))

        return {
            'vital_compliance': round(vital_compliance, 2),
            'trend_stability': round(trend_stability, 2),
            'risk_factors': round(risk_factors, 2),
            'alert_frequency': round(alert_frequency, 2)
        }

    def _aggregate_health_score(self, components: Dict[str, float]) -> float:
        """
        Aggregate component scores into final health score (0-100)
        Using research-based weights
        """
        score = (
            components['vital_compliance'] * self.SCORE_WEIGHTS['vital_compliance'] +
            components['trend_stability'] * self.SCORE_WEIGHTS['trend_stability'] +
            components['risk_factors'] * self.SCORE_WEIGHTS['risk_factors'] +
            components['alert_frequency'] * self.SCORE_WEIGHTS['alert_frequency']
        )
        return round(score, 1)

    def _determine_status(self, health_score: float, data: Dict) -> str:
        """
        Determine overall status based on score and critical alerts

        excellent: 90-100 + no critical alerts
        good: 75-89
        fair: 60-74
        warning: 40-59 OR has critical alerts
        critical: 0-39 OR multiple critical alerts
        """
        critical_alerts = data['summary']['critical']

        if critical_alerts >= 3:
            return 'critical'
        elif critical_alerts >= 1:
            return 'warning' if health_score >= 60 else 'critical'
        elif health_score >= 90:
            return 'excellent'
        elif health_score >= 75:
            return 'good'
        elif health_score >= 60:
            return 'fair'
        elif health_score >= 40:
            return 'warning'
        else:
            return 'critical'

    def _generate_analysis_prompt(
        self,
        data: Dict,
        score_components: Dict[str, float]
    ) -> str:
        """
        Generate optimized Gemini prompt based on medical best practices

        Prompt engineering research:
        - Chain-of-thought reasoning
        - Structured output format (JSON)
        - Medical context grounding
        - AHA/WHO guidelines reference
        """

        patient = data['patient']
        thresholds = data['thresholds'] or {}
        summary = data['summary']

        # Format medical info
        diseases_str = ", ".join(thresholds.get('chronic_diseases', [])) or "Không có"
        meds_str = ", ".join(thresholds.get('medications', [])) or "Không có"
        allergies_str = ", ".join(thresholds.get('allergies', [])) or "Không có"

        # Gender display
        gender_display = "Nam" if patient.get('gender') == 'M' else "Nữ" if patient.get('gender') == 'F' else "Khác"

        prompt = f"""Bạn là bác sĩ tim mạch và nội khoa chuyên gia với 20 năm kinh nghiệm phân tích dữ liệu sức khỏe từ thiết bị IoT.
Hãy phân tích dữ liệu bệnh nhân sau với tư duy y khoa chuyên sâu dựa trên các guidelines của AHA (American Heart Association) và WHO.

**THÔNG TIN BỆNH NHÂN:**
- Tên: {patient.get('name', 'N/A')}
- Tuổi: {patient.get('age', 'N/A')} tuổi ({self._age_category(patient.get('age', 0))})
- Giới tính: {gender_display}
- Bệnh mãn tính: {diseases_str}
- Thuốc đang dùng: {meds_str}
- Dị ứng: {allergies_str}

**NGƯỠNG CÁ NHÂN (Patient-Specific Thresholds):**
Các ngưỡng này đã được cá nhân hóa dựa trên tình trạng sức khỏe của bệnh nhân:
- Nhịp tim: {thresholds.get('hr_min', 60)}-{thresholds.get('hr_max', 100)} bpm
- SpO2: {thresholds.get('spo2_min', 95)}-{thresholds.get('spo2_max', 100)}%
- Huyết áp tâm thu: {thresholds.get('sys_min', 90)}-{thresholds.get('sys_max', 120)} mmHg
- Huyết áp tâm trương: {thresholds.get('dia_min', 60)}-{thresholds.get('dia_max', 80)} mmHg
- Nhiệt độ: {thresholds.get('temp_min', 36.1)}-{thresholds.get('temp_max', 37.2)}°C

**DỮ LIỆU 30 NGÀY GẦN NHẤT:**
Tổng số đo: {summary['total_records']} records
Độ đầy đủ dữ liệu: {summary['data_completeness']*100:.1f}%

1. NHỊP TIM (Heart Rate):
   - Trung bình: {summary['hr_avg']} bpm
   - Khoảng dao động: {summary['hr_min']} - {summary['hr_max']} bpm
   - Độ lệch chuẩn: {summary['hr_stdev']} ({"ổn định" if summary['hr_stdev'] < 10 else "dao động nhẹ" if summary['hr_stdev'] < 15 else "dao động nhiều"})
   - Số lần vượt ngưỡng: {summary['hr_violations']} ({summary['hr_violations']/max(1,summary['total_records'])*100:.1f}%)

2. SPO2 (Oxy máu):
   - Trung bình: {summary['spo2_avg']}%
   - Khoảng dao động: {summary['spo2_min']} - {summary['spo2_max']}%
   - Số lần vượt ngưỡng: {summary['spo2_violations']} ({summary['spo2_violations']/max(1,summary['total_records'])*100:.1f}%)

3. HUYẾT ÁP (Blood Pressure):
   - Trung bình: {summary['bp_sys_avg']}/{summary['bp_dia_avg']} mmHg
   - Tâm thu: {summary['bp_sys_min']} - {summary['bp_sys_max']} mmHg
   - Số lần vượt ngưỡng: {summary['bp_violations']} ({summary['bp_violations']/max(1,summary['total_records'])*100:.1f}%)

4. NHIỆT ĐỘ (Body Temperature):
   - Trung bình: {summary['temp_avg']}°C
   - Khoảng dao động: {summary['temp_min']} - {summary['temp_max']}°C
   - Số lần vượt ngưỡng: {summary['temp_violations']}

**CẢNH BÁO TRONG 30 NGÀY:**
- Tổng số: {summary['total']}
- Critical (nghiêm trọng): {summary['critical']}
- Warning (cảnh báo): {summary['warning']}
- Info (thông tin): {summary['info']}

**ĐIỂM SỨC KHỎE ĐÃ TÍNH (0-100):**
- Tuân thủ ngưỡng: {score_components['vital_compliance']:.1f}/100
- Ổn định xu hướng: {score_components['trend_stability']:.1f}/100
- Yếu tố nguy cơ: {score_components['risk_factors']:.1f}/100
- Tần suất cảnh báo: {score_components['alert_frequency']:.1f}/100

**GUIDELINES Y KHOA THAM CHIẾU:**
- AHA Blood Pressure Guidelines 2017/2023:
  * Bình thường: <120/80 mmHg
  * Cao: 120-129/<80 mmHg
  * Stage 1 HTN: 130-139/80-89 mmHg
  * Stage 2 HTN: ≥140/90 mmHg
  * Khủng hoảng THA: >180/120 mmHg

- Nhịp tim bình thường (người lớn): 60-100 bpm
- SpO2 bình thường: 95-100% (COPD có thể chấp nhận 88-92%)
- Nhiệt độ bình thường: 36.1-37.2°C

**YÊU CẦU PHÂN TÍCH:**

Hãy trả về JSON với cấu trúc sau (CHỈ TRẢ VỀ JSON CHUẨN, KHÔNG THÊM MARKDOWN HAY TEXT KHÁC):

{{
  "trends": {{
    "heart_rate": {{
      "direction": "increasing/decreasing/stable",
      "change_percent": <số thập phân>,
      "assessment": "Đánh giá xu hướng nhịp tim trong 30 ngày, so sánh với ngưỡng cá nhân (50-80 từ)",
      "prediction": "Dự đoán xu hướng 7-14 ngày tới dựa trên pattern hiện tại (30-50 từ)",
      "confidence": <0.0-1.0>
    }},
    "spo2": {{
      "direction": "increasing/decreasing/stable",
      "change_percent": <số thập phân>,
      "assessment": "Đánh giá SpO2, lưu ý nếu có COPD thì 88-92% vẫn chấp nhận được",
      "prediction": "Dự đoán SpO2",
      "confidence": <0.0-1.0>
    }},
    "blood_pressure": {{
      "direction": "increasing/decreasing/stable",
      "change_percent": <số thập phân>,
      "assessment": "Đánh giá huyết áp theo AHA guidelines, xem xét cả tâm thu và tâm trương",
      "prediction": "Dự đoán huyết áp",
      "confidence": <0.0-1.0>
    }},
    "temperature": {{
      "direction": "stable",
      "change_percent": 0,
      "assessment": "Đánh giá nhiệt độ",
      "prediction": "Dự đoán nhiệt độ",
      "confidence": <0.0-1.0>
    }}
  }},
  "insights": [
    {{
      "type": "positive/warning/critical",
      "vital": "heart_rate/spo2/blood_pressure/temperature/general",
      "message": "Tiêu đề ngắn gọn (10-15 từ)",
      "details": "Chi tiết đánh giá với số liệu cụ thể, so sánh với ngưỡng và guidelines (40-60 từ)",
      "confidence": <0.0-1.0>
    }}
  ],
  "recommendations": [
    {{
      "category": "lifestyle/medical/diet/exercise/sleep",
      "priority": "high/medium/low",
      "title": "Tiêu đề ngắn gọn (5-10 từ)",
      "description": "Mô tả chi tiết, cụ thể, thực tế cho người Việt Nam (60-100 từ)",
      "reasoning": "Lý do y khoa dựa trên guidelines (40-60 từ)",
      "evidence": "Tham chiếu guideline (vd: AHA 2017, WHO, JNC8)"
    }}
  ],
  "anomalies": [
    {{
      "date": "YYYY-MM-DDTHH:mm:ss",
      "vital": "heart_rate/spo2/blood_pressure/temperature",
      "value": <giá trị>,
      "threshold": <ngưỡng>,
      "severity": "high/medium/low",
      "description": "Mô tả bất thường với context (30-50 từ)"
    }}
  ],
  "overall_assessment": "Đánh giá tổng quan chi tiết về sức khỏe bệnh nhân trong 30 ngày, bao gồm: (1) Tóm tắt tình trạng hiện tại, (2) Các vấn đề cần lưu ý, (3) Tiên lượng ngắn hạn, (4) Khuyến nghị tổng quát. Nếu có bệnh mãn tính, đánh giá mức độ kiểm soát bệnh. (120-180 từ)",
  "confidence_notes": "Ghi chú về độ tin cậy của phân tích (vd: dữ liệu đầy đủ, có bệnh lý phức tạp cần theo dõi thêm, v.v.)"
}}

**LƯU Ý QUAN TRỌNG:**
1. ✅ So sánh với NGƯỠNG CÁ NHÂN (đã điều chỉnh cho bệnh nhân), không phải ngưỡng chuẩn
2. ✅ Xem xét bệnh mãn tính (vd: COPD → SpO2 88-92% là chấp nhận được; Beta-blocker → nhịp tim thấp hơn là bình thường)
3. ✅ Xem xét thuốc đang dùng và tác động của chúng
4. ✅ Đưa ra khuyến nghị CỤ THỂ, THỰC TẾ cho người Việt Nam (thức ăn, lối sống)
5. ✅ Nếu phát hiện vấn đề nghiêm trọng → khuyến cáo KHÁM BÁC SĨ rõ ràng
6. ✅ Sử dụng TIẾNG VIỆT trong tất cả message
7. ✅ Tạo ít nhất 3 insights (1 positive, 1-2 warning/critical nếu cần)
8. ✅ Tạo ít nhất 3 recommendations với priority phù hợp
9. ✅ Chỉ liệt kê anomalies nếu có bất thường rõ ràng (không liệt kê nếu mọi thứ bình thường)

CHỈ TRẢ VỀ JSON, KHÔNG THÊM TEXT HOẶC MARKDOWN.
"""

        return prompt

    def _age_category(self, age: int) -> str:
        """Categorize age for context"""
        if age < 18:
            return "trẻ vị thành niên"
        elif age < 40:
            return "người trưởng thành trẻ"
        elif age < 60:
            return "người trung niên"
        elif age < 75:
            return "người cao tuổi"
        else:
            return "người rất cao tuổi"

    def _parse_gemini_response(self, response_text: str) -> Dict[str, Any]:
        """Parse and validate Gemini response"""
        try:
            # Remove markdown code blocks if present
            clean_text = response_text.strip()
            if clean_text.startswith("```json"):
                clean_text = clean_text[7:]
            if clean_text.startswith("```"):
                clean_text = clean_text[3:]
            if clean_text.endswith("```"):
                clean_text = clean_text[:-3]

            result = json.loads(clean_text.strip())

            # Validate structure
            required_keys = ['trends', 'insights', 'recommendations', 'anomalies']
            for key in required_keys:
                if key not in result:
                    logger.warning(f"Missing key in Gemini response: {key}")
                    result[key] = {} if key == 'trends' else []

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response: {e}")
            logger.debug(f"Response text: {response_text[:500]}")
            # Return empty structure
            return {
                'trends': {},
                'insights': [{
                    'type': 'warning',
                    'vital': 'general',
                    'message': 'Không thể phân tích chi tiết',
                    'details': 'Có lỗi xảy ra khi phân tích dữ liệu. Vui lòng thử lại sau.',
                    'confidence': 0.0
                }],
                'recommendations': [],
                'anomalies': [],
                'overall_assessment': 'Không thể đưa ra đánh giá do lỗi xử lý dữ liệu.',
                'confidence_notes': 'Phân tích thất bại do lỗi định dạng.'
            }

    def _calculate_confidence(self, data: Dict, ai_result: Dict) -> float:
        """
        Calculate overall confidence score (0.0-1.0)

        Factors:
        - Data completeness (30%)
        - Record count (30%)
        - AI response quality (20%)
        - Data consistency (20%)
        """
        summary = data['summary']
        total_records = data['total_records']

        # Data completeness score
        completeness_score = summary['data_completeness']

        # Record count score (sigmoid function)
        # Good: >= 100 records, Poor: < 30 records
        count_score = 1 / (1 + math.exp(-0.05 * (total_records - 50)))

        # AI response quality (has all required fields)
        ai_quality = 1.0
        if not ai_result.get('trends'):
            ai_quality -= 0.3
        if not ai_result.get('insights'):
            ai_quality -= 0.3
        if not ai_result.get('recommendations'):
            ai_quality -= 0.2
        ai_quality = max(0, ai_quality)

        # Data consistency (low variance in vitals = higher confidence)
        consistency_score = 0.8  # Default
        if summary['hr_stdev'] > 0 and summary['hr_avg'] > 0:
            hr_cv = (summary['hr_stdev'] / summary['hr_avg']) * 100
            consistency_score = max(0, min(1, 1 - (hr_cv / 50)))

        # Weighted average
        confidence = (
            completeness_score * 0.30 +
            count_score * 0.30 +
            ai_quality * 0.20 +
            consistency_score * 0.20
        )

        return round(confidence, 2)

    def _save_analysis(
        self,
        patient_id: str,
        data: Dict,
        result: Dict[str, Any],
        raw_response: str
    ):
        """Save analysis result to database with 24h cache"""
        try:
            conn = mysql.connector.connect(**self.db_config)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO health_analysis (
                    patient_id, analysis_date, date_range_start, date_range_end,
                    health_score, overall_status, trends, insights, recommendations,
                    anomalies, ai_model, ai_confidence, ai_raw_response, data_summary,
                    score_breakdown, expires_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    DATE_ADD(NOW(), INTERVAL 24 HOUR)
                )
            """, (
                patient_id,
                datetime.now(),
                data['date_range']['start'],
                data['date_range']['end'],
                result['health_score'],
                result['overall_status'],
                json.dumps(result['trends'], ensure_ascii=False),
                json.dumps(result['insights'], ensure_ascii=False),
                json.dumps(result['recommendations'], ensure_ascii=False),
                json.dumps(result['anomalies'], ensure_ascii=False),
                'gemini-2.0-flash',
                result['ai_confidence'],
                raw_response[:10000],  # Limit size
                json.dumps(result['data_summary'], ensure_ascii=False),
                json.dumps(result['score_breakdown'], ensure_ascii=False)
            ))

            conn.commit()
            logger.info(f"✅ Analysis saved to database for patient: {patient_id}")

            cursor.close()
            conn.close()

        except Exception as e:
            logger.error(f"❌ Failed to save analysis: {e}")

    def _create_insufficient_data_response(self, data: Dict) -> Dict[str, Any]:
        """Create response when insufficient data"""
        patient = data.get('patient', {})
        return {
            'patient_id': patient.get('patient_id'),  # Add patient_id to response
            'health_score': 0,
            'overall_status': 'unknown',
            'trends': {},
            'insights': [{
                'type': 'info',
                'vital': 'general',
                'message': 'Không đủ dữ liệu để phân tích',
                'details': f'Chỉ có {data["total_records"]} records trong 30 ngày. Cần ít nhất 10 records để phân tích có ý nghĩa thống kê.',
                'confidence': 0.0
            }],
            'recommendations': [{
                'category': 'general',
                'priority': 'medium',
                'title': 'Tiếp tục theo dõi sức khỏe',
                'description': 'Hãy đeo thiết bị theo dõi thường xuyên để thu thập thêm dữ liệu. Khuyến nghị đo ít nhất 3-4 lần/ngày để có dữ liệu đủ cho phân tích xu hướng chính xác.',
                'reasoning': 'Cần ít nhất 7-10 ngày dữ liệu liên tục với 3-4 lần đo/ngày để phân tích xu hướng sức khỏe chính xác.',
                'evidence': 'Clinical practice guidelines for remote patient monitoring'
            }],
            'anomalies': [],
            'ai_confidence': 0.0,
            'data_summary': data['summary'],
            'score_breakdown': {
                'vital_compliance': 0,
                'trend_stability': 0,
                'risk_factors': 0,
                'alert_frequency': 0
            },
            'overall_assessment': 'Không thể đưa ra đánh giá do không đủ dữ liệu. Vui lòng tiếp tục theo dõi sức khỏe thường xuyên.'
        }


# ==================== Standalone Testing ====================

if __name__ == "__main__":
    # Test configuration
    import os

    DB_CONFIG = {
        'host': 'database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com',
        'user': 'admin',
        'password': os.getenv('MYSQL_PASSWORD', 'your_password'),
        'database': 'iot_health_cloud',
        'port': 3306,
        'charset': 'utf8mb4'
    }

    GEMINI_API_KEY = os.getenv('GOOGLE_GEMINI_API_KEY', '')

    if not GEMINI_API_KEY:
        print("❌ GOOGLE_GEMINI_API_KEY not set")
        exit(1)

    service = HealthAnalysisService(DB_CONFIG, GEMINI_API_KEY)

    # Test with a sample patient
    test_patient_id = "patient_001"

    # Check for cached analysis first
    cached = service.get_latest_analysis(test_patient_id)
    if cached:
        print(f"✅ Found cached analysis: score={cached['health_score']}")
    else:
        print("ℹ️ No cached analysis, generating new one...")
        result = service.analyze_patient_health(test_patient_id, days=30)
        print(f"✅ Analysis complete: score={result['health_score']}, status={result['overall_status']}")
        print(f"   Confidence: {result['ai_confidence']}")
        print(f"   Insights: {len(result['insights'])}")
        print(f"   Recommendations: {len(result['recommendations'])}")

