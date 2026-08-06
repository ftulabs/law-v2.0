# Slide 6 phút — beat map + prompt cho Claude design

Bài nói 6 phút của bạn, cấu trúc 1–2–2–1, bám flow chạy thật. Deck gốc
`Veritrade pitch deck creation.pdf` đã nộp giám khảo 20/7 → **chữ trên slide duplicate giữ nguyên
văn**, chỉ highlight + thêm rail diagram. Claude design lo toàn bộ phần thiết kế, kể cả màu.

**Ràng buộc mới:**
- Slide **1–4** (Title · Executive Summary · Problem Statement · Project Objectives) do người khác
  nói, thời lượng riêng → **giữ nguyên, không rail, không dim**.
- **Bỏ slide Technology & Innovation** khỏi bài nói. Các kỹ thuật trong đó được nói xen vào từng
  phần, neo vào *Backend Logic (1/2)*, *(2/2)* và *Competitive Advantage*.
- Kết luận 1 phút = **3 slide mới**: performance có chart · stack công cụ · future (rào cản → hướng).

---

## Ý tưởng rail diagram

Dải dọc bên phải mọi slide, vẽ đúng luồng chạy:

```
Economy + Pillar
   ZONE 1 · DISCOVERY & FETCH     Discover → Resolve versions → Fetch
   ZONE 2 · EXTRACT & MAP         Extract → Retrieve → Map → Confidence
   ZONE 3 · SCORING               Score
13-column CSV + JSON audit trail
```

Rail giống hệt nhau trên mọi slide, chỉ khác khối nào đang sáng — giám khảo luôn biết đang đứng ở
đâu trong luồng. Năm trạng thái: **active** (đúng bước đang nói, 1 khối/slide) · **related** (nhắc
tới, không phải trọng tâm) · **done** (đã chạy qua) · **upcoming** (chưa tới) · **slot** (khe cắm
vòng 2). Khối active mang caption đổi theo nhịp; dưới rail có một dòng chú thích của nhịp đó.

---

## Beat map — 14 nhịp / 6 phút

| # | Thời gian | Phần | Slide gốc | Highlight | Rail |
|---|---|---|---|---|---|
| 1 | 0:00–0:30 | ① kiến trúc | **System Architecture** | cả dải INPUT → ZONE 1 → ZONE 2 → OUTPUT + *IN PLAIN TERMS* | không khối nào sáng |
| 2 | 0:30–1:00 | ① accuracy | **Evaluation & Performance** | Citation fidelity 100% · Coverage 9/9 · OCR 1.11% · Discovery 14/0 | `CSV` active · `Extract`+`Confidence` related |
| 3 | 1:00–1:30 | ② Zone 1 | **Backend Logic (1/2)** | *1. Discover* — bullet 1 (two query lanes) | `Discover` |
| 4 | 1:30–2:00 | ② Zone 1 | **Backend Logic (1/2)** | *1. Discover* — bullet 2–3 (version resolution, in-force) | `Resolve versions` |
| 5 | 2:00–2:30 | ② Zone 1 | **Backend Logic (1/2)** | *2. Fetch* — cả khối | `Fetch` |
| 6 | 2:30–3:00 | ② Zone 1 | **Competitive Advantage** | thẻ *Survives real portals* | `Fetch` active · `Discover` related |
| 7 | 3:00–3:28 | ③ Zone 2 | **Backend Logic (1/2)** | *3. Extract* — bullet 1 (scan detector, CER) | `Extract` |
| 8 | 3:28–3:56 | ③ Zone 2 | **Backend Logic (1/2)** | *3. Extract* — bullet 2–3 (split, char spans) | `Extract` |
| 9 | 3:56–4:24 | ③ Zone 2 | **Backend Logic (1/2)** | dải dưới *5-signal hybrid retrieval* + dòng grade-all | `Retrieve` |
| 10 | 4:24–4:52 | ③ Zone 2 | **Map & Verify** | *Sibling-aware* + *Cross-model second opinion* + ô ví dụ SG P6-I4 | `Map` active · `Confidence` related |
| 11 | 4:52–5:00 | ③ Zone 3 | **Competitive Advantage** | chỉ thẻ *Zone 3 scoring, polarity included* | `Score` active · `CSV` related |
| 12 | 5:00–5:25 | ④ kết | **Evaluation & Performance** | *Cost per economy* + *Response time* + *Transparency note* | cả pipeline neutral |
| 13 | 5:25–5:37 | ④ kết | **References** | *AI MODELS* + *OPEN-SOURCE LIBRARIES* | cả pipeline neutral |
| 14 | 5:37–6:00 | ④ kết | **Scalability & Impact** | cột *SCALING OUT* + dải *ROUND 2 ROADMAP* | `Discover`+`Extract` ở **slot** |

Nhịp 11 chỉ 8 giây — bấm qua, một câu, đi tiếp.
Nhịp 6 gom cả ba cái bẫy (WAF chặn handshake · AU $search hỏng · Angular shell) vào một thẻ đã có
sẵn chữ trong deck, nên bỏ được slide Technology & Innovation mà không mất câu chuyện mạnh nhất.

---

## Kết luận 1 phút — không slide mới

Cả ba ý bạn muốn nói đều đã có sẵn chữ trong deck, chỉ cần highlight:

- **Performance** → *Evaluation & Performance*, hai ô *Cost per economy* + *Response time*, và
  **Transparency note** — chính đoạn đó liệt kê hạn chế (grader stochastic) kèm ba cách khắc phục
  đã làm (cross-model panel · review queue · result cache). Nói hạn chế bằng chữ deck đã nộp,
  không phải chữ mới.
- **Tools** → *References*, khối *AI MODELS* + *OPEN-SOURCE LIBRARIES*.
- **Future** → *Scalability & Impact*, cột *SCALING OUT* + dải *ROUND 2 ROADMAP*.

Nếu muốn gọn hơn nữa: bỏ nhịp 13, đứng nguyên trên *Scalability & Impact* cả phút cuối, tools nói
miệng.

---

## Prompt sửa (dán tiếp vào phiên Claude design đang chạy)

`prompt-delta.md` → đổi slide theo Tech & Innovation.
`prompt-delta-2.md` → huỷ 3 slide kết mới, quay về duplicate + highlight.

---

## Kiểm nhanh sau khi dựng

1. Slide 1–4 **không đụng gì** — vẫn đúng bản nộp.
2. Chữ trên các slide duplicate không đổi một từ.
3. Vùng bị làm mờ vẫn đọc được khi share Zoom 1080p.
4. Rail nhìn từ xa thấy ngay khối nào sáng.
5. Xuất PDF dự phòng; bấm thử toàn bài có đồng hồ.
