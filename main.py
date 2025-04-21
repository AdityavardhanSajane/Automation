from app import app
import webbrowser
import threading
import time
import os
import sys

def open_browser():
    """Open the browser after a short delay to ensure the server has started"""
    # Wait to make sure the server has started
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000/')
    print("Browser opened")

if __name__ == "__main__":
    # In debug mode, Flask starts two processes:
    # - A parent process that watches for code changes
    # - A child process that actually runs the app
    # We only want to open a browser in the child process
    
    # Check if this is the main process (WERKZEUG_RUN_MAIN is set by Flask)
    main_process = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    
    # If this is the first run of the parent process (before child is created)
    if not main_process:
        # Start a thread to open the browser only on the initial run
        threading.Thread(target=open_browser).start()
    
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)
