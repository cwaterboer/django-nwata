/* ============================================
   NWATA DASHBOARD - JAVASCRIPT
   ============================================ */

// Sample hourly data - replace with actual data from backend
const hourlyData = [
    { time: '0:00', count: 1, duration: '16.7m' },
    { time: '1:00', count: 1, duration: '64.4m' },
    { time: '2:00', count: 1, duration: '108.0m' },
    { time: '3:00', count: 1, duration: '45.6m' },
    { time: '4:00', count: 1, duration: '16.1m' },
    { time: '5:00', count: 1, duration: '104.9m' },
    { time: '6:00', count: 2, duration: '71.2m' },
    { time: '7:00', count: 43, duration: '81.4m' },
    { time: '8:00', count: 23, duration: '72.8m' },
    { time: '9:00', count: 4, duration: '1.1m' },
    { time: '14:00', count: 12, duration: '287.0m' },
    { time: '15:00', count: 4, duration: '198.6m' },
    { time: '16:00', count: 2, duration: '244.0m' },
    { time: '17:00', count: 1, duration: '244.0m' },
    { time: '18:00', count: 12, duration: '244.0m' },
    { time: '19:00', count: 4, duration: '139.9m' },
    { time: '20:00', count: 32, duration: '193.0m' },
    { time: '21:00', count: 8, duration: '394.3m' },
    { time: '22:00', count: 2, duration: '66.6m' },
    { time: '23:00', count: 1, duration: '61.0m' }
];

// DOM Elements
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const hourlyGrid = document.getElementById('hourlyGrid');

// ============================================
// SIDEBAR TOGGLE FUNCTIONALITY
// ============================================

function toggleSidebar() {
    sidebar.classList.toggle('collapsed');
    // Save state to localStorage
    const isCollapsed = sidebar.classList.contains('collapsed');
    localStorage.setItem('sidebarCollapsed', isCollapsed);
}

// Initialize sidebar state from localStorage
function initSidebarState() {
    const isCollapsed = localStorage.getItem('sidebarCollapsed') === 'true';
    if (isCollapsed) {
        sidebar.classList.add('collapsed');
    }
}

// Event listener for sidebar toggle
sidebarToggle.addEventListener('click', toggleSidebar);

// ============================================
// GENERATE HOURLY BREAKDOWN
// ============================================

function generateHourlyBreakdown() {
    if (!hourlyGrid) return;

    hourlyGrid.innerHTML = '';

    hourlyData.forEach(hour => {
        const hourBlock = document.createElement('div');
        hourBlock.className = 'hour-block';

        // Add active class to hours with significant activity
        if (hour.count > 10) {
            hourBlock.classList.add('active');
        }

        hourBlock.innerHTML = `
            <div class="hour-time">${hour.time}</div>
            <div class="hour-count">${hour.count}</div>
            <div class="hour-duration">${hour.duration}</div>
        `;

        // Add click event for potential drill-down
        hourBlock.addEventListener('click', () => {
            console.log(`Clicked on ${hour.time} with ${hour.count} activities`);
            // Add navigation or modal logic here
        });

        hourlyGrid.appendChild(hourBlock);
    });
}

// ============================================
// NAVIGATION ITEM CLICK HANDLERS
// ============================================

function setupNavigation() {
    const navItems = document.querySelectorAll('.nav-item[data-view]');

    navItems.forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const view = item.getAttribute('data-view');

            // Remove active class from all items
            navItems.forEach(nav => nav.classList.remove('active'));

            // Add active class to clicked item
            item.classList.add('active');

            // Navigate to view
            console.log(`Navigating to ${view} view`);
            // Add actual navigation logic here (e.g., load different content)
        });
    });
}

// ============================================
// REAL-TIME UPDATES (Optional)
// ============================================

function updateActivityFeed() {
    // This function would fetch latest activity data from backend
    // and update the activity feed section
    console.log('Updating activity feed...');
}

function updateMetrics() {
    // This function would fetch latest metrics from backend
    // and update the metric cards
    console.log('Updating metrics...');
}

// ============================================
// CHART INITIALIZATION (for future use)
// ============================================

function initCharts() {
    // If using a charting library like Chart.js or D3.js,
    // initialize charts here
    console.log('Charts initialized');
}

// ============================================
// RESPONSIVE BEHAVIOR
// ============================================

function handleResponsive() {
    const width = window.innerWidth;

    // Auto-collapse sidebar on mobile
    if (width <= 768) {
        sidebar.classList.remove('collapsed');
        sidebar.classList.add('show-mobile');
    } else {
        sidebar.classList.remove('show-mobile');
    }
}

// ============================================
// INITIALIZATION
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    // Initialize sidebar state
    initSidebarState();

    // Generate hourly breakdown (only on dashboard page)
    if (hourlyGrid) {
        generateHourlyBreakdown();
    }

    // Setup navigation
    setupNavigation();

    // Handle responsive behavior
    handleResponsive();

    // Initialize charts (if needed)
    initCharts();

    // Setup notifications
    setupNotifications();

    // Setup tabs
    setupTabs();

    // Setup username availability check
    setupUsernameCheck();

    // Setup forms
    setupForms();

    // Setup account type toggle
    setupAccountTypeToggle();

    // Set up periodic updates (optional)
    // setInterval(updateActivityFeed, 60000); // Update every minute
    // setInterval(updateMetrics, 300000); // Update every 5 minutes
});

// Handle window resize
window.addEventListener('resize', handleResponsive);

// ============================================
// UTILITY FUNCTIONS
// ============================================

// Format time duration
function formatDuration(minutes) {
    if (minutes < 60) {
        return `${minutes.toFixed(1)}m`;
    }
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return `${hours}h ${mins.toFixed(0)}m`;
}

// Format timestamp
function formatTimestamp(date) {
    const now = new Date();
    const diff = Math.floor((now - date) / 1000 / 60); // difference in minutes

    if (diff < 1) return 'Just now';
    if (diff < 60) return `${diff} minutes ago`;
    if (diff < 1440) return `${Math.floor(diff / 60)} hours ago`;
    return `${Math.floor(diff / 1440)} days ago`;
}

// ============================================
// NOTIFICATIONS DROPDOWN
// ============================================

function setupNotifications() {
    const notificationBtn = document.getElementById('notificationBtn');
    const notificationDropdown = document.getElementById('notificationDropdown');

    if (!notificationBtn || !notificationDropdown) return;

    notificationBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        notificationDropdown.classList.toggle('show');
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!notificationDropdown.contains(e.target) && e.target !== notificationBtn) {
            notificationDropdown.classList.remove('show');
        }
    });

    // Mark all as read
    const markReadBtn = notificationDropdown.querySelector('.mark-read-btn');
    if (markReadBtn) {
        markReadBtn.addEventListener('click', () => {
            const unreadItems = notificationDropdown.querySelectorAll('.notification-item.unread');
            unreadItems.forEach(item => item.classList.remove('unread'));

            // Update badge
            const badge = document.querySelector('.notification-badge');
            if (badge) badge.textContent = '0';
        });
    }
}

// ============================================
// TAB SWITCHING
// ============================================

function setupTabs() {
    const tabButtons = document.querySelectorAll('.tab-btn');

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.getAttribute('data-tab');

            // Remove active class from all tabs and content
            tabButtons.forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => {
                content.classList.remove('active');
            });

            // Add active class to clicked tab
            button.classList.add('active');

            // Show corresponding content
            const targetContent = document.getElementById(tabName + 'Tab');
            if (targetContent) {
                targetContent.classList.add('active');
            }
        });
    });
}

// ============================================
// USERNAME AVAILABILITY CHECK
// ============================================

function setupUsernameCheck() {
    const usernameInput = document.getElementById('username');
    const usernameStatus = document.getElementById('usernameStatus');
    const usernameHint = document.getElementById('usernameHint');

    if (!usernameInput) return;

    let checkTimeout;

    usernameInput.addEventListener('input', (e) => {
        clearTimeout(checkTimeout);
        const username = e.target.value.trim();

        if (username.length < 3) {
            usernameStatus.className = 'validation-status';
            usernameHint.textContent = 'Username must be at least 3 characters';
            return;
        }

        // Show checking state
        usernameStatus.className = 'validation-status checking';
        usernameStatus.innerHTML = `
            <svg class="spinner" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="2" x2="12" y2="6"></line>
                <line x1="12" y1="18" x2="12" y2="22"></line>
                <line x1="4.93" y1="4.93" x2="7.76" y2="7.76"></line>
                <line x1="16.24" y1="16.24" x2="19.07" y2="19.07"></line>
                <line x1="2" y1="12" x2="6" y2="12"></line>
                <line x1="18" y1="12" x2="22" y2="12"></line>
                <line x1="4.93" y1="19.07" x2="7.76" y2="16.24"></line>
                <line x1="16.24" y1="7.76" x2="19.07" y2="4.93"></line>
            </svg>
        `;
        usernameHint.textContent = 'Checking availability...';

        // Simulate API call with timeout
        checkTimeout = setTimeout(() => {
            // Simulate check (replace with actual API call)
            const isAvailable = Math.random() > 0.5; // Random for demo

            if (isAvailable) {
                usernameStatus.className = 'validation-status available';
                usernameStatus.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="20 6 9 17 4 12"></polyline>
                    </svg>
                `;
                usernameHint.textContent = 'Username is available!';
            } else {
                usernameStatus.className = 'validation-status unavailable';
                usernameStatus.innerHTML = `
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <line x1="18" y1="6" x2="6" y2="18"></line>
                        <line x1="6" y1="6" x2="18" y2="18"></line>
                    </svg>
                `;
                usernameHint.textContent = 'Username is already taken';
            }
        }, 800);
    });
}

// ============================================
// FORM SUBMISSIONS
// ============================================

function setupForms() {
    const profileForm = document.getElementById('profileForm');

    if (profileForm) {
        profileForm.addEventListener('submit', (e) => {
            e.preventDefault();

            // Get form data
            const formData = new FormData(profileForm);

            // Simulate save (replace with actual API call)
            console.log('Saving profile...', Object.fromEntries(formData));

            // Show success message (you can add a toast notification here)
            alert('Profile updated successfully!');
        });
    }
}

// ============================================
// ACCOUNT TYPE TOGGLE (for Members tab)
// ============================================

function setupAccountTypeToggle() {
    const toggle = document.getElementById('accountTypeToggle');

    if (!toggle) return;

    toggle.addEventListener('change', (e) => {
        const individualView = document.querySelector('.individual-account-view');
        const orgView = document.querySelector('.organization-account-view');

        if (e.target.checked) {
            individualView.style.display = 'none';
            orgView.style.display = 'block';
        } else {
            individualView.style.display = 'block';
            orgView.style.display = 'none';
        }
    });
}

// Export functions for potential use in Django templates
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        formatDuration,
        formatTimestamp,
        updateActivityFeed,
        updateMetrics,
        setupNotifications,
        setupTabs,
        setupUsernameCheck,
        setupForms
    };
}
