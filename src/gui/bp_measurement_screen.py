"""
Blood Pressure Measurement Screen
Màn hình đo chi tiết cho huyết áp (oscillometric method)
"""
import logging
import time
from typing import Optional
from kivy.uix.screenmanager import Screen
from kivy.clock import Clock
from kivy.metrics import dp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel, MDIcon
from kivymd.uix.progressbar import MDProgressBar
from kivymd.uix.toolbar import MDTopAppBar

from src.sensors.blood_pressure_sensor import BPState, BloodPressureMeasurement
from src.utils.tts_manager import ScenarioID

# Medical-themed colors (same as temperature_screen.py)
MED_BG_COLOR = (0.02, 0.18, 0.27, 1)
MED_CARD_BG = (0.07, 0.26, 0.36, 0.98)
MED_CARD_ACCENT = (0.0, 0.68, 0.57, 1)
MED_PRIMARY = (0.12, 0.55, 0.76, 1)
MED_WARNING = (0.96, 0.4, 0.3, 1)
TEXT_PRIMARY = (1, 1, 1, 1)
TEXT_MUTED = (0.78, 0.88, 0.95, 1)


class BPMeasurementScreen(Screen):
    """
    Màn hình đo chi tiết huyết áp theo phương pháp oscillometric
    
    Features:
    - Real-time pressure display during inflate/deflate
    - State-based progress indicators
    - SYS/DIA/MAP/HR results with AHA color coding
    - Safety warnings and TTS feedback
    """
    
    def __init__(self, app_instance, **kwargs):
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        
        # Measurement state
        self.measuring = False
        self.current_state = BPState.IDLE
        self.current_pressure = 0.0
        self.last_result: Optional[BloodPressureMeasurement] = None
        
        # UI update scheduler
        self.update_event = None
        
        # TTS state tracking (announce only once per state transition)
        self._inflate_announced = False
        self._deflate_announced = False
        
        self._build_layout()
    
    def _build_layout(self):
        """Build BP measurement layout - optimized for 480x320"""
        main_layout = MDBoxLayout(
            orientation='vertical',
            md_bg_color=MED_BG_COLOR,
            spacing=dp(5),
            padding=dp(5)
        )
        
        # Top bar: Title + Back button (compact)
        self._create_top_bar(main_layout)
        
        # Main content area
        content = MDBoxLayout(
            orientation='vertical',
            spacing=dp(5)
        )
        
        # Row 1: Pressure display + Status
        self._create_status_row(content)
        
        # Row 2: Results grid (2x2)
        self._create_results_grid(content)
        
        # Row 3: Progress bar
        self._create_progress_panel(content)
        
        main_layout.add_widget(content)
        
        # Bottom: Control buttons
        self._create_control_buttons(main_layout)
        
        self.add_widget(main_layout)
    
    def _create_top_bar(self, parent):
        """Create header toolbar (same style as temperature_screen)"""
        toolbar = MDTopAppBar(
            title='ĐO HUYẾT ÁP',
            elevation=0,
            md_bg_color=MED_PRIMARY,
            specific_text_color=TEXT_PRIMARY,
            left_action_items=[["arrow-left", lambda _: self._on_back_pressed()]],
            size_hint_y=None,
            height=dp(30),
        )
        parent.add_widget(toolbar)
    
    def _on_back_pressed(self):
        """Handle back button press"""
        if self.measuring:
            self._stop_measurement()
        self.app_instance.navigate_to_screen('dashboard')
    
    def _create_status_row(self, parent):
        """Create compact status row: Pressure | State"""
        row = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(5),
            size_hint_y=None,
            height=dp(70)
        )
        
        # Pressure display (left)
        pressure_card = MDCard(
            orientation='vertical',
            md_bg_color=MED_CARD_BG,
            padding=dp(8),
            radius=[dp(8)],
            size_hint_x=0.5
        )
        
        pressure_card.add_widget(MDLabel(
            text="Áp suất",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            size_hint_y=0.3
        ))
        
        self.pressure_label = MDLabel(
            text="0",
            font_style="H5",
            theme_text_color="Custom",
            text_color=MED_CARD_ACCENT,
            halign="center",
            bold=True,
            size_hint_y=0.7
        )
        pressure_card.add_widget(self.pressure_label)
        row.add_widget(pressure_card)
        
        # State display (right)
        state_card = MDCard(
            orientation='vertical',
            md_bg_color=MED_CARD_BG,
            padding=dp(8),
            radius=[dp(8)],
            size_hint_x=0.5
        )
        
        state_card.add_widget(MDLabel(
            text="Trạng thái",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            halign="center",
            size_hint_y=0.3
        ))
        
        self.state_label = MDLabel(
            text="Chờ đo",
            font_style="Body1",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            halign="center",
            size_hint_y=0.7
        )
        state_card.add_widget(self.state_label)
        row.add_widget(state_card)
        
        parent.add_widget(row)
    
    def _create_results_grid(self, parent):
        """Create compact 2x2 grid for SYS/DIA/MAP/HR"""
        results_card = MDCard(
            orientation='vertical',
            md_bg_color=MED_CARD_BG,
            padding=dp(8),
            radius=[dp(8)],
            size_hint_y=None,
            height=dp(100)
        )
        
        # Title
        results_card.add_widget(MDLabel(
            text="Kết quả",
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            size_hint_y=0.15
        ))
        
        # 2x2 Grid (compact)
        grid = MDBoxLayout(orientation='vertical', spacing=dp(3), size_hint_y=0.85)
        
        # Row 1: SYS | DIA
        row1 = MDBoxLayout(orientation='horizontal', spacing=dp(5))
        row1.add_widget(self._create_compact_result("SYS", "sys_label"))
        row1.add_widget(self._create_compact_result("DIA", "dia_label"))
        grid.add_widget(row1)
        
        # Row 2: MAP | HR
        row2 = MDBoxLayout(orientation='horizontal', spacing=dp(5))
        row2.add_widget(self._create_compact_result("MAP", "map_label"))
        row2.add_widget(self._create_compact_result("HR", "hr_label"))
        grid.add_widget(row2)
        
        results_card.add_widget(grid)
        parent.add_widget(results_card)
    
    def _create_compact_result(self, label_text, attr_name):
        """Create compact result item"""
        container = MDBoxLayout(
            orientation='horizontal',
            padding=dp(5),
            spacing=dp(5)
        )
        
        # Label
        container.add_widget(MDLabel(
            text=label_text,
            font_style="Caption",
            theme_text_color="Custom",
            text_color=TEXT_MUTED,
            size_hint_x=0.3,
            halign="left"
        ))
        
        # Value
        value_label = MDLabel(
            text="--",
            font_style="H6",
            theme_text_color="Custom",
            text_color=TEXT_PRIMARY,
            size_hint_x=0.7,
            bold=True,
            halign="right"
        )
        setattr(self, attr_name, value_label)
        container.add_widget(value_label)
        
        return container
    
    def _create_progress_panel(self, parent):
        """Create compact progress bar"""
        progress_card = MDCard(
            orientation='vertical',
            md_bg_color=MED_CARD_BG,
            padding=dp(8),
            radius=[dp(8)],
            size_hint_y=None,
            height=dp(40)
        )
        
        self.progress_bar = MDProgressBar(
            size_hint_y=1.0,
            color=MED_CARD_ACCENT
        )
        progress_card.add_widget(self.progress_bar)
        parent.add_widget(progress_card)
    
    def _create_control_buttons(self, parent):
        """Create compact control buttons"""
        button_layout = MDBoxLayout(
            orientation='horizontal',
            spacing=dp(5),
            size_hint_y=None,
            height=dp(45),
            padding=[0, dp(5), 0, dp(5)]
        )
        
        self.start_btn = MDRaisedButton(
            text="Bắt đầu",
            md_bg_color=MED_PRIMARY,
            on_press=self._start_measurement,
            size_hint_x=0.4
        )
        button_layout.add_widget(self.start_btn)
        
        self.stop_btn = MDRaisedButton(
            text="Dừng",
            md_bg_color=MED_WARNING,
            on_press=self._stop_measurement,
            size_hint_x=0.3,
            disabled=True
        )
        button_layout.add_widget(self.stop_btn)
        
        self.save_btn = MDRaisedButton(
            text="Lưu",
            md_bg_color=MED_CARD_ACCENT,
            on_press=self._save_measurement,
            size_hint_x=0.3,
            disabled=True
        )
        button_layout.add_widget(self.save_btn)
        
        parent.add_widget(button_layout)
    
    def _start_measurement(self, *args):
        """Start BP measurement"""
        try:
            bp_sensor = self.app_instance.sensors.get('BloodPressure')
            if not bp_sensor:
                self.logger.error("BloodPressure sensor not available")
                self._speak_scenario(ScenarioID.SENSOR_FAILURE)
                return
            
            if not self.app_instance.ensure_sensor_started('BloodPressure'):
                self.logger.error("Failed to start sensor")
                return
            
            self.measuring = True
            self.last_result = None
            
            # Update UI
            self.start_btn.disabled = True
            self.stop_btn.disabled = False
            self.save_btn.disabled = True
            self.state_label.text = "Đang chuẩn bị..."
            self.progress_bar.value = 0
            
            # Clear results
            self.sys_label.text = "--"
            self.dia_label.text = "--"
            self.map_label.text = "--"
            self.hr_label.text = "--"
            
            # Reset TTS announce flags
            self._inflate_announced = False
            self._deflate_announced = False
            
            # Start measurement
            bp_sensor.start_measurement(callback=self._on_measurement_complete)
            
            # Start UI updates (5Hz)
            self.update_event = Clock.schedule_interval(self._update_ui, 0.2)
            
            # TTS will be announced when sensor enters INFLATING state (in _update_ui)
            
            self.logger.info("BP measurement started")
            
        except Exception as e:
            self.logger.error(f"Error starting: {e}")
            self._reset_ui()
    
    def _stop_measurement(self, *args):
        """Emergency stop"""
        try:
            bp_sensor = self.app_instance.sensors.get('BloodPressure')
            if bp_sensor and hasattr(bp_sensor, 'stop_measurement'):
                bp_sensor.stop_measurement()
            
            self._reset_ui()
            self._speak_scenario(ScenarioID.SAFETY_EMERGENCY_RELEASE)
            self.logger.info("BP measurement stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping: {e}")
    
    def _update_ui(self, dt):
        """Update UI with real-time data (called at 5Hz)"""
        try:
            bp_sensor = self.app_instance.sensors.get('BloodPressure')
            if not bp_sensor:
                return
            
            # Get current state from sensor (use method, not property)
            self.current_state = bp_sensor.get_state()
            
            # Get current pressure from sensor buffer (fallback if property doesn't exist)
            try:
                # Try to get pressure from buffer (last reading)
                if hasattr(bp_sensor, 'pressure_buffer') and len(bp_sensor.pressure_buffer) > 0:
                    self.current_pressure = bp_sensor.pressure_buffer[-1]
                else:
                    self.current_pressure = 0.0
            except (AttributeError, IndexError):
                self.current_pressure = 0.0
            
            # Update pressure display
            self.pressure_label.text = f"{self.current_pressure:.0f}"
            
            # Update state and progress
            state_map = {
                BPState.IDLE: ("Chờ đo", 0),
                BPState.INITIALIZING: ("Khởi động", 5),
                BPState.INFLATING: ("Đang bơm", 30),
                BPState.DEFLATING: ("Đang đo", 65),
                BPState.ANALYZING: ("Phân tích", 90),
                BPState.COMPLETED: ("Hoàn thành", 100),
                BPState.ERROR: ("Lỗi", 0),
                BPState.EMERGENCY_DEFLATE: ("Xả khẩn", 0)
            }
            
            state_text, progress = state_map.get(self.current_state, ("Không rõ", 0))
            self.state_label.text = state_text
            self.progress_bar.value = progress
            
            # TTS feedback at state transitions (announce only once per state)
            if self.current_state == BPState.INFLATING:
                if not self._inflate_announced:
                    self._speak_scenario(ScenarioID.BP_INFLATE)
                    self._inflate_announced = True
                    self.logger.debug("TTS: BP_INFLATE announced")
            
            if self.current_state == BPState.DEFLATING:
                if not self._deflate_announced:
                    self._speak_scenario(ScenarioID.BP_DEFLATE)
                    self._deflate_announced = True
                    self.logger.debug("TTS: BP_DEFLATE announced")
            
        except Exception as e:
            self.logger.error(f"Error updating UI: {e}")
    
    def _on_measurement_complete(self, result: BloodPressureMeasurement):
        """Callback when measurement completes"""
        try:
            # Stop UI update loop
            if self.update_event:
                self.update_event.cancel()
                self.update_event = None
            
            self.measuring = False
            self.last_result = result
            
            # Display results
            self._display_results(result)
            
            # TTS announcement
            sys_int = int(round(result.systolic))
            dia_int = int(round(result.diastolic))
            self._speak_scenario(ScenarioID.BP_RESULT, sys=sys_int, dia=dia_int)
            
            # Update UI state
            self.start_btn.disabled = False
            self.start_btn.text = "Đo lại"
            self.stop_btn.disabled = True
            self.save_btn.disabled = False
            self.state_label.text = "Hoàn thành"
            self.progress_bar.value = 100
            self.pressure_label.text = "0"
            
            self.logger.info(
                f"Complete: SYS={result.systolic:.0f} DIA={result.diastolic:.0f} "
                f"MAP={result.map_value:.0f} HR={result.heart_rate:.0f} "
                f"Quality={result.quality} Confidence={result.confidence:.2f}"
            )
            
        except Exception as e:
            self.logger.error(f"Error handling completion: {e}")
            self._reset_ui()
    
    def _display_results(self, result: BloodPressureMeasurement):
        """Display results with AHA color coding"""
        try:
            self.sys_label.text = f"{result.systolic:.0f}"
            self.dia_label.text = f"{result.diastolic:.0f}"
            self.map_label.text = f"{result.map_value:.0f}"
            self.hr_label.text = f"{result.heart_rate:.0f}" if result.heart_rate else "--"
            
            # AHA color coding
            sys_val = result.systolic
            dia_val = result.diastolic
            
            if sys_val < 90 or dia_val < 60:
                color = (0.3, 0.6, 1.0, 1)  # Blue - Low
            elif sys_val < 120 and dia_val < 80:
                color = (0.2, 0.8, 0.2, 1)  # Green - Normal
            elif sys_val < 130 and dia_val < 80:
                color = (1.0, 0.8, 0.0, 1)  # Yellow - Elevated
            elif sys_val < 140 or dia_val < 90:
                color = (1.0, 0.6, 0.0, 1)  # Orange - Stage 1
            elif sys_val < 180 and dia_val < 120:
                color = (1.0, 0.3, 0.0, 1)  # Red-Orange - Stage 2
            else:
                color = (1.0, 0.0, 0.0, 1)  # Red - Crisis
            
            self.sys_label.text_color = color
            self.dia_label.text_color = color
            
        except Exception as e:
            self.logger.error(f"Error displaying results: {e}")
    
    def _save_measurement(self, *args):
        """Save measurement to database"""
        try:
            if not self.last_result:
                self.logger.warning("No measurement to save")
                return
            
            measurement_data = {
                'timestamp': time.time(),
                'systolic': self.last_result.systolic,
                'diastolic': self.last_result.diastolic,
                'map_value': self.last_result.map_value,
                'heart_rate': self.last_result.heart_rate,
                'measurement_type': 'blood_pressure',
                'quality': self.last_result.quality,
                'confidence': self.last_result.confidence
            }
            
            self.app_instance.save_measurement_to_database(measurement_data)
            
            self.app_instance.current_data['blood_pressure_systolic'] = self.last_result.systolic
            self.app_instance.current_data['blood_pressure_diastolic'] = self.last_result.diastolic
            
            self.save_btn.disabled = True
            self.logger.info("Measurement saved")
            
        except Exception as e:
            self.logger.error(f"Error saving: {e}")
    
    def _reset_ui(self):
        """Reset UI to idle state"""
        self.measuring = False
        self.current_state = BPState.IDLE
        self.current_pressure = 0.0
        
        if self.update_event:
            self.update_event.cancel()
            self.update_event = None
        
        self.start_btn.disabled = False
        self.start_btn.text = "Bắt đầu"
        self.stop_btn.disabled = True
        self.save_btn.disabled = True
        
        self.state_label.text = "Chờ đo"
        self.progress_bar.value = 0
        self.pressure_label.text = "0"
        
        # Clear results
        self.sys_label.text = "--"
        self.dia_label.text = "--"
        self.map_label.text = "--"
        self.hr_label.text = "--"
        
        # Reset TTS announce flags
        self._inflate_announced = False
        self._deflate_announced = False
    
    def _speak_scenario(self, scenario: ScenarioID, **kwargs):
        """Speak TTS scenario"""
        try:
            if hasattr(self.app_instance, '_speak_scenario'):
                self.app_instance._speak_scenario(scenario, **kwargs)
        except Exception as e:
            self.logger.debug(f"TTS not available: {e}")
    
    def on_enter(self):
        """Called when screen entered"""
        self._reset_ui()
        self.logger.info("Entered BP measurement screen")
    
    def on_leave(self):
        """Called when screen left"""
        if self.measuring:
            self._stop_measurement()
        
        if self.update_event:
            self.update_event.cancel()
            self.update_event = None
        
        self.logger.info("Left BP measurement screen")
