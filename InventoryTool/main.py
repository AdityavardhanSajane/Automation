from app import app
import webbrowser
import threading
import time
import os

def open_browser():
    """Open the browser after a short delay to ensure the server has started"""
    # Use environment variable instead of global variable to prevent multiple browser windows
    # This persists across Flask auto-reloads in debug mode
    if os.environ.get('BROWSER_OPENED') != 'true':
        time.sleep(1.5)
        webbrowser.open('http://localhost:5000/')
        os.environ['BROWSER_OPENED'] = 'true'
        print("Browser opened - only one instance should appear")

if __name__ == "__main__":
    # Start a thread to open the browser
    threading.Thread(target=open_browser).start()
    
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)