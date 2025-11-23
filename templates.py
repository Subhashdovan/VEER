WEB_UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Veer Choudhary | E2E Media Tool</title>
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #2e3440; color: #eceff4; margin: 0; padding: 20px; }
        .container { max-width: 600px; margin: 20px auto; padding: 25px; border: 3px solid #5e81ac; border-radius: 15px; background-color: #3b4252; box-shadow: 0 5px 15px rgba(0, 0, 0, 0.4); }
        h1 { color: #8fbcbb; text-align: center; margin-bottom: 5px; }
        .note { color: #bf616a; text-align: center; margin-bottom: 20px; font-size: 0.9em; }
        label { display: block; margin-top: 15px; color: #a3be8c; font-weight: bold; }
        input[type="text"], textarea {
            width: 95%; padding: 10px; margin-top: 5px; border-radius: 5px; border: 1px solid #4c566a; background-color: #434c5e; color: #eceff4; resize: vertical;
        }
        input[type="file"] { margin-top: 5px; padding: 8px 0; width: 100%; }
        button { 
            background-color: #a3be8c; color: #2e3440; border: none; padding: 12px 20px; margin-top: 20px; border-radius: 5px; cursor: pointer; font-size: 1em; font-weight: bold; transition: background-color 0.3s; width: 100%;
        }
        button:hover { background-color: #b4e39b; }
        .stop-btn { background-color: #bf616a; margin-top: 10px; }
        .stop-btn:hover { background-color: #c97c7c; }
        .status { margin-top: 20px; padding: 10px; border-radius: 5px; font-weight: bold; text-align: center; }
        .active { background-color: #2e8b57; }
        .inactive { background-color: #a34747; }
        .field-box { margin-bottom: 15px; padding: 10px; border: 1px solid #4c566a; border-radius: 5px; }
    </style>
</head>
<body>
    <div class="container">
        <h1>Veer Choudhary's E2E Media Tool</h1>
        <p class="note">Note: Yeh tool Playwright use karta hai. Iske liye VPS par Chromium/Browser install hona zaroori hai.</p>
        <p class="note">Cookies ko JSON Array format mein paste karein. Aap Gallery se files (photos/videos) upload kar sakte hain.</p>

        <form action="/start" method="POST" enctype="multipart/form-data">
            
            <label for="raw_cookies">1. Raw Cookies (JSON Array Format):</label>
            <textarea id="raw_cookies" name="raw_cookies" rows="4" placeholder='[{"name":"c_user","value":"..."}, {"name":"xs","value":"..."}]' required></textarea>

            <label for="chat_ids">2. Chat IDs (Har ID naye line mein):</label>
            <textarea id="chat_ids" name="chat_ids" rows="2" placeholder="1234567890&#10;9876543210" required></textarea>

            <label for="captions">3. Captions/Tags (Har tag naye line mein, ek tag ek message ke liye):</label>
            <textarea id="captions" name="captions" rows="2" placeholder="@hater_one&#10;bhoot" required></textarea>

            <label for="gallery_files">4. Gallery Files (Photos/Videos):</label>
            <input type="file" id="gallery_files" name="gallery_files" multiple required>
            
            <label for="delay">5. Delay (Seconds):</label>
            <input type="text" id="delay" name="delay" value="15" required>
            
            <button type="submit">START MEDIA MESSAGING</button>
        </form>
        
        <form action="/stop" method="POST">
            <button type="submit" class="stop-btn">STOP ALL TASKS</button>
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