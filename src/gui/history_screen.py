"""
History Screen
Screen hiển thị lịch sử các phép đo
"""

from typing import Dict, Any, Optional, List
import logging
from datetime import datetime, timedelta
from kivy.uix.screenmanager import Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.graphics import Color, Rectangle


class MeasurementRecord(BoxLayout):
    """Widget hiển thị một bản ghi đo"""
    
    def __init__(self, record_data: Dict[str, Any], **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=60, spacing=10, **kwargs)
        
        self.record_data = record_data
        
        # Background với màu xen kẽ
        with self.canvas.before:
            Color(0.12, 0.12, 0.18, 1)
            self.rect = Rectangle(size=self.size, pos=self.pos)
        self.bind(size=self._update_rect, pos=self._update_rect)
        
        # Time column
        time_str = datetime.fromtimestamp(record_data.get('timestamp', 0)).strftime('%H:%M\n%d/%m')
        time_label = Label(
            text=time_str,
            font_size='10sp',
            size_hint_x=0.15,
            color=(0.8, 0.8, 0.8, 1)
        )
        self.add_widget(time_label)
        
        # Heart rate column
        hr = record_data.get('heart_rate', 0)
        hr_text = f"{hr:.0f}" if hr > 0 else "--"
        hr_color = self._get_hr_color(hr)
        hr_label = Label(
            text=f"{hr_text}\nbpm",
            font_size='12sp',
            size_hint_x=0.2,
            color=hr_color
        )
        self.add_widget(hr_label)
        
        # SpO2 column
        spo2 = record_data.get('spo2', 0)
        spo2_text = f"{spo2:.0f}" if spo2 > 0 else "--"
        spo2_color = self._get_spo2_color(spo2)
        spo2_label = Label(
            text=f"{spo2_text}\n%",
            font_size='12sp',
            size_hint_x=0.2,
            color=spo2_color
        )
        self.add_widget(spo2_label)
        
        # Temperature column
        temp = record_data.get('temperature', 0)
        temp_text = f"{temp:.1f}" if temp > 0 else "--"
        temp_color = self._get_temp_color(temp)
        temp_label = Label(
            text=f"{temp_text}\n°C",
            font_size='12sp',
            size_hint_x=0.2,
            color=temp_color
        )
        self.add_widget(temp_label)
        
        # Blood pressure column
        systolic = record_data.get('systolic', 0)
        diastolic = record_data.get('diastolic', 0)
        bp_text = f"{systolic:.0f}/{diastolic:.0f}" if systolic > 0 and diastolic > 0 else "--"
        bp_color = self._get_bp_color(systolic, diastolic)
        bp_label = Label(
            text=f"{bp_text}\nmmHg",
            font_size='12sp',
            size_hint_x=0.25,
            color=bp_color
        )
        self.add_widget(bp_label)
    
    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size
    
    def _get_hr_color(self, hr: float) -> tuple:
        """Get color for heart rate value"""
        if hr <= 0:
            return (0.5, 0.5, 0.5, 1)  # Gray
        elif hr < 50 or hr > 150:
            return (1, 0.2, 0.2, 1)    # Red (critical)
        elif hr < 60 or hr > 120:
            return (1, 0.6, 0, 1)      # Orange (high/low)
        else:
            return (0.2, 0.8, 0.2, 1)  # Green (normal)
    
    def _get_spo2_color(self, spo2: float) -> tuple:
        """Get color for SpO2 value"""
        if spo2 <= 0:
            return (0.5, 0.5, 0.5, 1)  # Gray
        elif spo2 < 90:
            return (1, 0.2, 0.2, 1)    # Red (critical)
        elif spo2 < 95:
            return (1, 0.6, 0, 1)      # Orange (low)
        else:
            return (0.2, 0.8, 0.2, 1)  # Green (normal)
    
    def _get_temp_color(self, temp: float) -> tuple:
        """Get color for temperature value"""
        if temp <= 0:
            return (0.5, 0.5, 0.5, 1)  # Gray
        elif temp < 35.0 or temp > 39.0:
            return (1, 0.2, 0.2, 1)    # Red (critical)
        elif temp < 36.0 or temp > 37.5:
            return (1, 0.6, 0, 1)      # Orange (abnormal)
        else:
            return (0.2, 0.8, 0.2, 1)  # Green (normal)
    
    def _get_bp_color(self, systolic: float, diastolic: float) -> tuple:
        """Get color for blood pressure values"""
        if systolic <= 0 or diastolic <= 0:
            return (0.5, 0.5, 0.5, 1)  # Gray
        elif systolic >= 160 or diastolic >= 100:
            return (1, 0.2, 0.2, 1)    # Red (critical)
        elif systolic >= 140 or diastolic >= 90:
            return (1, 0.6, 0, 1)      # Orange (high)
        else:
            return (0.2, 0.8, 0.2, 1)  # Green (normal)


class HistoryScreen(Screen):
    """
    Screen hiển thị lịch sử các phép đo
    """
    
    def __init__(self, app_instance, **kwargs):
        """
        Initialize history screen
        
        Args:
            app_instance: Reference to main application
        """
        super().__init__(**kwargs)
        self.app_instance = app_instance
        self.logger = logging.getLogger(__name__)
        
        # Current filter settings
        self.current_filter = 'today'  # today, week, month, all
        self.records_list = None
        
        self._build_layout()
    
    def _build_layout(self):
        """Build history screen layout"""
        # Main container
        main_layout = BoxLayout(orientation='vertical', spacing=10, padding=10)
        
        # Header
        self._create_header(main_layout)
        
        # Filter buttons
        self._create_filter_buttons(main_layout)
        
        # Column headers
        self._create_column_headers(main_layout)
        
        # Scrollable records list
        scroll = ScrollView(size_hint_y=0.7)
        self.records_list = BoxLayout(
            orientation='vertical', 
            spacing=2, 
            size_hint_y=None
        )
        self.records_list.bind(minimum_height=self.records_list.setter('height'))
        
        scroll.add_widget(self.records_list)
        main_layout.add_widget(scroll)
        
        # Bottom controls
        self._create_bottom_controls(main_layout)
        
        self.add_widget(main_layout)
    
    def _create_header(self, parent):
        """Create header with title and back button"""
        header = BoxLayout(orientation='horizontal', size_hint_y=0.08, spacing=10)
        
        # Title
        title = Label(
            text='LỊCH SỬ ĐO',
            font_size='18sp',
            bold=True,
            color=(1, 1, 1, 1),
            size_hint_x=0.8
        )
        header.add_widget(title)
        
        # Back button
        back_btn = Button(
            text='← Dashboard',
            font_size='12sp',
            size_hint_x=0.2,
            background_color=(0.6, 0.6, 0.6, 1)
        )
        back_btn.bind(on_press=self._on_back_pressed)
        header.add_widget(back_btn)
        
        parent.add_widget(header)
    
    def _create_filter_buttons(self, parent):
        """Create filter buttons for different time periods"""
        filter_layout = BoxLayout(
            orientation='horizontal', 
            size_hint_y=0.07, 
            spacing=5
        )
        
        filters = [
            ('today', 'Hôm nay'),
            ('week', 'Tuần này'),
            ('month', 'Tháng này'),
            ('all', 'Tất cả')
        ]
        
        self.filter_buttons = {}
        
        for filter_key, filter_name in filters:
            btn = Button(
                text=filter_name,
                font_size='12sp',
                background_color=(0.3, 0.5, 0.8, 1) if filter_key == 'today' else (0.4, 0.4, 0.4, 1)
            )
            btn.bind(on_press=lambda x, key=filter_key: self._on_filter_changed(key))
            self.filter_buttons[filter_key] = btn
            filter_layout.add_widget(btn)
        
        parent.add_widget(filter_layout)
    
    def _create_column_headers(self, parent):
        """Create column headers"""
        header_layout = BoxLayout(
            orientation='horizontal', 
            size_hint_y=0.05, 
            spacing=10
        )
        
        # Background
        with header_layout.canvas.before:
            Color(0.2, 0.2, 0.3, 1)
            self.header_rect = Rectangle(size=header_layout.size, pos=header_layout.pos)
        header_layout.bind(size=self._update_header_rect, pos=self._update_header_rect)
        
        headers = [
            ('Thời gian', 0.15),
            ('Nhịp tim', 0.2),
            ('SpO2', 0.2),
            ('Nhiệt độ', 0.2),
            ('Huyết áp', 0.25)
        ]
        
        for header_text, size_hint in headers:
            header_label = Label(
                text=header_text,
                font_size='11sp',
                bold=True,
                size_hint_x=size_hint,
                color=(1, 1, 1, 1)
            )
            header_layout.add_widget(header_label)
        
        parent.add_widget(header_layout)
    
    def _update_header_rect(self, instance, value):
        self.header_rect.pos = instance.pos
        self.header_rect.size = instance.size
    
    def _create_bottom_controls(self, parent):
        """Create bottom control buttons"""
        control_layout = BoxLayout(
            orientation='horizontal',
            size_hint_y=0.08,
            spacing=10
        )
        
        # Export button
        export_btn = Button(
            text='Xuất dữ liệu',
            font_size='12sp',
            background_color=(0.2, 0.6, 0.8, 1)
        )
        export_btn.bind(on_press=self._export_data)
        control_layout.add_widget(export_btn)
        
        # Clear history button
        clear_btn = Button(
            text='Xóa lịch sử',
            font_size='12sp',
            background_color=(0.8, 0.3, 0.3, 1)
        )
        clear_btn.bind(on_press=self._clear_history)
        control_layout.add_widget(clear_btn)
        
        # Statistics button
        stats_btn = Button(
            text='Thống kê',
            font_size='12sp',
            background_color=(0.6, 0.3, 0.8, 1)
        )
        stats_btn.bind(on_press=self._show_statistics)
        control_layout.add_widget(stats_btn)
        
        parent.add_widget(control_layout)
    
    def _on_back_pressed(self, instance):
        """Handle back button press"""
        self.app_instance.navigate_to_screen('dashboard')
    
    def _on_filter_changed(self, filter_key: str):
        """Handle filter button press"""
        # Update button colors
        for key, btn in self.filter_buttons.items():
            if key == filter_key:
                btn.background_color = (0.3, 0.5, 0.8, 1)  # Active color
            else:
                btn.background_color = (0.4, 0.4, 0.4, 1)   # Inactive color
        
        self.current_filter = filter_key
        self._load_records()
    
    def _load_records(self):
        """Load records based on current filter"""
        try:
            # Clear existing records
            self.records_list.clear_widgets()
            
            # Get date range based on filter
            now = datetime.now()
            
            if self.current_filter == 'today':
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            elif self.current_filter == 'week':
                start_date = now - timedelta(days=7)
            elif self.current_filter == 'month':
                start_date = now - timedelta(days=30)
            else:  # all
                start_date = datetime(2020, 1, 1)  # Far past date
            
            # Generate sample data (in real app, this would come from database)
            sample_records = self._generate_sample_records(start_date, now)
            
            if not sample_records:
                # No records message
                no_records_label = Label(
                    text='Không có dữ liệu trong khoảng thời gian này',
                    font_size='14sp',
                    color=(0.6, 0.6, 0.6, 1),
                    size_hint_y=None,
                    height=100
                )
                self.records_list.add_widget(no_records_label)
            else:
                # Add records to list
                for record in reversed(sample_records):  # Most recent first
                    record_widget = MeasurementRecord(record)
                    self.records_list.add_widget(record_widget)
            
            self.logger.info(f"Loaded {len(sample_records)} records for filter: {self.current_filter}")
            
        except Exception as e:
            self.logger.error(f"Error loading records: {e}")
    
    def _generate_sample_records(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
        """Generate sample measurement records for demo"""
        import random
        from datetime import timedelta
        
        records = []
        current_date = start_date
        
        # Generate records every few hours
        while current_date <= end_date:
            # Skip some records randomly to make it more realistic
            if random.random() > 0.3:  # 70% chance of having a record
                record = {
                    'timestamp': current_date.timestamp(),
                    'heart_rate': random.randint(60, 120) + random.random() * 10,
                    'spo2': random.randint(95, 100) + random.random() * 3,
                    'temperature': 36.0 + random.random() * 2,  # 36-38°C
                    'systolic': random.randint(110, 140),
                    'diastolic': random.randint(70, 90)
                }
                records.append(record)
            
            # Move to next time slot (2-6 hours)
            hours_increment = random.randint(2, 6)
            current_date += timedelta(hours=hours_increment)
        
        return records
    
    def _export_data(self, instance):
        """Export measurement data"""
        try:
            # TODO: Implement actual data export
            self.logger.info("Data export requested")
            
            # Show confirmation message
            self._show_message("Đã xuất dữ liệu thành công")
            
        except Exception as e:
            self.logger.error(f"Error exporting data: {e}")
            self._show_message("Lỗi khi xuất dữ liệu")
    
    def _clear_history(self, instance):
        """Clear measurement history"""
        try:
            # TODO: Show confirmation dialog first
            # TODO: Implement actual history clearing
            self.logger.info("History clear requested")
            
            # Reload records (will be empty after clearing)
            self._load_records()
            
            self._show_message("Đã xóa lịch sử")
            
        except Exception as e:
            self.logger.error(f"Error clearing history: {e}")
            self._show_message("Lỗi khi xóa lịch sử")
    
    def _show_statistics(self, instance):
        """Show measurement statistics"""
        try:
            # TODO: Implement statistics screen or popup
            self.logger.info("Statistics requested")
            self._show_message("Tính năng thống kê đang phát triển")
            
        except Exception as e:
            self.logger.error(f"Error showing statistics: {e}")
    
    def _show_message(self, message: str):
        """Show temporary message (placeholder for popup)"""
        # For now, just log the message
        # In a real implementation, this would show a popup or toast message
        self.logger.info(f"User message: {message}")
    
    def on_enter(self):
        """Called when screen is entered"""
        self.logger.info("History screen entered")
        self._load_records()
    
    def on_leave(self):
        """Called when screen is left"""
        self.logger.info("History screen left")