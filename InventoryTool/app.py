import json
import logging
import os
import re
from datetime import datetime
from functools import wraps
from urllib.parse import urlparse

from flask import (Flask, Response, jsonify, redirect, render_template, request,
                   send_file, session, url_for)

from utils.api_client import AnsibleTowerClient, XLRClient
from utils.excel_generator import generate_excel_file

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = "your-secret-key-here"  # For session management

# Load configuration from JSON file
def load_config():
    """Load API URLs from config file"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        logger.info("Loaded configuration from config.json")
        return config
    except Exception as e:
        logger.error(f"Error loading config.json: {str(e)}")
        return {"xlr_url": "", "ansible_url": ""}

# Load configuration
config = load_config()

@app.route('/')
def index():
    """Render the main application page."""
    return render_template('index.html', 
                          xlr_url=config.get('xlr_url', ''),
                          ansible_url=config.get('ansible_url', ''))

@app.route('/authenticate', methods=['POST'])
def authenticate():
    """Authenticate with XLR and Ansible Tower APIs."""
    try:
        # Get credentials from request
        xlr_url = request.form.get('xlr_url')
        ansible_url = request.form.get('ansible_url')
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not all([xlr_url, ansible_url, username, password]):
            return jsonify({
                'status': 'error',
                'message': 'Missing required fields'
            }), 400
        
        # Store URLs in session
        session['xlr_url'] = xlr_url
        session['ansible_url'] = ansible_url
        
        # Test API connection
        xlr_client = XLRClient(xlr_url, username, password)
        ansible_client = AnsibleTowerClient(ansible_url, username, password)
        
        xlr_status = xlr_client.test_connection()
        ansible_status = ansible_client.test_connection()

        if xlr_status and ansible_status:
            # Store auth token in session (not credentials)
            session['xlr_token'] = xlr_client.get_auth_token()
            session['ansible_token'] = ansible_client.get_auth_token()
            return jsonify({
                'status': 'success',
                'message': 'Successfully authenticated with both APIs'
            })
        elif ansible_status and not xlr_status:
            # Partial success - only Ansible Tower works
            error_msg = "XebiaLabs Release (XLR) authentication failed, but Ansible Tower authentication succeeded."
            error_msg += " Please check your XLR credentials and API URL."
            logger.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': error_msg,
                'xlr_status': xlr_status,
                'ansible_status': ansible_status
            }), 401
        elif xlr_status and not ansible_status:
            # Partial success - only XLR works
            error_msg = "Ansible Tower authentication failed, but XebiaLabs Release (XLR) authentication succeeded."
            error_msg += " Please check your Ansible Tower credentials and API URL."
            logger.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': error_msg,
                'xlr_status': xlr_status,
                'ansible_status': ansible_status
            }), 401
        else:
            # Both failed
            error_msg = "Authentication failed for both XebiaLabs Release and Ansible Tower APIs."
            error_msg += " Please check your credentials and API URLs."
            logger.error(error_msg)
            return jsonify({
                'status': 'error',
                'message': error_msg,
                'xlr_status': xlr_status,
                'ansible_status': ansible_status
            }), 401
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error during authentication: {str(e)}'
        }), 500


@app.route('/fetch_data', methods=['POST'])
def fetch_data():
    """Fetch data from XLR and Ansible Tower APIs and return progress updates."""
    # Check if authenticated
    if 'xlr_token' not in session or 'ansible_token' not in session:
        return jsonify({
            'status': 'error',
            'message': 'Not authenticated. Please login first.'
        }), 401

    try:
        # Get release train URL from request
        release_train_url = request.form.get('release_train_url')
        if not release_train_url:
            return jsonify({
                'status': 'error',
                'message': 'Release train URL is required'
            }), 400

        # Create API clients with stored tokens
        xlr_client = XLRClient(session['xlr_url'], token=session['xlr_token'])
        ansible_client = AnsibleTowerClient(session['ansible_url'],
                                            token=session['ansible_token'])

        # Start a Server-Sent Events response for real-time updates
        def generate():
            # Step 1: Extract XLR data
            yield "data: " + json.dumps(
                {
                    'step': 1,
                    'status': 'in-progress',
                    'message': 'Retrieving component data from XLR...'
                }) + "\n\n"

            try:
                xlr_data = xlr_client.get_components_from_release(
                    release_train_url)
                yield "data: " + json.dumps(
                    {
                        'step': 1,
                        'status': 'complete',
                        'message':
                        f'Retrieved {len(xlr_data)} components from XLR'
                    }) + "\n\n"

                # Step 2: Extract environment data for each component
                yield "data: " + json.dumps(
                    {
                        'step': 2,
                        'status': 'in-progress',
                        'message':
                        'Retrieving environment data for components...'
                    }) + "\n\n"

                components_with_env = xlr_client.get_environments_for_components(
                    xlr_data)
                yield "data: " + json.dumps({
                    'step':
                    2,
                    'status':
                    'complete',
                    'message':
                    f'Retrieved environment data for {len(components_with_env)} components'
                }) + "\n\n"

                # Step 3: Retrieve inventory data from Ansible Tower
                yield "data: " + json.dumps({
                    'step':
                    3,
                    'status':
                    'in-progress',
                    'message':
                    'Retrieving inventory data from Ansible Tower...'
                }) + "\n\n"

                # Extract SPK from release train URL for Ansible Tower search
                spk = xlr_client.extract_spk_from_release(release_train_url)
                yield "data: " + json.dumps(
                    {
                        'step': 3,
                        'status': 'in-progress',
                        'message':
                        f'Extracted SPK: {spk} from release train URL'
                    }) + "\n\n"

                inventories = ansible_client.get_inventories_by_spk(spk)
                yield "data: " + json.dumps({
                    'step':
                    3,
                    'status':
                    'complete',
                    'message':
                    f'Retrieved {len(inventories)} inventories from Ansible Tower for SPK: {spk}'
                }) + "\n\n"

                # Step 4: Fetch server data for each component and environment
                yield "data: " + json.dumps({
                    'step':
                    4,
                    'status':
                    'in-progress',
                    'message':
                    'Fetching server data for each component and environment...'
                }) + "\n\n"

                server_data = []
                total = len(components_with_env) * len([
                    env for comp in components_with_env
                    for env in comp['environments']
                ])
                completed = 0

                for component in components_with_env:
                    component_servers = []
                    for env in component['environments']:
                        servers = ansible_client.get_servers_for_component(
                            component['name'], env, inventories)
                        component_servers.extend(servers)
                        completed += 1

                        # Send progress update
                        if completed % 5 == 0 or completed == total:
                            yield "data: " + json.dumps({
                                'step':
                                4,
                                'status':
                                'in-progress',
                                'message':
                                f'Processing server data: {completed}/{total} completed',
                                'progress': (completed / total) * 100
                            }) + "\n\n"

                    server_data.append({
                        'component': component['name'],
                        'servers': component_servers
                    })

                yield "data: " + json.dumps(
                    {
                        'step': 4,
                        'status': 'complete',
                        'message': f'Retrieved server data for all components'
                    }) + "\n\n"

                # Step 5: Generate Excel file
                yield "data: " + json.dumps(
                    {
                        'step': 5,
                        'status': 'in-progress',
                        'message': 'Generating Excel file...'
                    }) + "\n\n"

                # Generate a unique timestamp for the filename
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"server_inventory_{timestamp}.xlsx"

                # Generate Excel file
                excel_path = generate_excel_file(server_data, filename)

                yield "data: " + json.dumps({
                    'step': 5,
                    'status': 'complete',
                    'message': 'Excel file generated successfully',
                    'excel_path': excel_path,
                    'filename': filename
                }) + "\n\n"

                # Get the expected download location for display
                if os.name == 'nt':  # Windows
                    downloads_folder = os.path.join(os.path.expanduser('~'),
                                                    'Downloads')
                else:  # Linux/Mac
                    downloads_folder = os.path.join(os.path.expanduser('~'),
                                                    'Downloads')

                # Create the expected download location path
                download_location = os.path.join(downloads_folder, filename)

                # Store the download location in session
                session['last_download_location'] = download_location

                # Complete with download location info
                yield "data: " + json.dumps(
                    {
                        'step': 6,
                        'status': 'complete',
                        'message': 'Data collection and processing complete',
                        'download_ready': True,
                        'filename': filename,
                        'download_location': download_location
                    }) + "\n\n"

            except Exception as e:
                logger.error(f"Error in data fetching: {str(e)}")
                yield "data: " + json.dumps(
                    {
                        'status': 'error',
                        'message': f'Error processing data: {str(e)}'
                    }) + "\n\n"

        return Response(generate(), mimetype='text/event-stream')

    except Exception as e:
        logger.error(f"Error in fetch_data: {str(e)}")
        return jsonify({'status': 'error', 'message': f'Error: {str(e)}'}), 500


@app.route('/download/<filename>', methods=['GET'])
def download_file(filename):
    """Download the generated Excel file."""
    try:
        # Get the full path of the file
        file_path = os.path.join(os.getcwd(), filename)

        # Get user's downloads folder for display in the status
        if os.name == 'nt':  # Windows
            downloads_folder = os.path.join(os.path.expanduser('~'),
                                            'Downloads')
        else:  # Linux/Mac
            downloads_folder = os.path.join(os.path.expanduser('~'),
                                            'Downloads')

        # Create the expected download location path
        download_location = os.path.join(downloads_folder, filename)

        # Store the download location in session for the UI to display
        session['last_download_location'] = download_location

        # Log the download location
        logger.info(f"File ready for download: {download_location}")

        return send_file(file_path, as_attachment=True)
    except Exception as e:
        logger.error(f"Download error: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error downloading file: {str(e)}'
        }), 500


@app.route('/download_location', methods=['GET'])
def get_download_location():
    """Get the location of the last downloaded file."""
    if 'last_download_location' in session:
        return jsonify({
            'status': 'success',
            'download_location': session['last_download_location']
        })
    return jsonify({
        'status': 'error',
        'message': 'No download location available'
    }), 404


@app.route('/logout', methods=['POST'])
def logout():
    """Clear session data to logout."""
    session.clear()
    return jsonify({'status': 'success', 'message': 'Logged out successfully'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)