from app import app
import webbrowser
import threading
import time

def open_browser():
    """Open the browser after a short delay to ensure the server has started"""
    # Only open browser if not already launched (check environment variable)
    if not os.environ.get('BROWSER_LAUNCHED'):
        time.sleep(1.5)
        webbrowser.open('http://localhost:5000/')
        # Set environment variable to indicate browser has been launched
        os.environ['BROWSER_LAUNCHED'] = 'True'

if __name__ == "__main__":
    # Start a thread to open the browser
    threading.Thread(target=open_browser).start()
    
    # Run the Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)

