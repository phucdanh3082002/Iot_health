-- MySQL dump 10.13  Distrib 8.0.44, for Win64 (x86_64)
--
-- Host: database-1.cba08ks48qdc.ap-southeast-1.rds.amazonaws.com    Database: iot_health_cloud
-- ------------------------------------------------------
-- Server version	8.0.44

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;
SET @MYSQLDUMP_TEMP_LOG_BIN = @@SESSION.SQL_LOG_BIN;
SET @@SESSION.SQL_LOG_BIN= 0;

--
-- GTID state at the beginning of the backup 
--

SET @@GLOBAL.GTID_PURGED=/*!80000 '+'*/ '';

--
-- Table structure for table `alerts`
--

DROP TABLE IF EXISTS `alerts`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `alerts` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Patient identifier (NULL if device not assigned to patient)',
  `device_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Device that generated alert',
  `health_record_id` bigint DEFAULT NULL COMMENT 'Link to specific measurement',
  `alert_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Type of alert',
  `severity` enum('low','medium','high','critical') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Alert severity',
  `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Alert message',
  `vital_sign` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Affected vital sign',
  `current_value` decimal(10,2) DEFAULT NULL COMMENT 'Current value that triggered alert',
  `threshold_value` decimal(10,2) DEFAULT NULL COMMENT 'Threshold that was exceeded',
  `timestamp` datetime(6) NOT NULL COMMENT 'Alert creation time',
  `acknowledged` tinyint(1) DEFAULT '0' COMMENT 'Alert acknowledged flag',
  `acknowledged_at` datetime(6) DEFAULT NULL COMMENT 'Time alert was acknowledged',
  `acknowledged_by` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'User/System who acknowledged',
  `resolved` tinyint(1) DEFAULT '0' COMMENT 'Alert resolved flag',
  `resolved_at` datetime(6) DEFAULT NULL COMMENT 'Time alert was resolved',
  `notification_sent` tinyint(1) DEFAULT '0' COMMENT 'Notification sent flag',
  `notification_method` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Notification method: mqtt, fcm, email, sms',
  PRIMARY KEY (`id`),
  KEY `idx_patient_timestamp` (`patient_id`,`timestamp`),
  KEY `idx_device_timestamp` (`device_id`,`timestamp`),
  KEY `idx_severity` (`severity`),
  KEY `idx_acknowledged` (`acknowledged`),
  KEY `idx_resolved` (`resolved`),
  KEY `idx_device_id` (`device_id`),
  KEY `idx_unresolved_timestamp` (`resolved`,`timestamp` DESC),
  CONSTRAINT `alerts_ibfk_2` FOREIGN KEY (`device_id`) REFERENCES `devices` (`device_id`) ON DELETE RESTRICT,
  CONSTRAINT `fk_alerts_patient` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`patient_id`) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=74 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Health alerts and warnings';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `device_ownership`
--

DROP TABLE IF EXISTS `device_ownership`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `device_ownership` (
  `id` int NOT NULL AUTO_INCREMENT,
  `user_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Android app user ID (email or UUID)',
  `device_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Pi device ID (rasp_pi_001, etc.)',
  `role` enum('owner','admin','caregiver','viewer') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'owner' COMMENT 'Access level',
  `nickname` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Custom device name for this user',
  `added_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'When user added this device',
  `last_accessed` datetime(6) DEFAULT NULL COMMENT 'Last time user viewed this device',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_user_device` (`user_id`,`device_id`),
  KEY `idx_user_id` (`user_id`),
  KEY `idx_device_id` (`device_id`),
  KEY `idx_added_at` (`added_at`),
  CONSTRAINT `device_ownership_ibfk_1` FOREIGN KEY (`device_id`) REFERENCES `devices` (`device_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=3 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Device ownership and access control for multi-user support';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `devices`
--

DROP TABLE IF EXISTS `devices`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `devices` (
  `id` int NOT NULL AUTO_INCREMENT,
  `device_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Unique device identifier',
  `device_name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Friendly name',
  `location` varchar(200) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Physical location',
  `ip_address` varchar(45) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Last known IP address',
  `last_seen` datetime(6) DEFAULT NULL COMMENT 'Last connection time',
  `firmware_version` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Device firmware version',
  `os_version` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Operating system version',
  `is_active` tinyint(1) DEFAULT '1' COMMENT 'Device active status',
  `created_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `pairing_code` varchar(8) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT '6-8 character pairing code for QR/manual pairing',
  `pairing_qr_data` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Full QR code JSON payload',
  `paired_at` datetime(6) DEFAULT NULL COMMENT 'When device was paired with app',
  `paired_by` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'User ID who paired this device',
  `device_type` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'raspberry_pi_4b' COMMENT 'Device hardware type',
  PRIMARY KEY (`id`),
  UNIQUE KEY `device_id` (`device_id`),
  UNIQUE KEY `pairing_code` (`pairing_code`),
  KEY `idx_device_id` (`device_id`),
  KEY `idx_last_seen` (`last_seen`),
  KEY `idx_active` (`is_active`),
  KEY `idx_devices_pairing_code` (`pairing_code`),
  KEY `idx_devices_paired_by` (`paired_by`),
  KEY `idx_devices_type` (`device_type`),
  KEY `idx_pairing_code` (`pairing_code`)
) ENGINE=InnoDB AUTO_INCREMENT=8 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Raspberry Pi devices registry';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `health_records`
--

DROP TABLE IF EXISTS `health_records`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `health_records` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Auto-incrementing ID',
  `patient_id` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Patient identifier (NULL if device not assigned to patient)',
  `device_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Device that recorded this data',
  `timestamp` datetime(6) NOT NULL COMMENT 'Measurement timestamp with microseconds',
  `heart_rate` decimal(6,2) DEFAULT NULL COMMENT 'Heart rate in BPM',
  `spo2` decimal(5,2) DEFAULT NULL COMMENT 'SpO2 percentage',
  `temperature` decimal(4,2) DEFAULT NULL COMMENT 'Temperature in Celsius',
  `systolic_bp` decimal(6,2) DEFAULT NULL COMMENT 'Systolic blood pressure in mmHg',
  `diastolic_bp` decimal(6,2) DEFAULT NULL COMMENT 'Diastolic blood pressure in mmHg',
  `mean_arterial_pressure` decimal(6,2) DEFAULT NULL COMMENT 'MAP in mmHg',
  `sensor_data` json DEFAULT NULL COMMENT 'Additional sensor metadata (SQI, peaks, etc.)',
  `data_quality` decimal(3,2) DEFAULT NULL COMMENT 'Quality score 0-1',
  `measurement_context` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Context: rest/activity/sleep',
  `synced_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'Time synced to cloud',
  `sync_status` enum('pending','synced','conflict') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'synced',
  PRIMARY KEY (`id`,`timestamp`),
  KEY `idx_patient_timestamp` (`patient_id`,`timestamp`),
  KEY `idx_device_timestamp` (`device_id`,`timestamp`),
  KEY `idx_timestamp` (`timestamp`),
  KEY `idx_sync_status` (`sync_status`),
  KEY `idx_timestamp_quality` (`timestamp` DESC,`data_quality`)
) ENGINE=InnoDB AUTO_INCREMENT=65 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Health vital signs records'
/*!50100 PARTITION BY RANGE (year(`timestamp`))
(PARTITION p2024 VALUES LESS THAN (2025) ENGINE = InnoDB,
 PARTITION p2025 VALUES LESS THAN (2026) ENGINE = InnoDB,
 PARTITION p2026 VALUES LESS THAN (2027) ENGINE = InnoDB,
 PARTITION p2027 VALUES LESS THAN (2028) ENGINE = InnoDB,
 PARTITION pmax VALUES LESS THAN MAXVALUE ENGINE = InnoDB) */;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `patient_thresholds`
--

DROP TABLE IF EXISTS `patient_thresholds`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `patient_thresholds` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Patient identifier',
  `vital_sign` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Vital sign name',
  `min_normal` decimal(10,2) DEFAULT NULL COMMENT 'Minimum normal value',
  `max_normal` decimal(10,2) DEFAULT NULL COMMENT 'Maximum normal value',
  `min_critical` decimal(10,2) DEFAULT NULL COMMENT 'Minimum critical value',
  `max_critical` decimal(10,2) DEFAULT NULL COMMENT 'Maximum critical value',
  `is_active` tinyint(1) DEFAULT '1' COMMENT 'Threshold active status',
  `created_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `min_warning` float DEFAULT NULL COMMENT 'Minimum warning value (yellow alert)',
  `max_warning` float DEFAULT NULL COMMENT 'Maximum warning value (yellow alert)',
  `generation_method` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT 'manual' COMMENT 'How threshold was created: manual, rule_based, ai_generated',
  `ai_confidence` float DEFAULT NULL COMMENT 'AI confidence score (0-1) if AI-generated',
  `ai_model` varchar(50) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'AI model used: gemini-1.5-pro, rule_based, etc.',
  `generation_timestamp` datetime DEFAULT NULL COMMENT 'When threshold was generated',
  `applied_rules` json DEFAULT NULL COMMENT 'JSON array of applied rules (for rule_based/hybrid methods)',
  `metadata` json DEFAULT NULL COMMENT 'Additional metadata: {input_factors: [...], justification: "..."}',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_patient_vital` (`patient_id`,`vital_sign`),
  KEY `idx_patient_id` (`patient_id`),
  KEY `idx_active` (`is_active`),
  KEY `idx_generation_method` (`generation_method`),
  KEY `idx_ai_confidence` (`ai_confidence`),
  CONSTRAINT `patient_thresholds_ibfk_1` FOREIGN KEY (`patient_id`) REFERENCES `patients` (`patient_id`) ON DELETE CASCADE
) ENGINE=InnoDB AUTO_INCREMENT=209 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Patient-specific alert thresholds with AI generation support';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `patients`
--

DROP TABLE IF EXISTS `patients`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `patients` (
  `id` int NOT NULL AUTO_INCREMENT,
  `patient_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Unique patient ID',
  `device_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Primary monitoring device',
  `name` varchar(100) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Patient name',
  `age` int DEFAULT NULL COMMENT 'Patient age',
  `gender` char(1) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Gender: M/F/O',
  `medical_conditions` json DEFAULT NULL COMMENT 'Medical history as JSON',
  `emergency_contact` json DEFAULT NULL COMMENT 'Emergency contacts as JSON',
  `created_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6),
  `updated_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  `is_active` tinyint(1) DEFAULT '1' COMMENT 'Patient active status',
  `height` float DEFAULT NULL COMMENT 'Height in cm',
  `weight` float DEFAULT NULL COMMENT 'Weight in kg',
  `blood_type` varchar(5) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Blood type (A+, B+, AB+, O+, A-, B-, AB-, O-)',
  `chronic_diseases` json DEFAULT NULL COMMENT 'List of chronic diseases: [{"name": "Hypertension", "diagnosed_date": "2020-01-01", "severity": "moderate"}]',
  `medications` json DEFAULT NULL COMMENT 'Current medications: [{"name": "Aspirin", "dosage": "100mg", "frequency": "daily", "start_date": "2020-01-01"}]',
  `allergies` json DEFAULT NULL COMMENT 'Known allergies: [{"allergen": "Penicillin", "severity": "high", "reaction": "rash"}]',
  `family_history` json DEFAULT NULL COMMENT 'Family medical history: [{"condition": "Heart Disease", "relation": "father"}]',
  `smoking_status` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Smoking status: never, former, current',
  `alcohol_consumption` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Alcohol consumption: none, light, moderate, heavy',
  `exercise_frequency` varchar(20) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Exercise frequency: none, weekly, daily',
  `risk_factors` json DEFAULT NULL COMMENT 'Calculated risk factors: [{"factor": "Age", "level": "moderate"}]',
  PRIMARY KEY (`id`),
  UNIQUE KEY `patient_id` (`patient_id`),
  KEY `idx_patient_id` (`patient_id`),
  KEY `idx_device_id` (`device_id`),
  KEY `idx_active` (`is_active`),
  KEY `idx_blood_type` (`blood_type`),
  KEY `idx_smoking_status` (`smoking_status`),
  KEY `idx_active_device` (`is_active`,`device_id`),
  CONSTRAINT `patients_ibfk_1` FOREIGN KEY (`device_id`) REFERENCES `devices` (`device_id`) ON DELETE SET NULL,
  CONSTRAINT `patients_chk_1` CHECK ((`gender` in (_utf8mb4'M',_utf8mb4'F',_utf8mb4'O')))
) ENGINE=InnoDB AUTO_INCREMENT=35 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Patient information';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `sensor_calibrations`
--

DROP TABLE IF EXISTS `sensor_calibrations`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sensor_calibrations` (
  `id` int NOT NULL AUTO_INCREMENT,
  `device_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Device where sensor is installed',
  `sensor_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Sensor name (HX710B, MAX30102, etc.)',
  `calibration_type` varchar(20) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Calibration type (two_point, etc.)',
  `reference_values` json DEFAULT NULL COMMENT 'Reference calibration values',
  `measured_values` json DEFAULT NULL COMMENT 'Measured calibration values',
  `calibration_factors` json DEFAULT NULL COMMENT 'Calibration factors (offset, slope, etc.)',
  `calibrated_at` datetime(6) DEFAULT NULL COMMENT 'Calibration timestamp',
  `is_active` tinyint(1) DEFAULT '1' COMMENT 'Calibration active status',
  `notes` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Additional calibration notes',
  PRIMARY KEY (`id`),
  UNIQUE KEY `unique_device_sensor` (`device_id`,`sensor_name`),
  KEY `idx_device_id` (`device_id`),
  KEY `idx_sensor_name` (`sensor_name`),
  KEY `idx_active` (`is_active`),
  KEY `idx_device_sensor` (`device_id`,`sensor_name`),
  CONSTRAINT `sensor_calibrations_ibfk_1` FOREIGN KEY (`device_id`) REFERENCES `devices` (`device_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Sensor calibration data';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `sync_queue`
--

DROP TABLE IF EXISTS `sync_queue`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `sync_queue` (
  `id` bigint NOT NULL AUTO_INCREMENT,
  `device_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Source device',
  `table_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Table name being synced',
  `operation` enum('INSERT','UPDATE','DELETE') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Sync operation type',
  `record_id` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Record identifier',
  `data_snapshot` json NOT NULL COMMENT 'Full record data snapshot',
  `priority` int DEFAULT '5' COMMENT 'Priority (1=highest, 10=lowest)',
  `created_at` datetime(6) DEFAULT CURRENT_TIMESTAMP(6) COMMENT 'Queue entry creation time',
  `sync_attempts` int DEFAULT '0' COMMENT 'Number of sync attempts',
  `last_sync_attempt` datetime(6) DEFAULT NULL COMMENT 'Last sync attempt time',
  `sync_status` enum('pending','syncing','success','failed') CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT 'pending' COMMENT 'Sync status',
  `error_message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci COMMENT 'Error message if sync failed',
  PRIMARY KEY (`id`),
  KEY `idx_device_status` (`device_id`,`sync_status`),
  KEY `idx_status_created` (`sync_status`,`created_at`),
  KEY `idx_table_name` (`table_name`),
  KEY `idx_priority` (`priority`,`created_at`),
  CONSTRAINT `sync_queue_ibfk_1` FOREIGN KEY (`device_id`) REFERENCES `devices` (`device_id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Sync queue for offline operations';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `system_logs`
--

DROP TABLE IF EXISTS `system_logs`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `system_logs` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT 'Auto-incrementing ID',
  `device_id` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Source device',
  `level` varchar(20) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL',
  `message` text CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Log message',
  `module` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Source module',
  `function_name` varchar(50) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Source function name',
  `line_number` int DEFAULT NULL COMMENT 'Source line number',
  `timestamp` datetime(6) NOT NULL COMMENT 'Log timestamp',
  `additional_data` json DEFAULT NULL COMMENT 'Additional log data as JSON',
  PRIMARY KEY (`id`,`timestamp`),
  KEY `idx_device_timestamp` (`device_id`,`timestamp`),
  KEY `idx_level` (`level`),
  KEY `idx_timestamp` (`timestamp`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='System event logs'
/*!50100 PARTITION BY RANGE (year(`timestamp`))
(PARTITION p2024 VALUES LESS THAN (2025) ENGINE = InnoDB,
 PARTITION p2025 VALUES LESS THAN (2026) ENGINE = InnoDB,
 PARTITION p2026 VALUES LESS THAN (2027) ENGINE = InnoDB,
 PARTITION p2027 VALUES LESS THAN (2028) ENGINE = InnoDB,
 PARTITION pmax VALUES LESS THAN MAXVALUE ENGINE = InnoDB) */;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `threshold_generation_rules`
--

DROP TABLE IF EXISTS `threshold_generation_rules`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `threshold_generation_rules` (
  `id` int NOT NULL AUTO_INCREMENT COMMENT 'Rule ID',
  `rule_name` varchar(100) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Rule name',
  `vital_sign` varchar(50) COLLATE utf8mb4_unicode_ci NOT NULL COMMENT 'Vital sign this rule applies to',
  `conditions` json NOT NULL COMMENT 'Conditions: {age_range: [min, max], gender: "M/F/O", chronic_diseases: [...]}',
  `min_normal_adjustment` float DEFAULT '0' COMMENT 'Adjustment to min_normal baseline',
  `max_normal_adjustment` float DEFAULT '0' COMMENT 'Adjustment to max_normal baseline',
  `min_critical_adjustment` float DEFAULT '0' COMMENT 'Adjustment to min_critical baseline',
  `max_critical_adjustment` float DEFAULT '0' COMMENT 'Adjustment to max_critical baseline',
  `justification` text COLLATE utf8mb4_unicode_ci COMMENT 'Medical justification for this rule',
  `source` varchar(200) COLLATE utf8mb4_unicode_ci DEFAULT NULL COMMENT 'Medical guideline source',
  `priority` int DEFAULT '5' COMMENT 'Rule priority (1=highest, 10=lowest)',
  `is_active` tinyint(1) DEFAULT '1' COMMENT 'Whether rule is active',
  `created_at` datetime DEFAULT CURRENT_TIMESTAMP COMMENT 'Rule creation timestamp',
  `updated_at` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT 'Last update timestamp',
  PRIMARY KEY (`id`),
  KEY `idx_vital_sign` (`vital_sign`),
  KEY `idx_is_active` (`is_active`),
  KEY `idx_priority` (`priority`)
) ENGINE=InnoDB AUTO_INCREMENT=11 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Baseline rules for AI threshold generation';
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Temporary view structure for view `v_active_alerts`
--

DROP TABLE IF EXISTS `v_active_alerts`;
/*!50001 DROP VIEW IF EXISTS `v_active_alerts`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_active_alerts` AS SELECT 
 1 AS `id`,
 1 AS `patient_id`,
 1 AS `patient_name`,
 1 AS `device_id`,
 1 AS `device_name`,
 1 AS `severity`,
 1 AS `vital_sign`,
 1 AS `message`,
 1 AS `current_value`,
 1 AS `timestamp`,
 1 AS `acknowledged`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_alert_summary`
--

DROP TABLE IF EXISTS `v_alert_summary`;
/*!50001 DROP VIEW IF EXISTS `v_alert_summary`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_alert_summary` AS SELECT 
 1 AS `alert_date`,
 1 AS `device_id`,
 1 AS `vital_sign`,
 1 AS `severity`,
 1 AS `total_alerts`,
 1 AS `unacknowledged`,
 1 AS `unresolved`,
 1 AS `notifications_sent`,
 1 AS `avg_response_minutes`,
 1 AS `max_response_minutes`,
 1 AS `avg_resolution_minutes`,
 1 AS `avg_value`,
 1 AS `min_value`,
 1 AS `max_value`,
 1 AS `first_alert`,
 1 AS `last_alert`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_daily_summary`
--

DROP TABLE IF EXISTS `v_daily_summary`;
/*!50001 DROP VIEW IF EXISTS `v_daily_summary`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_daily_summary` AS SELECT 
 1 AS `summary_date`,
 1 AS `active_devices`,
 1 AS `unique_patients`,
 1 AS `total_records`,
 1 AS `synced_records`,
 1 AS `sync_success_rate`,
 1 AS `avg_data_quality`,
 1 AS `low_quality_count`,
 1 AS `total_alerts`,
 1 AS `critical_alerts`,
 1 AS `error_count`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_data_quality`
--

DROP TABLE IF EXISTS `v_data_quality`;
/*!50001 DROP VIEW IF EXISTS `v_data_quality`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_data_quality` AS SELECT 
 1 AS `device_id`,
 1 AS `measurement_date`,
 1 AS `total_measurements`,
 1 AS `avg_quality`,
 1 AS `min_quality`,
 1 AS `max_quality`,
 1 AS `excellent_count`,
 1 AS `good_count`,
 1 AS `fair_count`,
 1 AS `poor_count`,
 1 AS `missing_heart_rate`,
 1 AS `missing_spo2`,
 1 AS `missing_temperature`,
 1 AS `missing_bp`,
 1 AS `completeness_pct`,
 1 AS `avg_heart_rate`,
 1 AS `avg_spo2`,
 1 AS `avg_temperature`,
 1 AS `avg_systolic_bp`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_device_health`
--

DROP TABLE IF EXISTS `v_device_health`;
/*!50001 DROP VIEW IF EXISTS `v_device_health`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_device_health` AS SELECT 
 1 AS `device_id`,
 1 AS `device_name`,
 1 AS `location`,
 1 AS `is_active`,
 1 AS `last_seen`,
 1 AS `ip_address`,
 1 AS `firmware_version`,
 1 AS `minutes_since_last_seen`,
 1 AS `connection_status`,
 1 AS `records_today`,
 1 AS `records_24h`,
 1 AS `alerts_today`,
 1 AS `avg_data_quality`,
 1 AS `created_at`,
 1 AS `updated_at`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_device_status`
--

DROP TABLE IF EXISTS `v_device_status`;
/*!50001 DROP VIEW IF EXISTS `v_device_status`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_device_status` AS SELECT 
 1 AS `device_id`,
 1 AS `device_name`,
 1 AS `location`,
 1 AS `is_active`,
 1 AS `last_seen`,
 1 AS `patient_count`,
 1 AS `total_records`,
 1 AS `last_measurement`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_error_dashboard`
--

DROP TABLE IF EXISTS `v_error_dashboard`;
/*!50001 DROP VIEW IF EXISTS `v_error_dashboard`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_error_dashboard` AS SELECT 
 1 AS `error_date`,
 1 AS `error_hour`,
 1 AS `device_id`,
 1 AS `level`,
 1 AS `module`,
 1 AS `error_count`,
 1 AS `unique_errors`,
 1 AS `sample_messages`,
 1 AS `first_occurrence`,
 1 AS `last_occurrence`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_hourly_activity`
--

DROP TABLE IF EXISTS `v_hourly_activity`;
/*!50001 DROP VIEW IF EXISTS `v_hourly_activity`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_hourly_activity` AS SELECT 
 1 AS `device_id`,
 1 AS `activity_date`,
 1 AS `activity_hour`,
 1 AS `record_count`,
 1 AS `vital_types_collected`,
 1 AS `avg_quality`,
 1 AS `alerts_count`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_latest_vitals`
--

DROP TABLE IF EXISTS `v_latest_vitals`;
/*!50001 DROP VIEW IF EXISTS `v_latest_vitals`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_latest_vitals` AS SELECT 
 1 AS `patient_id`,
 1 AS `patient_name`,
 1 AS `device_id`,
 1 AS `device_name`,
 1 AS `timestamp`,
 1 AS `heart_rate`,
 1 AS `spo2`,
 1 AS `temperature`,
 1 AS `systolic_bp`,
 1 AS `diastolic_bp`,
 1 AS `mean_arterial_pressure`,
 1 AS `data_quality`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_patient_vitals_trend`
--

DROP TABLE IF EXISTS `v_patient_vitals_trend`;
/*!50001 DROP VIEW IF EXISTS `v_patient_vitals_trend`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_patient_vitals_trend` AS SELECT 
 1 AS `patient_id`,
 1 AS `trend_date`,
 1 AS `measurement_count`,
 1 AS `avg_heart_rate`,
 1 AS `min_heart_rate`,
 1 AS `max_heart_rate`,
 1 AS `stddev_heart_rate`,
 1 AS `avg_spo2`,
 1 AS `min_spo2`,
 1 AS `max_spo2`,
 1 AS `avg_temperature`,
 1 AS `min_temperature`,
 1 AS `max_temperature`,
 1 AS `avg_systolic`,
 1 AS `avg_diastolic`,
 1 AS `avg_map`,
 1 AS `has_heart_rate`,
 1 AS `has_spo2`,
 1 AS `has_temperature`,
 1 AS `has_blood_pressure`,
 1 AS `first_measurement`,
 1 AS `last_measurement`,
 1 AS `critical_alerts`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_sync_performance`
--

DROP TABLE IF EXISTS `v_sync_performance`;
/*!50001 DROP VIEW IF EXISTS `v_sync_performance`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_sync_performance` AS SELECT 
 1 AS `device_id`,
 1 AS `sync_date`,
 1 AS `sync_hour`,
 1 AS `total_records`,
 1 AS `synced_count`,
 1 AS `pending_count`,
 1 AS `conflict_count`,
 1 AS `success_rate_pct`,
 1 AS `avg_quality`,
 1 AS `min_quality`,
 1 AS `max_quality`,
 1 AS `has_heart_rate`,
 1 AS `has_spo2`,
 1 AS `has_temperature`,
 1 AS `has_blood_pressure`,
 1 AS `first_record_time`,
 1 AS `last_record_time`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_sync_queue_status`
--

DROP TABLE IF EXISTS `v_sync_queue_status`;
/*!50001 DROP VIEW IF EXISTS `v_sync_queue_status`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_sync_queue_status` AS SELECT 
 1 AS `device_id`,
 1 AS `sync_status`,
 1 AS `table_name`,
 1 AS `queue_count`,
 1 AS `max_age_minutes`,
 1 AS `avg_age_minutes`,
 1 AS `avg_attempts`,
 1 AS `max_attempts`,
 1 AS `oldest_entry`,
 1 AS `last_attempt`,
 1 AS `unique_errors`*/;
SET character_set_client = @saved_cs_client;

--
-- Temporary view structure for view `v_system_status`
--

DROP TABLE IF EXISTS `v_system_status`;
/*!50001 DROP VIEW IF EXISTS `v_system_status`*/;
SET @saved_cs_client     = @@character_set_client;
/*!50503 SET character_set_client = utf8mb4 */;
/*!50001 CREATE VIEW `v_system_status` AS SELECT 
 1 AS `metric_category`,
 1 AS `metric_name`,
 1 AS `metric_value`,
 1 AS `metric_unit`*/;
SET character_set_client = @saved_cs_client;

--
-- Final view structure for view `v_active_alerts`
--

/*!50001 DROP VIEW IF EXISTS `v_active_alerts`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_active_alerts` AS select `a`.`id` AS `id`,`a`.`patient_id` AS `patient_id`,`p`.`name` AS `patient_name`,`a`.`device_id` AS `device_id`,`d`.`device_name` AS `device_name`,`a`.`severity` AS `severity`,`a`.`vital_sign` AS `vital_sign`,`a`.`message` AS `message`,`a`.`current_value` AS `current_value`,`a`.`timestamp` AS `timestamp`,`a`.`acknowledged` AS `acknowledged` from ((`alerts` `a` join `patients` `p` on((`a`.`patient_id` = `p`.`patient_id`))) join `devices` `d` on((`a`.`device_id` = `d`.`device_id`))) where (`a`.`resolved` = false) order by `a`.`severity` desc,`a`.`timestamp` desc */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_alert_summary`
--

/*!50001 DROP VIEW IF EXISTS `v_alert_summary`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_alert_summary` AS select cast(`alerts`.`timestamp` as date) AS `alert_date`,`alerts`.`device_id` AS `device_id`,`alerts`.`vital_sign` AS `vital_sign`,`alerts`.`severity` AS `severity`,count(0) AS `total_alerts`,sum((case when (`alerts`.`acknowledged` = false) then 1 else 0 end)) AS `unacknowledged`,sum((case when (`alerts`.`resolved` = false) then 1 else 0 end)) AS `unresolved`,sum((case when (`alerts`.`notification_sent` = true) then 1 else 0 end)) AS `notifications_sent`,avg(timestampdiff(MINUTE,`alerts`.`timestamp`,`alerts`.`acknowledged_at`)) AS `avg_response_minutes`,max(timestampdiff(MINUTE,`alerts`.`timestamp`,`alerts`.`acknowledged_at`)) AS `max_response_minutes`,avg(timestampdiff(MINUTE,`alerts`.`timestamp`,`alerts`.`resolved_at`)) AS `avg_resolution_minutes`,avg(`alerts`.`current_value`) AS `avg_value`,min(`alerts`.`current_value`) AS `min_value`,max(`alerts`.`current_value`) AS `max_value`,min(`alerts`.`timestamp`) AS `first_alert`,max(`alerts`.`timestamp`) AS `last_alert` from `alerts` group by cast(`alerts`.`timestamp` as date),`alerts`.`device_id`,`alerts`.`vital_sign`,`alerts`.`severity` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_daily_summary`
--

/*!50001 DROP VIEW IF EXISTS `v_daily_summary`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_daily_summary` AS select curdate() AS `summary_date`,(select count(distinct `health_records`.`device_id`) from `health_records` where (cast(`health_records`.`timestamp` as date) = curdate())) AS `active_devices`,(select count(distinct `health_records`.`patient_id`) from `health_records` where (cast(`health_records`.`timestamp` as date) = curdate())) AS `unique_patients`,(select count(0) from `health_records` where (cast(`health_records`.`timestamp` as date) = curdate())) AS `total_records`,(select count(0) from `health_records` where ((cast(`health_records`.`timestamp` as date) = curdate()) and (`health_records`.`sync_status` = 'synced'))) AS `synced_records`,(select ((count(0) * 100.0) / nullif((select count(0) from `health_records` where (cast(`health_records`.`timestamp` as date) = curdate())),0))) AS `sync_success_rate`,(select avg(`health_records`.`data_quality`) from `health_records` where (cast(`health_records`.`timestamp` as date) = curdate())) AS `avg_data_quality`,(select count(0) from `health_records` where ((cast(`health_records`.`timestamp` as date) = curdate()) and (`health_records`.`data_quality` < 0.5))) AS `low_quality_count`,(select count(0) from `alerts` where (cast(`alerts`.`timestamp` as date) = curdate())) AS `total_alerts`,(select count(0) from `alerts` where ((cast(`alerts`.`timestamp` as date) = curdate()) and (`alerts`.`severity` = 'critical'))) AS `critical_alerts`,(select count(0) from `system_logs` where ((cast(`system_logs`.`timestamp` as date) = curdate()) and (`system_logs`.`level` in ('ERROR','CRITICAL')))) AS `error_count` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_data_quality`
--

/*!50001 DROP VIEW IF EXISTS `v_data_quality`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_data_quality` AS select `health_records`.`device_id` AS `device_id`,cast(`health_records`.`timestamp` as date) AS `measurement_date`,count(0) AS `total_measurements`,avg(`health_records`.`data_quality`) AS `avg_quality`,min(`health_records`.`data_quality`) AS `min_quality`,max(`health_records`.`data_quality`) AS `max_quality`,sum((case when (`health_records`.`data_quality` >= 0.9) then 1 else 0 end)) AS `excellent_count`,sum((case when ((`health_records`.`data_quality` >= 0.7) and (`health_records`.`data_quality` < 0.9)) then 1 else 0 end)) AS `good_count`,sum((case when ((`health_records`.`data_quality` >= 0.5) and (`health_records`.`data_quality` < 0.7)) then 1 else 0 end)) AS `fair_count`,sum((case when (`health_records`.`data_quality` < 0.5) then 1 else 0 end)) AS `poor_count`,sum((case when (`health_records`.`heart_rate` is null) then 1 else 0 end)) AS `missing_heart_rate`,sum((case when (`health_records`.`spo2` is null) then 1 else 0 end)) AS `missing_spo2`,sum((case when (`health_records`.`temperature` is null) then 1 else 0 end)) AS `missing_temperature`,sum((case when ((`health_records`.`systolic_bp` is null) or (`health_records`.`diastolic_bp` is null)) then 1 else 0 end)) AS `missing_bp`,(((count(0) - sum((case when (`health_records`.`heart_rate` is null) then 1 else 0 end))) * 100.0) / count(0)) AS `completeness_pct`,avg(`health_records`.`heart_rate`) AS `avg_heart_rate`,avg(`health_records`.`spo2`) AS `avg_spo2`,avg(`health_records`.`temperature`) AS `avg_temperature`,avg(`health_records`.`systolic_bp`) AS `avg_systolic_bp` from `health_records` group by `health_records`.`device_id`,cast(`health_records`.`timestamp` as date) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_device_health`
--

/*!50001 DROP VIEW IF EXISTS `v_device_health`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_device_health` AS select `d`.`device_id` AS `device_id`,`d`.`device_name` AS `device_name`,`d`.`location` AS `location`,`d`.`is_active` AS `is_active`,`d`.`last_seen` AS `last_seen`,`d`.`ip_address` AS `ip_address`,`d`.`firmware_version` AS `firmware_version`,timestampdiff(MINUTE,`d`.`last_seen`,now()) AS `minutes_since_last_seen`,(case when (timestampdiff(MINUTE,`d`.`last_seen`,now()) <= 5) then 'online' when (timestampdiff(MINUTE,`d`.`last_seen`,now()) <= 30) then 'idle' else 'offline' end) AS `connection_status`,(select count(0) from `health_records` where ((`health_records`.`device_id` = `d`.`device_id`) and (cast(`health_records`.`timestamp` as date) = curdate()))) AS `records_today`,(select count(0) from `health_records` where ((`health_records`.`device_id` = `d`.`device_id`) and (`health_records`.`timestamp` >= (now() - interval 24 hour)))) AS `records_24h`,(select count(0) from `alerts` where ((`alerts`.`device_id` = `d`.`device_id`) and (cast(`alerts`.`timestamp` as date) = curdate()))) AS `alerts_today`,(select avg(`health_records`.`data_quality`) from `health_records` where ((`health_records`.`device_id` = `d`.`device_id`) and (`health_records`.`timestamp` >= (now() - interval 24 hour)))) AS `avg_data_quality`,`d`.`created_at` AS `created_at`,`d`.`updated_at` AS `updated_at` from `devices` `d` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_device_status`
--

/*!50001 DROP VIEW IF EXISTS `v_device_status`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_device_status` AS select `d`.`device_id` AS `device_id`,`d`.`device_name` AS `device_name`,`d`.`location` AS `location`,`d`.`is_active` AS `is_active`,`d`.`last_seen` AS `last_seen`,count(distinct `p`.`patient_id`) AS `patient_count`,(select count(0) from `health_records` where (`health_records`.`device_id` = `d`.`device_id`)) AS `total_records`,(select max(`health_records`.`timestamp`) from `health_records` where (`health_records`.`device_id` = `d`.`device_id`)) AS `last_measurement` from (`devices` `d` left join `patients` `p` on((`d`.`device_id` = `p`.`device_id`))) group by `d`.`device_id`,`d`.`device_name`,`d`.`location`,`d`.`is_active`,`d`.`last_seen` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_error_dashboard`
--

/*!50001 DROP VIEW IF EXISTS `v_error_dashboard`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_error_dashboard` AS select cast(`system_logs`.`timestamp` as date) AS `error_date`,hour(`system_logs`.`timestamp`) AS `error_hour`,`system_logs`.`device_id` AS `device_id`,`system_logs`.`level` AS `level`,`system_logs`.`module` AS `module`,count(0) AS `error_count`,count(distinct `system_logs`.`message`) AS `unique_errors`,group_concat(distinct substr(`system_logs`.`message`,1,100) order by `system_logs`.`timestamp` DESC separator ' | ') AS `sample_messages`,min(`system_logs`.`timestamp`) AS `first_occurrence`,max(`system_logs`.`timestamp`) AS `last_occurrence` from `system_logs` where (`system_logs`.`level` in ('ERROR','CRITICAL')) group by cast(`system_logs`.`timestamp` as date),hour(`system_logs`.`timestamp`),`system_logs`.`device_id`,`system_logs`.`level`,`system_logs`.`module` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_hourly_activity`
--

/*!50001 DROP VIEW IF EXISTS `v_hourly_activity`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_hourly_activity` AS select `health_records`.`device_id` AS `device_id`,cast(`health_records`.`timestamp` as date) AS `activity_date`,hour(`health_records`.`timestamp`) AS `activity_hour`,count(0) AS `record_count`,(((count(distinct (case when (`health_records`.`heart_rate` is not null) then 'heart_rate' end)) + count(distinct (case when (`health_records`.`spo2` is not null) then 'spo2' end))) + count(distinct (case when (`health_records`.`temperature` is not null) then 'temperature' end))) + count(distinct (case when (`health_records`.`systolic_bp` is not null) then 'bp' end))) AS `vital_types_collected`,avg(`health_records`.`data_quality`) AS `avg_quality`,(select count(0) from `alerts` where ((`alerts`.`device_id` = `health_records`.`device_id`) and (cast(`alerts`.`timestamp` as date) = cast(`health_records`.`timestamp` as date)) and (hour(`alerts`.`timestamp`) = hour(`health_records`.`timestamp`)))) AS `alerts_count` from `health_records` group by `health_records`.`device_id`,cast(`health_records`.`timestamp` as date),hour(`health_records`.`timestamp`) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_latest_vitals`
--

/*!50001 DROP VIEW IF EXISTS `v_latest_vitals`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_latest_vitals` AS select `p`.`patient_id` AS `patient_id`,`p`.`name` AS `patient_name`,`d`.`device_id` AS `device_id`,`d`.`device_name` AS `device_name`,`hr`.`timestamp` AS `timestamp`,`hr`.`heart_rate` AS `heart_rate`,`hr`.`spo2` AS `spo2`,`hr`.`temperature` AS `temperature`,`hr`.`systolic_bp` AS `systolic_bp`,`hr`.`diastolic_bp` AS `diastolic_bp`,`hr`.`mean_arterial_pressure` AS `mean_arterial_pressure`,`hr`.`data_quality` AS `data_quality` from ((`patients` `p` left join `devices` `d` on((`p`.`device_id` = `d`.`device_id`))) left join `health_records` `hr` on((`p`.`patient_id` = `hr`.`patient_id`))) where (`hr`.`id` = (select `health_records`.`id` from `health_records` where (`health_records`.`patient_id` = `p`.`patient_id`) order by `health_records`.`timestamp` desc limit 1)) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_patient_vitals_trend`
--

/*!50001 DROP VIEW IF EXISTS `v_patient_vitals_trend`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_patient_vitals_trend` AS select `health_records`.`patient_id` AS `patient_id`,cast(`health_records`.`timestamp` as date) AS `trend_date`,count(0) AS `measurement_count`,avg(`health_records`.`heart_rate`) AS `avg_heart_rate`,min(`health_records`.`heart_rate`) AS `min_heart_rate`,max(`health_records`.`heart_rate`) AS `max_heart_rate`,std(`health_records`.`heart_rate`) AS `stddev_heart_rate`,avg(`health_records`.`spo2`) AS `avg_spo2`,min(`health_records`.`spo2`) AS `min_spo2`,max(`health_records`.`spo2`) AS `max_spo2`,avg(`health_records`.`temperature`) AS `avg_temperature`,min(`health_records`.`temperature`) AS `min_temperature`,max(`health_records`.`temperature`) AS `max_temperature`,avg(`health_records`.`systolic_bp`) AS `avg_systolic`,avg(`health_records`.`diastolic_bp`) AS `avg_diastolic`,avg(`health_records`.`mean_arterial_pressure`) AS `avg_map`,sum((case when (`health_records`.`heart_rate` is not null) then 1 else 0 end)) AS `has_heart_rate`,sum((case when (`health_records`.`spo2` is not null) then 1 else 0 end)) AS `has_spo2`,sum((case when (`health_records`.`temperature` is not null) then 1 else 0 end)) AS `has_temperature`,sum((case when (`health_records`.`systolic_bp` is not null) then 1 else 0 end)) AS `has_blood_pressure`,min(`health_records`.`timestamp`) AS `first_measurement`,max(`health_records`.`timestamp`) AS `last_measurement`,(select count(0) from `alerts` where ((`alerts`.`patient_id` = `health_records`.`patient_id`) and (cast(`alerts`.`timestamp` as date) = cast(`health_records`.`timestamp` as date)) and (`alerts`.`severity` = 'critical'))) AS `critical_alerts` from `health_records` group by `health_records`.`patient_id`,cast(`health_records`.`timestamp` as date) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_sync_performance`
--

/*!50001 DROP VIEW IF EXISTS `v_sync_performance`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_sync_performance` AS select `health_records`.`device_id` AS `device_id`,cast(`health_records`.`synced_at` as date) AS `sync_date`,hour(`health_records`.`synced_at`) AS `sync_hour`,count(0) AS `total_records`,sum((case when (`health_records`.`sync_status` = 'synced') then 1 else 0 end)) AS `synced_count`,sum((case when (`health_records`.`sync_status` = 'pending') then 1 else 0 end)) AS `pending_count`,sum((case when (`health_records`.`sync_status` = 'failed') then 1 else 0 end)) AS `conflict_count`,((sum((case when (`health_records`.`sync_status` = 'synced') then 1 else 0 end)) * 100.0) / count(0)) AS `success_rate_pct`,avg(`health_records`.`data_quality`) AS `avg_quality`,min(`health_records`.`data_quality`) AS `min_quality`,max(`health_records`.`data_quality`) AS `max_quality`,sum((case when (`health_records`.`heart_rate` is not null) then 1 else 0 end)) AS `has_heart_rate`,sum((case when (`health_records`.`spo2` is not null) then 1 else 0 end)) AS `has_spo2`,sum((case when (`health_records`.`temperature` is not null) then 1 else 0 end)) AS `has_temperature`,sum((case when (`health_records`.`systolic_bp` is not null) then 1 else 0 end)) AS `has_blood_pressure`,min(`health_records`.`timestamp`) AS `first_record_time`,max(`health_records`.`timestamp`) AS `last_record_time` from `health_records` where (`health_records`.`synced_at` is not null) group by `health_records`.`device_id`,cast(`health_records`.`synced_at` as date),hour(`health_records`.`synced_at`) */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_sync_queue_status`
--

/*!50001 DROP VIEW IF EXISTS `v_sync_queue_status`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_sync_queue_status` AS select `sync_queue`.`device_id` AS `device_id`,`sync_queue`.`sync_status` AS `sync_status`,`sync_queue`.`table_name` AS `table_name`,count(0) AS `queue_count`,max(timestampdiff(MINUTE,`sync_queue`.`created_at`,now())) AS `max_age_minutes`,avg(timestampdiff(MINUTE,`sync_queue`.`created_at`,now())) AS `avg_age_minutes`,avg(`sync_queue`.`sync_attempts`) AS `avg_attempts`,max(`sync_queue`.`sync_attempts`) AS `max_attempts`,min(`sync_queue`.`created_at`) AS `oldest_entry`,max(`sync_queue`.`last_sync_attempt`) AS `last_attempt`,count(distinct `sync_queue`.`error_message`) AS `unique_errors` from `sync_queue` group by `sync_queue`.`device_id`,`sync_queue`.`sync_status`,`sync_queue`.`table_name` */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;

--
-- Final view structure for view `v_system_status`
--

/*!50001 DROP VIEW IF EXISTS `v_system_status`*/;
/*!50001 SET @saved_cs_client          = @@character_set_client */;
/*!50001 SET @saved_cs_results         = @@character_set_results */;
/*!50001 SET @saved_col_connection     = @@collation_connection */;
/*!50001 SET character_set_client      = utf8mb4 */;
/*!50001 SET character_set_results     = utf8mb4 */;
/*!50001 SET collation_connection      = utf8mb4_0900_ai_ci */;
/*!50001 CREATE ALGORITHM=UNDEFINED */
/*!50013 DEFINER=`admin`@`%` SQL SECURITY DEFINER */
/*!50001 VIEW `v_system_status` AS select 'total_devices' AS `metric_category`,'count' AS `metric_name`,count(0) AS `metric_value`,'devices' AS `metric_unit` from `devices` union all select 'active_devices' AS `metric_category`,'count' AS `metric_name`,count(0) AS `metric_value`,'devices' AS `metric_unit` from `devices` where (`devices`.`is_active` = true) union all select 'total_patients' AS `metric_category`,'count' AS `metric_name`,count(0) AS `metric_value`,'patients' AS `metric_unit` from `patients` union all select 'total_health_records' AS `metric_category`,'count' AS `metric_name`,count(0) AS `metric_value`,'records' AS `metric_unit` from `health_records` union all select 'active_alerts' AS `metric_category`,'count' AS `metric_name`,count(0) AS `metric_value`,'alerts' AS `metric_unit` from `alerts` where (`alerts`.`resolved` = false) union all select 'pending_sync_items' AS `metric_category`,'count' AS `metric_name`,count(0) AS `metric_value`,'items' AS `metric_unit` from `sync_queue` where (`sync_queue`.`sync_status` = 'pending') */;
/*!50001 SET character_set_client      = @saved_cs_client */;
/*!50001 SET character_set_results     = @saved_cs_results */;
/*!50001 SET collation_connection      = @saved_col_connection */;
SET @@SESSION.SQL_LOG_BIN = @MYSQLDUMP_TEMP_LOG_BIN;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-12-30 14:13:13
