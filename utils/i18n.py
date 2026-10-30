"""Localised messages for responses that reach API clients."""

from __future__ import annotations

from contextvars import ContextVar, Token

SUPPORTED_LOCALES: tuple[str, ...] = ("zh", "en", "vi")
FALLBACK_LOCALE = "zh"

# Request-scoped locale, populated by the Accept-Language middleware in api/app.py.
# Code with no request in scope (e.g. a detached background thread) never sees a
# value set for it and correctly falls back to FALLBACK_LOCALE.
_locale_var: ContextVar[str] = ContextVar("locale", default=FALLBACK_LOCALE)


def get_locale() -> str:
    """Return the current request's locale, or FALLBACK_LOCALE outside a request."""
    return _locale_var.get()


def set_locale(locale: str) -> Token[str]:
    """Set the current-request locale. The caller must reset() the returned token."""
    return _locale_var.set(locale)


def reset_locale(token: Token[str]) -> None:
    _locale_var.reset(token)


MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        "identity.admin_name": "管理员",
        "auth.default_key_name_admin": "管理员密钥",
        "auth.default_key_name_user": "普通用户",
        "auth.key_invalid": "密钥无效或已失效，请重新登录",
        "auth.admin_required": "需要管理员权限才能执行这个操作",
        "auth.user_key_not_found": "这条用户密钥不存在，可能已经被删除",
        "account.not_found": "账号不存在",
        "account.no_email_password": "无邮箱密码",
        "account.no_changes": "还没有检测到改动，请修改后再保存",
        "account.export_incomplete": "没有可导出的完整账号，需要同时有 access_token、refresh_token 和 id_token",
        "filter.sensitive_word": "检测到敏感词，拒绝本次任务",
        "review.unavailable": "AI 审核服务暂时不可用，请稍后重试",
        "review.rejected": "AI 审核未通过，拒绝本次任务",
        "config.webdav_url_required": "启用 WebDAV 图片存储后必须填写 WebDAV URL",
        "config.webdav_password_required": "启用 WebDAV 图片存储后必须填写 WebDAV 密码",
        "auth.key_required": "请输入新的专用密钥",
        "auth.key_conflicts_with_admin": "这个密钥和管理员密钥冲突了，请换一个新的密钥",
        "auth.key_already_exists": "这个专用密钥已经存在，请换一个新的密钥",
        "auth.name_already_used": "这个名称已经在使用中了，换一个更容易区分的名称吧",
        "backup.openssl_missing_encrypt": "当前环境缺少 openssl，无法执行加密备份",
        "backup.openssl_missing_decrypt": "当前环境缺少 openssl，无法解密备份内容",
        "backup.openssl_exec_failed_generic": "openssl 执行失败",
        "backup.encrypt_failed": "加密备份失败：{detail}",
        "backup.decrypt_failed": "解密备份失败：{detail}",
        "backup.config_incomplete": "R2 配置不完整：缺少 {missing}",
        "backup.connect_failed": "连接 R2 失败：HTTP {status}",
        "backup.upload_failed": "上传备份失败：HTTP {status}",
        "backup.delete_failed": "删除备份失败：HTTP {status}",
        "backup.read_failed": "读取备份失败：HTTP {status}",
        "backup.list_failed": "获取备份列表失败：HTTP {status}",
        "backup.key_required": "备份对象 key 不能为空",
        "backup.passphrase_missing_download": "当前未配置加密口令，无法下载并解密已加密备份",
        "backup.already_running": "当前已有备份任务正在执行",
        "backup.passphrase_missing_encrypt": "已启用备份加密，但未设置加密口令",
        "backup.passphrase_missing_view": "当前未配置加密口令，无法查看已加密备份",
        "backup.archive_corrupted": "解析备份压缩包失败，备份可能已损坏",
        "image.webdav_disabled": "WebDAV 图片存储未启用",
        "image.url_parse_failed": "图片 URL 解析失败",
        "oauth.callback_url_parse_failed": "无法解析 callback URL: {exc}",
        "oauth.code_or_callback_missing": "缺少 code 或 callback URL",
        "oauth.session_id_missing": "既未提供 session_id，callback URL 中也未携带 state",
        "oauth.token_exchange_network_error": "换 token 网络异常: {exc}",
        "oauth.access_token_empty": "OpenAI 返回的 access_token 为空",
    },
    "en": {
        "identity.admin_name": "Admin",
        "auth.default_key_name_admin": "Admin key",
        "auth.default_key_name_user": "Regular user",
        "auth.key_invalid": "The key is invalid or has expired, please sign in again",
        "auth.admin_required": "This operation requires administrator permission",
        "auth.user_key_not_found": "This user key was not found, it may have already been deleted",
        "account.not_found": "Account not found",
        "account.no_email_password": "No email or password",
        "account.no_changes": "No changes were detected, please make changes before saving",
        "account.export_incomplete": "No complete accounts to export, access_token, refresh_token and id_token are all required",
        "filter.sensitive_word": "A sensitive word was detected, the request was rejected",
        "review.unavailable": "The AI review service is temporarily unavailable, please retry later",
        "review.rejected": "The AI review did not pass, the request was rejected",
        "config.webdav_url_required": "WebDAV URL is required when WebDAV image storage is enabled",
        "config.webdav_password_required": "WebDAV password is required when WebDAV image storage is enabled",
        "auth.key_required": "Please enter a new dedicated key",
        "auth.key_conflicts_with_admin": "This key conflicts with the admin key, please choose a different one",
        "auth.key_already_exists": "This dedicated key already exists, please choose a different one",
        "auth.name_already_used": "This name is already in use, please choose a more distinguishable name",
        "backup.openssl_missing_encrypt": "openssl is not available in this environment, the encrypted backup cannot run",
        "backup.openssl_missing_decrypt": "openssl is not available in this environment, the backup content cannot be decrypted",
        "backup.openssl_exec_failed_generic": "openssl execution failed",
        "backup.encrypt_failed": "Encrypted backup failed: {detail}",
        "backup.decrypt_failed": "Decrypting the backup failed: {detail}",
        "backup.config_incomplete": "R2 configuration is incomplete: missing {missing}",
        "backup.connect_failed": "Failed to connect to R2: HTTP {status}",
        "backup.upload_failed": "Uploading the backup failed: HTTP {status}",
        "backup.delete_failed": "Deleting the backup failed: HTTP {status}",
        "backup.read_failed": "Reading the backup failed: HTTP {status}",
        "backup.list_failed": "Fetching the backup list failed: HTTP {status}",
        "backup.key_required": "The backup object key cannot be empty",
        "backup.passphrase_missing_download": "No encryption passphrase is configured, the encrypted backup cannot be downloaded and decrypted",
        "backup.already_running": "A backup task is already running",
        "backup.passphrase_missing_encrypt": "Backup encryption is enabled but no passphrase is set",
        "backup.passphrase_missing_view": "No encryption passphrase is configured, the encrypted backup cannot be viewed",
        "backup.archive_corrupted": "Failed to parse the backup archive, the backup may be corrupted",
        "image.webdav_disabled": "WebDAV image storage is not enabled",
        "image.url_parse_failed": "Failed to resolve the image URL",
        "oauth.callback_url_parse_failed": "Failed to parse the callback URL: {exc}",
        "oauth.code_or_callback_missing": "Missing code or callback URL",
        "oauth.session_id_missing": "Neither session_id was provided nor does the callback URL carry state",
        "oauth.token_exchange_network_error": "Network error while exchanging the token: {exc}",
        "oauth.access_token_empty": "OpenAI returned an empty access_token",
    },
    "vi": {
        "identity.admin_name": "Quản trị viên",
        "auth.default_key_name_admin": "Khóa quản trị viên",
        "auth.default_key_name_user": "Người dùng thường",
        "auth.key_invalid": "Khóa không hợp lệ hoặc đã hết hạn, vui lòng đăng nhập lại",
        "auth.admin_required": "Thao tác này cần quyền quản trị viên",
        "auth.user_key_not_found": "Khóa người dùng này không tồn tại, có thể đã bị xóa",
        "account.not_found": "Tài khoản không tồn tại",
        "account.no_email_password": "Không có email hoặc mật khẩu",
        "account.no_changes": "Chưa phát hiện thay đổi nào, vui lòng chỉnh sửa rồi lưu lại",
        "account.export_incomplete": "Không có tài khoản đầy đủ để xuất, cần có đồng thời access_token, refresh_token và id_token",
        "filter.sensitive_word": "Phát hiện từ nhạy cảm, yêu cầu bị từ chối",
        "review.unavailable": "Dịch vụ kiểm duyệt AI tạm thời không khả dụng, vui lòng thử lại sau",
        "review.rejected": "Kiểm duyệt AI không đạt, yêu cầu bị từ chối",
        "config.webdav_url_required": "Cần nhập WebDAV URL khi đã bật lưu trữ ảnh qua WebDAV",
        "config.webdav_password_required": "Cần nhập mật khẩu WebDAV khi đã bật lưu trữ ảnh qua WebDAV",
        "auth.key_required": "Vui lòng nhập khóa riêng mới",
        "auth.key_conflicts_with_admin": "Khóa này trùng với khóa quản trị viên, vui lòng chọn khóa khác",
        "auth.key_already_exists": "Khóa riêng này đã tồn tại, vui lòng chọn khóa khác",
        "auth.name_already_used": "Tên này đang được sử dụng, vui lòng chọn một tên khác dễ phân biệt hơn",
        "backup.openssl_missing_encrypt": "Môi trường hiện tại thiếu openssl, không thể thực hiện sao lưu mã hóa",
        "backup.openssl_missing_decrypt": "Môi trường hiện tại thiếu openssl, không thể giải mã nội dung sao lưu",
        "backup.openssl_exec_failed_generic": "Thực thi openssl thất bại",
        "backup.encrypt_failed": "Sao lưu mã hóa thất bại: {detail}",
        "backup.decrypt_failed": "Giải mã bản sao lưu thất bại: {detail}",
        "backup.config_incomplete": "Cấu hình R2 chưa đầy đủ: thiếu {missing}",
        "backup.connect_failed": "Kết nối R2 thất bại: HTTP {status}",
        "backup.upload_failed": "Tải lên bản sao lưu thất bại: HTTP {status}",
        "backup.delete_failed": "Xóa bản sao lưu thất bại: HTTP {status}",
        "backup.read_failed": "Đọc bản sao lưu thất bại: HTTP {status}",
        "backup.list_failed": "Lấy danh sách bản sao lưu thất bại: HTTP {status}",
        "backup.key_required": "Khóa đối tượng sao lưu không được để trống",
        "backup.passphrase_missing_download": "Chưa cấu hình mật khẩu mã hóa, không thể tải xuống và giải mã bản sao lưu đã mã hóa",
        "backup.already_running": "Đang có một tác vụ sao lưu khác chạy",
        "backup.passphrase_missing_encrypt": "Đã bật mã hóa sao lưu nhưng chưa đặt mật khẩu mã hóa",
        "backup.passphrase_missing_view": "Chưa cấu hình mật khẩu mã hóa, không thể xem bản sao lưu đã mã hóa",
        "backup.archive_corrupted": "Phân tích gói sao lưu thất bại, bản sao lưu có thể đã bị hỏng",
        "image.webdav_disabled": "Lưu trữ ảnh qua WebDAV chưa được bật",
        "image.url_parse_failed": "Không thể phân giải URL hình ảnh",
        "oauth.callback_url_parse_failed": "Không thể phân tích callback URL: {exc}",
        "oauth.code_or_callback_missing": "Thiếu code hoặc callback URL",
        "oauth.session_id_missing": "Không có session_id và callback URL cũng không mang theo state",
        "oauth.token_exchange_network_error": "Lỗi mạng khi đổi token: {exc}",
        "oauth.access_token_empty": "OpenAI trả về access_token rỗng",
    },
}


def parse_accept_language(header: str | None) -> str:
    """Pick the best supported locale from an Accept-Language header."""
    if not header:
        return FALLBACK_LOCALE

    candidates: list[tuple[float, int, str]] = []
    for index, part in enumerate(header.split(",")):
        token, _, params = part.strip().partition(";")
        tag = token.strip().lower()
        if not tag:
            continue
        quality = 1.0
        if params.strip().startswith("q="):
            try:
                quality = float(params.strip()[2:])
            except ValueError:
                quality = 1.0
        # Negative quality sorts highest-first; index breaks ties in source order.
        candidates.append((-quality, index, tag))

    for _, _, tag in sorted(candidates):
        base = tag.split("-")[0]
        if base in SUPPORTED_LOCALES:
            return base
    return FALLBACK_LOCALE


def t(locale_or_key: str, key: str | None = None) -> str:
    """Look up a message, falling back to FALLBACK_LOCALE and then to the key.

    Call as t(key) to use the current request's locale (the ContextVar set by the
    Accept-Language middleware); call as t(locale, key) to force a specific locale
    regardless of the ambient context, which is what code with no request in scope
    (e.g. a detached background thread) should keep doing.
    """
    if key is None:
        locale, key = get_locale(), locale_or_key
    else:
        locale = locale_or_key
    catalog = MESSAGES.get(locale) or MESSAGES[FALLBACK_LOCALE]
    return catalog.get(key) or MESSAGES[FALLBACK_LOCALE].get(key) or key
