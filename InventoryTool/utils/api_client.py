import logging
import requests
import re
from functools import lru_cache
from base64 import b64encode

# Add this line to suppress the InsecureRequestWarning that will appear when using verify=False
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

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
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
    
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
            url = f"{self.base_url}/api/v1/config/templates"
            response = self.session.get(url, verify=False)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"XLR connection test failed: {str(e)}")
            return False
    
    def get_auth_token(self):
        """Get basic auth token for XLR"""
        return create_basic_auth(self.username, self.password)
    
    def extract_spk_from_release(self, release_url):
        """Extract SPK from release train URL"""
        # Example: Extract SPK123 from a URL like "/releases/release/SPK123_Release_Train"
        match = re.search(r'SPK(\d+)', release_url)
        if match:
            return f"SPK{match.group(1)}"
        return None
    
    def get_components_from_release(self, release_url):
        """Get component names and IDs from the release train URL"""
        try:
            # Set up Basic Authentication if not already done
            if 'Authorization' not in self.session.headers:
                auth_token = create_basic_auth(self.username, self.password)
                self.session.headers.update({'Authorization': f'Basic {auth_token}'})
                
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
            
            return components
        except Exception as e:
            logger.error(f"Error getting components from release: {str(e)}")
            return []
    
    def get_environments_for_components(self, components):
        """Get environment names for each component"""
        try:
            # Set up Basic Authentication if not already done
            if 'Authorization' not in self.session.headers:
                auth_token = create_basic_auth(self.username, self.password)
                self.session.headers.update({'Authorization': f'Basic {auth_token}'})
                
            updated_components = []
            
            for component in components:
                # Get component tasks
                url = f"{self.base_url}/api/v1/releases/tasks/{component['id']}"
                response = self.session.get(url, verify=False)
                
                if response.status_code != 200:
                    logger.warning(f"Failed to get tasks for component {component['name']}: {response.status_code}")
                    updated_components.append(component)
                    continue
                
                task_data = response.json()
                environments = []
                
                # Extract environment names from tasks
                for task in task_data.get('tasks', []):
                    # Look for environment indicators in task titles (LLE, PROD, etc.)
                    title = task.get('title', '').upper()
                    for env in ['LLE', 'PROD', 'UAT', 'DEV', 'TEST']:
                        if env in title:
                            if env not in environments:
                                environments.append(env)
                
                updated_component = component.copy()
                updated_component['environments'] = environments
                updated_components.append(updated_component)
            
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
            response = self.session.get(url, verify=False)
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ansible Tower connection test failed: {str(e)}")
            return False
    
    def get_auth_token(self):
        """Get basic auth token for Ansible Tower"""
        return create_basic_auth(self.username, self.password)
    
    @lru_cache(maxsize=32)
    def get_inventories_by_spk(self, spk):
        """Get inventory groups by SPK"""
        try:
            # Set up Basic Authentication if not already done
            if 'Authorization' not in self.session.headers:
                auth_token = create_basic_auth(self.username, self.password)
                self.session.headers.update({'Authorization': f'Basic {auth_token}'})
                
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
            
            return inventories
        except Exception as e:
            logger.error(f"Error getting inventories by SPK: {str(e)}")
            return []
    
    def get_servers_for_component(self, component_name, environment, inventories):
        """Get server details for a component and environment"""
        try:
            # Set up Basic Authentication if not already done
            if 'Authorization' not in self.session.headers:
                auth_token = create_basic_auth(self.username, self.password)
                self.session.headers.update({'Authorization': f'Basic {auth_token}'})
                
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