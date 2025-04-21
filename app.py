import os
import logging
import uuid
import json
from datetime import datetime
from functools import lru_cache
from flask import Flask, render_template, request, session, jsonify, send_file, Response
from utils.api_client import XLRClient, AnsibleTowerClient
from utils.excel_generator import generate_excel_file

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", str(uuid.uuid4()))


# Load configuration from config.json file
def load_config():
    """Load API URLs from config file"""
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        logger.info("Loaded configuration from config.json")
        return config
    except Exception as e:
        logger.error(f"Failed to load config.json: {str(e)}")
        # Return default values if config file is missing or invalid
        return {"xlr_url": "", "ansible_url": ""}


# Load configuration
config = load_config()

# Browser opening is now handled entirely in main.py
# The code below has been completely removed to prevent any double browser windows

# Comment: removed browser_opened variable
# Comment: removed open_browser function
# Comment: browser opening is now handled only in main.py


@app.route('/')
def index():
    """Render the main application page."""
    # Pass API URLs to the template
    return render_template('index.html', 
                          xlr_url=config.get('xlr_url', ''),
                          ansible_url=config.get('ansible_url', ''))


@app.route('/authenticate', methods=['POST'])
def authenticate():
    """Authenticate with XLR and Ansible Tower APIs."""
    try:
        # Get credentials from form or JSON
        if request.is_json:
            data = request.json
            xlr_username = data.get('username', data.get('xlr_username', ''))
            xlr_password = data.get('password', data.get('xlr_password', ''))
            ansible_username = data.get('username', data.get('ansible_username', ''))
            ansible_password = data.get('password', data.get('ansible_password', ''))
            xlr_url = data.get('xlr_url', config['xlr_url'])
            ansible_url = data.get('ansible_url', config['ansible_url'])
        else:
            # Get username from nbk_id field
            xlr_username = request.form.get('nbk_id', '')
            xlr_password = request.form.get('password', '')
            ansible_username = xlr_username
            ansible_password = xlr_password
            # Use custom URLs if provided in form, otherwise use config
            xlr_url = request.form.get('xlr_url', config['xlr_url'])
            ansible_url = request.form.get('ansible_url', config['ansible_url'])
            
        # Log form field names for debugging
        logger.debug(f"Form field names: {list(request.form.keys())}")
        logger.info(f"Using XLR URL: {xlr_url}")
        logger.info(f"Using Ansible URL: {ansible_url}")

        if not xlr_url or not ansible_url:
            return jsonify({
                'status':
                'error',
                'message':
                'API URLs not configured. Please update config.json file.'
            }), 500

        # Store API URLs in session
        session['xlr_url'] = xlr_url
        session['ansible_url'] = ansible_url

        # Log connection attempts (not credentials)
        logger.info(
            f"Authenticating to XLR at {xlr_url} and Ansible Tower at {ansible_url}"
        )

        # Create API clients and test connections
        xlr_client = XLRClient(xlr_url, xlr_username, xlr_password)
        ansible_client = AnsibleTowerClient(ansible_url, ansible_username,
                                            ansible_password)

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


@app.route('/fetch_data', methods=['POST', 'GET'])
def fetch_data():
    """Fetch data from XLR and Ansible Tower APIs and return progress updates."""
    # Check if authenticated
    if 'xlr_token' not in session or 'ansible_token' not in session:
        return jsonify({
            'status': 'error',
            'message': 'Not authenticated. Please login first.'
        }), 401

    try:
        # Get release train URL from request (form for POST, args for GET)
        if request.method == 'POST':
            release_train_url = request.form.get('release_train_url')
        else:
            release_train_url = request.args.get('release_train_url')
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
                
                # Check if we actually got any components
                if not xlr_data:
                    error_message = "Failed to retrieve any components from XLR. Please check the release train URL and try again."
                    logger.error(error_message)
                    yield "data: " + json.dumps(
                        {
                            'step': 1,
                            'status': 'error',
                            'message': error_message
                        }) + "\n\n"
                    return  # Stop processing here
                
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
                    xlr_data, release_train_url)
                
                # Check if environment data was retrieved
                if not components_with_env or all(len(comp.get('environments', [])) == 0 for comp in components_with_env):
                    error_message = "Failed to retrieve environment data for components. Please check if the release train has environment information."
                    logger.error(error_message)
                    yield "data: " + json.dumps(
                        {
                            'step': 2,
                            'status': 'error',
                            'message': error_message
                        }) + "\n\n"
                    return  # Stop processing here
                
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

                # Extract SPK and organization info from release train URL for Ansible Tower search
                release_data = xlr_client.extract_spk_from_release(release_train_url)
                spk = release_data.get('spk')
                org_name = release_data.get('org_name')
                
                # Check if SPK was successfully extracted
                if not spk:
                    error_message = "Failed to extract SPK from release train URL. Please check if the URL contains a valid SPK identifier."
                    logger.error(error_message)
                    yield "data: " + json.dumps(
                        {
                            'step': 3,
                            'status': 'error',
                            'message': error_message
                        }) + "\n\n"
                    return  # Stop processing here
                
                # Prepare status message including org name if available
                status_message = f'Extracted SPK: {spk} from release train URL'
                if org_name:
                    status_message += f' (Organization: {org_name})'
                    
                yield "data: " + json.dumps(
                    {
                        'step': 3,
                        'status': 'in-progress',
                        'message': status_message
                    }) + "\n\n"

                # Pass both SPK and org_name to filter inventories
                inventories = ansible_client.get_inventories_by_spk(release_data)
                
                # Check if inventories were found
                if not inventories:
                    error_message = f"No inventories found in Ansible Tower for SPK: {spk}. Please check if the SPK exists in Ansible Tower."
                    logger.error(error_message)
                    yield "data: " + json.dumps(
                        {
                            'step': 3,
                            'status': 'error',
                            'message': error_message
                        }) + "\n\n"
                    return  # Stop processing here
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
                
                # Check if there are any environments to process
                if total == 0:
                    error_message = "No environments found to process. Please check if the release train has valid environment information."
                    logger.error(error_message)
                    yield "data: " + json.dumps(
                        {
                            'step': 4,
                            'status': 'error',
                            'message': error_message
                        }) + "\n\n"
                    return  # Stop processing here

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
                
                # Check if any server data was found
                total_servers = sum(len(component.get('servers', [])) for component in server_data)
                if total_servers == 0:
                    # We'll continue but warn the user
                    warning_message = "No server data found for any components. Excel file will be generated with component information only."
                    logger.warning(warning_message)
                    yield "data: " + json.dumps(
                        {
                            'step': 4,
                            'status': 'warning',
                            'message': warning_message
                        }) + "\n\n"

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
