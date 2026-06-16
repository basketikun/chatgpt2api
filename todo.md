# TODO - chatgpt2api 注册机加入 Gmail IMAP 转发支持

- [x] 在 backend `services/register/mail_provider.py` 中实现 `GmailIMAPProvider` 类，对接 Gmail IMAP 并根据收件人/转发人头部进行精准过滤
- [x] 在 `mail_provider.py` 的 `_create_provider` 函数中注册 `gmail_imap` 类型的 provider
- [x] 在 frontend `web/src/app/register/components/register-card.tsx` 中增加 `gmail_imap` 类型的前端选择与配置表单输入
- [x] 测试和验证新加入的 `gmail_imap` 注册逻辑与界面配置
