import tkinter as tk
from tkinter import ttk, messagebox
import requests
from bs4 import BeautifulSoup
import threading
import time
import logging
from datetime import datetime
from collections import defaultdict
import os
import yaml
import smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from pathlib import Path
from PIL import ImageTk, Image # <--- 在这里添加这一行
import random
# --- Configuration ---
URL = "https://fcbooking.cse.hku.hk/"
REFRESH_INTERVAL_SECONDS = 60
ALERT_TIMEOUT_SECONDS = 300  # 5 minutes
current_dir = Path(os.path.abspath(__file__)).parent
SECRET_CONFIG_PATH = current_dir / 'secret.yaml'
logo_path = current_dir / 'asset' / 'logos'

# --- Set up Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class TimedAlert(tk.Toplevel):
    """
    A custom pop-up window with a countdown timer.
    Forces itself to the front and correctly handles modality to prevent freezing.
    """
    def __init__(self, parent, title, message, slot_id, on_acknowledge_callback, on_close_callback):
        super().__init__(parent)
        self.transient(parent)

        # --- FINAL SOLUTION FOR POP-UP ---
        # 1. Force the window to be the topmost window, ensuring it's visible.
        self.attributes('-topmost', True)

        self.title(title)
        self.geometry("450x150")
        self.resizable(False, False)

        # 2. Lift the window to the top of the stacking order and force focus.
        self.lift()
        self.focus_force()
        # ------------------------------------

        self.slot_id = slot_id
        self._on_acknowledge_callback = on_acknowledge_callback
        self._on_close_callback = on_close_callback
        self._countdown_seconds = ALERT_TIMEOUT_SECONDS
        self._timer_id = None
        self._acknowledged = False

        # --- Widgets ---
        message_label = ttk.Label(self, text=message, wraplength=430, justify='center')
        message_label.pack(pady=(10, 10), padx=10, fill='x', expand=True)

        self.timer_label = ttk.Label(self, text="")
        self.timer_label.pack(pady=5)

        acknowledge_button = ttk.Button(self, text="Acknowledge & Stop Monitoring", command=self._on_acknowledge)
        acknowledge_button.pack(pady=10)

        # --- Protocol Handlers ---
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._start_countdown()

        # 3. Defer grab_set to prevent the main window from freezing on some OS.
        self.after(500, self.grab_set)

        # 4. (Recommended) After 1 second, turn off the 'topmost' attribute.
        # The window will still be modal and on top of the parent app,
        # but it won't obstruct other unrelated applications.
        self.after(1000, lambda: self.attributes('-topmost', False))

    def _start_countdown(self):
        """Initiates the countdown timer."""
        self._update_timer()

    def _update_timer(self):
        """Updates the countdown label every second."""
        if self._countdown_seconds >= 0:
            mins, secs = divmod(self._countdown_seconds, 60)
            self.timer_label.config(text=f"This window will close and resume monitoring in {mins:02d}:{secs:02d}")
            self._countdown_seconds -= 1
            self._timer_id = self.after(1000, self._update_timer)
        else:
            self._on_close()

    def _on_acknowledge(self):
        """Handles the user clicking the acknowledge button."""
        logging.info(f"User acknowledged slot: {self.slot_id}. Monitoring for this slot will stop.")
        self._acknowledged = True
        if self._on_acknowledge_callback:
            self._on_acknowledge_callback(self.slot_id)
        self._on_close()

    def _on_close(self):
        """Cleans up and closes the window."""
        if self._timer_id:
            self.after_cancel(self._timer_id)
        if not self._acknowledged and self._on_close_callback:
            self._on_close_callback(self.slot_id)
        self.destroy()


class FitnessScheduleMonitor:
    def __init__(self, root):
        self.root = root
        self.root.title("HKU Fitness Centre Monitor")
        self.root.geometry("900x600")

        self.monitoring_thread = None
        self.is_monitoring = threading.Event()
        self.selected_slots = set()
        self.previous_statuses = {}
        self.active_alerts = set()
        
        self.logo_image = None
        
        self.email_enabled = False
        self.email_config = {}
        self.email_max_retries = 3

        self.container = ttk.Frame(self.root)
        self.container.pack(fill='both', expand=True)

        self._create_setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._quit_app)

    def _create_setup_ui(self):
        for widget in self.container.winfo_children():
            widget.destroy()

        # 创建一个容器，使其在窗口中居中
        setup_frame = ttk.Frame(self.container, padding="20")
        setup_frame.pack(expand=True)

        # --- 1. 添加主标题 ---
        title_label = ttk.Label(setup_frame, text="HKU Fitness Centre Monitor", font=("Helvetica", 22, "bold"))
        title_label.pack(pady=(0, 20)) # 顶部和下方的垂直边距

        # --- 2. 添加图片 (Logo) ---
        try:
            # 1. 定义存放Logo的文件夹路径
            logos_dir = logo_path

            # 2. 检查文件夹是否存在，并且不是一个文件
            if os.path.isdir(logos_dir):
                # 3. 获取文件夹中所有支持格式的图片文件名
                supported_formats = ('.png', '.jpg', '.jpeg', '.gif')
                images = [f for f in os.listdir(logos_dir) if f.lower().endswith(supported_formats)]

                # 4. 如果文件夹里有图片，就随机选一张
                if images:
                    # 5. 随机选择一个图片文件名
                    random_logo_name = random.choice(images)
                    # 6. 构建这张图片的完整路径
                    image_path = logos_dir / random_logo_name

                    logging.info(f"随机加载Logo: {random_logo_name}")

                    original_image = Image.open(image_path)
                    resized_image = original_image.resize((200, 200), Image.Resampling.LANCZOS)
                    self.logo_image = ImageTk.PhotoImage(resized_image)
                    
                    image_label = ttk.Label(setup_frame, image=self.logo_image)
                    image_label.pack(pady=10)
                else:
                    # 如果文件夹是空的，打印一条日志
                    logging.warning("'logos' 文件夹是空的，跳过显示图片。")
            else:
                # 如果 'logos' 文件夹不存在，也打印一条日志
                logging.warning("'logos' 文件夹未找到，跳过显示图片。")

        except Exception as e:
            logging.error(f"加载随机图片时出错: {e}")
        
        label = ttk.Label(setup_frame, text="Enable email notifications for available slots?", wraplength=330, justify='center', font=("", 12))
        label.pack(pady=20)
        btn_frame = ttk.Frame(setup_frame)
        btn_frame.pack(pady=10)
        enable_button = ttk.Button(btn_frame, text="Enable Email", command=self._show_email_input_ui)
        enable_button.pack(side='left', padx=10)
        skip_button = ttk.Button(btn_frame, text="Skip", command=self._create_main_ui)
        skip_button.pack(side='left', padx=10)
        
        # --- 3. 添加作者信息 (页脚) ---
        # 创建一个新的 Frame 用于放置页脚信息
        footer_frame = ttk.Frame(setup_frame)
        # 使用 side='bottom' 和 pady 将其推到窗口底部
        footer_frame.pack(side='bottom', pady=(30, 0))
        
        # 将 "Your Name" 和 "your.email@example.com" 替换为您的真实信息
        author_label = ttk.Label(footer_frame, text="Author: Triple Salty Fish")
        author_label.pack()
        
        email_label = ttk.Label(footer_frame, text="Email: ddddennis.chan@gmail.com")
        email_label.pack()

    def _show_email_input_ui(self):
        for widget in self.container.winfo_children():
            widget.destroy()
        input_frame = ttk.Frame(self.container, padding="20")
        input_frame.pack(expand=True)
        label = ttk.Label(input_frame, text="Please enter the recipient's email address:")
        label.pack(pady=(0, 5))
        self.recipient_email_entry = ttk.Entry(input_frame, width=40)
        self.recipient_email_entry.pack(pady=5)
        self.recipient_email_entry.focus_set()
        self.error_label = ttk.Label(input_frame, text="", foreground="red")
        self.error_label.pack(pady=5)
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(pady=10)
        confirm_button = ttk.Button(btn_frame, text="Confirm", command=self._confirm_and_proceed)
        confirm_button.pack(side='left', padx=10)
        back_button = ttk.Button(btn_frame, text="Back", command=self._create_setup_ui)
        back_button.pack(side='left', padx=10)

    def _create_main_ui(self):
        for widget in self.container.winfo_children():
            widget.destroy()
        control_frame = ttk.Frame(self.container, padding="10")
        control_frame.pack(fill='x', side='top')
        schedule_frame = ttk.Frame(self.container, padding="10")
        schedule_frame.pack(fill='both', expand=True)
        status_frame = ttk.Frame(self.container, padding="5")
        status_frame.pack(fill='x', side='bottom')
        self.select_button = ttk.Button(control_frame, text="Select", command=self._select_highlighted)
        self.select_button.pack(side='left', padx=5)
        self.deselect_button = ttk.Button(control_frame, text="Deselect", command=self._deselect_highlighted)
        self.deselect_button.pack(side='left', padx=5)
        self.start_button = ttk.Button(control_frame, text="Start Monitoring", command=self.start_monitoring)
        self.start_button.pack(side='left', padx=5)
        self.stop_button = ttk.Button(control_frame, text="Stop Monitoring", command=self.stop_monitoring, state='disabled')
        self.stop_button.pack(side='left', padx=5)
        self.refresh_button = ttk.Button(control_frame, text="Refresh Now", command=self._force_refresh)
        self.refresh_button.pack(side='left', padx=5)
        self.venues = {
            "CSE Active": {"id": "c10001Content", "tree": None},
            "HKU B-Active": {"id": "c10002Content", "tree": None}
        }
        for i, (name, venue_data) in enumerate(self.venues.items()):
            frame = ttk.LabelFrame(schedule_frame, text=name, padding="10")
            frame.grid(row=0, column=i, sticky="nsew", padx=5, pady=5)
            schedule_frame.grid_columnconfigure(i, weight=1)
            tree = ttk.Treeview(frame, columns=('Time', 'Status'), show='headings', selectmode='browse')
            tree.heading('Time', text='Time')
            tree.heading('Status', text='Availability')
            tree.column('Time', width=150)
            tree.column('Status', width=100, anchor='center')
            tree.pack(fill='both', expand=True)
            tree.bind("<<TreeviewSelect>>", lambda e, venue_name=name: self._on_single_selection(e, venue_name))
            tree.tag_configure('selected', background='yellow')
            venue_data["tree"] = tree
        schedule_frame.grid_rowconfigure(0, weight=1)
        self.status_label = ttk.Label(status_frame, text="Ready. Fetching initial data...", anchor='w')
        self.status_label.pack(fill='x')
        self.root.after(100, self.initial_load)

    def _confirm_and_proceed(self):
        recipient_email = self.recipient_email_entry.get().strip()
        if not recipient_email or "@" not in recipient_email:
            self.error_label.config(text="Please enter a valid email address.")
            return
        required_keys = ['smtp_server', 'smtp_port', 'sender_email', 'sender_password']
        if not os.path.exists(SECRET_CONFIG_PATH):
            self.error_label.config(text=f"Error: '{SECRET_CONFIG_PATH}' not found.")
            return
        try:
            with open(SECRET_CONFIG_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            if not config or not all(key in config for key in required_keys):
                missing = [k for k in required_keys if k not in (config or {})]
                self.error_label.config(text=f"Error: Missing keys in YAML: {', '.join(missing)}")
                return
            if "@" not in config['sender_email']:
                self.error_label.config(text="Error: 'sender_email' in YAML is not a valid email address.")
                return
            self.email_config = config
            self.email_config['recipient_email'] = recipient_email
            self.email_enabled = True
            logging.info(f"Email notifications enabled for recipient: {recipient_email}")
        except (yaml.YAMLError, IOError) as e:
            self.error_label.config(text=f"Error reading '{SECRET_CONFIG_PATH}':\n{e}")
            return
        self._create_main_ui()

    def _on_single_selection(self, event, current_venue_name):
        for venue_name, venue_data in self.venues.items():
            if venue_name != current_venue_name:
                other_tree = venue_data["tree"]
                if other_tree.selection():
                    other_tree.selection_set('')

    def _fetch_and_parse(self):
        try:
            logging.info(f"Fetching data from {URL}")
            response = requests.get(URL, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            parsed_data = defaultdict(list)
            for name, venue_data in self.venues.items():
                content_div = soup.find('div', id=venue_data["id"])
                if not content_div: continue
                current_date = "Unknown Date"
                for element in content_div.find_all(recursive=False):
                    if 'py-2' in element.get('class', []) and 'grey' in element.get('class', []):
                        current_date = element.get_text(strip=True)
                    elif 'border-top' in element.get('class', []):
                        row = element.find('div', class_='row')
                        if row:
                            cols = row.find_all('div', class_='col')
                            if len(cols) >= 2:
                                time_slot = cols[0].get_text(strip=True)
                                status = cols[1].get_text(strip=True)
                                slot_id = f"{name}|{current_date}|{time_slot}"
                                parsed_data[name].append({"id": slot_id, "date": current_date, "time": time_slot, "status": status})
            return parsed_data
        except requests.RequestException as e:
            logging.error(f"Failed to fetch HTML: {e}")
            self._update_status(f"Error: Could not fetch data. Check connection.", "red")
            return None

    def _update_gui(self, data):
        if not data: return
        for name, venue_data in self.venues.items():
            tree = venue_data["tree"]
            current_selection = tree.selection()
            tree.delete(*tree.get_children())
            last_date = None
            for slot in data.get(name, []):
                if slot["date"] != last_date:
                    tree.insert('', 'end', values=(f'--- {slot["date"]} ---', ''), iid=f"date_{slot['date']}", tags=('date',))
                    last_date = slot["date"]
                tags = ('selected',) if slot["id"] in self.selected_slots else ()
                tree.insert('', 'end', values=(slot["time"], slot["status"]), iid=slot["id"], tags=tags)
            if current_selection:
                try:
                    tree.selection_set(current_selection)
                except tk.TclError: # Item might not exist anymore
                    pass
        logging.info("GUI has been updated with the latest data.")

    def _update_status(self, text, color="black"):
        self.status_label.config(text=text, foreground=color)

    def initial_load(self):
        self._force_refresh(initial=True)

    def _force_refresh(self, initial=False):
        def task():
            if not initial:
                self.root.after(0, lambda: self.refresh_button.config(state='disabled'))
                self.root.after(0, lambda: self._update_status("Refreshing..."))
            data = self._fetch_and_parse()
            if data:
                if initial:
                    for venue_slots in data.values():
                        for slot in venue_slots: self.previous_statuses[slot['id']] = slot['status']
                self.root.after(0, self._update_gui, data)
                self.root.after(0, lambda: self._update_status(f"Data loaded successfully. Last updated: {datetime.now().strftime('%H:%M:%S')}"))
            if not initial:
                self.root.after(0, lambda: self.refresh_button.config(state='normal'))
        threading.Thread(target=task, daemon=True).start()

    def _select_highlighted(self):
        for venue_data in self.venues.values():
            tree = venue_data["tree"]
            for item_id in tree.selection():
                if not item_id.startswith("date_"):
                    self.selected_slots.add(item_id)
                    tree.item(item_id, tags=('selected',))
        logging.info(f"Selected slots for monitoring: {self.selected_slots}")

    def _deselect_highlighted(self):
        for venue_data in self.venues.values():
            tree = venue_data["tree"]
            for item_id in tree.selection():
                if item_id in self.selected_slots:
                    self.selected_slots.remove(item_id)
                    tree.item(item_id, tags=())
        logging.info(f"Deselected slots: {self.selected_slots}")

    def start_monitoring(self):
        if self.monitoring_thread and self.monitoring_thread.is_alive(): return
        self.is_monitoring.set()
        self.monitoring_thread = threading.Thread(target=self._monitor_worker, daemon=True)
        self.monitoring_thread.start()
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self._update_status("Monitoring started...")
        logging.info("Monitoring has started.")

    def stop_monitoring(self):
        self.is_monitoring.clear()
        
        # 检查 start_button 是否存在，如果存在再修改它的状态
        if hasattr(self, 'start_button'):
            self.start_button.config(state='normal')
            
        # 同样检查 stop_button
        if hasattr(self, 'stop_button'):
            self.stop_button.config(state='disabled')

        # 同样检查 status_label，因为 _update_status 会用到它
        if hasattr(self, 'status_label'):
            self._update_status("Monitoring stopped.")
            
        logging.info("Monitoring has been stopped by the user.")

    def _show_alert(self, slot_id):
        if slot_id in self.active_alerts: return
        self.active_alerts.add(slot_id)
        if self.email_enabled:
            email_thread = threading.Thread(target=self._send_email_alert, args=(slot_id,), daemon=True)
            email_thread.start()
        message = f"A spot has opened up for:\n\n{slot_id.replace('|', ' - ')}"
        TimedAlert(
            parent=self.root,
            title="Slot Available!",
            message=message,
            slot_id=slot_id,
            on_acknowledge_callback=self._on_alert_acknowledge,
            on_close_callback=self._on_alert_close
        )
        logging.info(f"Alert shown for available slot: {slot_id}")

    def _on_alert_acknowledge(self, slot_id):
        if slot_id in self.selected_slots:
            self.selected_slots.remove(slot_id)
            venue_name = slot_id.split('|')[0]
            if venue_name in self.venues:
                tree = self.venues[venue_name]['tree']
                if tree.exists(slot_id): tree.item(slot_id, tags=())
        if slot_id in self.active_alerts:
            self.active_alerts.remove(slot_id)

    def _on_alert_close(self, slot_id):
        logging.info(f"Alert for {slot_id} closed without acknowledgement. Resuming full monitoring.")
        if slot_id in self.active_alerts:
            self.active_alerts.remove(slot_id)
        if slot_id in self.previous_statuses:
            logging.info(f"Resetting previous status for {slot_id} to FULL to allow re-notification.")
            self.previous_statuses[slot_id] = 'FULL'

    def _monitor_worker(self):
        while self.is_monitoring.is_set():
            logging.info("Monitor thread: Checking for updates...")
            data = self._fetch_and_parse()
            if data:
                self.root.after(0, self._update_gui, data)
                self.root.after(0, lambda: self._update_status(f"Monitoring... Last checked: {datetime.now().strftime('%H:%M:%S')}"))
                flat_data = {slot['id']: slot['status'] for venue in data.values() for slot in venue}
                for slot_id in list(self.selected_slots):
                    prev_status = self.previous_statuses.get(slot_id, 'N/A')
                    new_status = flat_data.get(slot_id, 'N/A')
                    if prev_status.upper() == 'FULL' and new_status.upper() != 'FULL' and new_status != 'N/A':
                        logging.info(f"CHANGE DETECTED! Slot {slot_id} is now available ({new_status}).")
                        self.root.after(0, self._show_alert, slot_id)
                    self.previous_statuses[slot_id] = new_status
            for _ in range(REFRESH_INTERVAL_SECONDS):
                if not self.is_monitoring.is_set(): break
                time.sleep(1)

    def _send_email_alert(self, slot_id):
        if not self.email_enabled: return
        cfg = self.email_config
        slot_details = slot_id.replace('|', ' - ')
        message = MIMEText(f'An appointment slot is now available:\n\n{slot_details}\n\nPlease check the website to book: {URL}', 'plain', 'utf-8')
        message['From'] = formataddr(('HKU Gym Monitor', cfg['sender_email']), 'utf-8')
        message['To'] = formataddr(('Recipient', cfg['recipient_email']), 'utf-8')
        message['Subject'] = Header(f'HKU Gym Slot Available: {slot_details}', 'utf-8')
        for attempt in range(self.email_max_retries):
            try:
                smtp_connection = smtplib.SMTP_SSL(cfg['smtp_server'], cfg['smtp_port'], timeout=15)
                smtp_connection.login(cfg['sender_email'], cfg['sender_password'])
                smtp_connection.sendmail(cfg['sender_email'], [cfg['recipient_email']], message.as_string())
                smtp_connection.quit()
                logging.info(f"Successfully sent email for slot {slot_id} on attempt {attempt + 1}.")
                return
            except Exception as e:
                logging.error(f"Email attempt {attempt + 1} for {slot_id} failed: {e}")
                if attempt < self.email_max_retries - 1:
                    time.sleep(10)
                else:
                    logging.error("All email attempts failed. Disabling email notifications for this session.")
                    self.email_enabled = False
                    self.root.after(0, self._show_email_failure_alert)

    def _show_email_failure_alert(self):
        messagebox.showerror(
            "Email Failure",
            "Failed to send email notification after multiple retries.\n\nEmail functionality has been disabled for this session. Desktop alerts will continue."
        )

    def _quit_app(self):
        self.stop_monitoring()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FitnessScheduleMonitor(root)
    root.mainloop()