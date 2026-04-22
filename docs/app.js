document.addEventListener('DOMContentLoaded', () => {
    // Navigation Definition
    const navItems = [
        { label: 'The Vision', path: 'index.html' },
        { label: 'Quickstart', path: 'quickstart.html' },
        { label: 'Architecture', path: 'architecture.html' },
        { label: 'Swarm & Tools', path: 'swarm-and-tools.html' },
        { label: 'Backtester', path: 'backtester.html' }
    ];

    const currentPath = window.location.pathname.split('/').pop() || 'index.html';

    // Inject Sidebar Content
    const sidebar = document.querySelector('#sidebar');
    if (sidebar) {
        const navHtml = `
            <div class="sidebar-content">
                <a href="index.html" class="sidebar-logo">
                    <img src="assets/logo.svg" alt="logo">
                    <span>indie-market-analyst</span>
                </a>
                <ul class="nav-menu">
                    ${navItems.map(item => `
                        <li class="nav-item">
                            <a href="${item.path}" class="nav-link ${currentPath === item.path ? 'active' : ''}">
                                ${item.label}
                            </a>
                        </li>
                    `).join('')}
                    <li class="nav-item" style="margin-top: 2rem;">
                        <a href="https://github.com/dharunashokkumar/indie-market-analyst" target="_blank" class="nav-link" style="font-style: normal; font-size: 0.9rem; opacity: 0.6;">
                            GitHub ↗
                        </a>
                    </li>
                </ul>
            </div>
            <div class="sidebar-footer">
                <button id="theme-toggle" class="theme-toggle" aria-label="Toggle theme">
                    <svg class="sun-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
                    <svg class="moon-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
                </button>
            </div>
        `;
        sidebar.innerHTML = navHtml;
    }

    // Theme Toggle Logic
    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', () => {
            const currentTheme = document.documentElement.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            document.documentElement.setAttribute('data-theme', newTheme);
            localStorage.setItem('ima-docs-theme', newTheme);
        });
    }

    // Copy Code Buttons
    document.querySelectorAll('pre').forEach(block => {
        const button = document.createElement('button');
        button.className = 'copy-btn';
        button.innerText = 'Copy';
        block.appendChild(button);

        button.addEventListener('click', () => {
            const code = block.querySelector('code').innerText;
            navigator.clipboard.writeText(code).then(() => {
                button.innerText = 'Copied!';
                setTimeout(() => button.innerText = 'Copy', 2000);
            });
        });
    });

    // Intersection Observer for scroll animations
    const observerOptions = {
        threshold: 0.1
    };

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
            }
        });
    }, observerOptions);

    document.querySelectorAll('.section, .card').forEach(el => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = 'all 0.6s cubic-bezier(0.23, 1, 0.32, 1)';
        observer.observe(el);
    });
});
