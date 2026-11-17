/* listLoader.js —— 打开页面时实时向 /api/list 取目录列表
   失败（服务没起 / 断网）时回退到旧的静态 folders.html / songs.html。 */
(function () {
  function currentPath() {
    var p = location.pathname.replace(/index\.html$/i, '');
    return p.replace(/^\/+|\/+$/g, '');
  }

  function render(items, box) {
    box.innerHTML = '';
    if (!items || !items.length) {
      box.textContent = '这里还没有内容';
      return;
    }
    var frag = document.createDocumentFragment();
    items.forEach(function (it) {
      var a = document.createElement('a');
      a.href = it.href;
      a.textContent = it.label;
      a.target = '_blank';
      frag.appendChild(a);
      frag.appendChild(document.createElement('br'));
    });
    box.appendChild(frag);
  }

  window.loadListing = function (opts) {
    opts = opts || {};
    var box = document.getElementById('loadedContent');
    if (!box) return;
    var path = opts.path || currentPath();
    var url = '/api/list?path=' + encodeURIComponent(path) + (opts.dirsOnly ? '&dirs=1' : '');

    fetch(url, { cache: 'no-store' })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data.ok) throw new Error(data.error || 'api error');
        render(data.items, box);
      })
      .catch(function (err) {
        console.warn('[list] API 不可用，回退静态列表：' + err.message);
        if (typeof window.fetchData === 'function') {
          window.fetchData(opts.fallback || 'folders.html');
        } else {
          box.textContent = '列表加载失败';
        }
      });
  };
})();
