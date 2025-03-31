from app import app
import webbrowser
import threading
import time

def open_browser():
    """Open the browser after a short delay to ensure the server has started"""
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000/')

if __name__ == "__main__":
    # Start a thread to open the browser
    threading.Thread(target=open_browser).start()
    
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)

