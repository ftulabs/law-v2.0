# VIDEO NỘP BGK — PHƯƠNG ÁN TỐI GIẢN (1 take ~5 phút, 3 cửa sổ, không dựng)

> BGK chỉ yêu cầu đúng một điều trong video: **engine xử lý scanned/image PDF và sinh
> citation đúng** (trần 10 phút). Kịch bản này làm đúng và đủ điều đó.

## Chuẩn bị (5 phút)

1. Mở sẵn 4 thứ:
  - **PDF viewer**: `data/samples/SG/mas_notice_655.pdf`
  - **Terminal** tại thư mục dự án (font to), đã gõ sẵn — CHƯA Enter:
  `python main.py --economy Singapore --pillar 7 --pdf data/samples/SG/mas_notice_655.pdf --ocr rapidocr --llm openrouter --fresh`
  (PHẢI có `--fresh` — thiếu nó lượt chạy trúng cache, ra kết quả ngay mà KHÔNG hiện
  dòng OCR/CER trên hình → hỏng cảnh chính)
  - **Notepad**: `data/samples/SG/mas_notice_655.ocr.txt`
  - **File Explorer**: thư mục `outputs/`
2. Tắt notification (Focus assist), không mở `.env`. Bật quay màn hình.



## Quay 1 mạch — 5 bước


| Bước      | Làm gì                                                                                                                                         | Nói ý gì                                                                                                                                                                                                                                                                                                                                                  |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 (0:00)  | Đứng ở cửa sổ PDF, kéo 1-2 trang, **thử bôi đen chữ → không được**                                                                             | "Đây là VeriTrade của team FTU. File này là PDF ảnh scan — không có lớp text, bôi đen không ăn. Video này cho thấy engine xử lý nó và sinh trích dẫn đúng."                                                                                                                                                                                               |
| 2 (0:30)  | Chuyển terminal → **Enter**. Để log chạy tự nhiên trên hình (~2-3 phút). Trong lúc chờ nói vài câu (bên dưới), im lặng vài đoạn cũng không sao | "Một lệnh duy nhất. Hệ thống tự phát hiện đây là bản scan bằng bộ dò mật độ text, chuyển sang OCR ảnh, tách điều khoản, rồi map vào các chỉ số RDTII bằng LLM — LLM và OCR đều đổi được bằng một dòng config. Bình thường hệ thống tự tìm luật trên portal chính phủ, không cần ai đưa file — bản demo web ở veritrade.ftu.fyi giám khảo có thể tự chạy." |
| 3 (~3:00) | Log xong → cuộn tìm dòng `CER` → **zoom to** dòng `CER = 1.11% (PASS < 5%)`                                                                    | "Hệ thống tự đo chất lượng OCR của chính nó: sai số ký tự 1.11%, vượt chuẩn 5% của đề — đo với bản đối chiếu kiểm tay."                                                                                                                                                                                                                                   |
| 4 (~3:40) | File Explorer → mở **file CSV mới nhất** trong `outputs/` → chỉ 2 cột **Article / Section** và **Verbatim Snippet**                            | "Kết quả: mỗi dòng map một điều khoản vào một chỉ số, trích dẫn tới cấp điều/khoản, kèm nguyên văn."                                                                                                                                                                                                                                                      |
| 5 (~4:20) | **Copy 1 câu** (~10 từ) trong 1 ô snippet → chuyển Notepad → **Ctrl-F → dán → Enter** → thấy khớp highlight                                    | "Copy một câu bất kỳ, tìm trong văn bản gốc — khớp từng chữ. Model không bao giờ được tự viết trích dẫn: snippet copy từ văn bản trích xuất và được máy kiểm tra tồn tại trong nguồn. Trích dẫn không thể bị bịa. Cảm ơn ban giám khảo."                                                                                                                  |


Dừng quay. Cắt phần thừa ở đầu/cuối clip là xong.

## (TÙY CHỌN — nếu còn sức) Cảnh mở đầu 40 giây

Trước bước 1: vào **veritrade.ftu.fyi** → chọn Singapore + Pillar 6 → tick **"Ignore the
saved result"** → Run → lia qua **discovery feed** đang hiện các luật tìm thấy ~15 giây →
"hệ thống đang tự tìm luật trực tiếp trên portal chính phủ, không seed URL" → bỏ đó, chuyển
sang bước 1. Cảnh này chặn nghi vấn "tool chỉ xử lý file đưa sẵn" — không bắt buộc.

## Sự cố

- **Lệnh lỗi 402/timeout** (key hết hạn mức ngày): chờ 30 phút chạy lại, hoặc quay hôm sau.
- **Không thấy dòng CER**: cuộn ngược log lên trên (nó nằm ở khúc `[ocr]`).



## Checklist xuất

- [x] Thấy rõ: PDF không bôi đen được → dòng CER PASS → Ctrl-F khớp nguyên văn
- [x] ≤10 phút, 1080p, không lộ key
- [ ] Tên: `FTU-VeriTrade_Walkthrough.mp4` + upload bản backup Drive/YouTube unlisted
  ```
  (điền ô "Screen Recording Backup Link" trên form)
  ```

