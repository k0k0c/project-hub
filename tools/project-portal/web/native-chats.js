/* External chat addresses are supplied by the server, independently of Hub actors. */
(() => {
  'use strict';
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const privateParameters = new Set(['token','accesstoken','idtoken','refreshtoken','bearertoken',
    'apikey','authorization','password','secret','clientsecret','credential','credentials',
    'signature','sig','xamzsignature','xgoogsignature']);
  function uri(resource) {
    const value = resource?.openUri;
    if (typeof value !== 'string' || /[\x00-\x20\\"<>]/.test(value)) return null;
    try {
      const parsed = new URL(value);
      if (parsed.username || parsed.password) return null;
      for (const parameters of [parsed.search, parsed.hash.replace(/^#/, '').split('?').pop()]) {
        for (const key of new URLSearchParams(parameters).keys()) {
          if (privateParameters.has(key.toLowerCase().replace(/[^a-z0-9]/g, ''))) return null;
        }
      }
      if (parsed.protocol === 'https:') return value;
      if (parsed.protocol === 'http:' && ['localhost','127.0.0.1','[::1]'].includes(parsed.hostname)) return value;
      if (/^codex:\/\/threads\/[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value)) return value;
    } catch (_) { /* Unknown source addresses remain plain metadata. */ }
    return null;
  }
  function link(resource, label) {
    const target = uri(resource);
    if (!target) return '';
    return `<a href="${escape(target)}" target="_blank" rel="noopener noreferrer">${escape(label || resource.title || resource.client || 'Chat')}</a>`;
  }
  window.HubNativeChats = {uri,link};
})();
