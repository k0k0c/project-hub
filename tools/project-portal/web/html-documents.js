/* Rendering for versioned HTML knowledge documents. */
(() => {
  'use strict';
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function url(item,project,revision) {
    const bundle=item?.htmlBundle, entry=String(bundle?.entry||'');
    const path=entry.split('/').map(encodeURIComponent).join('/');
    return `/api/v1/knowledge/html/${encodeURIComponent(project||'')}/${encodeURIComponent(revision??'')}/${encodeURIComponent(item?.id||'')}/files/${path}`;
  }
  function comparisonText(item) {
    if(item?.format!=='html'&&!item?.htmlBundle)return String(item?.markdown||'');
    const bundle=item?.htmlBundle||{};
    const files=(Array.isArray(bundle.files)?bundle.files:[]).map(file=>({path:String(file?.path||''),hash:String(file?.hash||''),size:file?.size??null})).sort((a,b)=>a.path<b.path?-1:a.path>b.path?1:0);
    return JSON.stringify({entry:String(bundle.entry||''),files},null,2);
  }
  function warning(title,values) {
    if(!Array.isArray(values)||!values.length)return '';
    const list=values.map(value=>`<li>${esc(typeof value==='string'?value:(value?.path||value?.url||value?.id||JSON.stringify(value)))}</li>`).join('');
    return `<details class="d-html-warning"><summary>${esc(title)} <span>(${values.length})</span></summary><ul>${list}</ul></details>`;
  }
  function render(item,project,revision) {
    const href=url(item,project,revision), bundle=item?.htmlBundle||{};
    const external=Array.isArray(item?.externalResources)?item.externalResources:[];
    const status={historical:(globalThis.HubI18n?.t?.("html-documents.947a1802ee02") ?? 'Исторический материал'),draft:(globalThis.HubI18n?.t?.("html-documents.65fd24f1cb37") ?? 'Черновик'),current:(globalThis.HubI18n?.t?.("html-documents.f5b5eef91751") ?? 'Актуальный материал'),archived:(globalThis.HubI18n?.t?.("html-documents.ef422ab46b3c") ?? 'Архивный материал')}[item?.status];
    const date=item?.documentDate, dateBasis=item?.dateBasis;
    const meta=[status,date?`<time datetime="${esc(date)}"${dateBasis?(globalThis.HubI18n?.t ? globalThis.HubI18n.t("html-documents.a231f4299c1b",{v0:(esc(dateBasis))}) : ` title="Основание даты: ${esc(dateBasis)}"`):''}>${esc(date)}</time>`:'',item?.versionLabel?esc(item.versionLabel):''].filter(Boolean).map(value=>`<span>${value}</span>`).join('');
    const description=item?.description||item?.summary;
    return (globalThis.HubI18n?.t ? globalThis.HubI18n.t("html-documents.616860f14b91",{v0:(description?`<p class="d-html-description">${esc(description)}</p>`:''),v1:(warning((globalThis.HubI18n?.t?.("html-documents.6a695f6f0d7e") ?? 'Не найдены ресурсы'),item?.missingAssets)),v2:(warning((globalThis.HubI18n?.t?.("html-documents.05352527f978") ?? 'Не найдены ссылки'),item?.missingLinks)),v3:(warning((globalThis.HubI18n?.t?.("html-documents.b0b264ca9314") ?? 'Внешние ресурсы не выполняются в изолированном просмотре'),external)),v4:(meta),v5:(esc(href)),v6:(esc(href)),v7:(esc(item?.title||(globalThis.HubI18n?.t?.("html-documents.71c53cb63469") ?? 'HTML-документ'))),v8:(bundle.entry?'':(globalThis.HubI18n?.t?.("html-documents.8d1c5ffcc2fc") ?? '<p class="d-html-warning" role="alert">У HTML-документа отсутствует исходный файл.</p>'))}) : `<article class="d-html-document">${description?`<p class="d-html-description">${esc(description)}</p>`:''}${warning((globalThis.HubI18n?.t?.("html-documents.6a695f6f0d7e") ?? 'Не найдены ресурсы'),item?.missingAssets)}${warning((globalThis.HubI18n?.t?.("html-documents.05352527f978") ?? 'Не найдены ссылки'),item?.missingLinks)}${warning((globalThis.HubI18n?.t?.("html-documents.b0b264ca9314") ?? 'Внешние ресурсы не выполняются в изолированном просмотре'),external)}<div class="d-html-toolbar"><div class="d-html-meta" aria-label="Сведения о документе">${meta}</div><a class="d-html-open" href="${esc(href)}" target="_blank" rel="noopener noreferrer">Открыть отдельно</a></div><iframe class="d-html-frame" src="${esc(href)}" title="${esc(item?.title||(globalThis.HubI18n?.t?.("html-documents.71c53cb63469") ?? 'HTML-документ'))}" sandbox="allow-scripts"></iframe>${bundle.entry?'':(globalThis.HubI18n?.t?.("html-documents.8d1c5ffcc2fc") ?? '<p class="d-html-warning" role="alert">У HTML-документа отсутствует исходный файл.</p>')}</article>`);
  }
  window.HtmlDocuments={render,url,comparisonText};
})();
