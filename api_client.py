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
    
    def extract_release_id_from_url(self, release_url):
        """
        Extract the release ID from a release train URL, handling relationship table URLs.
        
        Args:
            release_url: URL of the release train, may include '#/releases/' and '/relationships/table'
            
        Returns:
            str: The extracted release ID
        """
        logger.info(f"Extracting release ID from URL: {release_url}")
        
        # Handle URL encoding
        release_url = release_url.replace('%23', '#').replace('%2F', '/')
        
        # FIRST APPROACH: Direct regex pattern matching for Release ID
        # This is the most reliable method and should work with any URL format
        release_pattern = r'Release([a-zA-Z0-9]+)'
        release_match = re.search(release_pattern, release_url)
        if release_match:
            release_id = "Release" + release_match.group(1)
            logger.info(f"Extracted Release ID using direct regex: {release_id}")
            return release_id
        
        # SECOND APPROACH: Special handling for complex URLs with hash fragments and relationships/table
        if '#/' in release_url and '/relationships/table' in release_url:
            # For URLs like "https://release.horizon.bankofamerica.com/#/releases/Folder-Folder-Folder-ReleaseXXX/relationships/table"
            # Extract the Release part using a more specific pattern
            parts = release_url.split('/')
            for part in parts:
                if 'Release' in part:
                    # This handles both standalone "ReleaseXXX" and "Folder-Folder-ReleaseXXX" patterns
                    if '-Release' in part:
                        final_parts = part.split('-')
                        for p in final_parts:
                            if p.startswith('Release'):
                                release_id = p
                                logger.info(f"Extracted Release ID from folder-release pattern: {release_id}")
                                return release_id
                    elif part.startswith('Release'):
                        logger.info(f"Found Release ID directly: {part}")
                        return part
        
        # THIRD APPROACH: General case - handle URL fragments
        modified_url = release_url
        if '#/' in modified_url:
            modified_url = modified_url.replace('#/', '/')
        
        if '/relationships/table' in modified_url:
            modified_url = modified_url.replace('/relationships/table', '')
        
        # Split the modified URL by '/'
        parts = modified_url.split('/')
        
        # Look for any part that contains 'Release'
        for part in parts:
            if 'Release' in part:
                if '-Release' in part:
                    # Handle the case where Release is part of a compound ID
                    for segment in part.split('-'):
                        if segment.startswith('Release'):
                            logger.info(f"Found Release ID in compound part: {segment}")
                            return segment
                elif part.startswith('Release'):
                    logger.info(f"Found Release ID as standalone part: {part}")
                    return part
        
        # FALLBACK: If all else fails, create a generic fallback
        logger.warning(f"Could not extract Release ID from URL using any method: {release_url}")
        return "table"  # This will trigger a 401 error which is better than using a wrong ID
    
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
            # Extract release ID from URL using the dedicated method
            release_id = self.extract_release_id_from_url(release_url)
            
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
                
                # First try to get SPK from releaseComponents variable (highest priority)
                release_components_var = None
                for var in variables:
                    if var.get('key') == 'releaseComponents':
                        release_components_var = var.get('value')
                        logger.info(f"Found releaseComponents variable: {release_components_var}")
                        break
                
                if release_components_var:
                    # The first word in release_components_var should be the SPK
                    parts = release_components_var.split()
                    if parts and len(parts) > 0:
                        spk_name = parts[0].strip()
                        if spk_name and spk_name != "SPK_PROD":
                            logger.info(f"Using first word from releaseComponents as SPK: {spk_name}")
                            result['spk'] = spk_name
                
                # Try to get SPK from releaseName variable if not found yet
                if not result.get('spk'):
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
            # Extract release ID from URL using the dedicated method
            release_id = self.extract_release_id_from_url(release_url)
            
            # Get release details with variables
            url = f"{self.base_url}/api/v1/releases/{release_id}"
            logger.debug(f"Getting release details from: {url}")
            response = self.session.get(url, verify=False)
            
            if response.status_code != 200:
                logger.error(f"Failed to get release details: {response.status_code}")
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
            
            if release_components_var:
                # Split by spaces and skip the first word (which is the SPK)
                parts = release_components_var.split()
                if len(parts) > 1:
                    # Skip the first part (SPK) and use the remaining as components
                    for component_name in parts[1:]:
                        component_name = component_name.strip()
                        if component_name:
                            components.append({
                                'id': f"component_{len(components)}",
                                'name': component_name,
                                'environments': []
                            })
                    
                    logger.info(f"Successfully extracted {len(components)} components from releaseComponents variable")
                    return components
            
            # Fallback: Extract components from phase titles or task groups
            logger.info("Falling back to phase/task analysis for component extraction")
            
            # Look for phases named after components
            for phase in release_data.get('phases', []):
                phase_title = phase.get('title', '')
                
                # Check if this might be a component phase
                if "component" in phase_title.lower():
                    component_name = phase_title.replace("Component", "").replace("component", "").strip()
                    if component_name:
                        components.append({
                            'id': phase.get('id', f"phase_{len(components)}"),
                            'name': component_name,
                            'environments': []
                        })
                
                # Look for ParallelGroup tasks that might be component groups
                for task in phase.get('tasks', []):
                    if task.get('type') == 'xlrelease.ParallelGroup':
                        task_title = task.get('title', '')
                        
                        # If title contains "component" or looks like a component name
                        if "component" in task_title.lower() or (task_title and task_title[0].isupper()):
                            # Clean up the name
                            component_name = task_title.replace("Component", "").replace("component", "").strip()
                            if component_name:
                                components.append({
                                    'id': task.get('id', f"task_{len(components)}"),
                                    'name': component_name,
                                    'environments': []
                                })
            
            logger.info(f"Extracted {len(components)} components from phases/tasks")
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
            # If no components, return empty list
            if not components:
                return []
            
            # Create a copy of components to update
            updated_components = []
            
            # If we have a release URL, try to get environments from variables
            if release_url:
                # Extract release ID from URL
                release_id = self.extract_release_id_from_url(release_url)
                
                # Get release details with variables
                url = f"{self.base_url}/api/v1/releases/{release_id}"
                logger.debug(f"Getting release details for environments from: {url}")
                response = self.session.get(url, verify=False)
                
                if response.status_code == 200:
                    release_data = response.json()
                    variables = release_data.get('variables', [])
                    
                    # Try to get environments from integratedReleaseEnvironments variable
                    environments_var = None
                    for var in variables:
                        if var.get('key') == 'integratedReleaseEnvironments':
                            environments_var = var.get('value')
                            logger.info(f"Found integratedReleaseEnvironments variable: {environments_var}")
                            break
                    
                    if environments_var:
                        # Split environments by comma, semicolon, or space
                        env_parts = re.split(r'[,;\s]+', environments_var)
                        environments = [env.strip() for env in env_parts if env.strip()]
                        
                        # Apply these environments to all components
                        for component in components:
                            updated_component = component.copy()
                            updated_component['environments'] = environments
                            updated_components.append(updated_component)
                        
                        logger.info(f"Applied environments from variable to all {len(components)} components: {environments}")
                        return updated_components
            
            # Fallback: Look for environment indicators in tasks
            logger.info("Falling back to task title analysis for environment extraction")
            
            for component in components:
                # Start with an empty list of environments
                environments = []
                
                # Try to get component details if we have an ID
                if 'id' in component and component['id']:
                    try:
                        # This might be a phase or task ID
                        # First try as a task
                        url = f"{self.base_url}/api/v1/tasks/{component['id']}"
                        response = self.session.get(url, verify=False)
                        
                        # If that fails, try as a phase
                        if response.status_code != 200:
                            url = f"{self.base_url}/api/v1/phases/{component['id']}"
                            response = self.session.get(url, verify=False)
                        
                        if response.status_code == 200:
                            task_data = response.json()
                            
                            # Look for subtasks
                            for task in task_data.get('tasks', []):
                                title = task.get('title', '').upper()
                                
                                # Check for common environment keywords
                                env_keywords = ['DEV', 'TEST', 'QA', 'UAT', 'STAGING', 'PROD', 'PRODUCTION', 'LLE']
                                for env in env_keywords:
                                    if env in title:
                                        if env not in environments:
                                            environments.append(env)
                                            break
                    except Exception as e:
                        logger.warning(f"Error getting task details for component {component['name']}: {str(e)}")
                
                # If we didn't find any environments, use defaults
                if not environments:
                    environments = ['DEV', 'TEST', 'PROD']
                    logger.info(f"Using default environments for component {component['name']}")
                
                # Update the component with environments
                updated_component = component.copy()
                updated_component['environments'] = environments
                updated_components.append(updated_component)
            
            logger.info(f"Assigned environments to {len(updated_components)} components")
            return updated_components
            
        except Exception as e:
            logger.error(f"Error getting environments for components: {str(e)}")
            # Return original components if there's an error
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
            
            if response.status_code == 200:
                logger.info("Ansible Tower connection successful")
                return True
            else:
                try:
                    error_content = response.json()
                    logger.error(f"Ansible Tower API error: {error_content}")
                except:
                    logger.error(f"Ansible Tower API returned status code: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"Ansible Tower connection test failed: {str(e)}")
            return False
    
    def get_auth_token(self):
        """Get basic auth token for Ansible Tower"""
        return create_basic_auth(self.username, self.password)
    
    def get_inventories_by_spk(self, spk_data):
        """
        Get inventory groups by SPK, filtered by organization name if available
        
        Args:
            spk_data: Either a string containing just the SPK, or a dictionary with 'spk' and 'org_name' keys
            
        Returns:
            List of inventories matching the SPK, filtered by organization name if provided
        """
        try:
            # Extract SPK and org_name from input
            spk = spk_data
            org_name = None
            
            if isinstance(spk_data, dict):
                spk = spk_data.get('spk')
                org_name = spk_data.get('org_name')
            
            if not spk:
                logger.error("No SPK provided for inventory search")
                return []
            
            # Log what we're searching for
            if org_name:
                logger.info(f"Searching for inventories with SPK: {spk} and org: {org_name}")
            else:
                logger.info(f"Searching for inventories with SPK: {spk}")
            
            # Get all inventories
            url = f"{self.base_url}/api/v2/inventories/"
            logger.debug(f"Getting all inventories from: {url}")
            response = self.session.get(url, verify=False)
            
            if response.status_code != 200:
                logger.error(f"Failed to get inventories: {response.status_code}")
                return []
            
            inventories_data = response.json()
            matching_inventories = []
            
            # First look for exact inventory name match
            exact_pattern = f"{spk}_PROD"
            for inventory in inventories_data.get('results', []):
                inventory_name = inventory.get('name', '')
                inventory_id = inventory.get('id')
                
                # Check for exact match
                if exact_pattern in inventory_name:
                    logger.info(f"Found exact inventory match: {inventory_name}")
                    
                    # If we have org_name, check if it's in the inventory name
                    if org_name and org_name not in inventory_name:
                        logger.debug(f"Skipping inventory {inventory_name} because it doesn't match org {org_name}")
                        continue
                    
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
                    
                    matching_inventories.append(inventory_with_groups)
            
            # If we didn't find any exact matches, look for partial matches
            if not matching_inventories:
                logger.info(f"No exact inventory matches found, looking for partial matches with SPK: {spk}")
                
                for inventory in inventories_data.get('results', []):
                    inventory_name = inventory.get('name', '')
                    inventory_id = inventory.get('id')
                    
                    # Check for SPK in inventory name (case-insensitive)
                    if spk.lower() in inventory_name.lower():
                        logger.info(f"Found partial inventory match: {inventory_name}")
                        
                        # If we have org_name, check if it's in the inventory name
                        if org_name and org_name not in inventory_name:
                            logger.debug(f"Skipping inventory {inventory_name} because it doesn't match org {org_name}")
                            continue
                        
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
                        
                        matching_inventories.append(inventory_with_groups)
            
            logger.info(f"Found {len(matching_inventories)} matching inventories for SPK: {spk}")
            return matching_inventories
            
        except Exception as e:
            logger.error(f"Error getting inventories for SPK {spk_data}: {str(e)}")
            return []
    
    def get_servers_for_component(self, component_name, environment, inventories):
        """Get server details for a component and environment"""
        try:
            if not component_name or not environment or not inventories:
                logger.warning("Missing required parameters for getting servers")
                return []
            
            servers = []
            
            logger.info(f"Looking for servers for component '{component_name}' in environment '{environment}'")
            
            # Handle environment naming variants
            environment_variants = [environment.upper()]
            if environment.upper() == 'PROD':
                environment_variants.append('PRODUCTION')
            if environment.upper() == 'DEV':
                environment_variants.append('DEVELOPMENT')
            
            # For each inventory
            for inventory in inventories:
                inventory_name = inventory.get('name', '')
                logger.debug(f"Checking inventory: {inventory_name}")
                
                # For each group in the inventory
                for group in inventory.get('groups', []):
                    group_name = group.get('name', '')
                    group_id = group.get('id')
                    
                    # Check if group name contains component name
                    component_match = component_name.lower() in group_name.lower()
                    
                    # Check if group name contains environment
                    env_match = False
                    for env_variant in environment_variants:
                        if env_variant.lower() in group_name.lower():
                            env_match = True
                            break
                    
                    if component_match and env_match:
                        logger.info(f"Found matching group: {group_name}")
                        
                        # Get hosts in this group
                        hosts_url = f"{self.base_url}/api/v2/groups/{group_id}/hosts/"
                        hosts_response = self.session.get(hosts_url, verify=False)
                        
                        if hosts_response.status_code != 200:
                            logger.warning(f"Failed to get hosts for group {group_name}: {hosts_response.status_code}")
                            continue
                        
                        hosts_data = hosts_response.json()
                        
                        # Process each host
                        for host in hosts_data.get('results', []):
                            host_id = host.get('id')
                            host_name = host.get('name')
                            
                            # Skip if we've already processed this host
                            existing_hosts = [s['server_name'] for s in servers]
                            if host_name in existing_hosts:
                                logger.debug(f"Skipping duplicate host: {host_name}")
                                continue
                            
                            logger.debug(f"Processing host: {host_name}")
                            
                            # Get host details
                            try:
                                host_url = f"{self.base_url}/api/v2/hosts/{host_id}/"
                                host_response = self.session.get(host_url, verify=False)
                                
                                if host_response.status_code != 200:
                                    logger.warning(f"Failed to get details for host {host_name}: {host_response.status_code}")
                                    
                                    # Even if we can't get details, include basic info
                                    server = {
                                        'server_name': host_name,
                                        'group_name': group_name,
                                        'component_name': component_name,
                                        'environment': environment,
                                        'os_info': "Unknown",
                                        'enabled': True  # Assume enabled if we can't get details
                                    }
                                    servers.append(server)
                                    continue
                                
                                host_details = host_response.json()
                                
                                # Try to get variables (might contain OS info)
                                variables = host_details.get('variables', '{}')
                                try:
                                    if isinstance(variables, str) and variables.strip():
                                        variables_dict = eval(variables)
                                    else:
                                        variables_dict = {}
                                except:
                                    variables_dict = {}
                                
                                # Extract OS information if available
                                os_name = variables_dict.get('ansible_distribution', '')
                                os_version = variables_dict.get('ansible_distribution_version', '')
                                os_info = f"{os_name} {os_version}".strip()
                                if not os_info:
                                    os_info = "Unknown"
                                
                                server = {
                                    'server_name': host_name,
                                    'group_name': group_name,
                                    'component_name': component_name,
                                    'environment': environment,
                                    'os_info': os_info,
                                    'enabled': host_details.get('enabled', True)
                                }
                                
                                servers.append(server)
                                logger.debug(f"Added server: {host_name}")
                                
                            except Exception as e:
                                logger.error(f"Error processing host {host_name}: {str(e)}")
                                # Include basic info even if there's an error
                                server = {
                                    'server_name': host_name,
                                    'group_name': group_name,
                                    'component_name': component_name,
                                    'environment': environment,
                                    'os_info': "Unknown (Error)",
                                    'enabled': True  # Assume enabled if we can't get details
                                }
                                servers.append(server)
            
            logger.info(f"Found {len(servers)} servers for component '{component_name}' in environment '{environment}'")
            return servers
            
        except Exception as e:
            logger.error(f"Error getting servers for component {component_name} in {environment}: {str(e)}")
            return []