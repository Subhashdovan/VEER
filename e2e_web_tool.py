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

# --- GLOBAL SETUP AND CONFIGURATION ---
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

# --- Utility Functions ---

def get_random_color(): return random.choice(colors)
def get_current_time():
    try:
        return datetime.now(pytz.timezone("Asia/Kolkata")).strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def load_cookies(filepath):
    """Loads cookies from a JSON file."""
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except Exception:
        return None

def sanitize_cookies(cookies):
    """Normalizes sameSite property for Playwright compatibility."""
    for ck in cookies:
        s=ck.get('sameSite','Lax').capitalize()
        ck['sameSite'] = s if s in ["Lax","Strict","None"] else "Lax"
    return cookies

# --- CORE E2E MESSAGING LOGIC (ASYNC PLAYWRIGHT) ---

async def switch_account_and_setup(browser, cookie_file):
    """Loads cookies and sets up the Playwright session."""
    ctx = await browser.new_context(
        user_agent="Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Mobile Safari/537.36",
        viewport={"width": 412, "height": 892}
    )
    page = await ctx.new_page()
    
    try:
        if os.path.exists(cookie_file):
            ck = sanitize_cookies(load_cookies(cookie_file))
            await ctx.add_cookies(ck)
            await page.goto("https://www.facebook.com", timeout=60000)
            await page.wait_for_load_state("networkidle", timeout=60000)
            
            if 'login.php' not in page.url:
                 print(Fore.GREEN + f"[{get_current_time()}] Cookies loaded successfully. Ready for E2E.")
            else:
                 raise Exception("Cookies expired/invalid. Redirected to login.")
        else:
             raise Exception(f"Cookies file not found: {cookie_file}")

        return page
    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [!] Setup Error: {e}")
        await page.close()
        await ctx.close()
        return None

async def send_messages_e2e(page, chat_id, haters, messages, delay, task_key):
    """Sends a message in an E2E chat by simulating typing/Enter press."""
    try:
        idx = message_indices.setdefault(task_key, 0)
        hater = random.choice(haters)
        main_msg = messages[idx]
        full_msg = f"{hater} {main_msg}"
        message_indices[task_key] = (idx+1) % len(messages)

        await page.goto(f"https://www.facebook.com/messages/t/{chat_id}", timeout=60000)

        box = None
        for attempt in range(5):
            try:
                box = await page.wait_for_selector('div[role="textbox"][contenteditable="true"]', timeout=10000)
                
                await box.click()
                await box.fill("") 
                await box.type(full_msg, delay=0.03)
                await box.press("Enter")
                break
            except Exception:
                await asyncio.sleep(3)
        
        if not box:
            print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] [FAIL] Message box not found after 5 attempts.")
            return

        print(Fore.GREEN + f"[{get_current_time()}] [TASK {task_key}] [SUCCESS] Message sent: '{full_msg[:20]}...'")
        await asyncio.sleep(delay)

    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] [CRITICAL FAIL] Error sending message: {e}")
        await asyncio.sleep(delay + 10)


async def run_task_async(cookie_file, chat_id, haters, messages, delay, task_key):
    """Initializes Playwright instance and runs the messaging loop."""
    global MESSAGING_ACTIVE
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, 
            args=['--disable-gpu', '--no-sandbox', '--disable-setuid-sandbox']
        )
        
        page = await switch_account_and_setup(browser, cookie_file)
        
        if not page:
            await browser.close()
            return

        while MESSAGING_ACTIVE:
            try:
                await send_messages_e2e(page, chat_id, haters, messages, delay, task_key)
            except Exception as e:
                print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] Loop error: {e}. Retrying in 30 seconds.")
                await asyncio.sleep(30)
        
        print(Fore.CYAN + f"[{get_current_time()}] [TASK {task_key}] Browser instance stopped.")
        await browser.close()


def start_async_task_in_thread(cookie_file, chat_id, haters, messages, delay, task_key):
    """Wrapper to run the async Playwright task in a separate thread."""
    print(Fore.YELLOW + f"[{get_current_time()}] [TASK {task_key}] Starting asyncio loop in new thread.")
    try:
        asyncio.run(run_task_async(cookie_file, chat_id, haters, messages, delay, task_key))
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(run_task_async(cookie_file, chat_id, haters, messages, delay, task_key))
    except Exception as e:
        print(Fore.RED + f"[{get_current_time()}] [TASK {task_key}] Thread/Async Error: {e}")


def start_messaging_threads(cookie_file, chat_ids_list, haters_list, messages_list, delay):
    """Starts all messaging tasks concurrently using Python threads."""
    global tasks, MESSAGING_ACTIVE
    
    MESSAGING_ACTIVE = False
    time.sleep(2) 
    
    MESSAGING_ACTIVE = True
    tasks.clear()
    message_indices.clear()
    
    task_counter = 1
    for chat_id in chat_ids_list:
        task_key = f"Task-{task_counter}"
        tasks[task_key] = threading.Thread(
            target=start_async_task_in_thread, 
            args=(cookie_file, chat_id, haters_list, messages_list, delay, task_key),
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
        <title>Veer Choudhary | E2E Control Panel</title>
        <style>
            body { font-family: 'Inter', sans-serif; background-color: #2e3440; color: #eceff4; margin: 0; padding: 20px; }
            .container { max-width: 600px; margin: 20px auto; padding: 20px; border: 3px solid #5e81ac; border-radius: 15px; background-color: #3b4252; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.4); }
            h1 { color: #8fbcbb; text-align: center; margin-bottom: 20px; }
            .e2e-note { color: #bf616a; text-align: center; font-weight: bold; margin-bottom: 15px; }
            label { display: block; margin-top: 15px; color: #a3be8c; font-weight: bold; }
            input[type="text"], textarea {
                width: 95%; padding: 10px; margin-top: 5px; border-radius: 5px; border: 1px solid #4c566a; background-color: #434c5e; color: #eceff4; resize: vertical;
            }
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
            <h1>Veer Choudhary's E2E Web Tool</h1>
            <p class="e2e-note">Note: Yeh tool Playwright use karta hai. Iske liye VPS par Chromium/Browser install hona zaroori hai.</p>
            <p class="instructions">Sabhi data ko sahi format mein dalen. Cookies file server ke saath wale folder mein honi chahiye.</p>

            <form action="/start" method="POST">
                <label for="cookie_file">1. Cookie File Name:</label>
                <input type="text" id="cookie_file" name="cookie_file" value="cookies_acc1.json" required>

                <label for="chat_ids">2. Chat IDs (Har ID naye line mein):</label>
                <textarea id="chat_ids" name="chat_ids" rows="3" required placeholder="1234567890&#10;9876543210"></textarea>

                <label for="haters">3. Haters List (Har naam naye line mein):</label>
                <textarea id="haters" name="haters" rows="3" required placeholder="@hater_one&#10;bhoot"></textarea>

                <label for="messages">4. Messages (Har message naye line mein):</label>
                <textarea id="messages" name="messages" rows="5" required placeholder="Kya haal hai?&#10;Kaisa chal raha hai?"></textarea>
                
                <label for="delay">5. Delay (Seconds):</label>
                <input type="text" id="delay" name="delay" value="15" required>
                
                <button type="submit" name="action" value="start">START E2E MESSAGING</button>
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
    """Handles START button click and initiates messaging threads."""
    try:
        data = request.form
        
        cookie_file = data.get('cookie_file').strip()
        delay = float(data.get('delay'))
        
        chat_ids = [i.strip() for i in data.get('chat_ids').split('\n') if i.strip()]
        haters = [i.strip() for i in data.get('haters').split('\n') if i.strip()]
        messages = [i.strip() for i in data.get('messages').split('\n') if i.strip()]
        
        if not all([cookie_file, chat_ids, haters, messages, delay]):
            return render_template_string(home_ui(), status_message="ERROR: Sabhi fields bharo.", status_class="inactive"), 400

        num_tasks = start_messaging_threads(cookie_file, chat_ids, haters, messages, delay)
        
        print(Fore.GREEN + f"\n[{get_current_time()}] --- COMMAND: START E2E ---")
        print(Fore.GREEN + f"[{get_current_time()}] {num_tasks} Playwright threads started. Delay: {delay}s")
        
        return render_template_string(home_ui(), status_message=f"E2E Messaging Shuru! {num_tasks} threads chal rahe hain.", status_class="active")

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
    print(Fore.YELLOW + "  VEER CHOUDHARY'S E2E WEB TOOL")
    print(Fore.CYAN + "  (REQUIRES VPS/CHROME ENGINE)")
    print(Fore.GREEN + "_"*40)
    print(Fore.MAGENTA + f"\n[STATUS] Server {HOST}:{PORT} par chal raha hai.")
    print(Fore.YELLOW + "Web Panel Access: Public URL or http://127.0.0.1:5000 (for local testing)\n")
    print(Fore.YELLOW + "Messaging status console mein dekhein.")
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
        
