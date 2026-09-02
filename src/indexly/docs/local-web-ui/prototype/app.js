(() => {
  const $ = (selector) => document.querySelector(selector);
  const inspector = $('#inspector');
  const workspace = $('.workspace');
  if (window.matchMedia('(max-width: 1050px)').matches) workspace.classList.add('inspector-collapsed');
  const splitter = $('#splitter');
  const toast = $('#toast');
  const showToast = (message) => { toast.textContent = message; toast.classList.add('show'); setTimeout(() => toast.classList.remove('show'), 2600); };
  const navToggle = $('#workspace-nav-toggle');
  const closeNavigation = () => { workspace.classList.remove('nav-open'); navToggle.setAttribute('aria-expanded', 'false'); };
  navToggle.addEventListener('click', () => { const open = workspace.classList.toggle('nav-open'); navToggle.setAttribute('aria-expanded', String(open)); if (open) $('#workspace-nav-close').focus(); });
  $('#workspace-nav-close').addEventListener('click', () => { closeNavigation(); navToggle.focus(); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && workspace.classList.contains('nav-open')) { closeNavigation(); navToggle.focus(); } });

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
  const showWorkspaceView = (view) => {
    viewPages.forEach((page) => { page.hidden = page.id !== `${view}-page`; });
    workspaceViews.forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle('active', active);
      button.toggleAttribute('aria-current', active);
    });
    const isSearch = view === 'search';
    if (!isSearch) {
      closeInspector(false);
      $('#show-preview').hidden = true;
    } else if (workspace.classList.contains('inspector-collapsed')) {
      $('#show-preview').hidden = false;
    }
    closeNavigation();
    document.title = `Indexly — ${isSearch ? 'Search workspace' : view === 'activity' ? 'Activity' : 'Index health'} prototype`;
    $('#main-content').focus({ preventScroll: true });
  };
  workspaceViews.forEach((button) => button.addEventListener('click', () => showWorkspaceView(button.dataset.view)));
  document.querySelectorAll('[data-prototype-action]').forEach((button) => button.addEventListener('click', () => showToast(button.dataset.prototypeAction)));

  const resize = (width) => { const clamped = Math.max(270, Math.min(540, width)); workspace.style.setProperty('--inspector-width', `${clamped}px`); splitter.setAttribute('aria-valuenow', String(Math.round(clamped))); };
  splitter.addEventListener('pointerdown', (event) => { splitter.setPointerCapture(event.pointerId); const move = (moveEvent) => resize(window.innerWidth - moveEvent.clientX); const stop = () => { splitter.removeEventListener('pointermove', move); splitter.removeEventListener('pointerup', stop); }; splitter.addEventListener('pointermove', move); splitter.addEventListener('pointerup', stop); });
  splitter.addEventListener('keydown', (event) => { const value = Number(splitter.getAttribute('aria-valuenow')); if (event.key === 'ArrowLeft') { resize(value + 20); event.preventDefault(); } if (event.key === 'ArrowRight') { resize(value - 20); event.preventDefault(); } if (event.key === 'Home') { resize(270); event.preventDefault(); } if (event.key === 'End') { resize(540); event.preventDefault(); } });

  $('#filters-toggle').addEventListener('click', (event) => { const filters = $('#filters'); filters.hidden = !filters.hidden; event.currentTarget.setAttribute('aria-expanded', String(!filters.hidden)); });
  $('.search-form').addEventListener('submit', (event) => { event.preventDefault(); showToast(`Showing static prototype results for “${$('#query').value}”.`); });
  const dialog = $('#view-dialog');
  $('#workspace-manager').addEventListener('click', () => dialog.showModal());
  $('#settings-button').addEventListener('click', () => dialog.showModal());
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
