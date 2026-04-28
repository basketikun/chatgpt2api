from __future__ import annotations

from services.user_service import QuotaReservation, UserServiceError


def reserve_image_quota(identity: dict[str, object], requested_count: int, endpoint: str) -> QuotaReservation:
    from services.user_service import user_service

    return user_service.reserve_image_quota(identity, requested_count, endpoint)


def settle_image_quota(
    reservation: QuotaReservation | None,
    *,
    success: bool,
    actual_count: int = 0,
    error: str = "",
) -> None:
    from services.user_service import user_service

    user_service.settle_image_quota(
        reservation,
        success=success,
        actual_count=actual_count,
        error=error,
    )


def count_images(value: object) -> int:
    if isinstance(value, dict):
        count = 0
        data = value.get("data")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and (item.get("b64_json") or item.get("url")):
                    count += 1
            if count:
                return count
        for key, item in value.items():
            if key in {"b64_json", "url"} and item:
                count += 1
            elif key != "data":
                count += count_images(item)
        return count
    if isinstance(value, list):
        return sum(count_images(item) for item in value)
    return 0


def openai_quota_error(exc: UserServiceError) -> dict[str, object]:
    code = "insufficient_quota" if exc.code == "insufficient_quota" else exc.code
    error_type = "insufficient_quota" if exc.code == "insufficient_quota" else "rate_limit_exceeded"
    return {
        "error": {
            "message": exc.message,
            "type": error_type,
            "param": None,
            "code": code,
        }
    }
