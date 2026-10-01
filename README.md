# Log Viewer EVC

Desktop app để xem log console Java (Spring Boot) tải về dạng `.zip`.
Chỉ cần kéo thả file zip vào: app tự giải nén các file `.tar.gz` theo giờ, nối thành log trọn 1 ngày và hiển thị trong bảng dễ đọc.

## Tính năng

- **Kéo thả** file `.zip`, `.tar.gz`, `.gz`, `.log` hoặc cả thư mục
- Tự **sắp xếp theo giờ** trong tên file (`accountant_logs_2026-09-29_13-00.tar.gz`), giải nén cả các file log đã xoay vòng (`*.log.2026-09-29.0.gz`) bên trong
- **Gom stack trace** vào đúng dòng log của nó
- Hiển thị giờ VN (UTC+7), tô màu theo level: ERROR đỏ, WARN cam, INFO xanh
- **Lọc** theo level, **tìm kiếm** theo nội dung, trace ID, mã KH… (có hỗ trợ regex và phân biệt hoa/thường)
- **Panel chi tiết**: message đầy đủ, Headers/Payload JSON được format sẵn, stack trace
- **Tự lưu các ngày đã mở** ở cột bên trái, xếp theo tháng
  - Click để mở 1 ngày
  - Tick nhiều ngày để **tự gộp** thành 1 log liên tục
- Xuất log gộp cả ngày, hoặc chỉ các dòng đang lọc

## Phím tắt

| Phím | Chức năng |
|---|---|
| `Ctrl+O` | Mở file |
| `Ctrl+F` | Tìm kiếm |
| `F8` / `Shift+F8` | ERROR tiếp theo / trước đó |
| `F7` / `Shift+F7` | WARN tiếp theo / trước đó |
| `Ctrl+R` | Xoá tất cả bộ lọc (giữ nguyên dòng đang chọn để xem ngữ cảnh) |
| `Ctrl+S` | Xuất log gộp |
| `Ctrl+Shift+S` | Xuất các dòng đang lọc |
| Double-click 1 dòng | Tìm theo trace ID của dòng đó |

## Chạy từ source

Yêu cầu: Python 3.11+

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

## Build file .exe

```powershell
.\build.bat            # dist\LogViewer\LogViewer.exe  (mở nhanh, phải giữ cả thư mục)
.\build.bat onefile    # dist\LogViewer.exe            (1 file duy nhất, mở chậm hơn ~2-3s)
```

> Dùng Command Prompt hoặc double-click thì bỏ `.\` phía trước.

## Dữ liệu lưu ở đâu

Các ngày đã mở được copy vào `%LOCALAPPDATA%\LogViewer\library\`, gồm file gốc và `library.json`.
Build lại hay cập nhật app đều không làm mất danh sách này.
Xoá 1 ngày trong app chỉ xoá bản copy, file bạn tải về vẫn còn nguyên.

## Cấu trúc code

```
main.py                     # khởi động app
logviewer/
├── loader.py               # đọc zip → tar.gz → .gz, sắp theo giờ
├── parser.py               # tách entry, level, trace ID, stack trace
├── library.py              # lưu các ngày đã mở
├── models.py               # dữ liệu cho bảng log
└── ui/
    ├── main_window.py      # cửa sổ chính
    ├── library_panel.py    # cột "Đã lưu" bên trái
    ├── filter_bar.py       # thanh lọc và tìm kiếm
    ├── log_delegate.py     # cách vẽ bảng log (màu, nhãn level…)
    └── detail_panel.py     # panel chi tiết
```

Nếu log đổi format thì sửa regex trong `logviewer/parser.py`.
