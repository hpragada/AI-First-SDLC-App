/* ============================================================================
   Edvensoft AI-First SDLC — shell.js
   Injects the canonical app shell (240px navy sidebar + 56px top bar) around a
   screen's content so every authed screen shares identical chrome.

   USAGE (per authed screen):
     <body>
       <main id="screen"> ...states built from components.css... </main>
       <script src="../shell.js"></script>
       <script>shellMount("work-items");</script>
     </body>

   shellMount(navId, opts?) — navId activates a sidebar item. opts (all optional):
     { tenant:"Acme Corp", project:"Payment Gateway v2",
       companion:"ready"|"offline"|"connecting", bell:4,
       user:"You", email:"you@acme.test", admin:true }
   Unauth screens (S-01..S-04) do NOT load shell.js — they render a centered card.
   ========================================================================== */
(function () {
  "use strict";

  var ICON = {
    dashboard: '<path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z"/>',
    work: '<path d="M4 4h16v4H4zM4 10h16v4H4zM4 16h10v4H4z"/>',
    runs: '<path d="M8 5v14l11-7z"/>',
    gate: '<path d="M12 2l8 4v6c0 5-3.4 8.6-8 10-4.6-1.4-8-5-8-10V6l8-4z"/>',
    clar: '<path d="M21 6h-7M3 6h7M3 12h18M3 18h11"/><circle cx="17" cy="18" r="3"/>',
    artifacts: '<path d="M4 4h10l6 6v10H4z"/><path d="M14 4v6h6"/>',
    profile: '<path d="M14 3H6v18h12V9z"/><path d="M14 3v6h6"/><path d="M9 13h6M9 16h4"/>',
    onboarding: '<path d="M12 3l9 5-9 5-9-5 9-5z"/><path d="M3 13l9 5 9-5"/>',
    integrations: '<rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>',
    repos: '<path d="M5 3h11l3 3v15H5z"/><path d="M9 7h6M9 11h6M9 15h4"/>',
    admin: '<circle cx="12" cy="8" r="4"/><path d="M4 21v-1c0-3.3 3.6-5 8-5s8 1.7 8 5v1"/>',
    a11y: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="7.5" r="1.4"/><path d="M7 10.5h10M12 11v4M12 15l-2.2 3.5M12 15l2.2 3.5"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>'
  };

  function svg(path, cls) {
    return '<svg class="' + (cls || '') + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + path + '</svg>';
  }

  // Canonical nav (matches SCREEN_INVENTORY shared-chrome; expanded per IA §2.1
  // so every authed screen has an active target). counts use sample data.
  var NAV = [
    { section: null, items: [
      { id: 'dashboard',     label: 'Workspace Dashboard',     icon: ICON.dashboard, href: 'S-31-dashboard.html' },
      { id: 'work-items',    label: 'Work Items',              icon: ICON.work,      href: 'S-14-work-items-board.html' },
      { id: 'runs',          label: 'Phases & Runs',           icon: ICON.runs,      href: 'S-18-phases-runs.html' },
      { id: 'gates',         label: 'Gates',                   icon: ICON.gate,      href: 'S-21-gates.html', count: 3 },
      { id: 'clarifications',label: 'Clarifications',          icon: ICON.clar,      href: 'S-20-clarifications.html', count: 1 },
      { id: 'artifacts',     label: 'Artifacts & Traceability',icon: ICON.artifacts, href: 'S-28-artifacts.html' },
      // Accessibility (QA-23a). Its own item rather than buried under Gates/Artifacts: it is a
      // named job a named role does repeatedly, and the count is how the reviewer learns there
      // is work without going to look. ALWAYS present, never revealed by a run — "no menu" and
      // "nothing was ever checked" must not look the same.
      { id: 'a11y',          label: 'Accessibility',           icon: ICON.a11y,      href: 'S-36-a11y-review.html', count: 7 }
    ]},
    { section: 'Project', items: [
      { id: 'profile',       label: 'Project Profile',         icon: ICON.profile,      href: 'S-10-project-profile.html' },
      { id: 'onboarding',    label: 'Onboarding',              icon: ICON.onboarding,   href: 'S-24-onboarding-hub.html' },
      { id: 'integrations',  label: 'Integrations',            icon: ICON.integrations, href: 'S-11-integrations.html' },
      { id: 'repositories',  label: 'Repositories',            icon: ICON.repos,        href: 'S-13-repositories.html' }
    ]},
    { section: 'Admin', adminOnly: true, items: [
      { id: 'admin',         label: 'Workspace Admin',         icon: ICON.admin,        href: 'S-07-users-invites.html' }
    ]}
  ];

  function initials(name) {
    return name.split(/\s+/).map(function (w) { return w[0]; }).slice(0, 2).join('').toUpperCase();
  }

  function navItemHTML(it, activeId) {
    var current = it.id === activeId ? ' aria-current="page"' : '';
    var count = it.count != null ? '<span class="nav-item__count">' + it.count + '</span>' : '';
    return '<a class="nav-item" href="' + it.href + '"' + current + '>' +
      svg(it.icon) + '<span class="nav-item__label">' + it.label + '</span>' + count + '</a>';
  }

  function buildSidebar(o) {
    var groups = NAV.map(function (g) {
      if (g.adminOnly && !o.admin) return '';
      var head = g.section ? '<div class="sidebar__section">' + g.section + '</div>' : '';
      return head + g.items.map(function (it) { return navItemHTML(it, o.navId); }).join('');
    }).join('');

    var compState = o.companion;                 // ready | offline | connecting
    var compLabel = { ready: 'Ready', offline: 'Offline', connecting: 'Connecting' }[compState] || 'Ready';

    return '' +
      '<aside class="sidebar">' +
        '<div class="sidebar__brand">' +
          '<span class="sidebar__brand-mark" aria-hidden="true"></span>' +
          '<span class="sidebar__brand-text">edvensoft</span>' +
        '</div>' +
        '<nav class="sidebar__nav" aria-label="Primary">' + groups + '</nav>' +
        '<div class="sidebar__foot">' +
          '<span class="companion-pill companion-pill--' + compState + '">' +
            '<span class="status-dot"></span>Companion: ' + compLabel +
          '</span>' +
        '</div>' +
      '</aside>';
  }

  function buildTopbar(o) {
    return '' +
      '<header class="topbar">' +
        '<button class="switcher" aria-label="Switch tenant">' +
          '<span class="switcher__glyph">' + initials(o.tenant) + '</span>' + o.tenant +
          '<span class="switcher__caret" aria-hidden="true">&#9662;</span>' +
        '</button>' +
        '<span class="crumb-sep" aria-hidden="true">/</span>' +
        '<button class="switcher" aria-label="Switch project">' +
          '<span aria-hidden="true">&#9873;</span>' + o.project +
          '<span class="switcher__caret" aria-hidden="true">&#9662;</span>' +
        '</button>' +
        '<span class="u-spacer"></span>' +
        '<span class="companion-pill companion-pill--' + o.companion + '" style="width:auto;background:var(--bg-subtle);color:var(--text-body)">' +
          '<span class="status-dot"></span>Companion: ' +
          ({ ready: 'Ready', offline: 'Offline', connecting: 'Connecting' }[o.companion] || 'Ready') +
        '</span>' +
        '<button class="bell" aria-label="Notifications, ' + o.bell + ' unread">' +
          svg(ICON.bell) + (o.bell ? '<span class="bell__badge">' + o.bell + '</span>' : '') +
        '</button>' +
        // Account menu — the topbar avatar toggles a dropdown with the signed-in
        // user + Sign out (mirrors the built React AppShell AccountMenu).
        '<div class="account-menu" id="account-menu">' +
          '<button class="avatar" id="account-menu-trigger" aria-label="Account menu for ' + o.user + '"' +
            ' aria-haspopup="menu" aria-expanded="false">' + initials(o.user) + '</button>' +
          '<div class="account-menu__pop" id="account-menu-pop" role="menu" aria-label="Account" hidden>' +
            '<div class="account-menu__head">' +
              '<div class="account-menu__name">' + o.user + '</div>' +
              '<div class="account-menu__email">' + o.email + '</div>' +
            '</div>' +
            '<div class="account-menu__sep" role="separator"></div>' +
            '<a class="account-menu__item account-menu__item--danger" role="menuitem" href="S-02-login.html">Sign out</a>' +
          '</div>' +
        '</div>' +
      '</header>';
  }

  // Wire the topbar account menu: toggle on the avatar, close on outside click / Esc —
  // the same open/close lifecycle the built AppShell account menu uses.
  function wireAccountMenu() {
    var root = document.getElementById('account-menu');
    var trigger = document.getElementById('account-menu-trigger');
    var pop = document.getElementById('account-menu-pop');
    if (!root || !trigger || !pop) return;

    function setOpen(open) {
      pop.hidden = !open;
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    trigger.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(pop.hidden);
    });
    document.addEventListener('click', function (e) {
      if (!root.contains(e.target)) setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setOpen(false);
    });
  }

  window.shellMount = function (navId, opts) {
    var o = Object.assign({
      navId: navId,
      tenant: 'Acme Corp',
      project: 'Payment Gateway v2',
      companion: 'ready',
      bell: 4,
      user: 'You',
      email: 'you@acme.test',
      admin: true
    }, opts || {});
    o.navId = navId;

    var screen = document.getElementById('screen');
    if (!screen) { console.warn('shell.js: no #screen element found'); return; }

    var shell = document.createElement('div');
    shell.className = 'app-shell';
    shell.innerHTML = buildSidebar(o) +
      '<div class="app-main">' + buildTopbar(o) + '<div class="app-canvas" id="app-canvas"></div></div>';

    document.body.insertBefore(shell, screen);
    shell.querySelector('#app-canvas').appendChild(screen);
    wireAccountMenu();
  };
})();
