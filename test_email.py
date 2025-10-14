import smtplib
from email.mime.text import MIMEText
from email.header import Header
import yaml
from email.utils import formataddr # <--- 导入 formataddr
from pathlib import Path
# 从 YAML 文件读取配置信息
current_dir = Path(__file__).parent
with open(current_dir/'secret.yaml', 'r', encoding='utf-8') as f:
  config = yaml.safe_load(f)

smtp_server = config['smtp_server']
smtp_port = config['smtp_port']
sender_email = config['sender_email']
sender_password = config['sender_password']
recipient_email = config.get('recipient_email')  # 可选：默认收件人

if not recipient_email:
    recipient_email = sender_email  # 如果未指定收件人，则发送给自己

# --- 邮件内容 (保持不变) ---
message = MIMEText('This is a test! Hello, World!', 'plain', 'utf-8')

# --- 关键修改部分：正确设置 From 和 To 标头 ---
# 使用 formataddr 来格式化发件人和收件人信息
# 它会自动处理昵称的编码，并确保整体格式符合 RFC 标准
message['From'] = formataddr(('发件人昵称', sender_email), 'utf-8')
message['To'] = formataddr(('收件人昵称', recipient_email), 'utf-8')

# --- 主题设置 (可以保持不变，但用 formataddr 也是好习惯) ---
message['Subject'] = Header('邮件主题', 'utf-8')


# --- 发送逻辑 (保持不变) ---
try:
    smtp_connection = smtplib.SMTP_SSL(smtp_server, smtp_port)
    # 如果不需要调试信息，可以注释掉下面这行
    # smtp_connection.set_debuglevel(1) 
    smtp_connection.login(sender_email, sender_password)
    smtp_connection.sendmail(sender_email, [recipient_email], message.as_string())
    smtp_connection.quit()
    
    print("邮件发送成功！")
    print(f"发件人: {message['From']}, 收件人: {message['To']}, 主题: {message['Subject']}")
    

except Exception as e:
    print(f"邮件发送失败：{e}")