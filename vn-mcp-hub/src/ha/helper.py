"""ha_helper — tools chuyên cho Home Assistant voice assistant.

Bổ sung cho HA conversation agent: giờ hoàng đạo, gợi ý format câu lệnh,
tips tránh từ khoá nhập nhằng giữa device names và verbs.

Tools:
- get_hoang_dao_today(): giờ hoàng đạo hôm nay (cho automation kiểu cúng/khai trương)
- check_command_format(text): kiểm tra câu lệnh HA voice có rõ ràng không
- list_command_patterns(): list mẫu câu HA voice tốt
"""

from __future__ import annotations

from datetime import date

from fastmcp import FastMCP

mcp = FastMCP("ha_helper")

# 12 giờ hoàng đạo theo can chi truyền thống VN.
HOANG_DAO_BY_DAY_CHI = {
    "Tý": ["Tý", "Sửu", "Mão", "Ngọ", "Thân", "Dậu"],
    "Sửu": ["Dần", "Mão", "Tỵ", "Thân", "Tuất", "Hợi"],
    "Dần": ["Tý", "Sửu", "Thìn", "Tỵ", "Mùi", "Tuất"],
    "Mão": ["Tý", "Dần", "Mão", "Ngọ", "Mùi", "Dậu"],
    "Thìn": ["Dần", "Thìn", "Tỵ", "Thân", "Dậu", "Hợi"],
    "Tỵ": ["Sửu", "Thìn", "Ngọ", "Mùi", "Tuất", "Hợi"],
    "Ngọ": ["Tý", "Sửu", "Mão", "Ngọ", "Thân", "Dậu"],
    "Mùi": ["Dần", "Mão", "Tỵ", "Thân", "Tuất", "Hợi"],
    "Thân": ["Tý", "Sửu", "Thìn", "Tỵ", "Mùi", "Tuất"],
    "Dậu": ["Tý", "Dần", "Mão", "Ngọ", "Mùi", "Dậu"],
    "Tuất": ["Dần", "Thìn", "Tỵ", "Thân", "Dậu", "Hợi"],
    "Hợi": ["Sửu", "Thìn", "Ngọ", "Mùi", "Tuất", "Hợi"],
}

CHI_HOURS = {
    "Tý": "23:00-01:00", "Sửu": "01:00-03:00", "Dần": "03:00-05:00",
    "Mão": "05:00-07:00", "Thìn": "07:00-09:00", "Tỵ": "09:00-11:00",
    "Ngọ": "11:00-13:00", "Mùi": "13:00-15:00", "Thân": "15:00-17:00",
    "Dậu": "17:00-19:00", "Tuất": "19:00-21:00", "Hợi": "21:00-23:00",
}

CHI_LIST = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]


def _day_chi(d: date) -> str:
    """Tính chi của ngày dương lịch (theo công thức truyền thống)."""
    # Chi của ngày 1/1/2000 là "Quý Mùi" → chi = Mùi (index 7)
    # Chu kỳ chi: ngày sau cộng 1, mod 12.
    delta = (d - date(2000, 1, 1)).days
    return CHI_LIST[(7 + delta) % 12]


@mcp.tool()
def get_hoang_dao_today() -> str:
    """Tính giờ hoàng đạo hôm nay (theo lịch can chi truyền thống VN).

    Returns:
        Danh sách 6 giờ hoàng đạo trong ngày kèm khung giờ dương.
    """
    today = date.today()
    chi = _day_chi(today)
    hoang_dao_chi = HOANG_DAO_BY_DAY_CHI.get(chi, [])
    if not hoang_dao_chi:
        return f"Không tính được giờ hoàng đạo cho ngày {today.isoformat()}."
    lines = [
        f"**Giờ hoàng đạo {today.isoformat()} (ngày {chi}):**",
        "",
    ]
    for c in hoang_dao_chi:
        lines.append(f"- Giờ {c}: {CHI_HOURS[c]}")
    return "\n".join(lines)


@mcp.tool()
def check_command_format(text: str) -> str:
    """Kiểm tra câu lệnh HA voice có dễ hiểu cho intent recognition không.

    Args:
        text: Câu lệnh người dùng (vd: "bật đèn phòng khách").

    Returns:
        Đánh giá + gợi ý cải thiện nếu câu lệnh nhập nhằng.
    """
    t = text.strip().lower()
    issues: list[str] = []
    if len(t) < 5:
        issues.append("Câu quá ngắn — HA có thể không xác định được intent.")
    if len(t) > 100:
        issues.append("Câu quá dài — nên tách thành 2 lệnh ngắn.")
    verbs = ["bật", "tắt", "mở", "đóng", "khoá", "tăng", "giảm", "đặt"]
    if not any(v in t for v in verbs):
        issues.append("Thiếu động từ rõ ràng (bật/tắt/mở/đóng/khoá...).")
    if " và " in t or " thì " in t:
        issues.append("Câu có nhiều mệnh đề — nên tách lệnh.")

    if not issues:
        return f"✅ Câu lệnh '{text}' rõ ràng, HA voice nên hiểu được."
    return f"⚠️ Câu lệnh '{text}' có vấn đề:\n" + "\n".join(f"- {i}" for i in issues)


@mcp.tool()
def list_command_patterns() -> str:
    """Liệt kê các mẫu câu HA voice thường được nhận diện tốt.

    Returns:
        Danh sách mẫu câu kèm ví dụ.
    """
    patterns = [
        ("Bật/tắt thiết bị", "bật đèn phòng khách", "tắt quạt phòng ngủ"),
        ("Đặt giá trị", "đặt nhiệt độ điều hòa 25 độ", "đặt độ sáng đèn 50%"),
        ("Trạng thái", "trạng thái cửa chính", "kiểm tra camera sân"),
        ("Câu hỏi cảm biến", "nhiệt độ phòng khách bao nhiêu", "độ ẩm trong nhà"),
        ("Quy tắc thời gian", "đặt báo thức 6 giờ sáng", "tắt đèn sau 30 phút"),
    ]
    lines = ["**Mẫu câu HA voice tốt:**", ""]
    for name, ex1, ex2 in patterns:
        lines.append(f"- **{name}**:")
        lines.append(f"  - Ví dụ: \"{ex1}\"")
        lines.append(f"  - Ví dụ: \"{ex2}\"")
    return "\n".join(lines)
