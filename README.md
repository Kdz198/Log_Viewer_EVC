# Log Viewer EVC (v1.1.0)

Desktop app chuyên dụng để xem, phân tích và gộp log console Java (Spring Boot) tải về dạng `.zip`, `.tar.gz` hoặc tải trực tiếp từ **MinIO Console**.

---

## Tính năng nổi bật

- **Tích hợp MinIO Console (`Ctrl+M`)**:
  - Tự động đăng nhập và tải danh sách các ngày/gói log từ MinIO bucket (`accounting-file-logs`…).
  - Chọn 1 ngày hoặc tick nhiều ngày: App tự động tải file `.zip` về, giải nén và nạp vào bảng log.
  - Hỗ trợ cấu hình qua file `.env` hoặc nhập trực tiếp trên giao diện (có tuỳ chọn lưu mật khẩu an toàn).
- **Tuỳ chọn thư mục lưu trữ log & Tự động di chuyển**:
  - Cho phép người dùng tự do chọn thư mục lưu trữ log (ở cửa sổ MinIO hoặc menu `File -> Đổi thư mục lưu log…`).
  - Mọi file tải từ MinIO hoặc import từ bên ngoài đều được tạo 1 bản copy lưu gọn gàng vào thư mục này.
  - Khi người dùng đổi sang thư mục mới, app **tự động copy toàn bộ dữ liệu log đã lưu sang nơi mới**.
- **Tính năng Xoá cứng file từ trong app (`Delete`)**:
  - Chuột phải hoặc bấm phím `Delete` trên danh sách ngày để xoá vĩnh viễn file vật lý khỏi ổ cứng.
  - Hỗ trợ tuỳ chọn xoá cả file gốc ở ngoài (nếu trước đó import từ `Downloads`/Desktop) hoặc chỉ bỏ khỏi danh sách hiển thị.
  - Cho phép click `Mở vị trí file trong Explorer` để xem trực tiếp file trên ổ đĩa.
- **Tìm kiếm trực tiếp trong chi tiết log (`Ctrl+F`)**:
  - Khi bấm vào 1 dòng log, nhấn `Ctrl+F` để mở thanh tìm kiếm riêng cho khung chi tiết bên dưới.
  - Tô màu (highlight) kết quả, đếm số lượng khớp, nhảy nhanh qua `Enter`/`Shift+Enter` (hoặc `F3`/`Shift+F3`), hỗ trợ `Regex` và `Aa`.
- **Loading Overlay hiển thị tiến trình mượt mà**:
  - Card xoay nổi giữa màn hình (60 FPS) kèm thanh phần trăm (%) và số MB tải về theo thời gian thực thay vì chỉ xoay con trỏ chuột.
- **Tự động gom nhóm & xử lý thông minh**:
  - Tự sắp xếp các file `.tar.gz` theo giờ (`accountant_logs_YYYY-MM-DD_HH-mm.tar.gz`), giải nén cả các file quay vòng `.gz` bên trong.
  - Gom stack trace nhiều dòng vào đúng dòng log gốc.
  - Định dạng hiển thị giờ VN (UTC+7), tô màu theo level (ERROR đỏ, WARN cam, INFO xanh).
  - Tự format các chuỗi JSON lồng nhau trong `Headers` / `Payload`.
- **Quản lý lịch sử các ngày đã mở**:
  - Cột "Đã lưu" bên trái tự động gom theo tháng.
  - Click để mở 1 ngày, hoặc tick chọn nhiều ngày để **tự gộp** thành 1 dòng thời gian liên tục.

---

## Phím tắt

| Phím | Chức năng |
|---|---|
| `Ctrl+M` | Mở cửa sổ tải log trực tiếp từ MinIO & Cấu hình nơi lưu |
| `Ctrl+O` | Mở file log / zip từ ổ cứng |
| `Ctrl+Shift+O` | Mở thư mục chứa nhiều file log |
| `Ctrl+F` | Tìm kiếm trong chi tiết dòng đang chọn (hoặc tìm tổng nếu chưa chọn) |
| `Ctrl+Shift+F` | Focus nhanh lên thanh tìm kiếm tổng (bộ lọc bảng) |
| `Enter` / `Shift+Enter` | Kết quả tiếp theo / trước đó (khi tìm trong chi tiết) |
| `Esc` | Đóng thanh tìm kiếm chi tiết |
| `Delete` | Xoá cứng file log của ngày đang chọn khỏi ổ cứng |
| `F8` / `Shift+F8` | Nhảy đến dòng ERROR tiếp theo / trước đó |
| `F7` / `Shift+F7` | Nhảy đến dòng WARN tiếp theo / trước đó |
| `Ctrl+R` | Xoá tất cả bộ lọc (giữ nguyên dòng đang chọn để xem ngữ cảnh) |
| `Ctrl+S` | Xuất log gộp cả ngày ra file text |
| `Ctrl+Shift+S` | Xuất các dòng đang lọc ra file text |
| Double-click 1 dòng | Tự động lọc toàn bộ bảng theo trace ID của dòng đó |

---

## Cấu hình MinIO (`.env`)

Tạo file `.env` ở thư mục gốc (hoặc đặt cạnh file `.exe` khi build):

```env
MINIO_URL=https://minio.example.com/browser/your-log-bucket
MINIO_USERNAME=ten_tai_khoan
MINIO_PASSWORD=mat_khau_cua_ban
```

---

## Chạy từ Source

Yêu cầu: Python 3.11+

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

---

## Build file .exe

Tắt ứng dụng trước khi build để file `.exe` được tự động ghi đè bản mới nhất:

```powershell
.\build.bat            # dist\LogViewer\LogViewer.exe  (khuyên dùng, mở nhanh)
.\build.bat onefile    # dist\LogViewer.exe            (1 file duy nhất, tiện chia sẻ)
```

---

## Cấu trúc dự án

```
main.py                         # Khởi động ứng dụng
.env.example                    # Mẫu cấu hình MinIO
build.bat                       # Script build PyInstaller
logviewer/
├── loader.py                   # Đọc zip → tar.gz → .gz, sắp xếp theo giờ
├── parser.py                   # Phân tích log, level, trace ID, stack trace
├── library.py                  # Quản lý kho lưu trữ, đổi thư mục & xoá cứng
├── minio_client.py             # Client REST API kết nối MinIO Console
├── models.py                   # Model bảng log (QAbstractTableModel)
└── ui/
    ├── main_window.py          # Cửa sổ chính
    ├── minio_dialog.py         # Cửa sổ duyệt & tải log MinIO, chọn nơi lưu
    ├── loading_overlay.py      # Card loading mượt mà & thanh tiến trình
    ├── library_panel.py        # Cột danh sách ngày đã lưu bên trái
    ├── filter_bar.py           # Thanh tìm kiếm và bộ lọc level
    ├── log_delegate.py         # Custom paint bảng log (màu, badge dòng)
    └── detail_panel.py         # Khung xem chi tiết & tìm kiếm nội dung
```
