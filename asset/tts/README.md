# Piper TTS Assets

Thư mục này chứa các file âm thanh `.wav` đã được sinh sẵn từ Piper TTS cho các câu thoại hệ thống (tĩnh, không có tham số).

> **Cách tạo hoặc cập nhật audio:**
>
> ```bash
> source /home/pi/Desktop/IoT_health/.venv/bin/activate
> python -m src.utils.export_tts_assets
> ```
>
> * Tập lệnh đọc cấu hình từ `config/app_config.yaml`, sử dụng model Piper đã khai báo và mặc định sinh file vào `asset/tts` (có thể đổi với `--output`).
> * Các kịch bản cần tham số động (ví dụ đọc giá trị nhịp tim) vẫn được phát thời gian thực trong ứng dụng, không lưu sẵn tại đây.

Khi đã có đủ file, ứng dụng sẽ ưu tiên phát trực tiếp từ thư mục này để rút ngắn thời gian phản hồi.
