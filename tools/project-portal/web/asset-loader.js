/* Lazy loading for the architecture workspace's sizeable graph dependencies. */
(function (root) {
  'use strict';

  const architectureAssets = [
    '/vendor/cytoscape.js',
    '/vendor/layout-base.js',
    '/vendor/cose-base.js',
    '/vendor/cytoscape-fcose.js',
    '/vendor/elk-api.js',
    '/architecture-map.js',
    '/architecture-routing.js',
    '/architecture-canvas.js',
  ];
  const pending = new Map();
  let architecturePending = null;

  function assetUrl(path) {
    const url = new URL(path, root.location?.origin || root.location?.href || '/');
    const expectedOrigin = root.location?.origin;
    if ((expectedOrigin && expectedOrigin !== 'null' && url.origin !== expectedOrigin) || (url.protocol !== 'http:' && url.protocol !== 'https:')) {
      throw new Error('Unsafe asset URL');
    }
    return url.href;
  }

  function loadScript(path) {
    if (pending.has(path)) return pending.get(path);
    const promise = new Promise((resolve, reject) => {
      const script = root.document.createElement('script');
      script.async = false;
      script.src = assetUrl(path);
      script.onload = () => resolve();
      script.onerror = () => {
        script.remove?.();
        reject(new Error(`Failed to load ${path}`));
      };
      (root.document.head || root.document.documentElement).appendChild(script);
    }).catch(error => {
      pending.delete(path);
      throw error;
    });
    pending.set(path, promise);
    return promise;
  }

  function ensureArchitecture() {
    if (!architecturePending) {
      architecturePending = architectureAssets.reduce((chain, path) => chain.then(() => loadScript(path)), Promise.resolve())
        .catch(error => { architecturePending = null; throw error; });
    }
    return architecturePending;
  }

  root.HubAssets = Object.freeze({ ensureArchitecture });
})(typeof window !== 'undefined' ? window : globalThis);
