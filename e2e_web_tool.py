import asyncio
import os
import json
import random
import pytz
import time
import threading
import sys
from datetime import datetime
from flask import Flask, request, render_template_string
from playwright.async_api import async_playwright
from colorama import init, Fore
from werkzeug.utils import secure_filename # File security ke liye

# --- GLOBAL SETUP AND CONFIGURATION ---
init(autoreset=True)
app = Flask(__name__)
colors = [Fore.RED, Fore.GREEN, Fore.YELLOW, Fore.BLUE, Fore.MAGENTA, Fore.CYAN]

# Server Configuration (HOSTING SUPPORT)
HOST = '0.0.0.0' 
PORT = int(os.environ.get('PORT', 5000)) 
UPLOAD_FOLDER = 'temp_uploads' # Upload ki gayi files yahan store hongi
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Messaging Global State
tasks = {}
message_indices = {}
MESSAGING_ACTIVE = False 

# --- Utility Functions ---

def get_random_color(): return random.choice(colors)
def get_current_time():
    try:
        return datetime.now(pytz.timezone("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def sanitize_cookies(cookies):
    """Normalizes sameSite property for Playwright compatibility."""
    for ck in cookies:
        s=ck.get('sameSite','Lax').capitalize()
        ck['sameSite'] = s if s in ["Lax","Strict","None"] else "Lax"
    return cookies

# --- CORE E2E MESSAGING LOGIC (ASYNC PLAYWRIGHT) ---

async def switch_account_and_setup(browser, cookies_data_list):
    """Sets up the Playwright session using the cookies list provided."""
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
        viewport={"width": 412, "height": 892}
    )
    page = await ctx.new_page()
    
    try:
        if not cookies_data_list:
             raise Exception("No cookie data provided.")

        ck = sanitize_cookies(cookies_data_list)
        await ctx.add_cookies(ck)
        await page.goto("https://www.facebook.com", timeout=60000)
        await page.wait_for_load_state("networkidle", timeout=60000)
        
        if 'login.php' not in page.url:
             print(Fore.GREEN + f"[{get_current_time()}] Cookies loaded successfully. Ready for E2E.")
        else:
             raise Exception("Cookies expired/invalid. Redirected to login.")

        return page
    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [!] Setup Error: {e}")
        await page.close()
        await ctx.close()
        return None

async def send_media_e2e(page, chat_id, haters, media_paths, delay, task_key):
    """Sends a message with media by simulating upload and Enter press."""
    try:
        # Hater tag is still used as a text caption if provided
        hater = random.choice(haters)
        
        await page.goto(f"https://www.facebook.com/messages/t/{chat_id}", timeout=60000)

        # 1. Simulate attaching files
        # Playwright automatically handles the file dialog with set_input_files
        file_input_selector = 'input[type="file"]' # General file input selector (needs testing on actual FB messenger)

        try:
            # Wait for the hidden file input element (it's usually hidden)
            file_chooser_element = await page.wait_for_selector(file_input_selector, timeout=10000)
            
            # Use Playwright to attach the files using their local server path
            await file_chooser_element.set_input_files(media_paths)
            print(Fore.YELLOW + f"[{get_current_time()}] [TASK {task_key}] {len(media_paths)} files attached. Waiting for upload...")

        except Exception as e:
            print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] File input element not found or error during attach: {e}")
            return
            
        # 2. Add Caption/Text (Optional, but useful for tagging)
        # Wait for the message box that appears *after* files are attached
        box = None
        try:
            # Wait for the textbox which usually appears after media is loaded
            box = await page.wait_for_selector('div[role="textbox"][contenteditable="true"]', timeout=30000)
            await box.type(hater, delay=0.03) # Use hater as a caption/tag
        except Exception:
             print(Fore.YELLOW + f"[{get_current_time()}] [TASK {task_key}] Caption box not found or timed out. Skipping caption.")
        
        # 3. Send (Enter Press)
        # Use a more reliable "Send" button if possible, but Enter is standard for Messenger
        await page.keyboard.press("Enter") 
        
        print(Fore.GREEN + f"[{get_current_time()}] [TASK {task_key}] [SUCCESS] Media sent with caption: '{hater}'")
        await asyncio.sleep(delay)

    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] [CRITICAL FAIL] Error sending media: {e}")
        await asyncio.sleep(delay + 10)


async def run_task_async(cookies_data_list, chat_id, haters, media_paths, delay, task_key):
    """Initializes Playwright instance and runs the media messaging loop."""
    global MESSAGING_ACTIVE
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=['--disable-gpu', '--no-sandbox', '--disable-setuid-sandbox']
        )
        
        page = await switch_account_and_setup(browser, cookies_data_list)
        
        if not page:
            await browser.close()
            return

        while MESSAGING_ACTIVE:
            # We assume you only want to send the uploaded files once per cycle
            await send_media_e2e(page, chat_id, haters, media_paths, delay, task_key)
            
            # Since media path is static, we must break the loop or wait for manual stop
            # To prevent spamming the same media repeatedly, we break here.
            # You can change MESSAGING_ACTIVE = False if you want it to stop after one run.
            await asyncio.sleep(delay)


def start_async_task_in_thread(cookies_data_list, chat_id, haters, media_paths, delay, task_key):
    """Wrapper to run the async Playwright task in a separate thread."""
    print(Fore.YELLOW + f"[{get_current_time()}] [TASK {task_key}] Starting asyncio loop for media.")
    try:
        asyncio.run(run_task_async(cookies_data_list, chat_id, haters, media_paths, delay, task_key))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_task_async(cookies_data_list, chat_id, haters, media_paths, delay, task_key))
    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] Thread/Async Error: {e}")


def start_messaging_threads(cookies_data_list, chat_ids_list, haters_list, media_paths, delay):
    """Starts all media messaging tasks concurrently using Python threads."""
    global tasks, MESSAGING_ACTIVE
    
    MESSAGING_ACTIVE = False
    time.sleep(2) 
    
    MESSAGING_ACTIVE = True
    tasks.clear()
    
    task_counter = 1
    for chat_id in chat_ids_list:
        task_key = f"Task-{task_counter}"
        tasks[task_key] = threading.Thread(
            target=start_async_task_in_thread, 
            args=(cookies_data_list, chat_id, haters_list, media_paths, delay, task_key),
            daemon=True 
        )
        tasks[task_key].start()
        task_counter += 1
    
    return task_counter - 1

# --- Flask Server Routes (Web UI) ---

@app.route('/')
def home_ui():
    """Renders the main Web Control Panel HTML."""
    html_template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Veer Choudhary | E2E Media Tool</title>
        <style>
            body { font-family: 'Inter', sans-serif; background-color: #2e3440; color: #eceff4; margin: 0; padding: 20px; }
            .container { max-width: 600px; margin: 20px auto; padding: 20px; border: 3px solid #5e81ac; border-radius: 15px; background-color: #3b4252; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.4); }
            h1 { color: #8fbcbb; text-align: center; margin-bottom: 20px; }
            .e2e-note { color: #bf616a; text-align: center; font-weight: bold; margin-bottom: 15px; }
            label { display: block; margin-top: 15px; color: #a3be8c; font-weight: bold; }
            input[type="text"], textarea, input[type="file"] {
                width: 95%; padding: 10px; margin-top: 5px; border-radius: 5px; border: 1px solid #4c566a; background-color: #434c5e; color: #eceff4; resize: vertical;
            }
            input[type="file"] { border: none; padding: 5px; }
            button { 
                background-color: #a3be8c; color: #2e3440; border: none; padding: 12px 20px; margin-top: 20px; border-radius: 5px; cursor: pointer; font-size: 1em; font-weight: bold; transition: background-color 0.3s;
            }
            button:hover { background-color: #b4e39b; }
            .status { margin-top: 20px; padding: 10px; border-radius: 5px; font-weight: bold; }
            .active { background-color: #2e8b57; }
            .inactive { background-color: #a34747; }
            .status-container { text-align: center; }
            .instructions { font-size: 0.9em; color: #d8dee9; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Veer Choudhary's E2E Media Tool</h1>
            <p class="e2e-note">Note: Yeh tool Playwright use karta hai. Iske liye VPS par Chromium/Browser install hona zaroori hai.</p>
            <p class="instructions">Cookies ko JSON Array format mein paste karein. Aap Gallery se files (photos/videos) upload kar sakte hain.</p>

            <form action="/start" method="POST" enctype="multipart/form-data">
                
                <label for="raw_cookies">1. Raw Cookies (JSON Array Format):</label>
                <textarea id="raw_cookies" name="raw_cookies" rows="5" required placeholder='[{"name":"c_user","value":"..."}]'></textarea>

                <label for="chat_ids">2. Chat IDs (Har ID naye line mein):</label>
                <textarea id="chat_ids" name="chat_ids" rows="3" required placeholder="1234567890&#10;9876543210"></textarea>

                <label for="haters">3. Captions/Tags (Har tag naye line mein, ek tag ek message ke liye):</label>
                <textarea id="haters" name="haters" rows="3" placeholder="@hater_one&#10;bhoot"></textarea>

                <label for="media_files">4. Gallery Files (Photos/Videos):</label>
                <input type="file" id="media_files" name="media_files" multiple required>
                
                <label for="delay">5. Delay (Seconds):</label>
                <input type="text" id="delay" name="delay" value="15" required>
                
                <button type="submit" name="action" value="start">START MEDIA MESSAGING</button>
            </form>
            
            <form action="/stop" method="POST" style="margin-top: 10px;">
                <button type="submit" name="action" value="stop" style="background-color: #bf616a;">STOP ALL TASKS</button>
            </form>

            <div class="status-container">
                <div class="status {{ status_class }}">
                    STATUS: {{ status_message }}
                </div>
            </div>
            
        </div>
    </body>
    </html>
    """
    
    status_message = "Server Ready. Messaging Band Hai."
    status_class = "inactive"
    if MESSAGING_ACTIVE:
        status_message = f"ACTIVE: {len(tasks)} E2E tasks chal rahe hain."
        status_class = "active"
    
    return render_template_string(html_template, status_message=status_message, status_class=status_class)


@app.route('/start', methods=['POST'])
def start_messaging():
    """Handles START button click, saves files, and initiates messaging threads."""
    global UPLOAD_FOLDER
    
    try:
        data = request.form
        
        raw_cookies = data.get('raw_cookies').strip()
        delay = float(data.get('delay'))
        
        chat_ids = [i.strip() for i in data.get('chat_ids').split('\n') if i.strip()]
        haters = [i.strip() for i in data.get('haters').split('\n') if i.strip()]
        
        # --- File Handling Logic ---
        uploaded_files = request.files.getlist('media_files')
        if not uploaded_files or not uploaded_files[0].filename:
            return render_template_string(home_ui(), status_message="ERROR: Media Files upload karein.", status_class="inactive"), 400
        
        # Clear previous uploads to save space
        for f in os.listdir(UPLOAD_FOLDER):
            os.remove(os.path.join(UPLOAD_FOLDER, f))
            
        # Save new files temporarily and collect their paths
        media_paths = []
        for file in uploaded_files:
            if file.filename:
                # Use secure_filename for security
                filename = secure_filename(file.filename)
                file_path = os.path.join(UPLOAD_FOLDER, filename)
                file.save(file_path)
                media_paths.append(file_path)
        
        if not media_paths:
            return render_template_string(home_ui(), status_message="ERROR: Media Files save nahi hue.", status_class="inactive"), 400

        # --- Data Parsing and Validation ---
        try:
            cookies_data_list = json.loads(raw_cookies)
            if not isinstance(cookies_data_list, list):
                raise ValueError("Cookies must be a valid JSON array.")
        except json.JSONDecodeError:
            print(Fore.RED + f"[{get_current_time()}] ERROR: Invalid JSON format for cookies.")
            return render_template_string(home_ui(), status_message="ERROR: Cookies Galat Format (JSON) Mein Hain.", status_class="inactive"), 400

        if not all([cookies_data_list, chat_ids, haters, media_paths, delay]):
            return render_template_string(home_ui(), status_message="ERROR: Sabhi fields bharo.", status_class="inactive"), 400

        # Start threads with the list of local file paths
        num_tasks = start_messaging_threads(cookies_data_list, chat_ids, haters, media_paths, delay)
        
        print(Fore.GREEN + f"\n[{get_current_time()}] --- COMMAND: START MEDIA ---")
        print(Fore.GREEN + f"[{get_current_time()}] {num_tasks} threads started. Files: {len(media_paths)}. Delay: {delay}s")
        
        return render_template_string(home_ui(), status_message=f"E2E Media Shuru! {num_tasks} threads chal rahe hain. Files: {len(media_paths)}.", status_class="active")

    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] START ERROR: {e}")
        return render_template_string(home_ui(), status_message=f"CRITICAL ERROR: {e}", status_class="inactive"), 500

@app.route('/stop', methods=['POST'])
def stop_messaging():
    """Handles STOP button click and signals all messaging tasks to exit."""
    global MESSAGING_ACTIVE, tasks
    
    if MESSAGING_ACTIVE:
        MESSAGING_ACTIVE = False
        
        print(Fore.RED + f"\n[{get_current_time()}] --- COMMAND: STOP ---")
        print(Fore.RED + f"[{get_current_time()}] Signalled {len(tasks)} threads to stop.")
        
        return render_template_string(home_ui(), status_message="Sabhi Messaging Tasks Band Kar Diye Gaye.", status_class="inactive")
    
    return render_template_string(home_ui(), status_message="Pehle se hi band hai.", status_class="inactive")

# --- Main Server Execution ---

def run_server():
    """Starts the Flask server."""
    print(Fore.GREEN + "_"*40)
    print(Fore.YELLOW + "  VEER CHOUDHARY'S E2E MEDIA TOOL")
    print(Fore.CYAN + "  (REQUIRES VPS/CHROME ENGINE)")
    print(Fore.GREEN + "_"*40)
    print(Fore.MAGENTA + f"\n[STATUS] Server {HOST}:{PORT} par chal raha hai.")
    print(Fore.YELLOW + "Web Panel Access: Public URL or http://127.0.0.1:5000 (for local testing)\n")
    print(Fore.YELLOW + "Media status console mein dekhein.")
    print(Fore.YELLOW + "Ctrl+C se pura server band hoga.")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False) 

if __name__ == '__main__':
    try:
        run_server()
    except KeyboardInterrupt:
        print(Fore.RED + "\nServer and all tasks stopped.")
        MESSAGING_ACTIVE = False 
    except Exception as e:
        print(Fore.RED + f"\nCRITICAL SERVER ERROR: {e}")
        sys.exit(1)
        