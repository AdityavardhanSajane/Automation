import logging
import requests
import re
from functools import lru_cache
from base64 import b64encode

# Add this line to suppress the InsecureRequestWarning that will appear when using verify=False
try:
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
except ImportError:
    # If urllib3 is not available, we'll still continue
    pass

logger = logging.getLogger(__name__)

def create_basic_auth(username, password):
    """Create a basic auth token from username and password"""
    if username is None or password is None:
        return ""
    auth_str = f"{username}:{password}"
    return b64encode(auth_str.encode()).decode('ascii')

class BaseAPIClient:
    """Base class for API clients"""
    
    def __init__(self, base_url, username=None, password=None, token=None):
        # Strip any trailing slashes and make sure we don't have '/api' at the end already
        self.base_url = base_url.rstrip('/').rstrip('/api')
        logger.debug(f"Initialized API client with base URL: {self.base_url}")
        self.username = username
        self.password = password
        self.token = token
        self.session = requests.Session()
        
        # If token is provided, set up authentication header
        if token:
            self.session.headers.update({'Authorization': f'Bearer {token}'})
    
    def test_connection(self):
        """Test the API connection"""
        raise NotImplementedError("Subclasses must implement this method")
    
    def get_auth_token(self):
        """Get authentication token"""
        raise NotImplementedError("Subclasses must implement this method")


class XLRClient(BaseAPIClient):
    """Client for interacting with XebiaLabs Release API"""
    
    def test_connection(self):
        """Test connection to XLR API"""
        try:
            # Set up Basic Authentication
            auth_token = create_basic_auth(self.username, self.password)
            self.session.headers.update({'Authorization': f'Basic {auth_token}'})
            
            # Test API access with a simple request
            # Try standard XLR endpoints in order of likelihood to exist
            endpoints = [
                "/api/v1/releases",
                "/api/v1/templates",
                "/api/v1/folders",
                "/api/v1/config/templates"
            ]
            
            for endpoint in endpoints:
                url = f"{self.base_url}{endpoint}"
                logger.debug(f"Making XLR request to URL: {url}")
                response = self.session.get(url, verify=False)
                logger.debug(f"XLR response status: {response.status_code} for endpoint {endpoint}")
                
                if response.status_code == 200:
                    logger.info(f"XLR connection successful using endpoint: {endpoint}")
                    return True
                else:
                    try:
                        error_content = response.json()
                        logger.error(f"XLR API error for {endpoint}: {error_content}")
                    except:
                        logger.error(f"XLR API error with status code {response.status_code} for {endpoint}")
            
            logger.error("XLR connection failed - all endpoints returned errors")
            return False
        except Exception as e:
            logger.error(f"XLR connection test failed: {str(e)}")
            return False
    
    def get_auth_token(self):
        """Get basic auth token for XLR"""
        return create_basic_auth(self.username, self.password)
    
    def extract_spk_from_release(self, release_url):
        """
        Extract SPK and organization information from release train URL or from release variables
        First attempts to get it from release variables, then falls back to URL pattern matching
        
        Returns:
            dict: A dictionary containing 'spk', 'folder_id', and 'org_name'
        """
        # Initialize result dict
        result = dict()
        result['spk'] = None
        result['folder_id'] = None
        result['org_name'] = None
            
        try:
            # Extract release ID from URL
            release_id = release_url.split('/')[-1]
            
            # Get release details with variables
            url = f"{self.base_url}/api/v1/releases/{release_id}"
            logger.debug(f"Getting release details from: {url}")
            response = self.session.get(url, verify=False)
            
            if response.status_code == 200:
                release_data = response.json()
                variables = release_data.get('variables', [])
                
                # First, try to get organization from releaseConfigRepoLocation variable
                for var in variables:
                    if var.get('key') == 'releaseConfigRepoLocation':
                        repo_location = var.get('value')
                        logger.info(f"Found releaseConfigRepoLocation variable: {repo_location}")
                        
                        # Parse the repo_location in format "SPK@repo_name@ait/SPK/train_name"
                        if repo_location and '@' in repo_location:
                            parts = repo_location.split('@')
                            if len(parts) >= 2:
                                repo_name = parts[1]
                                logger.info(f"Extracted repo_name: {repo_name}")
                                
                                # Extract the folder/organization name from repo_name
                                # Format is typically domain_subdomain_folder_name, we want the last part
                                repo_parts = repo_name.split('_')
                                if len(repo_parts) >= 3:
                                    # Last two parts should be the folder name (e.g., vgpdr_bh)
                                    folder_name = '_'.join(repo_parts[-2:])
                                    
                                    # Convert to uppercase and replace underscore with triple hyphen
                                    formatted_org = folder_name.replace('_', '---').upper()
                                    if formatted_org:
                                        result['org_name'] = formatted_org
                                        logger.info(f"Extracted and formatted organization name: {formatted_org}")
                        
                        break
                
                # If we didn't get org_name from releaseConfigRepoLocation, try folderID
                if not result.get('org_name'):
                    # Extract folderID if present
                    for var in variables:
                        if var.get('key') == 'folderID':
                            folder_id = var.get('value')
                            if folder_id:
                                result['folder_id'] = folder_id
                                logger.info(f"Found folderID variable: {folder_id}")
                            
                                # Try to get the folder details to extract org name
                                try:
                                    folder_url = f"{self.base_url}/api/v1/folders/{folder_id}"
                                    folder_response = self.session.get(folder_url, verify=False)
                                    
                                    if folder_response.status_code == 200:
                                        folder_data = folder_response.json()
                                        folder_title = folder_data.get('title', '')
                                        
                                        # Look for pattern matching org name (e.g., "VGPDR---BH")
                                        org_match = re.search(r'([A-Z]{5}[-]{3}[A-Z]{2})', folder_title)
                                        if org_match:
                                            org_name = org_match.group(1)
                                            if org_name:
                                                result['org_name'] = org_name
                                                logger.info(f"Extracted organization name from folder: {org_name}")
                                except Exception as e:
                                    logger.warning(f"Error getting folder info: {str(e)}")
                
                # Try to get SPK from releaseName variable
                release_name = None
                for var in variables:
                    if var.get('key') == 'releaseName':
                        release_name = var.get('value')
                        logger.info(f"Found releaseName variable: {release_name}")
                        break
                
                if release_name:
                    # Look for capitalized words that might be SPK names like CODECTS
                    parts = re.split(r'[/_\-\s]', release_name)
                    for part in parts:
                        # Check if part is fully capitalized with at least 3 characters
                        if part.isupper() and len(part) >= 3 and part not in ["WMTO", "DEVOPS"]:
                            logger.info(f"Identified SPK name from releaseName: {part}")
                            result['spk'] = part
                            break
                
                # If we didn't get the org name from previous methods but have folder information in release data
                if not result.get('org_name') and release_data.get('folder'):
                    folder_path = release_data.get('folder', {}).get('path', '')
                    # Extract org name from folder path using regex pattern
                    org_match = re.search(r'([A-Z]{5}[-]{3}[A-Z]{2})', folder_path)
                    if org_match:
                        org_name = org_match.group(1)
                        if org_name:
                            result['org_name'] = org_name
                            logger.info(f"Extracted organization name from folder path: {org_name}")
            
            # If we still don't have an SPK, fall back to URL pattern matching
            if not result.get('spk'):
                logger.info("Falling back to URL pattern matching for SPK")
                
                # First check if URL contains SPK pattern with numbers (SPK123)
                spk_num_match = re.search(r'SPK(\d+)', release_url)
                if spk_num_match:
                    spk = f"SPK{spk_num_match.group(1)}"
                    result['spk'] = spk
                    logger.info(f"Extracted SPK from URL number pattern: {spk}")
                else:
                    # If not, look for capitalized words that might be SPK names
                    parts = re.split(r'[/_\-\s]', release_url)
                    for part in parts:
                        # Check if part is fully capitalized with at least 3 characters
                        if part.isupper() and len(part) >= 3:
                            logger.info(f"Identified potential SPK name from URL: {part}")
                            result['spk'] = part
                            break
                    
                    # Last resort: look for words with pattern like 'CODECTS'
                    if not result.get('spk'):
                        words_match = re.search(r'([A-Z]{3,})', release_url)
                        if words_match:
                            potential_spk = words_match.group(1)
                            if potential_spk:
                                result['spk'] = potential_spk
                                logger.info(f"Using best guess for SPK: {potential_spk}")
            
            # Try to extract org name from URL if not found yet
            if not result.get('org_name'):
                org_match = re.search(r'([A-Z]{5}[-]{3}[A-Z]{2})', release_url)
                if org_match:
                    org_name = org_match.group(1)
                    if org_name:
                        result['org_name'] = org_name
                        logger.info(f"Extracted organization name from URL: {org_name}")
                
            if not result.get('spk'):
                logger.warning(f"Could not identify SPK in release or URL: {release_url}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error extracting data from release: {str(e)}")
            result = dict()
            result['spk'] = None
            result['folder_id'] = None
            result['org_name'] = None
            return result
    
    def get_components_from_release(self, release_url):
        """
        Get component names from the release train URL
        First tries to get components from releaseComponents variable, 
        then falls back to finding component groups in phases
        """
        try:
            # Extract release ID from URL
            release_id = release_url.split('/')[-1]
            
            # Get release details
            url = f"{self.base_url}/api/v1/releases/{release_id}"
            response = self.session.get(url, verify=False)
            
            if response.status_code != 200:
                logger.error(f"Failed to get release: {response.status_code}")
                return []
            
            release_data = response.json()
            components = []
            
            # First try to get components from releaseComponents variable
            variables = release_data.get('variables', [])
            release_components_var = None
            
            for var in variables:
                if var.get('key') == 'releaseComponents':
                    release_components_var = var.get('value')
                    logger.info(f"Found releaseComponents variable: {release_components_var}")
                    break
            
            # If we found the releaseComponents variable, parse it
            if release_components_var:
                # Split by lines or spaces
                component_entries = re.split(r'[\n\r\s]+', release_components_var)
                
                for entry in component_entries:
                    entry = entry.strip()
                    if not entry:
                        continue
                        
                    # Check if this looks like a component name (not just the SPK or date)
                    if '_' in entry and not re.match(r'\d{4}\.\d{2}\.\d{2}', entry) and entry not in components:
                        logger.info(f"Adding component from releaseComponents: {entry}")
                        components.append({
                            'id': None,  # No task ID when getting from variables
                            'name': entry,
                            'environments': []
                        })
            
            # If we didn't get any components from variables, fall back to the old method
            if not components:
                logger.info("No components found in releaseComponents variable, falling back to phase extraction")
                # Extract components from phases
                for phase in release_data.get('phases', []):
                    for task in phase.get('tasks', []):
                        if task.get('type') == 'xlrelease.ParallelGroup':
                            # This might be a component group
                            component_name = task.get('title')
                            if component_name:
                                components.append({
                                    'id': task.get('id'),
                                    'name': component_name,
                                    'environments': []
                                })
            
            logger.info(f"Found {len(components)} components for release")
            return components
        except Exception as e:
            logger.error(f"Error getting components from release: {str(e)}")
            return []
    
    def get_environments_for_components(self, components, release_url=None):
        """
        Get environment names for each component
        First tries to get environments from integratedReleaseEnvironments variable,
        then falls back to task titles
        """
        try:
            # Try to get environments from integratedReleaseEnvironments variable if release_url is provided
            global_environments = []
            
            if release_url:
                # Extract release ID from URL
                release_id = release_url.split('/')[-1]
                
                # Get release details
                url = f"{self.base_url}/api/v1/releases/{release_id}"
                response = self.session.get(url, verify=False)
                
                if response.status_code == 200:
                    release_data = response.json()
                    variables = release_data.get('variables', [])
                    
                    # Look for the integratedReleaseEnvironments variable
                    for var in variables:
                        if var.get('key') == 'integratedReleaseEnvironments':
                            env_var_value = var.get('value')
                            logger.info(f"Found integratedReleaseEnvironments variable: {env_var_value}")
                            
                            # Parse environments from the variable
                            if env_var_value:
                                # Split by common separators
                                env_entries = re.split(r'[\n\r\s,;]+', env_var_value)
                                for env in env_entries:
                                    env = env.strip().upper()
                                    if env and env not in global_environments:
                                        global_environments.append(env)
                            
                            break
                    
                    logger.info(f"Extracted global environments from variable: {global_environments}")
            
            updated_components = []
            
            for component in components:
                # Initialize with global environments if available
                environments = global_environments.copy() if global_environments else []
                
                # If no global environments or component has a task ID, try to get environments from tasks
                if (not environments or not component.get('id')):
                    # If component has a task ID, try to get environments from task titles
                    if component.get('id'):
                        url = f"{self.base_url}/api/v1/releases/tasks/{component['id']}"
                        response = self.session.get(url, verify=False)
                        
                        if response.status_code == 200:
                            task_data = response.json()
                            
                            # Extract environment names from tasks
                            for task in task_data.get('tasks', []):
                                # Look for environment indicators in task titles (LLE, PROD, etc.)
                                title = task.get('title', '').upper()
                                for env in ['LLE', 'PROD', 'UAT', 'DEV', 'TEST']:
                                    if env in title and env not in environments:
                                        environments.append(env)
                    
                    # If still no environments, use default set
                    if not environments:
                        logger.info(f"No environments found for component {component['name']}, using default set")
                        environments = ['PROD']  # Default to PROD if nothing found
                
                updated_component = component.copy()
                updated_component['environments'] = environments
                updated_components.append(updated_component)
                
                logger.info(f"Component {component['name']} has environments: {environments}")
            
            return updated_components
        except Exception as e:
            logger.error(f"Error getting environments for components: {str(e)}")
            return components


class AnsibleTowerClient(BaseAPIClient):
    """Client for interacting with Ansible Tower API"""
    
    def test_connection(self):
        """Test connection to Ansible Tower API"""
        try:
            # Set up Basic Authentication
            auth_token = create_basic_auth(self.username, self.password)
            self.session.headers.update({'Authorization': f'Basic {auth_token}'})
            
            # Test API access with a simple request
            url = f"{self.base_url}/api/v2/inventories/"
            logger.debug(f"Making Ansible Tower request to URL: {url}")
            response = self.session.get(url, verify=False)
            logger.debug(f"Ansible Tower response status: {response.status_code}")
            if response.status_code != 200:
                try:
                    error_content = response.json()
                    logger.error(f"Ansible Tower API error: {error_content}")
                except:
                    logger.error(f"Ansible Tower API error with status code {response.status_code}")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ansible Tower connection test failed: {str(e)}")
            return False
    
    def get_auth_token(self):
        """Get basic auth token for Ansible Tower"""
        return create_basic_auth(self.username, self.password)
    
    @lru_cache(maxsize=32)
    def get_inventories_by_spk(self, spk_data):
        """
        Get inventory groups by SPK, filtered by organization name if available
        
        Args:
            spk_data: Either a string containing just the SPK, or a dictionary with 'spk' and 'org_name' keys
            
        Returns:
            List of inventories matching the SPK, filtered by organization name if provided
        """
        try:
            # Handle both string and dictionary input
            if isinstance(spk_data, dict):
                spk = spk_data.get('spk')
                org_name = spk_data.get('org_name')
            else:
                spk = spk_data
                org_name = None
                
            if not spk:
                logger.error("No SPK provided to get_inventories_by_spk")
                return []
                
            url = f"{self.base_url}/api/v2/inventories/"
            params = {
                'search': f"{spk}_PROD"
            }
            
            response = self.session.get(url, params=params, verify=False)
            
            if response.status_code != 200:
                logger.error(f"Failed to get inventories: {response.status_code}")
                return []
            
            inventories_data = response.json()
            inventories = []
            
            for inventory in inventories_data.get('results', []):
                inventory_id = inventory.get('id')
                inventory_name = inventory.get('name')
                
                # Get inventory groups
                groups_url = f"{self.base_url}/api/v2/inventories/{inventory_id}/groups/"
                groups_response = self.session.get(groups_url, verify=False)
                
                if groups_response.status_code != 200:
                    logger.warning(f"Failed to get groups for inventory {inventory_name}: {groups_response.status_code}")
                    continue
                
                groups_data = groups_response.json()
                
                inventory_with_groups = {
                    'id': inventory_id,
                    'name': inventory_name,
                    'groups': groups_data.get('results', [])
                }
                
                inventories.append(inventory_with_groups)
            
            # If we have multiple inventories and an organization name, filter by organization
            if len(inventories) > 1 and org_name:
                logger.info(f"Found {len(inventories)} inventories for SPK {spk}, filtering by organization {org_name}")
                filtered_inventories = []
                
                for inventory in inventories:
                    # Check if the inventory path or name contains the organization pattern
                    if org_name in inventory.get('name', ''):
                        logger.info(f"Selected inventory {inventory.get('name')} based on organization match {org_name}")
                        filtered_inventories.append(inventory)
                        continue
                        
                    # Check inventory groups as well
                    found_org = False
                    for group in inventory.get('groups', []):
                        if org_name in group.get('name', ''):
                            logger.info(f"Selected inventory {inventory.get('name')} based on group match for {org_name}")
                            filtered_inventories.append(inventory)
                            found_org = True
                            break
                    
                    if found_org:
                        continue
                
                # If we found any inventories matching the organization, use those
                if filtered_inventories:
                    logger.info(f"Filtered to {len(filtered_inventories)} inventories based on organization {org_name}")
                    return filtered_inventories
                else:
                    logger.warning(f"No inventories found matching organization {org_name}, using all {len(inventories)} inventories")
                    
            return inventories
        except Exception as e:
            logger.error(f"Error getting inventories by SPK: {str(e)}")
            return []
    
    def get_servers_for_component(self, component_name, environment, inventories):
        """Get server details for a component and environment"""
        try:
            servers = []
            
            for inventory in inventories:
                for group in inventory['groups']:
                    group_name = group.get('name', '')
                    
                    # Check if group matches component and environment
                    if component_name.lower() in group_name.lower() and environment.lower() in group_name.lower():
                        group_id = group.get('id')
                        
                        # Get hosts in this group
                        hosts_url = f"{self.base_url}/api/v2/groups/{group_id}/hosts/"
                        hosts_response = self.session.get(hosts_url, verify=False)
                        
                        if hosts_response.status_code != 200:
                            logger.warning(f"Failed to get hosts for group {group_name}: {hosts_response.status_code}")
                            continue
                        
                        hosts_data = hosts_response.json()
                        
                        for host in hosts_data.get('results', []):
                            host_id = host.get('id')
                            host_name = host.get('name')
                            
                            # Get host details including variables
                            host_url = f"{self.base_url}/api/v2/hosts/{host_id}/"
                            host_response = self.session.get(host_url, verify=False)
                            
                            if host_response.status_code != 200:
                                logger.warning(f"Failed to get details for host {host_name}: {host_response.status_code}")
                                continue
                            
                            host_details = host_response.json()
                            
                            # Get OS information from variables
                            variables = host_details.get('variables', '{}')
                            try:
                                variables_dict = eval(variables) if isinstance(variables, str) else variables
                            except:
                                variables_dict = {}
                            
                            os_info = variables_dict.get('ansible_distribution', '') + ' ' + variables_dict.get('ansible_distribution_version', '')
                            if not os_info.strip():
                                os_info = "Unknown"
                            
                            server = {
                                'server_name': host_name,
                                'group_name': group_name,
                                'component_name': component_name,
                                'environment': environment,
                                'os_info': os_info,
                                'enabled': host_details.get('enabled', False)
                            }
                            
                            servers.append(server)
            
            return servers
        except Exception as e:
            logger.error(f"Error getting servers for component {component_name} in {environment}: {str(e)}")
            return []
