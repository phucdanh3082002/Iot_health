"""
Blood Pressure Measurement Screen
Screen cho quá trình đo huyết áp
"""

from typing import Dict, Any, Optional
import logging
import time
import subprocess
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.progressbar import ProgressBar
from kivy.clock import Clock
from kivy.graphics import Color, Rectangle


class BPMeasurementScreen(Screen):
    """
    Screen cho quá trình đo huyết áp tự động
    """
    
    def __init__(self, app_instance, **kwargs):
        """
        Initialize BP measurement screen
        
        Args:
            app_instance: Reference to main application
        """
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        
        # Measurement state
        self.measurement_state = 'idle'  # idle, preparing, inflating, measuring, deflating, complete
        self.measurement_timer = None
        self.measurement_progress = 0.0
        self.current_pressure = 0.0
        self.measurement_start_time = 0
        self.estimated_duration = 60  # seconds
        
        # Results
        self.systolic_result = 0
        self.diastolic_result = 0
        
        self._build_layout()
    
    def _build_layout(self):
        """Build BP measurement layout"""
        # Main container with background
        main_layout = BoxLayout(orientation='vertical', spacing=10, padding=15)
        
        with main_layout.canvas.before:
            Color(0.1, 0.1, 0.15, 1)  # Dark blue background
            self.bg_rect = Rectangle(size=main_layout.size, pos=main_layout.pos)
        main_layout.bind(size=self._update_bg_rect, pos=self._update_bg_rect)
        
        # Header
        self._create_header(main_layout)
        
        # Main content area
        content_area = BoxLayout(orientation='vertical', size_hint_y=0.8, spacing=15)
        
        # Instruction panel
        self._create_instruction_panel(content_area)
        
        # Progress panel
        self._create_progress_panel(content_area)
        
        # Pressure display
        self._create_pressure_display(content_area)
        
        # Result panel
        self._create_result_panel(content_area)
        
        main_layout.add_widget(content_area)
        
        # Control buttons
        self._create_control_panel(main_layout)
        
        self.add_widget(main_layout)
    
    def _update_bg_rect(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size
    
    def _create_header(self, parent):
        """Create header with title and back button"""
        header = BoxLayout(orientation='horizontal', size_hint_y=0.1, spacing=10)
        
        # Title
        title = Label(
            text='ĐO HUYẾT ÁP',
            font_size='20sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_x=0.8
        )
        header.add_widget(title)
        
        # Back button
        back_btn = Button(
            text='← Quay lại',
            font_size='14sp',
            size_hint_x=0.2,
            background_color=(0.6, 0.6, 0.6, 1)
        )
        back_btn.bind(on_press=self._on_back_pressed)
        header.add_widget(back_btn)
        
        parent.add_widget(header)
    
    def _create_instruction_panel(self, parent):
        """Create instruction panel"""
        instruction_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.25,
            spacing=5
        )
        
        # Background
        with instruction_container.canvas.before:
            Color(0.2, 0.2, 0.3, 1)
            self.instruction_rect = Rectangle(
                size=instruction_container.size,
                pos=instruction_container.pos
            )
        instruction_container.bind(
            size=self._update_instruction_rect,
            pos=self._update_instruction_rect
        )
        
        # Instruction title
        instruction_title = Label(
            text='HƯỚNG DẪN',
            font_size='16sp',
            bold=True,
            size_hint_y=0.3,
            color=(0.9, 0.9, 0.9, 1)
        )
        instruction_container.add_widget(instruction_title)
        
        # Instruction text
        self.instruction_label = Label(
            text='Ngồi thẳng, đặt cánh tay lên bàn\nThư giãn và không nói chuyện\nBấm "Bắt đầu đo" để tiến hành',
            font_size='12sp',
            size_hint_y=0.7,
            color=(0.8, 0.8, 0.8, 1),
            halign='center'
        )
        self.instruction_label.bind(size=self.instruction_label.setter('text_size'))
        instruction_container.add_widget(self.instruction_label)
        
        parent.add_widget(instruction_container)
    
    def _update_instruction_rect(self, instance, value):
        self.instruction_rect.pos = instance.pos
        self.instruction_rect.size = instance.size
    
    def _create_progress_panel(self, parent):
        """Create progress indicator panel"""
        progress_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.2,
            spacing=10
        )
        
        # Progress label
        self.progress_label = Label(
            text='Sẵn sàng đo',
            font_size='14sp',
            size_hint_y=0.4,
            color=(1, 1, 1, 1)
        )
        progress_container.add_widget(self.progress_label)
        
        # Progress bar
        self.progress_bar = ProgressBar(
            max=100,
            value=0,
            size_hint_y=0.6
        )
        progress_container.add_widget(self.progress_bar)
        
        parent.add_widget(progress_container)
    
    def _create_pressure_display(self, parent):
        """Create real-time pressure display"""
        pressure_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.25,
            spacing=5
        )
        
        # Background
        with pressure_container.canvas.before:
            Color(0.15, 0.15, 0.2, 1)
            self.pressure_rect = Rectangle(
                size=pressure_container.size,
                pos=pressure_container.pos
            )
        pressure_container.bind(
            size=self._update_pressure_rect,
            pos=self._update_pressure_rect
        )
        
        # Pressure label
        pressure_title = Label(
            text='ÁP SUẤT HIỆN TẠI',
            font_size='12sp',
            size_hint_y=0.3,
            color=(0.7, 0.7, 0.7, 1)
        )
        pressure_container.add_widget(pressure_title)
        
        # Pressure value
        self.pressure_value_label = Label(
            text='0 mmHg',
            font_size='24sp',
            bold=True,
            size_hint_y=0.7,
            color=(0, 0.8, 1, 1)  # Cyan color
        )
        pressure_container.add_widget(self.pressure_value_label)
        
        parent.add_widget(pressure_container)
    
    def _update_pressure_rect(self, instance, value):
        self.pressure_rect.pos = instance.pos
        self.pressure_rect.size = instance.size
    
    def _create_result_panel(self, parent):
        """Create result display panel"""
        result_container = BoxLayout(
            orientation='vertical',
            size_hint_y=0.3,
            spacing=5
        )
        
        # Background
        with result_container.canvas.before:
            Color(0.1, 0.3, 0.1, 1)  # Dark green background
            self.result_rect = Rectangle(
                size=result_container.size,
                pos=result_container.pos
            )
        result_container.bind(
            size=self._update_result_rect,
            pos=self._update_result_rect
        )
        
        # Result title
        result_title = Label(
            text='KẾT QUẢ ĐO',
            font_size='14sp',
            bold=True,
            size_hint_y=0.2,
            color=(0.9, 0.9, 0.9, 1)
        )
        result_container.add_widget(result_title)
        
        # BP values
        bp_display = BoxLayout(orientation='horizontal', size_hint_y=0.6)
        
        # Systolic
        systolic_layout = BoxLayout(orientation='vertical')
        systolic_title = Label(
            text='Tâm thu',
            font_size='12sp',
            size_hint_y=0.3,
            color=(0.8, 0.8, 0.8, 1)
        )
        self.systolic_label = Label(
            text='--',
            font_size='32sp',
            bold=True,
            size_hint_y=0.7,
            color=(1, 1, 1, 1)
        )
        systolic_layout.add_widget(systolic_title)
        systolic_layout.add_widget(self.systolic_label)
        bp_display.add_widget(systolic_layout)
        
        # Separator
        separator = Label(
            text='/',
            font_size='28sp',
            size_hint_x=0.2,
            color=(0.8, 0.8, 0.8, 1)
        )
        bp_display.add_widget(separator)
        
        # Diastolic
        diastolic_layout = BoxLayout(orientation='vertical')
        diastolic_title = Label(
            text='Tâm trương',
            font_size='12sp',
            size_hint_y=0.3,
            color=(0.8, 0.8, 0.8, 1)
        )
        self.diastolic_label = Label(
            text='--',
            font_size='32sp',
            bold=True,
            size_hint_y=0.7,
            color=(1, 1, 1, 1)
        )
        diastolic_layout.add_widget(diastolic_title)
        diastolic_layout.add_widget(self.diastolic_label)
        bp_display.add_widget(diastolic_layout)
        
        result_container.add_widget(bp_display)
        
        # Status
        self.bp_status_label = Label(
            text='Chưa đo',
            font_size='12sp',
            size_hint_y=0.2,
            color=(0.7, 0.7, 0.7, 1)
        )
        result_container.add_widget(self.bp_status_label)
        
        parent.add_widget(result_container)
    
    def _update_result_rect(self, instance, value):
        self.result_rect.pos = instance.pos
        self.result_rect.size = instance.size
    
    def _create_control_panel(self, parent):
        """Create control buttons panel"""
        control_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=0.1,
            spacing=10
        )
        
        # Start/Stop button
        self.start_stop_btn = Button(
            text='Bắt đầu đo',
            font_size='16sp',
            background_color=(0.2, 0.8, 0.2, 1)
        )
        self.start_stop_btn.bind(on_press=self._on_start_stop_pressed)
        control_layout.add_widget(self.start_stop_btn)
        
        # Save button (initially disabled)
        self.save_btn = Button(
            text='Lưu kết quả',
            font_size='16sp',
            background_color=(0.6, 0.6, 0.6, 1),
            disabled=True
        )
        self.save_btn.bind(on_press=self._on_save_pressed)
        control_layout.add_widget(self.save_btn)
        
        parent.add_widget(control_layout)
    
    def _on_start_stop_pressed(self, instance):
        """Handle start/stop button press"""
        if self.measurement_state == 'idle':
            self.start_measurement()
        else:
            self.stop_measurement()
    
    def _on_save_pressed(self, instance):
        """Handle save button press"""
        if self.systolic_result > 0 and self.diastolic_result > 0:
            self.save_measurement(self.systolic_result, self.diastolic_result)
            self._play_measurement_audio("Đã lưu kết quả đo huyết áp")
    
    def _on_back_pressed(self, instance):
        """Handle back button press"""
        if self.measurement_state != 'idle':
            self.stop_measurement()
        self.app_instance.navigate_to_screen('dashboard')
    
    def start_measurement(self):
        """Start blood pressure measurement process"""
        try:
            self.measurement_state = 'preparing'
            self.measurement_start_time = time.time()
            self.measurement_progress = 0
            
            # Update UI
            self.start_stop_btn.text = 'Dừng đo'
            self.start_stop_btn.background_color = (0.8, 0.2, 0.2, 1)
            self.save_btn.disabled = True
            self.save_btn.background_color = (0.6, 0.6, 0.6, 1)
            
            # Reset results
            self.systolic_label.text = '--'
            self.diastolic_label.text = '--'
            self.bp_status_label.text = 'Đang chuẩn bị...'
            
            # Play audio instruction
            self._play_measurement_audio("Bắt đầu đo huyết áp. Hãy giữ yên và thở đều")
            
            # Start measurement timer
            self.measurement_timer = Clock.schedule_interval(
                self._update_measurement_progress, 0.5
            )
            
            self.logger.info("Blood pressure measurement started")
            
        except Exception as e:
            self.logger.error(f"Error starting BP measurement: {e}")
            self.measurement_state = 'idle'
    
    def stop_measurement(self):
        """Stop blood pressure measurement process"""
        try:
            if self.measurement_timer:
                self.measurement_timer.cancel()
                self.measurement_timer = None
            
            self.measurement_state = 'idle'
            
            # Update UI
            self.start_stop_btn.text = 'Bắt đầu đo'
            self.start_stop_btn.background_color = (0.2, 0.8, 0.2, 1)
            self.progress_bar.value = 0
            self.progress_label.text = 'Đã dừng đo'
            self.pressure_value_label.text = '0 mmHg'
            
            self._play_measurement_audio("Đã dừng đo huyết áp")
            
            self.logger.info("Blood pressure measurement stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping BP measurement: {e}")
    
    def _update_measurement_progress(self, dt):
        """Update measurement progress"""
        try:
            elapsed = time.time() - self.measurement_start_time
            progress_percent = min((elapsed / self.estimated_duration) * 100, 100)
            
            self.progress_bar.value = progress_percent
            
            # Simulate measurement phases
            if elapsed < 10:
                self.measurement_state = 'preparing'
                self.progress_label.text = 'Đang chuẩn bị...'
                self.current_pressure = 0
            elif elapsed < 25:
                self.measurement_state = 'inflating'
                self.progress_label.text = 'Đang bơm...'
                # Simulate pressure increase
                self.current_pressure = min(30 + (elapsed - 10) * 8, 180)
            elif elapsed < 45:
                self.measurement_state = 'measuring'
                self.progress_label.text = 'Đang đo...'
                # Simulate pressure decrease with oscillations
                base_pressure = 180 - (elapsed - 25) * 6
                self.current_pressure = max(base_pressure, 30)
            elif elapsed < 55:
                self.measurement_state = 'deflating'
                self.progress_label.text = 'Đang xả khí...'
                self.current_pressure = max(30 - (elapsed - 45) * 3, 0)
            else:
                # Measurement complete
                self._handle_measurement_complete()
                return False  # Stop the timer
            
            # Update pressure display
            self.pressure_value_label.text = f"{self.current_pressure:.0f} mmHg"
            
        except Exception as e:
            self.logger.error(f"Error updating measurement progress: {e}")
    
    def _handle_measurement_complete(self):
        """Handle measurement completion"""
        try:
            # Simulate realistic BP values (for demo purposes)
            import random
            
            # Generate somewhat realistic values
            base_systolic = random.randint(110, 140)
            base_diastolic = random.randint(70, 90)
            
            self.systolic_result = base_systolic
            self.diastolic_result = base_diastolic
            
            # Update display
            self.systolic_label.text = str(self.systolic_result)
            self.diastolic_label.text = str(self.diastolic_result)
            
            # Update status and colors
            status = self._get_bp_status(self.systolic_result, self.diastolic_result)
            status_colors = {
                'normal': (0.2, 0.8, 0.2, 1),
                'high': (1, 0.6, 0, 1),
                'critical': (1, 0.2, 0.2, 1)
            }
            
            color = status_colors.get(status, (1, 1, 1, 1))
            self.systolic_label.color = color
            self.diastolic_label.color = color
            
            status_text = {
                'normal': 'Bình thường',
                'high': 'Cao',
                'critical': 'Rất cao'
            }
            
            self.bp_status_label.text = status_text.get(status, 'Hoàn thành')
            
            # Update UI state
            self.measurement_state = 'complete'
            self.progress_label.text = 'Hoàn thành'
            self.progress_bar.value = 100
            self.pressure_value_label.text = '0 mmHg'
            
            # Enable save button
            self.save_btn.disabled = False
            self.save_btn.background_color = (0.2, 0.6, 0.8, 1)
            
            # Update start button
            self.start_stop_btn.text = 'Đo lại'
            self.start_stop_btn.background_color = (0.2, 0.8, 0.2, 1)
            
            # Play completion audio
            audio_msg = f"Đo huyết áp hoàn thành. Kết quả {self.systolic_result} trên {self.diastolic_result}. {status_text.get(status, '')}"
            self._play_measurement_audio(audio_msg)
            
            self.logger.info(f"BP measurement complete: {self.systolic_result}/{self.diastolic_result}")
            
        except Exception as e:
            self.logger.error(f"Error handling measurement completion: {e}")
    
    def _get_bp_status(self, systolic: float, diastolic: float) -> str:
        """Get blood pressure status"""
        if systolic >= 160 or diastolic >= 100:
            return 'critical'
        elif systolic >= 140 or diastolic >= 90:
            return 'high'
        else:
            return 'normal'
    
    def _play_measurement_audio(self, message: str):
        """Play audio instruction/feedback"""
        try:
            # Use espeak-ng for Vietnamese TTS
            subprocess.Popen([
                'espeak-ng', '-v', 'vi', '-s', '150', '-a', '80', message
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.logger.error(f"Error playing audio: {e}")
    
    def save_measurement(self, systolic: float, diastolic: float):
        """Save measurement results"""
        try:
            measurement_data = {
                'timestamp': time.time(),
                'systolic': systolic,
                'diastolic': diastolic,
                'measurement_type': 'blood_pressure'
            }
            
            # Save to app's current data
            self.app_instance.current_data['blood_pressure_systolic'] = systolic
            self.app_instance.current_data['blood_pressure_diastolic'] = diastolic
            
            # Save to database if available
            self.app_instance.save_measurement_to_database(measurement_data)
            
            self.logger.info(f"Saved BP measurement: {systolic}/{diastolic}")
            
        except Exception as e:
            self.logger.error(f"Error saving measurement: {e}")
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("BP measurement screen entered")
        # Reset to idle state
        if self.measurement_state != 'idle':
            self.stop_measurement()
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("BP measurement screen left")
        # Stop any ongoing measurement
        if self.measurement_state != 'idle':
            self.stop_measurement()