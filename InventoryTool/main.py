from app import app
import webbrowser
import threading
import time

# Global variable to track if browser has been opened
browser_opened = False

def open_browser():
    """Open the browser after a short delay to ensure the server has started"""
    global browser_opened
    # Only open browser if not already launched
    if not browser_opened:
        time.sleep(1.5)
        webbrowser.open('http://localhost:5000/')
        browser_opened = True

if __name__ == "__main__":
    # Start a thread to open the browser
    threading.Thread(target=open_browser).start()
    
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)
