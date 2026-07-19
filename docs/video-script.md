# KỊCH BẢN QUAY MỘT LÈO (1 take, ~7 phút, không dựng — chỉ cắt đầu/cuối)

> Yêu cầu chấm duy nhất của BGK cho video: **scanned/image PDF → OCR → citation đúng**,
> trần 10 phút. Kịch bản này quay LIỀN MẠCH một lần: không có đoạn nào phải đứng chờ máy —
> mọi khoảng chạy nền đều được lấp bằng một nội dung nói khác. Nếu quay hỏng thì có điểm
> "cứu" ở giữa (ghi ở cuối file) để không phải quay lại từ đầu.

---

## CHUẨN BỊ (15 phút, ngoài video — làm đủ thì lúc quay không bị khựng)

1. **Cửa sổ mở sẵn, theo thứ tự Alt-Tab:**
   - Chrome **tab 1**: https://veritrade.ftu.fyi (load xong hẳn)
   - Chrome **tab 2**: http://localhost:8501 — *sidebar đã chọn sẵn Singapore + Pillar 6,
     đã tick "Ignore the saved result", CHƯA bấm Run*
   - Chrome **tab 3**: http://localhost:8501 (mở thêm 1 tab nữa, session riêng) — *sidebar đã
     chọn sẵn Singapore + Pillar 6, KHÔNG tick ignore, CHƯA bấm Run* → tab này lát bấm Run
     sẽ hiện NGAY kết quả lượt live đã lưu
   - **Terminal** tại thư mục dự án, font to, đã gõ sẵn (CHƯA Enter):
     `python main.py --economy Singapore --pillar 7 --pdf data/samples/SG/mas_notice_655.pdf --ocr rapidocr --llm openrouter`
   - **Excel**: mở sẵn `outputs/FTU-VeriTrade_RDTII_Round1_Output.csv`, con trỏ đặt ở ô A1
   - **PDF viewer**: mở sẵn `data/samples/SG/mas_notice_655.pdf` (cửa sổ riêng)
   - **Notepad**: mở sẵn `data/samples/SG/mas_notice_655.ocr.txt` (để Ctrl-F đối chiếu)
2. **Điều kiện cần:** localhost đã từng chạy xong 1 lượt live Singapore-P6 (để tab 3 có saved
   result). Nếu chưa có thì chạy 1 lượt trước khi quay.
3. Đóng mọi cửa sổ khác; không mở `.env`; tắt notification Windows (Focus assist).
4. Bấm quay và làm đúng thứ tự dưới — mỗi mục là một nhịp liền nhau.

---

## MỘT TAKE — 10 NHỊP LIỀN MẠCH

**[0:00 · Nhịp 1 — web deploy, 30s]**
Ở Chrome tab 1, cuộn chậm trang chủ veritrade.ftu.fyi.
🗣 *"Đây là VeriTrade — nhập một quốc gia và một pillar RDTII, hệ thống tự tìm luật trên
cổng thông tin chính phủ, đọc cả PDF scan, map từng điều khoản vào đúng chỉ số kèm trích
dẫn nguyên văn. Bản live này ở veritrade.ftu.fyi, giám khảo dùng ngay không cần cài gì."*

**[0:30 · Nhịp 2 — bấm Run lượt live, 45s]**
Chuyển Chrome tab 2 (đã set sẵn SG + P6 + tick ignore). Chỉ chuột vào ô tick
**"Ignore the saved result"** 2 giây → bấm **Run analysis** → chờ panel phải bắt đầu chạy chữ
→ khi discovery feed hiện các dòng luật (tên luật + sso.agc.gov.sg), rê chuột theo 3-4 dòng.
🗣 *"Tôi chạy Singapore Pillar 6, tick bỏ qua mọi cache — hệ thống đang search và crawl
TRỰC TIẾP trên Singapore Statutes Online ngay lúc này. Không seed URL, không hardcode tên
luật. Lượt trọn vẹn mất khoảng chục phút — tôi để nó chạy nền và quay lại sau."*

**[1:15 · Nhịp 3 — mở PDF scan, 30s]**
Chuyển cửa sổ PDF viewer (mas_notice_655.pdf). Kéo 1-2 trang, **thử bôi đen chữ — không được**.
🗣 *"Giờ đến yêu cầu chính của video: PDF dạng ảnh scan. Văn bản này không có lớp text —
bôi đen không ăn. Crawler thường sẽ chịu chết với loại này."*

**[1:45 · Nhịp 4 — Enter lệnh OCR, 20s]**
Chuyển terminal → **Enter** lệnh đã gõ sẵn. Nhìn log bắt đầu chạy 5 giây.
🗣 *"Tôi đưa đúng file này vào engine. Nó sẽ tự phát hiện đây là bản scan, chuyển sang OCR
ảnh, rồi map luôn các điều khoản. Trong lúc máy chạy, tôi giới thiệu file kết quả nộp."*
**(ĐỪNG chờ — chuyển nhịp 5 ngay. Lệnh cần ~2-3 phút, vừa khít nhịp 5.)**

**[2:05 · Nhịp 5 — Excel master file, 90s]** *(đây là đoạn lấp thời gian chạy máy)*
Chuyển Excel (`FTU-VeriTrade_RDTII_Round1_Output.csv`).
1. Kéo ngang header, đếm bằng chuột: 🗣 *"13 cột đầu đúng y template chính thức — Economy,
   Law Name, … Confidence, Notes. Ba cột phụ Pillar, RDTII_Raw_Score, Coverage đặt SAU 13
   cột bắt buộc, đúng như BGK xác nhận trong Q&A."*
2. Chỉ vào vài dòng: 🗣 *"110 dòng — ba quốc gia, hai pillar, đủ 9 chỉ số mỗi nước trong một
   sheet."*
3. Cuộn/lọc tới 1 dòng **No provision found**: 🗣 *"Chỉ số không có bằng chứng vẫn khai báo
   tường minh, Confidence và Discovery Tag ghi N/A — không bỏ trống âm thầm."*
4. Chỉ 1 dòng Last Amended = **Original** (Cyber Security Act 2024): 🗣 *"Ngày sửa đổi đọc
   từ chính timeline của portal; luật chưa từng sửa ghi Original theo Q&A của BGK."*
5. Chỉ cột RDTII_Raw_Score: 🗣 *"Điểm Zone 3 tự chọn: 0, 0.5, 1 theo thang chính thức."*

**[3:35 · Nhịp 6 — quay lại terminal: CER, 40s]**
Chuyển terminal. Lúc này log đã có (hoặc sắp có) dòng **CER**. Cuộn tìm và **zoom dòng
`CER = 1.11% (PASS < 5%)`**.
🗣 *"Xong rồi — và đây là điểm mấu chốt: hệ thống TỰ ĐO chất lượng OCR của nó. Sai số ký tự
1.11%, vượt xa chuẩn 5% của đề. Phép đo dùng bản đối chiếu kiểm tay, và engine nào có thể
ăn gian bằng cách đọc bản đối chiếu thì bị loại khỏi phép đo."*
*(Nếu lệnh chưa xong: nói thêm 20-30s về audit JSON — "mỗi kết quả còn kèm file JSON lưu
điểm retrieval, ngữ cảnh trước sau của trích dẫn để re-verify" — rồi mới cuộn tìm CER.)*

**[4:15 · Nhịp 7 — citation khớp nguồn, 60s]**
1. Mở File Explorer `outputs/` → mở **file CSV mới nhất** (lệnh vừa tạo).
2. Chỉ 2 cột **Article / Section** và **Verbatim Snippet** → click 1 ô snippet dài →
   **copy 1 câu** (~10 từ).
3. Chuyển Notepad (`mas_notice_655.ocr.txt`) → **Ctrl-F → dán → Enter** → thấy highlight khớp.
🗣 *"Trích dẫn tới cấp điều khoản, trích NGUYÊN VĂN. Tôi copy một câu bất kỳ, tìm trong văn
bản gốc — khớp từng chữ. Model không bao giờ được viết trích dẫn: snippet copy từ văn bản
trích xuất và được máy kiểm tra tồn tại trong nguồn. Trích dẫn không thể bị bịa."*

**[5:15 · Nhịp 8 — kết quả mapping (saved), 75s]**
Chuyển Chrome **tab 3** (đã set sẵn SG + P6, KHÔNG tick) → bấm **Run analysis** → kết quả
hiện ngay.
🗣 *"Lượt live lúc nãy vẫn đang chạy nền, nên tôi mở kết quả của lượt live đã hoàn thành
trước — cùng một pipeline."*
1. Cuộn tới card **Personal Data Protection Act 2012 — Section 26 → P6-I4**:
   🗣 *"PDPA Điều 26: cấm chuyển dữ liệu ra nước ngoài TRỪ KHI đạt điều kiện — tức chuyển có
   điều kiện: chỉ số 6.4, không phải 6.1 lệnh cấm. Trùng đáp án chính thức. Model không nhầm
   vì mỗi lần chấm nó thấy định nghĩa của tất cả chỉ số anh em."*
2. Chỉ 1 card xanh + 1 card vàng: 🗣 *"Đèn xanh tự chấp nhận, đèn vàng vào hàng đợi người
   duyệt — không bao giờ im lặng nhận thứ không chắc."*
3. Click **link nguồn** 1 card → mở đúng sso.agc.gov.sg → đóng tab.
4. Mở tab **Needs review**, rê chuột qua 3 nút **Approve / Reject / Fix indicator**:
   🗣 *"Người duyệt xử lý ngay trên giao diện, mọi thao tác vào audit log."*

**[6:30 · Nhịp 9 — Australia 30s]** *(tùy chọn — cắt nếu sợ lố)*
Trên tab 3, đổi Country = Australia (không tick) → Run → kết quả hiện ngay → chỉ card
**My Health Records Act — Section 77** xuất hiện ở cả **P6-I1 và P6-I2**, và 1 card tag **NEW**.
🗣 *"Portal Úc là app JavaScript — text luật không nằm trong HTML; hệ thống phát hiện vỏ rỗng
và lấy đúng PDF hợp nhất chính thức qua API. Điều 77 map cả 6.1 lẫn 6.2 đúng như answer key.
Tag NEW là luật tự tìm ra ngoài sample kit."*

**[7:00 · Nhịp 10 — kết, 20s]**
Chuyển Chrome tab 1 (web) 3 giây → mở github.com/ftulabs/law-v2.0.
🗣 *"Mã nguồn Apache-2.0, README hướng dẫn chạy trong 10 phút, web demo sống đến hết kỳ chấm.
Cảm ơn ban giám khảo."* → dừng quay.

---

## ĐIỂM CỨU nếu quay hỏng giữa chừng (không cần quay lại từ đầu)
- Hỏng từ nhịp 3 trở đi: quay lại **từ nhịp 3** thành file thứ 2 (lượt nền không ảnh hưởng),
  ghép 2 file nối đuôi — vẫn chỉ 1 mối ghép.
- Hỏng ở nhịp 8-10: quay lại **từ nhịp 8** (tab 3 bấm Run lại là kết quả hiện ngay).

## CHECKLIST XUẤT
- [ ] Nhìn rõ: ô ignore đã tick (nhịp 2) · PDF không bôi đen được (nhịp 3) · dòng CER PASS
  (nhịp 6) · Ctrl-F khớp (nhịp 7)
- [ ] Không khung hình nào lộ API key · ≤10:00 · 1080p
- [ ] Tên file `FTU-VeriTrade_Walkthrough.mp4` + upload bản backup (Drive/YouTube unlisted)
  → điền ô "Screen Recording Backup Link" trên form
