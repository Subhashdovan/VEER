import asyncio
import os
import json
import random
import pytz
import time
import threading
import sys
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string
from playwright.async_api import async_playwright
from colorama import init, Fore
from templates import WEB_UI_HTML # Import the HTML template
from werkzeug.utils import secure_filename

# --- Global Setup and Configuration ---
init(autoreset=True)
app = Flask(__name__)
colors = [Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]

# Server Configuration (HOSTING SUPPORT)
HOST = '0.0.0.0' 
PORT = int(os.environ.get('PORT', 5000))

# Messaging Global State
tasks = {}
message_indices = {}
MESSAGING_ACTIVE = False 
UPLOAD_FOLDER = 'uploads'

# Create upload directory if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Utility Functions ---

def get_random_color(): return random.choice(colors)
def get_current_time():
    try:
        return datetime.now(pytz.timezone("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def parse_cookies(raw_json_string):
    """Raw JSON cookie string ko Playwright-compatible list mein parse karta hai."""
    try:
        data = json.loads(raw_json_string)
        # Ensure it's a list of cookie objects
        if isinstance(data, list) and all(isinstance(item, dict) for item in data):
            return data
        # Agar single object hai toh list mein wrap karo
        if isinstance(data, dict):
             return [data]
        raise ValueError("Not a valid JSON array or object.")
    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [ERROR] Cookie Parsing Failed: {e}")
        return None

# --- Core Messaging Logic (Playwright) ---

async def switch_account_and_setup(browser, cookies_data):
    """Cookies load karta hai aur Playwright session set karta hai."""
    # Setting viewport for mobile responsiveness on Render
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
        viewport={"width": 412, "height": 892}
    )
    page = await ctx.new_page()
    
    try:
        # Load cookies into context
        await ctx.add_cookies(cookies_data)
        await page.goto("https://www.facebook.com", timeout=60000)
        await page.wait_for_load_state("networkidle", timeout=60000)
        
        # Check if login was successful
        if 'login.php' not in page.url and 'checkpoint' not in page.url:
             print(Fore.GREEN + f"[{get_current_time()}] Cookies loaded successfully. Ready for E2E.")
        else:
             # This is the RED error scenario
             raise Exception("Cookies expired/invalid. Redirected to login.")

        return page
    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [!] Setup Error: {e}")
        # Close browser on failure
        await page.close()
        await ctx.close()
        return None

async def send_media_message_e2e(page, chat_id, captions, file_paths, delay, task_key):
    """E2E chat mein media message bhejta hai by simulating typing and upload."""
    
    try:
        idx = message_indices.setdefault(task_key, 0)
        caption = captions[idx]
        message_indices[task_key] = (idx+1) % len(captions)
        
        print(Fore.YELLOW + f"[{get_current_time()}] [TASK {task_key}] Navigating to {chat_id}...")
        
        await page.goto(f"https://www.facebook.com/messages/t/{chat_id}", timeout=60000)
        
        # 1. Find the file input field (Usually hidden)
        file_input_selector = 'input[type="file"][accept*="image"], input[type="file"][accept*="video"]'
        await page.wait_for_selector(file_input_selector, timeout=10000)

        # 2. Attach files to the input field
        await page.set_input_files(file_input_selector, file_paths)
        print(Fore.GREEN + f"[{get_current_time()}] [TASK {task_key}] Files attached: {len(file_paths)}")
        
        # 3. Wait for the file to process (This wait is CRITICAL for E2E upload)
        await asyncio.sleep(8) 
        
        # 4. Find the caption/send box (Should be visible after file processing)
        box = await page.wait_for_selector('div[role="textbox"][contenteditable="true"]', timeout=10000)
        await box.click()
        
        # 5. Type the caption and send (Enter key)
        await box.type(caption, delay=0.03) 
        await box.press("Enter")
        
        print(Fore.GREEN + f"[{get_current_time()}] [TASK {task_key}] [SUCCESS] Media sent with caption: '{caption[:20]}...'")
        await asyncio.sleep(delay)

    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] [CRITICAL FAIL] Error sending media: {e}")
        await asyncio.sleep(delay + 10)

async def run_task(task_key, cookies_data, chat_id, captions, file_paths, delay):
    """Main asynchronous loop for a single messaging task."""
    
    # Run the main asyncio logic inside a Playwright context
    async with async_playwright() as p:
        # Launch Chromium with headless=False to increase stability on containerized environments
        browser = await p.chromium.launch(
            headless=False, 
            args=['--disable-gpu', '--no-sandbox', '--disable-setuid-sandbox', '--single-process']
        )
        
        page = await switch_account_and_setup(browser, cookies_data)
        
        if not page:
            await browser.close()
            return

        while MESSAGING_ACTIVE:
            try:
                await send_media_message_e2e(page, chat_id, captions, file_paths, delay, task_key)
            except Exception as e:
                print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] Main loop error: {e}. Retrying in 30 seconds.")
                await asyncio.sleep(30)
        
        await browser.close()

def start_messaging_threads(cookies_data, chat_ids_list, captions_list, file_paths, delay):
    """Server se data lekar naye threads mein messaging tasks shuru karta hai."""
    global tasks, MESSAGING_ACTIVE
    
    # 1. Stop existing tasks
    MESSAGING_ACTIVE = False
    time.sleep(1) 
    
    # 2. Start new tasks
    MESSAGING_ACTIVE = True
    tasks.clear()
    message_indices.clear()
    
    task_counter = 1
    threads = []
    
    for chat_id in chat_ids_list:
        task_key = f"Task-{task_counter}"
        
        # Create a thread that runs the asyncio event loop for each task
        def run_asyncio_task(task_key, *args):
            asyncio.run(run_task(task_key, *args))

        thread = threading.Thread(
            target=run_asyncio_task, 
            args=(task_key, cookies_data, chat_id, captions_list, file_paths, delay)
        )
        tasks[task_key] = thread
        threads.append(thread)
        thread.start()
        task_counter += 1
    
    return task_counter - 1

# --- Flask Server Routes (Web UI) ---

@app.route('/')
def home_ui():
    """Web interface ke liye HTML with form."""
    
    status_message = "Server Ready. Messaging Band Hai."
    status_class = "inactive"
    if MESSAGING_ACTIVE:
        status_message = f"ACTIVE: {len(tasks)} tasks chal rahe hain."
        status_class = "active"
    
    # Render the HTML template from templates.py
    return render_template_string(WEB_UI_HTML, status_message=status_message, status_class=status_class)


@app.route('/start', methods=['POST'])
def start_messaging():
    """Form data lekar messaging shuru karta hai."""
    try:
        # Ensure content type is correct for file upload
        if 'multipart/form-data' not in request.content_type:
            raise ValueError("Invalid content type. Expected multipart/form-data.")

        # --- 1. Data Validation and Parsing ---
        raw_cookies = request.form.get('raw_cookies', '').strip()
        delay = float(request.form.get('delay'))
        chat_ids = [i.strip() for i in request.form.get('chat_ids').split('\n') if i.strip()]
        captions = [i.strip() for i in request.form.get('captions').split('\n') if i.strip()]
        
        # Parse cookies
        cookies_data = parse_cookies(raw_cookies)
        if not cookies_data:
             raise ValueError("Cookies could not be parsed. Check JSON format.")

        # --- 2. File Handling (Saving Uploaded Files) ---
        uploaded_files = request.files.getlist('gallery_files')
        
        if not uploaded_files or uploaded_files[0].filename == '':
            raise ValueError("No media files selected for upload.")

        file_paths = []
        for file in uploaded_files:
            if file and file.filename:
                # Use secure_filename to prevent directory traversal attacks
                filename = secure_filename(file.filename)
                full_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(full_path)
                file_paths.append(full_path)
                print(Fore.CYAN + f"[{get_current_time()}] File saved: {filename}")
        
        if not file_paths:
            raise ValueError("Could not save any uploaded files.")


        # --- 3. Start Threads ---
        num_tasks = start_messaging_threads(cookies_data, chat_ids, captions, file_paths, delay)
        
        print(Fore.GREEN + f"\n[{get_current_time()}] --- COMMAND: START ---")
        print(Fore.GREEN + f"[{get_current_time()}] {num_tasks} threads shuru kiye. Files: {len(file_paths)}. Delay: {delay}s")
        
        return render_template_string(WEB_UI_HTML, status_message=f"Messaging Shuru! {num_tasks} tasks chal rahe hain.", status_class="active")

    except ValueError as e:
        error_msg = f"INPUT ERROR: {e}"
        print(Fore.RED + f"[{get_current_time()}] {error_msg}")
        return render_template_string(WEB_UI_HTML, status_message=error_msg, status_class="inactive"), 400

    except Exception as e:
        error_msg = f"CRITICAL SERVER ERROR: {e}"
        print(Fore.RED + f"[{get_current_time()}] {error_msg}")
        # Stop messaging on unrecoverable error
        global MESSAGING_ACTIVE
        MESSAGING_ACTIVE = False
        return render_template_string(WEB_UI_HTML, status_message=error_msg, status_class="inactive"), 500

@app.route('/stop', methods=['POST'])
def stop_messaging():
    """Sabhi messaging tasks ko band karta hai."""
    global MESSAGING_ACTIVE, tasks
    
    if MESSAGING_ACTIVE:
        MESSAGING_ACTIVE = False
        
        print(Fore.RED + f"\n[{get_current_time()}] --- COMMAND: STOP ---")
        print(Fore.RED + f"[{get_current_time()}] Sabhi {len(tasks)} threads ko band karne ka nirdesh diya gaya.")
        
        return render_template_string(WEB_UI_HTML, status_message="Sabhi Messaging Tasks Band Kar Diye Gaye.", status_class="inactive")
    
    return render_template_string(WEB_UI_HTML, status_message="Pehle se hi band hai.", status_class="inactive")

# --- Main Server Execution ---

def run_server():
    """Flask server ko chalaata hai."""
    # Console Banner
    print(Fore.GREEN + "_"*40)
    print(Fore.YELLOW + "  VEER CHOUDHARY'S E2E MEDIA TOOL")
    print(Fore.CYAN + "  CONTROL PANEL (MEDIA READY)")
    print(Fore.GREEN + "_"*40)
    print(Fore.MAGENTA + f"\n[STATUS] Server {HOST}:{PORT} par chal raha hai.")
    print(Fore.YELLOW + "Web Panel Access: Public URL\n")
    print(Fore.YELLOW + "Messaging status console mein dekhein.")
    # Flask server ko chalao
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False) 

if __name__ == '__main__':
    try:
        run_server()
    except KeyboardInterrupt:
        print(Fore.RED + "\nServer aur sabli tasks band kar diye gaye.")
        MESSAGING_ACTIVE = False # Ensure all threads stop
    except Exception as e:
        print(Fore.RED + f"\nCRITICAL SERVER STARTUP ERROR: {e}")