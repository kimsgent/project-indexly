(() => {
  const $ = (selector) => document.querySelector(selector);
  const inspector = $('#inspector');
  const workspace = $('.workspace');
  if (window.matchMedia('(max-width: 1050px)').matches) workspace.classList.add('inspector-collapsed');
  const splitter = $('#splitter');
  const toast = $('#toast');
  const showToast = (message) => { toast.textContent = message; toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 2600); };
  const navToggle = $('#workspace-nav-toggle');
  const navigation = $('#workspace-navigation');
  const mainContent = $('#main-content');
  const isTabletDrawer = () => window.matchMedia('(max-width: 1050px) and (min-width: 801px)').matches;
  const setDrawerState = (open) => {
    const active = open && isTabletDrawer();
    [mainContent, splitter, inspector, $('#show-preview')].forEach((element) => { element.inert = active; });
  };
  const closeNavigation = () => { workspace.classList.remove('nav-open'); navToggle.setAttribute('aria-expanded', 'false'); setDrawerState(false); };
  navToggle.addEventListener('click', () => { const open = workspace.classList.toggle('nav-open'); navToggle.setAttribute('aria-expanded', String(open)); setDrawerState(open); if (open) $('#workspace-nav-close').focus(); });
  $('#workspace-nav-close').addEventListener('click', () => { closeNavigation(); navToggle.focus(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && workspace.classList.contains('nav-open')) { closeNavigation(); navToggle.focus(); } });
  navigation.addEventListener('keydown', (event) => {
    if (event.key !== 'Tab' || !workspace.classList.contains('nav-open') || !isTabletDrawer()) return;
    const focusable = [...navigation.querySelectorAll('button:not([disabled]), a[href]')].filter((element) => !element.hidden);
    const first = focusable[0]; const last = focusable.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  window.addEventListener('resize', () => { if (!isTabletDrawer()) closeNavigation(); });

  document.querySelectorAll('.result').forEach((result) => {
    const select = () => {
      document.querySelector('.result.selected')?.classList.remove('selected');
      result.classList.add('selected');
      $('#preview-title').textContent = result.dataset.title;
      $('#preview-body').textContent = result.dataset.body;
      $('#preview-path').textContent = result.dataset.path;
      $('#preview-date').textContent = result.dataset.date;
      $('#preview-type').textContent = result.dataset.type;
      $('#preview-kind').textContent = `${result.dataset.type === 'PDF' ? 'PDF reference' : result.dataset.type === 'TXT' ? 'Plain text note' : 'Markdown document'}`;
      workspace.classList.remove('inspector-collapsed');
      workspace.classList.add('inspector-visible');
      inspector.classList.add('open');
      $('#show-preview').hidden = true;
    };
    result.addEventListener('click', select);
    result.addEventListener('keydown', (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); select(); } });
  });
  const closeInspector = (returnFocus = true) => { inspector.classList.remove('open'); workspace.classList.remove('inspector-visible'); workspace.classList.add('inspector-collapsed'); $('#show-preview').hidden = false; if (returnFocus) $('#show-preview').focus(); };
  $('#collapse-preview').addEventListener('click', closeInspector);
  $('#show-preview').addEventListener('click', () => { workspace.classList.remove('inspector-collapsed'); workspace.classList.add('inspector-visible'); inspector.classList.add('open'); $('#show-preview').hidden = true; });
  $('#open-original').addEventListener('click', () => showToast('Prototype only — opening originals needs the future local service.'));

  const workspaceViews = [...document.querySelectorAll('#workspace-navigation [data-view]')];
  const viewPages = [...document.querySelectorAll('.view-page')];
  const settingsControls = [$('#settings-button'), $('#settings-link')];
  const showWorkspaceView = (view) => {
    const activePage = $(`#${view}-page`);
    viewPages.forEach((page) => { page.hidden = page !== activePage; });
    workspaceViews.forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    });
    settingsControls.forEach((button) => {
      const active = view === 'settings';
      button.classList.toggle('active', active);
      if (active) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
    });
    const isSearch = view === 'search';
    if (!isSearch) {
      closeInspector(false);
      $('#show-preview').hidden = true;
    } else if (workspace.classList.contains('inspector-collapsed')) {
      $('#show-preview').hidden = false;
    }
    closeNavigation();
    document.title = `Indexly — ${isSearch ? 'Search workspace' : view === 'activity' ? 'Activity' : 'Settings'} prototype`;
    activePage.querySelector('h1, h2')?.focus({ preventScroll: true });
  };
  workspaceViews.forEach((button) => button.addEventListener('click', () => showWorkspaceView(button.dataset.view)));
  settingsControls.forEach((button) => button.addEventListener('click', () => showWorkspaceView('settings')));
  document.querySelectorAll('[data-activity-filter]').forEach((button) => button.addEventListener('click', () => {
    document.querySelectorAll('[data-activity-filter]').forEach((filter) => filter.setAttribute('aria-pressed', String(filter === button)));
    showToast(`${button.textContent.trim()} selected for the static activity sample.`);
  }));
  $('#add-source').addEventListener('click', () => {
    const input = $('#source-path'); const value = input.value.trim();
    if (!value) { input.focus(); showToast('Enter an illustrative source path first.'); return; }
    const row = document.createElement('div'); row.className = 'source-row';
    const details = document.createElement('div'); const title = document.createElement('h3'); const note = document.createElement('p');
    title.textContent = 'Added illustrative source'; note.textContent = value; details.append(title, note);
    const scope = document.createElement('span'); scope.textContent = 'Not indexed';
    const state = document.createElement('span'); state.className = 'source-state'; state.textContent = 'Prototype only';
    row.append(details, scope, state); $('#added-sources').append(row); input.value = '';
    showToast('Illustrative source added locally; no filesystem scope changed.');
  });
  $('#run-index').addEventListener('click', () => {
    $('#index-action-status').textContent = 'Illustrative index intent recorded. No plan, filesystem operation, or database write was started.';
    showToast('Prototype only — a real index run requires a reviewed plan.');
  });
  const addManualTag = () => {
    const nameInput = $('#new-tag'); const name = nameInput.value.trim().replace(/^#/, '');
    if (!name) { nameInput.focus(); return; }
    const tag = document.createElement('span'); tag.className = 'tag-chip'; tag.style.setProperty('--tag-color', $('#tag-colour').value); tag.textContent = name;
    $('#manual-tags').append(tag); nameInput.value = ''; nameInput.focus();
    showToast(`“${name}” added to the local prototype tag list.`);
  };
  $('#add-tag').addEventListener('click', addManualTag);
  $('#new-tag').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); addManualTag(); } });
  $('#collect-virtual-tags').addEventListener('change', (event) => {
    $('#virtual-tags').hidden = !event.target.checked;
    showToast(event.target.checked ? 'Illustrative virtual tags shown.' : 'Illustrative virtual tags hidden.');
  });

  const resize = (width) => { const clamped = Math.max(270, Math.min(540, width)); workspace.style.setProperty('--inspector-width', `${clamped}px`); splitter.setAttribute('aria-valuenow', String(Math.round(clamped))); };
  splitter.addEventListener('pointerdown', (event) => { splitter.setPointerCapture(event.pointerId); const move = (moveEvent) => resize(window.innerWidth - moveEvent.clientX); const stop = () => { splitter.removeEventListener('pointermove', move); splitter.removeEventListener('pointerup', stop); }; splitter.addEventListener('pointermove', move); splitter.addEventListener('pointerup', stop); });
  splitter.addEventListener('keydown', (event) => { const value = Number(splitter.getAttribute('aria-valuenow')); if (event.key === 'ArrowLeft') { resize(value + 20); event.preventDefault(); } if (event.key === 'ArrowRight') { resize(value - 20); event.preventDefault(); } if (event.key === 'Home') { resize(270); event.preventDefault(); } if (event.key === 'End') { resize(540); event.preventDefault(); } });

  $('#filters-toggle').addEventListener('click', (event) => { const filters = $('#filters'); filters.hidden = !filters.hidden; event.currentTarget.setAttribute('aria-expanded', String(!filters.hidden)); });
  $('.search-form').addEventListener('submit', (event) => { event.preventDefault(); showToast(`Showing static prototype results for “${$('#query').value}”.`); });
  const dialog = $('#view-dialog');
  $('#open-workspace-views').addEventListener('click', () => dialog.showModal());
  const viewList = $('.view-list');
  const updateViewControls = () => {
    [...viewList.querySelectorAll('.view-row')].forEach((row, index, rows) => {
      row.querySelector('[data-direction="up"]').disabled = index === 0;
      row.querySelector('[data-direction="down"]').disabled = index === rows.length - 1;
    });
  };
  const setStartup = (row) => {
    const name = row.querySelector('strong').textContent;
    viewList.querySelector('.startup-tag')?.replaceWith(Object.assign(document.createElement('button'), { className: 'pin-button', type: 'button', textContent: 'Make startup' }));
    const tag = document.createElement('span'); tag.className = 'startup-tag'; tag.textContent = 'Startup';
    row.querySelector('.pin-button')?.replaceWith(tag);
    $('#startup-name').textContent = name;
  };
  viewList.addEventListener('click', (event) => {
    const button = event.target.closest('button');
    if (!button) return;
    const row = button.closest('.view-row');
    if (button.classList.contains('pin-button')) { setStartup(row); return; }
    if (!button.classList.contains('move-button')) return;
    const sibling = button.dataset.direction === 'up' ? row.previousElementSibling : row.nextElementSibling;
    if (!sibling) return;
    viewList.insertBefore(button.dataset.direction === 'up' ? row : sibling, button.dataset.direction === 'up' ? sibling : row);
    const navSection = workspaceViews[0]?.parentElement;
    const navButton = navigation.querySelector(`[data-view="${row.dataset.view}"]`);
    const siblingButton = navigation.querySelector(`[data-view="${sibling.dataset.view}"]`);
    if (navSection && navButton && siblingButton) {
      navSection.insertBefore(button.dataset.direction === 'up' ? navButton : siblingButton, button.dataset.direction === 'up' ? siblingButton : navButton);
    }
    updateViewControls();
    row.querySelector(`[data-direction="${button.dataset.direction}"]`).focus();
    showToast(`${row.querySelector('strong').textContent} moved ${button.dataset.direction}.`);
  });
  viewList.addEventListener('change', (event) => {
    if (event.target.type !== 'checkbox') return;
    const row = event.target.closest('.view-row');
    const name = row.querySelector('strong').textContent;
    if (!event.target.checked && row.querySelector('.startup-tag')) {
      event.target.checked = true;
      showToast(`${name} is this workspace's startup view and must remain enabled.`);
    } else if (!event.target.checked) {
      const button = document.querySelector(`#workspace-navigation [data-view="${row.dataset.view}"]`);
      if (button) button.hidden = true;
      if (!document.querySelector(`#${row.dataset.view}-page`).hidden) showWorkspaceView('search');
      showToast(`${name} disabled — it will no longer appear in workspace navigation.`);
    } else {
      const button = document.querySelector(`#workspace-navigation [data-view="${row.dataset.view}"]`);
      if (button) button.hidden = false;
    }
  });
  updateViewControls();
})();
