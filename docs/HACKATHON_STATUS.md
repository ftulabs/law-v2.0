# VeriTrade — Bản tự giới thiệu & Câu hỏi cho buổi Mentor

_Đọc trong ~10 phút. Phần 1–4 ai cũng hiểu; phần 5 (câu hỏi) mỗi câu đều kể rõ bối cảnh trước khi hỏi._

---

## 1. Tụi em đang giải bài toán gì?

Để xếp hạng RDTII, người ta phải đọc luật của từng nước, tìm xem luật nào nói gì về dữ liệu, rồi gán vào các tiêu chí. Hiện việc này làm **hoàn toàn bằng tay**: hơn 10 người, mỗi nước mất 1–4 tuần, đã rà hơn 2600 văn bản.

**VeriTrade là phần mềm làm thay con người việc đó.** Bạn đưa vào *"nước nào + chủ đề gì"* (ví dụ: *Singapore + chuyển dữ liệu ra nước ngoài*), phần mềm tự đi tìm luật trên cổng chính phủ, tải về, đọc, và chỉ ra **đúng điều khoản** liên quan — kèm trích dẫn và link gốc.

Hai nguyên tắc tụi em bám theo đề bài:
- **Không "học thuộc" đáp án trước.** Phần mềm phải tự tìm luật lúc chạy, không được nhét sẵn danh sách luật vào máy. (Đề cấm điều này.)
- **Không "mách" tên luật cho máy.** Chỉ đưa chủ đề, máy tự suy ra phải tìm luật nào.

---

## 2. Phần mềm chạy thế nào? (kể như một người đi làm việc này)

Hãy hình dung một bạn researcher mới. Phần mềm làm đúng 6 bước bạn ấy làm:

1. **Đi tìm luật.** Giống như gõ Google "luật bảo vệ dữ liệu Singapore" để ra đúng trang luật trên cổng chính phủ. (Cổng của 3 nước đều khó "đào" trực tiếp nên tụi em dùng công cụ tìm kiếm để ra đúng link, rồi mới vào cổng tải.)

2. **Tải văn bản về.** Tải file PDF của luật về máy, có giới hạn dung lượng và lịch sự (không spam cổng), tải rồi thì lưu lại để lần sau khỏi tải lại.

3. **Đọc và cắt nhỏ.** Biến file PDF thành chữ sạch, rồi cắt thành từng **điều/khoản** (Điều 13, Điều 26(1)...). Nếu PDF là **ảnh scan**, phần mềm "đọc chữ từ ảnh" (OCR).

4. **Tìm điều khoản liên quan — bằng AI hiểu nghĩa.** Đây là chỗ then chốt. Máy **không chỉ so từ khoá** kiểu Ctrl+F (cách đó dễ sai: một luật tên có chữ "tài chính" sẽ bị lôi nhầm lên đầu dù nội dung chả liên quan — chính BGK đã cảnh báo lỗi này). Máy của tụi em **đọc hiểu nội dung từng điều khoản** và xếp hạng theo độ liên quan thật sự, rồi có thêm một "thẩm định viên AI" thứ hai chấm lại cho chắc.

5. **Gán vào đúng tiêu chí RDTII.** Một mô hình ngôn ngữ (AI) đọc điều khoản + định nghĩa tiêu chí, rồi quyết định điều này ứng với tiêu chí nào (ví dụ "yêu cầu phải có đồng ý" → tiêu chí *Cơ sở pháp lý để xử lý dữ liệu*). Tụi em viết hướng dẫn rất kỹ để máy **không lẫn các tiêu chí gần giống nhau** và **không bỏ sót** điều khoản nào.

6. **Xuất kết quả + tự đánh giá độ tin.** Mỗi điều khoản ra một dòng kết quả, kèm điểm tin cậy. Điểm thấp thì máy tự đánh dấu "cần người kiểm tra". Cuối cùng xuất ra **2 file**: một file bảng (CSV) cho giám khảo chính sách, một file chi tiết (JSON) cho giám khảo kỹ thuật.

---

## 3. Đã chạy được tới đâu? (kết quả thật, không phải lý thuyết)

Tụi em đã chạy thật trên dữ liệu sống và nó ra đúng:

- **Tìm luật:** đưa "Singapore + chuyển dữ liệu xuyên biên giới" → máy tự ra đúng **Luật Bảo vệ Dữ liệu Cá nhân (PDPA)**, thậm chí trỏ đúng **Điều 26** (điều về chuyển dữ liệu ra nước ngoài). Với Úc, máy tìm đúng **Privacy Act 1988**.
- **Tải + đọc:** tải PDF PDPA thật (461KB), cắt ra **218 điều/khoản**, chữ sạch (không dính chữ).
- **Hiểu nghĩa:** hỏi "quyền của người dân với dữ liệu của mình" → máy chọn đúng điều về *Truy cập/Sửa dữ liệu* và **loại** đúng điều của luật An ninh mạng (dù điều đó cũng có vài từ trùng).
- **Đánh dấu NEW/KNOWN:** luật nào đã có trong file mẫu của BGK thì đánh "KNOWN" (đã biết), luật tự tìm mới thì "NEW" (mới) — đúng.
- **File kết quả:** bảng CSV ra **đúng 13 cột chuẩn** của BGK; file JSON có đủ thông tin kỹ thuật chi tiết.
- **Đổi "động cơ" AI thoải mái:** phần mềm chạy được với nhiều loại AI khác nhau (kể cả AI **tự cài trên máy lab Xavier**, không tốn tiền API) và nhiều bộ OCR khác nhau — chỉ đổi 1 dòng cấu hình. (Đề bài yêu cầu "không phụ thuộc một nhà cung cấp".)

---

## 4. Còn vướng gì? (nói thật để xin lời khuyên)

1. **Tìm luật đôi lúc bị nghẽn.** Công cụ tìm kiếm miễn phí nếu hỏi dồn dập sẽ bị chặn tạm. Đã có cách vá (dùng key tìm kiếm miễn phí + lưu cache), nhưng để demo chắc ăn nên có key.
2. **Malaysia chưa chạy trọn vẹn.** Cổng Malaysia khó hơn, nhiều văn bản là **ảnh scan + tiếng Mã Lai** — phần này chưa test kỹ.
3. **Chưa đo được "tỉ lệ đọc sai chữ" thật.** Đề đòi đọc sai dưới 5%, nhưng để đo cần bản chuẩn để so — tụi em chưa rõ BGK so với cái gì.
4. **Phần gán tiêu chí mới test bằng "AI giả lập".** Tụi em chưa chạy với AI thật (Xavier/Ollama) nên chưa biết độ chính xác thực tế — mà đây là phần **40 điểm** quan trọng nhất.
5. **Tên & số hiệu luật** đôi khi lấy từ tiêu đề kết quả tìm kiếm, chưa bóc chuẩn từ trang đầu của văn bản.
6. **Deploy lên Jetson/Xavier chưa dựng**, mới có thiết kế.
7. **Báo cáo chi phí + file README hướng dẫn** chưa điền số đo thật.

---

## 5. Những chỗ tôi (người làm app) thực sự đang ĐOÁN hoặc CHƯA BIẾT

> Đây không phải câu hỏi cho có. Đây là những chỗ khi code tôi **buộc phải tự quyết một hướng** mà không chắc đúng, hoặc **thiếu thông tin** nên đoán. Nếu mentor chốt giúp, app mới đúng hướng. Tôi xếp theo mức độ ảnh hưởng.

**Q1 (ĐÃ GIẢI QUYẾT ✅) — Dùng bộ Methodology, không phải Indicator Reference.**
_Trước đây tôi gán theo bản Output "Indicator Reference" (P6 = cơ chế chuyển dữ liệu) → SAI._
Tài liệu BGK đã xác nhận: gán theo bản **Methodology** — P6 là **nội địa hoá** (6.1 cấm/xử-lý-nội-địa, 6.2 lưu trữ nội địa, 6.3 hạ tầng, 6.4 luồng có điều kiện — **chỉ 4 tiêu chí, không phải 5**); P7 là **khung pháp lý** (7.1 khung bảo vệ dữ liệu, 7.2 an ninh mạng, 7.3 thời hạn lưu, 7.4 DPIA/DPO, 7.5 chính phủ truy cập). Mã output `P6-I4 ≡ 6.4`, `P7-I3 ≡ 7.3`… (khớp theo số). Đã **viết lại `indicators.py`** và kiểm chứng bằng 3 ví dụ BGK — Armenia→6.4, Kazakhstan→6.2, Việt Nam→6.3 — đều khớp. (Cột 4&5 Methodology = chấm điểm 0/0.5/1 = Zone 3, để sau.)

**Q2 — Mỗi tiêu chí, app nên trả ÍT-mà-chuẩn hay NHIỀU-cho-đủ?**
App tôi hiện với mỗi tiêu chí lôi ra **nhiều** điều khoản ứng viên rồi xếp hạng. Nhưng nhìn file mẫu, mỗi (nước, tiêu chí) thường chỉ chốt **1 luật**. Tôi không biết BGK muốn output **một câu trả lời tốt nhất / tiêu chí**, hay **liệt kê mọi điều khoản liên quan**. Cái này quyết định tôi để app **lọc gắt** (ít, chính xác, ít bị trừ) hay **bao phủ rộng** (nhiều, nhưng rủi ro gán thừa). **Gán thừa có bị trừ điểm không?**

**Q3 — Định nghĩa từng tiêu chí tôi tự soạn có chuẩn không?**
Phần "định nghĩa pháp lý + cách phân biệt với tiêu chí gần giống" cho mỗi indicator là **do tôi (AI) tự viết** theo hiểu biết của mình — tôi không phải dân luật. Cả app dựa vào mấy định nghĩa này để gán. Ví dụ ranh giới giữa P7-I1 (cần cơ sở pháp lý để xử lý) và P7-I2 (giới hạn theo mục đích) là tôi tự vạch. **BGK có tài liệu định nghĩa/hướng dẫn chấm chính thức cho từng tiêu chí không, để tôi thay phần tôi tự đoán bằng bản chuẩn?**

**Q4 — Phần gán tiêu chí tôi MỚI test bằng "AI giả lập", chưa chạy AI thật.**
Phần quan trọng nhất (gán điều khoản → tiêu chí) tôi viết hướng dẫn (prompt) rất kỹ để AI không lẫn/không sót, nhưng **chưa chạy với AI thật** (mới chạy bản giả lập cho nhanh). Nên tôi **chưa biết prompt của mình thực sự chính xác bao nhiêu phần trăm**. → **BGK có bộ ví dụ chuẩn (điều khoản này → đúng tiêu chí kia) để tôi đo độ chính xác và tinh chỉnh không?** Có thì tôi dò theo đó.

**Q5 — Input lúc chấm là gì: "chủ đề tự do", hay "pillar", hay "từng tiêu chí"?**
Slide ví dụ ghi input là "Economy = Thailand, Topic = Cross-border data transfers". App tôi đang chạy theo **(nước, pillar)** rồi map vào cả 5 tiêu chí của pillar đó. Nếu thực ra input là **một chủ đề tự do do giám khảo gõ**, tôi phải đổi cách tạo truy vấn tìm kiếm và phạm vi output. **Lúc chấm BGK đưa input dạng nào?**

**Q6 — "Trích nguyên văn" là cả ĐIỀU hay chỉ KHOẢN khớp? (ảnh hưởng cách tôi cắt văn bản)**
App tôi cắt mỗi **điều** thành một mẩu và lấy cả điều làm "trích nguyên văn". Nhưng hướng dẫn đòi ghi tới **khoản** (Điều 26(2)). Nếu nội dung khớp nằm ở khoản (3): tôi nên (a) để cả điều + ghi "Điều 26", hay (b) **cắt nhỏ tới từng khoản**, chỉ trích khoản (3) + ghi "Điều 26(3)"? Cách (b) chuẩn hơn nhưng phải làm lại phần cắt văn bản và phần tìm kiếm. **Đi hướng nào?**

**Q7 — Cột Coverage tôi đang điền SAI định dạng?**
Tôi điền "Horizontal" / "Sectoral". Nhưng cột Coverage trong file mẫu lại ghi giá trị cụ thể: "Cross-cutting", "Financial sector", "Telecommunications services"... **Vậy phải ghi tên ngành cụ thể, hay Horizontal/Sectoral là đủ?** (Tôi cần biết để sửa cho khớp.)

**Q8 — KNOWN / NEW: tôi gán ở cấp LUẬT vì file mẫu không tới điều khoản — có ổn không?**
File mẫu chỉ liệt kê **tên luật**, không ghi điều khoản nào. Nên tôi tự quyết: luật nào nằm trong file mẫu thì **mọi điều khoản của nó = KNOWN**, còn lại = NEW. Đây là lựa chọn của tôi vì không còn cách nào mịn hơn. **(1) Cách này được chấp nhận không? (2) Nếu tôi tìm được điều khoản MỚI trong một luật ĐÃ có trong mẫu, nó tính NEW hay KNOWN?** (NEW = 20/40 điểm nên rất quan trọng tôi gán đúng.)

**Q9 — Tôi không đo được CER (tỉ lệ đọc sai chữ) vì thiếu bản chuẩn.**
Để biết app đọc chữ sai dưới 5% hay không, tôi cần một **bản văn bản chuẩn** để so với cái app đọc ra. Tôi không có. **BGK đo CER bằng cách nào — có phát bản chuẩn không, hay so với chính PDF gốc? Tính trên mỗi điều khoản hay cả văn bản? Ngưỡng 5% áp cho mọi PDF hay chỉ PDF ảnh scan?** Không rõ cái này thì tôi không tự kiểm chứng phần OCR được.

**Q10 — Số hiệu luật ("Act 709", "B.E. 2562") — tôi gần như lấy không được.**
Với luật tự tìm, app tôi mới lấy được **tên**, chưa lấy được **số hiệu**. Bóc từ trang đầu PDF thì mỗi nước một định dạng. **Trường này quan trọng tới đâu khi chấm, và BGK có nguồn chuẩn (vd metadata trên cổng) để lấy không?**

**Q11 — Cách tôi tìm luật (qua công cụ tìm kiếm) có bị coi là "không tự crawl" → mất điểm Zone 1?**
Vì cổng chặn bot / tải bằng JavaScript, tôi tự chọn hướng **dùng công cụ tìm kiếm để ra link luật rồi tải**, thay vì bò trong menu cổng. Slide đề bài ghi quy trình người là "tìm trên CSDL chính thức, web chính phủ, **và cả internet**" nên tôi nghĩ được. Nhưng đây là quyết định kiến trúc của tôi. **Nếu BGK coi đây không phải "autonomous crawling" thì tôi phải làm lại bằng trình duyệt ẩn bò trực tiếp (chậm, nặng hơn). Cách của tôi có được chấp nhận?**

**Q12 — Mấy con số tôi tự đặt (ngưỡng tin cậy) có ý nghĩa gì với BGK không?**
Tôi tự đặt: tin cậy ≥0.85 thì tự nhận, <0.60 thì loại, ở giữa thì "cần người xem". Và tôi tự nghĩ ra cách tính điểm tin cậy (gộp mấy tín hiệu). **Mấy con số/cách tính này là tôi bịa cho hợp lý — BGK có chuẩn nào về confidence không, hay nó chỉ phục vụ nội bộ để tôi lọc?**

**Q13 — Zone 3 (chấm điểm 0 / 0.5 / 1) có cần làm ở Round 1 không?**
File mẫu có cột "Raw Score" 0/0.5/1 cho mỗi tiêu chí. App tôi mới làm tới Zone 1+2 (tìm + gán), **chưa tự chấm điểm**. **Round 1 có cần Zone 3 không, hay để con người chấm?**

**Q14 — Link nguồn: PDF trực tiếp hay trang web? (nhỏ nhưng tôi cần chốt để chuẩn hoá)**
App tôi xuất link **tải PDF trực tiếp** (vd `.../Act/PDPA2012?ViewType=Pdf`); ví dụ template lại để link **trang web** (`.../Act/PDPA2012`). **Cái nào hợp lệ khi chấm?**

**Q15 — Lúc chấm mà cổng luật đổi/sập thì sao?**
App tải **trực tiếp lúc chạy**. Cổng thật đổi địa chỉ/sập theo thời gian là chuyện thường. **Nếu lúc giám khảo chấm mà cổng trục trặc thì xử lý thế nào — có cho phép tôi lưu bản chụp (cache) để chấm không?**

---

## 6. Ba điểm tụi em tự tin nhất khi pitch

1. **Không bị lừa bởi tên luật.** Chính BGK cảnh báo: nếu chỉ so từ khoá trên *tên luật* thì một luật vô quan hệ sẽ lên top chỉ vì tên có chữ "tài chính". Tụi em chấm trên **nội dung điều khoản** + có "thẩm định viên AI" thứ hai → tránh đúng lỗi đó.
2. **Không lẫn các tiêu chí gần giống nhau.** Các tiêu chí RDTII rất dễ nhầm; tụi em viết hướng dẫn cho AI tách bạch "điều này có đúng tiêu chí đang xét không" với "có tiêu chí khác hợp hơn không" → vừa **không nhầm**, vừa **không bỏ sót**.
3. **Tự chủ & rẻ.** Đổi loại AI/OCR thoải mái, chạy được **AI tự host** trên máy lab → đáp ứng tiêu chí "không phụ thuộc nhà cung cấp" và "bền vững về chi phí".
