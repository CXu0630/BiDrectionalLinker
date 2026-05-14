import re
import json
import os
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import requests
import urllib.parse
import pyperclip
import threading
import queue
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# --- CONFIGURATION ---
WEB_APP_URL = "https://script.google.com/a/macros/andrew.cmu.edu/s/AKfycbwqsMqVfUqh8aYBxWY0rMXmyRj6NSDm-N8ArSh2CdMm1NESjB-B3s7RvKPLmwp-3f-r/exec" # The /exec URL
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/script.external_request"
]
ACCEPTED_TYPES = ["Google Doc", "Medium", "Google Drive PDF"]

class InputObj:
    def __init__(self, doc_type: str, identifier: str, text: str):
        self.doc_type = doc_type
        self.identifier = identifier
        self.text = text

class GDocLinkerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Two-Way Linker")
        self.root.geometry("400x580")
        self.root.configure(bg="white")
        
        self.creds = None
        self.driver = None
        self.ui_queue = queue.Queue()
        self.root.after(100, self._drain_ui_queue)

        # --- UI STYLING ---
        title_label = tk.Label(root, text="Two-Way Linker", fg="royalblue", bg="white", 
                               font=("Segoe UI", 12, "bold"), pady=10)
        title_label.pack(fill="x")

        hr = tk.Frame(root, height=1, bg="whitesmoke")
        hr.pack(fill="x", padx=15, pady=5)

        # --- SOURCE SECTION ---
        # 1. Label (Top)
        self.create_label("Document 1 (ID or Title)")
        
        # 2. Controls Frame: Dropdown & Button (Middle)
        src_controls_frame = tk.Frame(root, bg="white")
        src_controls_frame.pack(fill="x", padx=20, pady=(0, 5))
        
        self.src_dropdown = ttk.Combobox(src_controls_frame, values=ACCEPTED_TYPES, state="readonly", width=15)
        self.src_dropdown.set("Google Doc")
        self.src_dropdown.pack(side="left", padx=(0, 10))
        # self.src_dropdown.bind("<<ComboboxSelected>>", self.on_type_change)
        
        self.src_current_btn = tk.Button(src_controls_frame, text="Find Open Documents", bg="royalblue", fg="white",
                                        font=("Segoe UI", 8, "bold"), relief="flat", padx=10,
                                        command=lambda: self.use_current("source"))
        self.src_current_btn.pack(side="left")

        # 3. Text Entry Box (Bottom)
        self.source_doc_entry = ttk.Combobox(root, values=[], state="normal", width=45)
        self.source_doc_entry.pack(fill="x", padx=20, pady=(0, 10), ipady=3)
        
        self.create_label("Doc 1 Text")
        self.source_text_entry = self.create_entry()

        hr2 = tk.Frame(root, height=1, bg="whitesmoke")
        hr2.pack(fill="x", padx=15, pady=15)

        # --- TARGET SECTION ---
        # 1. Label (Top)
        self.create_label("Document 2 (ID or Title)")
        
        # 2. Controls Frame: Dropdown & Button (Middle)
        tgt_controls_frame = tk.Frame(root, bg="white")
        tgt_controls_frame.pack(fill="x", padx=20, pady=(0, 5))
        
        self.tgt_dropdown = ttk.Combobox(tgt_controls_frame, values=ACCEPTED_TYPES, state="readonly", width=15)
        self.tgt_dropdown.set("Google Doc")
        self.tgt_dropdown.pack(side="left", padx=(0, 10))
        # self.tgt_dropdown.bind("<<ComboboxSelected>>", self.on_type_change)

        self.tgt_current_btn = tk.Button(tgt_controls_frame, text="Find Open Documents", bg="royalblue", fg="white",
                                        font=("Segoe UI", 8, "bold"), relief="flat", padx=10,
                                        command=lambda: self.use_current("target"))
        self.tgt_current_btn.pack(side="left")

        # 3. Text Entry Box (Bottom)
        self.target_doc_entry = ttk.Combobox(root, values=[], state="normal", width=45)
        self.target_doc_entry.pack(fill="x", padx=20, pady=(0, 10), ipady=3)
        
        self.create_label("Doc 2 Text")
        self.target_text_entry = self.create_entry()

        # Submit Button
        self.submit_btn = tk.Button(root, text="Create Bi-Directional Links", bg="royalblue", 
                                   fg="white", font=("Segoe UI", 10, "bold"), relief="flat",
                                   command=self.handle_submit, state="disabled")
        self.submit_btn.pack(pady=20, padx=20, fill="x")

        # Status
        self.status_label = tk.Label(root, text="Initializing...", fg="gray", bg="white", font=("Segoe UI", 9))
        self.status_label.pack(pady=5)

        # Start Initialization
        self.root.after(100, self.initialize_app)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _ui(self, fn, *args, **kwargs):
        self.ui_queue.put((fn, args, kwargs))

    def _drain_ui_queue(self):
        try:
            while True:
                fn, args, kwargs = self.ui_queue.get_nowait()
                fn(*args, **kwargs)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_ui_queue)

    # def on_type_change(self, event=None):
    #     self._toggle_text_entry(self.src_dropdown, self.source_text_entry)
    #     self._toggle_text_entry(self.tgt_dropdown, self.target_text_entry)

    # def _toggle_text_entry(self, dropdown, entry):
    #     selected = dropdown.get()

    #     if selected == "Google Drive PDF":
    #         entry.config(state="normal")
    #         entry.delete(0, tk.END)
    #         entry.config(state="disabled", disabledbackground="#f3f3f3")
    #     else:
    #         entry.config(state="normal", bg="white")

    def create_label(self, text):
        lbl = tk.Label(self.root, text=text.upper(), fg="gray", bg="white", font=("Segoe UI", 8, "bold"))
        lbl.pack(anchor="w", padx=20)

    def create_entry(self):
        entry = tk.Entry(self.root, font=("Segoe UI", 10), bg="white", relief="flat", 
                         highlightthickness=1, highlightbackground="lightgray")
        entry.pack(padx=20, pady=(0, 10), fill="x", ipady=5)
        return entry

    def set_status(self, text, color="gray"):
        self.status_label.config(text=text, fg=color)
        self.root.update_idletasks()

    def get_google_auth(self):
        creds = None
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            with open('token.json', 'w') as token:
                token.write(creds.to_json())
        self.creds = creds
        return creds
    
    def construct_medium_url(self, post_id, text):
        if not text:
            return f"https://medium.com/p/{post_id}"
        else:
            encoded_text = urllib.parse.quote(text)
            return f"https://medium.com/p/{post_id}#:~:text={encoded_text}"

    def initialize_app(self):
        # kick off background init so the UI doesn't freeze
        t = threading.Thread(target=self._initialize_app_worker, daemon=True)
        t.start()

    def _initialize_app_worker(self):
        try:
            self._ui(self.set_status, "Authenticating...")
            self.get_google_auth()

            self._ui(self.set_status, "Starting Browser...")
            chrome_options = Options()
            # chrome_options.add_argument(r"--user-data-dir=C:\Users\HFinchPC\AppData\Local\Google\Chrome\User Data")
            # chrome_options.add_argument("--profile-directory=Profile 4")

            # stabilizers
            # chrome_options.add_argument("--remote-debugging-port=0")
            # chrome_options.add_argument("--no-first-run")
            # chrome_options.add_argument("--no-default-browser-check")
            # chrome_options.add_argument("--disable-background-networking")
            # chrome_options.add_argument("--disable-dev-shm-usage")
            # chrome_options.add_argument("--disable-extensions")
            # chrome_options.add_argument("--disable-gpu")
            # chrome_options.add_argument("--window-size=1200,900")
            # chrome_options.add_argument("--no-sandbox")

            self.driver = webdriver.Chrome(options=chrome_options)

            self._ui(self.submit_btn.config, state="normal")
            self._ui(self.set_status, "Ready", "forestgreen")

        except Exception as e:
            self._ui(self.set_status, f"Init Error: {type(e).__name__}: {e}", "firebrick")

    def _type_to_domain_patterns(self, doc_type: str):
        """
        Returns a list of predicates for URL matching and an ID extractor.
        """
        if doc_type == "Google Doc":
            def is_match(url: str) -> bool:
                return "docs.google.com/document" in url
            def extract_id(url: str) -> str | None:
                m = re.search(r"/d/([a-zA-Z0-9-_]+)", url)
                return m.group(1) if m else None
            return is_match, extract_id

        if doc_type == "Medium":
            def is_match(url: str) -> bool:
                return "medium.com/p" in url
            def extract_id(url: str) -> str | None:
                m = re.search(r"/p/([a-zA-Z0-9-_]+)", url)
                return m.group(1) if m else None
            return is_match, extract_id

        if doc_type == "Google Drive PDF":
            def is_match(url: str) -> bool:
                return "drive.google.com/file" in url
            def extract_id(url: str) -> str | None:
                # Handles /file/d/<id>, open?id=<id>, uc?id=<id>
                m = re.search(r"/file/d/([a-zA-Z0-9-_]+)", url)
                if m: return m.group(1)
                m = re.search(r"[?&]id=([a-zA-Z0-9-_]+)", url)
                if m: return m.group(1)
                return None
            return is_match, extract_id

        # Unknown type
        def is_match(url: str) -> bool:
            return False
        def extract_id(url: str) -> str | None:
            return None
        return is_match, extract_id


    def _collect_open_tabs_for_type(self, doc_type: str):
        """
        Returns list of dicts: [{handle, url, title, id, display}, ...]
        """
        if not self.driver:
            return []

        is_match, extract_id = self._type_to_domain_patterns(doc_type)

        tabs = []
        current = self.driver.current_window_handle

        for handle in self.driver.window_handles:
            try:
                self.driver.switch_to.window(handle)
                url = self.driver.current_url
                if not url or not is_match(url):
                    continue

                tab_id = extract_id(url)
                title = ""
                try:
                    title = self.driver.title or ""
                except Exception:
                    title = ""

                # display string shown in combobox
                if tab_id:
                    display = f"{title} | {tab_id}".strip()
                else:
                    display = f"{title} | {url}".strip()

                tabs.append({
                    "handle": handle,
                    "url": url,
                    "title": title,
                    "id": tab_id,
                    "display": display
                })
            except Exception:
                continue

        # restore
        # try:
        #     self.driver.switch_to.window(current)
        # except Exception:
        #     pass

        # de-dup displays
        seen = set()
        unique = []
        for t in tabs:
            if t["display"] in seen:
                continue
            seen.add(t["display"])
            unique.append(t)

        return unique


    def _set_identifier_dropdown(self, field_type: str, values: list[str], default_text: str | None):
        if field_type == "source":
            box = self.source_doc_entry
        else:
            box = self.target_doc_entry

        box["values"] = values
        if default_text:
            box.set(default_text)
        else:
            box.set("")


    def use_current(self, field_type: str):
        """
        Populate the identifier combobox with all open tabs that match the type currently selected.
        Uses the TYPE DROPDOWN as input, not the current tab type.
        """
        if not self.driver:
            messagebox.showerror("Error", "Browser not connected.")
            return

        if field_type == "source":
            chosen_type = self.src_dropdown.get()
        else:
            chosen_type = self.tgt_dropdown.get()

        tabs = self._collect_open_tabs_for_type(chosen_type)

        if not tabs:
            messagebox.showwarning(
                "No matching tabs",
                f"No open tabs found for type: {chosen_type}"
            )
            return

        displays = [t["display"] for t in tabs]

        # default selection: first tab that yielded an ID; otherwise first tab
        default = None
        for t in tabs:
            if t["id"]:
                default = t["display"]
                # show just the id in the box by default (cleaner)
                break
        if default is None:
            # if no IDs extracted, default to the first display string
            default = displays[0]

        self._set_identifier_dropdown(field_type, displays, default)
        self.set_status(f"{field_type.capitalize()} list populated ({chosen_type})", "forestgreen")

    def _parse_identifier(self, s: str) -> str:
        # If user selected "ID | title", return the ID part.
        return s.split("|", 1)[-1].strip()
    

    def order_pair_by_type(self, objs: list[InputObj]) -> tuple[InputObj, InputObj]:
        if len(objs) != 2:
            raise ValueError("Expected exactly two input objects.")

        for doc_type in ACCEPTED_TYPES:
            matching = [obj for obj in objs if obj.doc_type == doc_type]
            if len(matching) == 1:
                src = matching[0]
                tgt = objs[0] if objs[1] is src else objs[1]
                return src, tgt

        # If both objects have the same type, keep original order
        return objs[0], objs[1]

    def handle_submit(self):
        source_id = self._parse_identifier(self.source_doc_entry.get())
        target_id = self._parse_identifier(self.target_doc_entry.get())
        if not source_id or not target_id:
            messagebox.showwarning("Warning", "Please provide a source and target documents.")
            return
        source_text = self.source_text_entry.get()
        target_text = self.target_text_entry.get()

        if not (source_text and target_text):
            messagebox.showwarning("Warning", "Please provide text input.")
            return

        self.submit_btn.config(state="disabled")
        self.set_status("Linking documents...", "royalblue")

        srcObj = InputObj(self.src_dropdown.get(), source_id, source_text)
        tgtObj = InputObj(self.tgt_dropdown.get(), target_id, target_text)

        obj1, obj2 = self.order_pair_by_type([srcObj, tgtObj])

        if obj1.doc_type == "Google Doc":
            if obj2.doc_type == "Google Doc":
                payload = {
                    "action": "createBiDiDocLink",
                    "srcId": obj1.identifier,
                    "tgtId": obj2.identifier,
                    "srcText": obj1.text,
                    "tgtText": obj2.text
                }
            elif obj2.doc_type == "Medium":
                mediumUrl = self.construct_medium_url(obj2.identifier, obj2.text)
                payload = {
                    "action": "createOutwardDocLink",
                    "srcId": obj1.identifier,
                    "srcText": obj1.text,
                    "tgtUrl": mediumUrl
                }
            elif obj2.doc_type == "Google Drive PDF":
                payload = {
                    "action": "createDocToPdfLink",
                    "srcId": obj1.identifier,
                    "srcText": obj1.text,
                    "tgtId": obj2.identifier,
                    "tgtText": obj2.text
                }

        elif obj1.doc_type == "Medium":
            if obj2.doc_type == "Medium":
                messagebox.showerror("Error", "Linking Medium to Medium is not supported.")
                self.set_status("Linking failed", "firebrick")
                self.submit_btn.config(state="normal")
                return
            elif obj2.doc_type == "Google Drive PDF":
                mediumUrl = self.construct_medium_url(obj1.identifier, obj1.text)
                payload = {
                    "action": "createPdfLink",
                    "srcId": obj2.identifier,
                    "srcText": obj2.text,
                    "tgtUrl": mediumUrl
                }

        elif obj1.doc_type == "Google Drive PDF":
            if obj2.doc_type == "Google Drive PDF":
                payload = {
                    "action": "createBidiPdfLink",
                    "srcId": obj1.identifier,
                    "srcText": obj1.text,
                    "tgtId": obj2.identifier,
                    "tgtText": obj2.text
                }

        if payload is None:
            self.set_status("Linking failed", "firebrick")
            self.submit_btn.config(state="normal")
            messagebox.showerror("Error", "Unsupported document type combination.")
            return

        try:
            self.get_google_auth()
            headers = {"Authorization": f"Bearer {self.creds.token}"}
            response = requests.post(WEB_APP_URL, headers=headers, json=payload)
            res = response.json()
            
            if "error" in res: raise Exception(res["error"])
            
            if "docUrl" in res:
                pyperclip.copy(res["docUrl"])
                self.set_status("Success! Link created, target link copied to clipboard.", "forestgreen")
                messagebox.showinfo("Success", f"Uni-directional link added successfully!\nLink to target copied to clipboard!")
            else:
                self.set_status("Success! Links created.", "forestgreen")
                messagebox.showinfo("Success", "Bi-directional links added successfully!")
        except Exception as e:
            self.set_status("Execution Failed", "firebrick")
            messagebox.showerror("Error", str(e))
        finally:
            self.submit_btn.config(state="normal")

    def on_close(self):
        if self.driver:
            try: self.driver.quit()
            except: pass
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = GDocLinkerApp(root)
    root.mainloop()