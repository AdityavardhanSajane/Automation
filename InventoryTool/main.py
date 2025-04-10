from app import app
import webbrowser
import threading
import time
import os

def open_browser():
    """Open the browser after a short delay to ensure the server has started"""
    # Use a file as a flag to check if browser is already opened
    flag_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.browser_opened')
    
    if not os.path.exists(flag_file):
        # Create the flag file
        with open(flag_file, 'w') as f:
            f.write('1')
            
        time.sleep(1.5)
        webbrowser.open('http://localhost:5000/')
        print("Browser opened - only one instance should appear")

if __name__ == "__main__":
    # Start a thread to open the browser
    browser_thread = threading.Thread(target=open_browser)
    browser_thread.daemon = True  # Make the thread exit when the main thread exits
    browser_thread.start()
    
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)