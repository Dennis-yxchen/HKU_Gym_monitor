import tkinter as tk
from tkinter import ttk, messagebox
import requests
from bs4 import BeautifulSoup
import threading
import time
import logging
from datetime import datetime
from collections import defaultdict

# --- Configuration ---
URL = "https://fcbooking.cse.hku.hk/"
# Time in seconds between each check when monitoring is active.
REFRESH_INTERVAL_SECONDS = 60

# --- Set up Logging ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class FitnessScheduleMonitor:
    def __init__(self, root):
        """
        Initializes the GUI application.
        """
        self.root = root
        self.root.title("HKU Fitness Centre Monitor")
        self.root.geometry("900x600")

        # --- State Management ---
        self.monitoring_thread = None
        self.is_monitoring = threading.Event()
        self.selected_slots = set()
        self.previous_statuses = {}

        # --- GUI Setup ---
        self._create_widgets()
        
        # --- Initial Data Load ---
        self.root.after(100, self.initial_load)
        
        # --- Handle graceful shutdown ---
        self.root.protocol("WM_DELETE_WINDOW", self._quit_app)

    def _create_widgets(self):
        """
        Creates and arranges all the GUI elements.
        """
        # --- Main Frames ---
        control_frame = ttk.Frame(self.root, padding="10")
        control_frame.pack(fill='x', side='top')

        schedule_frame = ttk.Frame(self.root, padding="10")
        schedule_frame.pack(fill='both', expand=True)
        
        status_frame = ttk.Frame(self.root, padding="5")
        status_frame.pack(fill='x', side='bottom')

        # --- Control Buttons ---
        self.select_button = ttk.Button(control_frame, text="Select", command=self._select_highlighted)
        self.select_button.pack(side='left', padx=5)

        self.deselect_button = ttk.Button(control_frame, text="Deselect", command=self._deselect_highlighted)
        self.deselect_button.pack(side='left', padx=5)

        self.start_button = ttk.Button(control_frame, text="Start Monitoring", command=self.start_monitoring)
        self.start_button.pack(side='left', padx=5)

        self.stop_button = ttk.Button(control_frame, text="Stop Monitoring", command=self.stop_monitoring, state='disabled')
        self.stop_button.pack(side='left', padx=5)

        # --- Treeview Setup ---
        self.venues = {
            "CSE Active": {"id": "c10001Content", "tree": None},
            "HKU B-Active": {"id": "c10002Content", "tree": None}
        }

        for i, (name, venue_data) in enumerate(self.venues.items()):
            frame = ttk.LabelFrame(schedule_frame, text=name, padding="10")
            frame.grid(row=0, column=i, sticky="nsew", padx=5, pady=5)
            schedule_frame.grid_columnconfigure(i, weight=1)
            
            tree = ttk.Treeview(frame, columns=('Time', 'Status'), show='headings', selectmode='extended')
            tree.heading('Time', text='Time')
            tree.heading('Status', text='Availability')
            tree.column('Time', width=150)
            tree.column('Status', width=100, anchor='center')
            tree.pack(fill='both', expand=True)
            
            # Style for selected rows
            tree.tag_configure('selected', background='yellow')
            
            venue_data["tree"] = tree
            
        schedule_frame.grid_rowconfigure(0, weight=1)

        # --- Status Bar ---
        self.status_label = ttk.Label(status_frame, text="Ready. Fetching initial data...", anchor='w')
        self.status_label.pack(fill='x')

    def _fetch_and_parse(self):
        """
        Fetches HTML from the URL and parses it to extract schedule data.
        Returns a dictionary with the structured schedule.
        """
        try:
            logging.info(f"Fetching data from {URL}")
            response = requests.get(URL, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            parsed_data = defaultdict(list)
            for name, venue_data in self.venues.items():
                content_div = soup.find('div', id=venue_data["id"])
                if not content_div:
                    continue

                current_date = "Unknown Date"
                for element in content_div.find_all(recursive=False):
                    # Date headers have this specific class combination
                    if 'py-2' in element.get('class', []) and 'grey' in element.get('class', []):
                        current_date = element.get_text(strip=True)
                    # Slot rows are in divs with this class
                    elif 'border-top' in element.get('class', []):
                        row = element.find('div', class_='row')
                        if row:
                            cols = row.find_all('div', class_='col')
                            if len(cols) >= 2:
                                time_slot = cols[0].get_text(strip=True)
                                status = cols[1].get_text(strip=True)
                                # Generate a unique ID for each slot for tracking
                                slot_id = f"{name}|{current_date}|{time_slot}"
                                parsed_data[name].append({
                                    "id": slot_id,
                                    "date": current_date,
                                    "time": time_slot,
                                    "status": status,
                                })
            return parsed_data
        except requests.RequestException as e:
            logging.error(f"Failed to fetch HTML: {e}")
            self._update_status(f"Error: Could not fetch data. Check connection.", "red")
            return None

    def _update_gui(self, data):
        """
        Populates the Treeview widgets with fresh data. This function is thread-safe.
        """
        if not data:
            return

        for name, venue_data in self.venues.items():
            tree = venue_data["tree"]
            # Clear existing items
            tree.delete(*tree.get_children())
            
            # Insert new data
            last_date = None
            for slot in data.get(name, []):
                # Add a date separator
                if slot["date"] != last_date:
                    tree.insert('', 'end', values=(f'--- {slot["date"]} ---', ''), iid=f"date_{slot['date']}", tags=('date',))
                    last_date = slot["date"]

                # Apply 'selected' tag if the slot is being monitored
                tags = ('selected',) if slot["id"] in self.selected_slots else ()
                tree.insert('', 'end', values=(slot["time"], slot["status"]), iid=slot["id"], tags=tags)
        
        logging.info("GUI has been updated with the latest data.")
        
    def _update_status(self, text, color="black"):
        """ Safely updates the status bar label from any thread. """
        self.status_label.config(text=text, foreground=color)

    def initial_load(self):
        """
        Performs the first data load and populates the GUI.
        """
        def task():
            data = self._fetch_and_parse()
            if data:
                # Store initial statuses for comparison later
                for venue_slots in data.values():
                    for slot in venue_slots:
                        self.previous_statuses[slot['id']] = slot['status']
                
                # Update GUI in the main thread
                self.root.after(0, self._update_gui, data)
                self.root.after(0, self._update_status, f"Initial data loaded successfully. Last updated: {datetime.now().strftime('%H:%M:%S')}")
        
        # Run the initial load in a separate thread to avoid freezing the GUI on start
        threading.Thread(target=task, daemon=True).start()

    def _select_highlighted(self):
        """ Adds the user-highlighted slots to the monitoring set. """
        for venue_data in self.venues.values():
            tree = venue_data["tree"]
            for item_id in tree.selection():
                if not item_id.startswith("date_"): # Ignore date separators
                    self.selected_slots.add(item_id)
                    tree.item(item_id, tags=('selected',))
        logging.info(f"Selected slots for monitoring: {self.selected_slots}")
        
    def _deselect_highlighted(self):
        """ Removes the user-highlighted slots from the monitoring set. """
        for venue_data in self.venues.values():
            tree = venue_data["tree"]
            for item_id in tree.selection():
                if item_id in self.selected_slots:
                    self.selected_slots.remove(item_id)
                    tree.item(item_id, tags=())
        logging.info(f"Deselected slots: {self.selected_slots}")

    def start_monitoring(self):
        """ Starts the background monitoring thread. """
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            logging.warning("Monitoring is already active.")
            return
            
        self.is_monitoring.set()
        self.monitoring_thread = threading.Thread(target=self._monitor_worker, daemon=True)
        self.monitoring_thread.start()
        
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self._update_status("Monitoring started...")
        logging.info("Monitoring has started.")

    def stop_monitoring(self):
        """ Stops the background monitoring thread. """
        self.is_monitoring.clear()
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self._update_status("Monitoring stopped.")
        logging.info("Monitoring has been stopped by the user.")
        
    def _show_alert(self, slot_id):
        """
        Shows a pop-up alert and automatically deselects the slot.
        """
        # Deselect logic
        if slot_id in self.selected_slots:
            self.selected_slots.remove(slot_id)
        
        # Display message
        message = f"A spot has opened up for:\n\n{slot_id.replace('|', ' - ')}\n\nThis slot has been removed from monitoring."
        messagebox.showinfo("Slot Available!", message)
        logging.info(f"Alert shown for available slot: {slot_id}")

    def _monitor_worker(self):
        """ The main loop for the background monitoring thread. """
        while self.is_monitoring.is_set():
            logging.info("Monitor thread: Checking for updates...")
            
            data = self._fetch_and_parse()
            if data:
                # Update GUI in the main thread
                self.root.after(0, self._update_gui, data)
                self.root.after(0, self._update_status, f"Monitoring... Last checked: {datetime.now().strftime('%H:%M:%S')}")

                # Check for availability changes in selected slots
                flat_data = {slot['id']: slot['status'] for venue in data.values() for slot in venue}
                
                for slot_id in list(self.selected_slots): # Iterate on a copy
                    prev_status = self.previous_statuses.get(slot_id, 'N/A')
                    new_status = flat_data.get(slot_id, 'N/A')

                    if prev_status.upper() == 'FULL' and new_status.upper() != 'FULL' and new_status != 'N/A':
                        logging.info(f"CHANGE DETECTED! Slot {slot_id} is now available ({new_status}).")
                        # Schedule alert in the main thread
                        self.root.after(0, self._show_alert, slot_id)
                    
                    # Update the status for the next comparison
                    self.previous_statuses[slot_id] = new_status
            
            # Wait for the next interval, but check for stop signal every second
            for _ in range(REFRESH_INTERVAL_SECONDS):
                if not self.is_monitoring.is_set():
                    break
                time.sleep(1)

    def _quit_app(self):
        """ Handles application closing. """
        self.stop_monitoring()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FitnessScheduleMonitor(root)
    root.mainloop()