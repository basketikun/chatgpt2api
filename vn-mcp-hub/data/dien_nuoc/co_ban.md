# Kiến thức cơ bản điện, nước, điều hòa, chiller

## 1. Kiến thức điện cơ bản

### MCB (Miniature Circuit Breaker)
MCB là cầu dao tự động dùng cho hệ thống điện dân dụng và công nghiệp nhẹ. Chức năng chính: bảo vệ quá tải và ngắn mạch.

- Dòng định mức phổ biến: 6A, 10A, 16A, 20A, 25A, 32A, 40A, 50A, 63A.
- Đường cong tác động: B (3-5 In, dùng cho thiết bị thuần trở), C (5-10 In, dùng cho thiết bị có dòng khởi động cao như đèn LED, máy điều hòa), D (10-20 In, động cơ công suất lớn).
- Số cực: 1P, 1P+N, 2P, 3P, 3P+N, 4P.

### RCBO/RCCB (Aptomat chống giật)
RCCB chỉ chống dòng rò; RCBO kết hợp chống quá tải/ngắn mạch và chống dòng rò trong cùng thiết bị.

- Dòng rò định mức: 30 mA (ổ cắm dân dụng), 100/300 mA (mạch chính tổng).
- Quy tắc lắp đặt: bắt buộc có RCBO hoặc RCCB cho mạch ổ cắm trong nhà tắm, bếp, ngoài trời.

### Aptomat tổng (MCCB)
MCCB dùng cho dòng cao 63A đến vài nghìn A. Có thể chỉnh dòng tác động (adjustable).

### Tính dòng điện
Công thức: I = P / (U × cosφ)

- 1 pha 220V, cosφ = 0.85: I (A) ≈ P (W) / 187
- 3 pha 380V, cosφ = 0.85: I (A) ≈ P (W) / 559

Ví dụ: tải 5 kW 1 pha → dòng ≈ 27 A → chọn MCB 32A loại C.

### Tiết diện dây dẫn theo dòng tải

| Dòng tải (A) | Tiết diện đồng (mm²) | Ứng dụng |
|--------------|----------------------|----------|
| 10 | 1.5 | Đèn, ổ cắm thường |
| 16 | 2.5 | Ổ cắm bếp, máy giặt |
| 25 | 4 | Máy lạnh, bình nóng lạnh |
| 32 | 6 | Tủ lạnh công suất lớn |
| 50 | 10 | Mạch chính nhà ở |
| 63 | 16 | Mạch tổng nhỏ |
| 100 | 25 | Mạch tổng |
| 125 | 35 | Cấp điện 3 pha công nghiệp nhỏ |

Tính ngược: tiết diện S (mm²) ≈ I × L / (K × ΔU%) — K = 56 với đồng, ΔU% giới hạn 5% cho mạch chiếu sáng, 3% cho ổ cắm.

## 2. Kiến thức nước cơ bản

### Áp lực nước cấp
Đơn vị thường dùng: bar, kg/cm², mH₂O. 1 bar ≈ 1 kg/cm² ≈ 10 mH₂O.

- Áp lực mạng cấp đô thị Việt Nam: 1.5-3 bar.
- Áp lực tối thiểu cho thiết bị gia dụng (vòi sen, máy giặt): 0.5 bar.
- Bồn nước trên mái nhà 5m → áp lực ≈ 0.5 bar.

### Đường kính ống nước (PPR/PVC) phổ biến

| DN (mm) | Lưu lượng tối đa (L/phút) | Ứng dụng |
|---------|---------------------------|----------|
| 16 | 8 | Ống chia nhánh nhỏ |
| 20 | 15 | Vòi rửa, vòi sen |
| 25 | 30 | Tuyến cấp tầng |
| 32 | 50 | Tuyến cấp tầng nhiều thiết bị |
| 40 | 80 | Tuyến cấp khối nhà |
| 50 | 130 | Tuyến chính chung cư mini |

### Bơm tăng áp
Loại phổ biến: bơm li tâm tự mồi (Pentax PM45, Wilo PB-088EA, Panasonic A-130JAK).

- Công suất 100-250W cho căn hộ, 370-750W cho nhà 3-4 tầng.
- Cách lắp: lắp sau bồn chứa (downstream), không lắp đẩy trực tiếp từ đồng hồ nước (vi phạm quy định cấp nước đô thị).
- Nguyên lý hoạt động: cảm biến lưu lượng/áp suất kích hoạt khi có vòi mở.

### Bơm chìm hố ga / nước thải
Chọn theo lưu lượng và độ sâu hút (head).

- Hố ga gia đình: 250-750W, head 5-10m.
- Lưu ý: phải có phao chống cạn để tự ngắt khi hết nước.

## 3. Điều hòa không khí (HVAC dân dụng)

### Tính tải điều hòa
Quy tắc thực tế cho phòng ngủ Việt Nam:

- 9 BTU/h cho 1 m² (không có nắng trực tiếp)
- 12 BTU/h cho 1 m² (có cửa sổ hướng tây hoặc tải nhiệt cao)
- Mỗi người trong phòng cộng thêm 600 BTU/h
- Mỗi thiết bị điện tử (TV, PC) cộng thêm 300 BTU/h

Quy tắc chọn nhanh:
- 9000 BTU (1 HP): phòng 9-12 m²
- 12000 BTU (1.5 HP): phòng 13-18 m²
- 18000 BTU (2 HP): phòng 19-25 m²
- 24000 BTU (2.5 HP): phòng 26-35 m²

### Inverter vs Non-inverter
- Inverter: tiết kiệm 30-50% điện ở chế độ chạy ổn định, đắt hơn 20-30%.
- Non-inverter: rẻ, sửa chữa đơn giản, phù hợp dùng < 4 giờ/ngày.

### Bảo dưỡng điều hòa
- Vệ sinh dàn lạnh + dàn nóng 6 tháng/lần (vùng nhiều bụi: 3 tháng/lần).
- Nạp gas khi: hơi lạnh không đủ, dòng tiêu thụ cao, dàn ngoài nóng bất thường.
- Loại gas phổ biến hiện nay: R32 (mới, môi trường), R410A (cũ), R22 (đã ngừng sản xuất).

## 4. Chiller (làm lạnh trung tâm)

### Phân loại theo nguồn nhiệt
- Air-cooled chiller: giải nhiệt bằng không khí (quạt). Đặt ngoài trời. Công suất 5-500 RT.
- Water-cooled chiller: giải nhiệt bằng nước qua tháp giải nhiệt. Hiệu suất cao hơn 10-20%, công suất lớn 100-3000+ RT.

### Đơn vị
- 1 RT (refrigeration ton) = 12000 BTU/h ≈ 3.517 kW lạnh.
- COP (Coefficient of Performance) = công suất lạnh / công suất điện. COP 3.0-4.5 phổ biến cho chiller hiện đại.
- IPLV (Integrated Part Load Value): hiệu suất trung bình theo nhiều mức tải, quan trọng hơn COP định mức.

### Tính tải làm lạnh tòa nhà
Quy tắc thiết kế nhanh:
- Văn phòng: 60-100 W/m² (phụ tải làm lạnh).
- Trung tâm thương mại: 100-150 W/m².
- Khách sạn (phòng ngủ): 80-100 W/m².
- Nhà xưởng có tải nhiệt: tính cụ thể qua phần mềm Carrier HAP, Trace 700.

Ví dụ: tòa văn phòng 5000 m² × 80 W/m² = 400 kW = 114 RT → chọn 2 chiller 60 RT (dự phòng N+1).

### Vận hành chiller
- Nhiệt độ nước lạnh đầu ra (CHWS): thường 7°C.
- Chênh lệch CHWS/CHWR: 5°C (thiết kế cũ), 8-10°C (low-flow design tiết kiệm bơm).
- Khởi động chiller theo quy trình: bơm nước giải nhiệt → bơm nước lạnh → quạt tháp → máy nén.

### Bảo dưỡng chiller
- Vệ sinh dàn ngưng (condenser) 6 tháng/lần — quyết định 70% hiệu suất.
- Lấy mẫu nước giải nhiệt kiểm tra pH, độ cứng, vi sinh vật theo tháng.
- Đại tu máy nén sau 30000-50000 giờ vận hành.

## 5. An toàn hệ thống

### Điện
- Mỗi nhà phải có dây nối đất (PE), điện trở nối đất < 4Ω cho gia đình, < 1Ω cho công nghiệp.
- Cắt điện hoàn toàn trước khi sửa chữa, kiểm tra bằng bút thử điện hoặc đồng hồ vạn năng.

### Nước
- Test áp đường ống mới lắp 1.5 lần áp làm việc, giữ áp 30 phút.
- Mối nối PPR phải hàn đúng nhiệt: 260°C, ngậm 5-7 giây tùy đường kính.

### Điều hòa
- Đường ống gas phải bọc cách nhiệt suốt tuyến.
- Đường thoát nước ngưng phải có độ dốc ≥ 2% để chảy tự nhiên.

### Chiller
- Phòng đặt máy phải có thông gió cưỡng bức để tránh tích tụ gas trong trường hợp rò rỉ.
- Hệ thống cảnh báo: cảm biến rò gas, áp suất bất thường, nhiệt độ cao.
