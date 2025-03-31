document.addEventListener('DOMContentLoaded', function() {
    // DOM Elements
    const authForm = document.getElementById('auth-form');
    const dataForm = document.getElementById('data-form');
    const dataFormCard = document.getElementById('data-form-card');
    const statusContainer = document.getElementById('status-container');
    const progressContainer = document.getElementById('progress-container');
    const stepsContainer = document.getElementById('steps-container');
    const logContainer = document.getElementById('log-messages');
    const downloadContainer = document.getElementById('download-container');
    const downloadLocationContainer = document.getElementById('download-location-container');
    const downloadLocationText = document.getElementById('download-location-text');
    const overallProgress = document.getElementById('overall-progress');
    const downloadBtn = document.getElementById('download-btn');
    const loginBtn = document.getElementById('login-btn');
    const logoutBtn = document.getElementById('logout-btn');
    const clearLogsBtn = document.getElementById('clear-logs-btn');
    const themeToggleBtn = document.getElementById('theme-toggle-btn');
    const togglePasswordBtn = document.getElementById('toggle-password');
    const passwordInput = document.getElementById('password');
    
    // EventSource for server-sent events
    let eventSource = null;
    
    // App state
    let currentTheme = 'dark';
    let authenticated = false;
    let currentFilename = '';
    
    // Initialize UI
    initializeUI();
    
    // Form submission handlers
    authForm.addEventListener('submit', handleAuthSubmit);
    dataForm.addEventListener('submit', handleDataSubmit);
    
    // Button event handlers
    logoutBtn.addEventListener('click', handleLogout);
    clearLogsBtn.addEventListener('click', clearLogs);
    themeToggleBtn.addEventListener('click', toggleTheme);
    togglePasswordBtn.addEventListener('click', togglePasswordVisibility);
    
    /**
     * Initialize UI elements and check for stored theme
     */
    function initializeUI() {
        // Check for stored theme preference
        const storedTheme = localStorage.getItem('theme');
        if (storedTheme) {
            setTheme(storedTheme);
        }
        
        // Add initial log entry
        addLogEntry('Tool initialized and ready.', 'info');
    }
    
    /**
     * Handle authentication form submission
     */
    function handleAuthSubmit(event) {
        event.preventDefault();
        
        // Update UI
        loginBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Authenticating...';
        loginBtn.disabled = true;
        addLogEntry('Authenticating with XLR and Ansible Tower...', 'info');
        
        // Get form data
        const formData = new FormData(authForm);
        
        // Send authentication request
        fetch('/authenticate', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.status === 'success') {
                authenticated = true;
                updateUIAfterAuth(true);
                addLogEntry(data.message, 'success');
            } else {
                authenticated = false;
                updateUIAfterAuth(false);
                addLogEntry(`Authentication failed: ${data.message}`, 'error');
            }
        })
        .catch(error => {
            authenticated = false;
            updateUIAfterAuth(false);
            addLogEntry(`Error during authentication: ${error.message}`, 'error');
        })
        .finally(() => {
            loginBtn.innerHTML = '<i class="fas fa-sign-in-alt"></i> Login';
            loginBtn.disabled = false;
        });
    }
    
    /**
     * Update UI after authentication attempt
     */
    function updateUIAfterAuth(success) {
        if (success) {
            // Show data form
            dataFormCard.classList.remove('d-none');
            
            // Update auth form
            loginBtn.classList.add('d-none');
            logoutBtn.classList.remove('d-none');
            
            // Disable inputs
            document.getElementById('nbk_id').disabled = true;
            document.getElementById('password').disabled = true;
            
            // Update status
            statusContainer.innerHTML = `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle"></i> Successfully authenticated. You can now fetch server data.
                </div>
            `;
        } else {
            // Hide data form
            dataFormCard.classList.add('d-none');
            
            // Update auth form
            loginBtn.classList.remove('d-none');
            logoutBtn.classList.add('d-none');
            
            // Enable inputs
            document.getElementById('nbk_id').disabled = false;
            document.getElementById('password').disabled = false;
            
            // Update status
            statusContainer.innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-circle"></i> Authentication failed. Please check your credentials.
                </div>
            `;
        }
    }
    
    /**
     * Handle data form submission
     */
    function handleDataSubmit(event) {
        event.preventDefault();
        
        if (!authenticated) {
            addLogEntry('Not authenticated. Please login first.', 'error');
            return;
        }
        
        // Get form data
        const formData = new FormData(dataForm);
        const fetchBtn = document.getElementById('fetch-btn');
        
        // Update UI
        resetProgressUI();
        fetchBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Fetching...';
        fetchBtn.disabled = true;
        progressContainer.classList.remove('d-none');
        stepsContainer.classList.remove('d-none');
        downloadContainer.classList.add('d-none');
        
        addLogEntry('Starting data collection process...', 'info');
        
        // Close any existing EventSource
        if (eventSource) {
            eventSource.close();
        }
        
        // Create new EventSource for real-time updates
        eventSource = new EventSource(`/fetch_data?${new URLSearchParams({
            release_train_url: formData.get('release_train_url')
        })}`);
        
        // Set up event handlers
        eventSource.onmessage = handleEventMessage;
        eventSource.onerror = handleEventError;
        
        // Use regular fetch to start the process
        fetch('/fetch_data', {
            method: 'POST',
            body: formData
        });
    }
    
    /**
     * Handle SSE message events
     */
    function handleEventMessage(event) {
        const data = JSON.parse(event.data);
        
        // Update progress based on the step
        if (data.step) {
            updateStepStatus(data.step, data.status, data.message);
            
            // Update overall progress based on completed steps
            const completedSteps = document.querySelectorAll('.step-complete').length;
            const totalSteps = 5; // Total number of steps
            const progressPercentage = (completedSteps / totalSteps) * 100;
            overallProgress.style.width = `${progressPercentage}%`;
            
            // Add log entry
            addLogEntry(data.message, data.status === 'error' ? 'error' : 'info');
            
            // If we have progress information
            if (data.progress) {
                // Update the specific step progress
                const stepElement = document.getElementById(`step-${data.step}`);
                if (stepElement) {
                    const statusBadge = stepElement.querySelector('.step-status');
                    if (statusBadge) {
                        statusBadge.textContent = `${Math.round(data.progress)}%`;
                    }
                }
            }
            
            // If download is ready
            if (data.download_ready && data.filename) {
                currentFilename = data.filename;
                
                // If we have download location directly in the event data
                if (data.download_location) {
                    downloadLocationContainer.classList.remove('d-none');
                    downloadLocationText.innerHTML = `<code>${data.download_location}</code>`;
                    addLogEntry(`File will be saved to: ${data.download_location}`, 'info');
                }
                
                showDownloadButton(data.filename);
                closeEventSource();
                resetFetchButton();
            }
        } else if (data.status === 'error') {
            // Handle general error
            addLogEntry(data.message, 'error');
            closeEventSource();
            resetFetchButton();
        }
    }
    
    /**
     * Handle SSE error events
     */
    function handleEventError(event) {
        addLogEntry('Error in data stream connection. Retrying...', 'warning');
        
        // If the connection was closed and we were in the middle of processing
        if (document.getElementById('fetch-btn').disabled) {
            setTimeout(() => {
                if (eventSource.readyState === EventSource.CLOSED) {
                    addLogEntry('Connection closed. Please try again.', 'error');
                    resetFetchButton();
                }
            }, 5000);
        }
    }
    
    /**
     * Update the status of a processing step
     */
    function updateStepStatus(stepNumber, status, message) {
        const stepElement = document.getElementById(`step-${stepNumber}`);
        if (!stepElement) return;
        
        const statusBadge = stepElement.querySelector('.step-status');
        
        // Reset classes
        stepElement.classList.remove('step-in-progress', 'step-complete', 'step-error');
        
        // Update based on status
        switch (status) {
            case 'in-progress':
                stepElement.classList.add('step-in-progress');
                statusBadge.textContent = 'in progress';
                statusBadge.classList.remove('bg-secondary', 'bg-success', 'bg-danger');
                statusBadge.classList.add('bg-primary');
                break;
            case 'complete':
                stepElement.classList.add('step-complete');
                statusBadge.textContent = 'complete';
                statusBadge.classList.remove('bg-secondary', 'bg-primary', 'bg-danger');
                statusBadge.classList.add('bg-success');
                break;
            case 'error':
                stepElement.classList.add('step-error');
                statusBadge.textContent = 'error';
                statusBadge.classList.remove('bg-secondary', 'bg-primary', 'bg-success');
                statusBadge.classList.add('bg-danger');
                break;
            default:
                statusBadge.textContent = 'pending';
                statusBadge.classList.remove('bg-primary', 'bg-success', 'bg-danger');
                statusBadge.classList.add('bg-secondary');
        }
    }
    
    /**
     * Show the download button with the correct filename and location
     */
    function showDownloadButton(filename) {
        downloadContainer.classList.remove('d-none');
        downloadBtn.href = `/download/${filename}`;
        downloadBtn.download = filename;
        
        // Check if we have download location
        if (downloadLocationContainer) {
            // Make an API call to get the download location
            fetch('/download_location')
                .then(response => response.json())
                .then(data => {
                    if (data.status === 'success' && data.download_location) {
                        // Show the download location
                        downloadLocationContainer.classList.remove('d-none');
                        downloadLocationText.innerHTML = `<code>${data.download_location}</code>`;
                        addLogEntry(`File will be saved to: ${data.download_location}`, 'info');
                    }
                })
                .catch(error => {
                    console.error('Error getting download location:', error);
                });
        }
        
        addLogEntry(`Excel file '${filename}' is ready for download.`, 'success');
    }
    
    /**
     * Close the EventSource connection
     */
    function closeEventSource() {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }
    }
    
    /**
     * Reset the fetch button to its original state
     */
    function resetFetchButton() {
        const fetchBtn = document.getElementById('fetch-btn');
        fetchBtn.innerHTML = '<i class="fas fa-cloud-download-alt"></i> Fetch Server Data';
        fetchBtn.disabled = false;
    }
    
    /**
     * Reset the progress UI elements
     */
    function resetProgressUI() {
        // Reset progress bar
        overallProgress.style.width = '0%';
        
        // Reset step statuses
        for (let i = 1; i <= 5; i++) {
            updateStepStatus(i, 'pending');
        }
        
        // Hide download location container
        if (downloadLocationContainer) {
            downloadLocationContainer.classList.add('d-none');
            downloadLocationText.innerHTML = '';
        }
    }
    
    /**
     * Handle logout button click
     */
    function handleLogout() {
        fetch('/logout', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            authenticated = false;
            updateUIAfterAuth(false);
            addLogEntry('Logged out successfully.', 'info');
            resetProgressUI();
            progressContainer.classList.add('d-none');
            stepsContainer.classList.add('d-none');
            downloadContainer.classList.add('d-none');
            downloadLocationContainer.classList.add('d-none');
        })
        .catch(error => {
            addLogEntry(`Error during logout: ${error.message}`, 'error');
        });
    }
    
    /**
     * Add a log entry to the log container
     */
    function addLogEntry(message, type = 'info') {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${type}`;
        logEntry.innerHTML = `[${timestamp}] ${message}`;
        
        logContainer.appendChild(logEntry);
        logContainer.scrollTop = logContainer.scrollHeight;
    }
    
    /**
     * Clear all log entries
     */
    function clearLogs() {
        logContainer.innerHTML = '';
        addLogEntry('Logs cleared.', 'info');
    }
    
    /**
     * Toggle between light and dark theme
     */
    function toggleTheme() {
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        setTheme(newTheme);
    }
    
    /**
     * Set the application theme
     */
    function setTheme(theme) {
        const htmlElement = document.documentElement;
        const themeToggleIcon = themeToggleBtn.querySelector('i');
        const themeToggleText = themeToggleBtn.textContent.replace(themeToggleIcon.textContent, '').trim();
        
        htmlElement.setAttribute('data-bs-theme', theme);
        
        if (theme === 'dark') {
            themeToggleIcon.className = 'fas fa-sun';
            themeToggleBtn.innerHTML = `<i class="fas fa-sun"></i> Light Mode`;
        } else {
            themeToggleIcon.className = 'fas fa-moon';
            themeToggleBtn.innerHTML = `<i class="fas fa-moon"></i> Dark Mode`;
        }
        
        currentTheme = theme;
        localStorage.setItem('theme', theme);
    }
    
    /**
     * Toggle password visibility
     */
    function togglePasswordVisibility() {
        const type = passwordInput.type === 'password' ? 'text' : 'password';
        passwordInput.type = type;
        
        const icon = togglePasswordBtn.querySelector('i');
        icon.className = type === 'password' ? 'fas fa-eye' : 'fas fa-eye-slash';
    }
});

