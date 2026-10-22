/* Mouse gestures and render helpers for the architecture canvas. */
(() => {
  'use strict';
  const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
  function wheelZoom(zoom,logStep,min=.01,max=4) {
    if(logStep===0)return clamp(zoom,min,max);
    // Move in a smooth log coordinate whose slope is bounded at both ends.
    const scale=.35,coordinate=Math.log(zoom)+Math.log1p(zoom/scale),shifted=coordinate+logStep*Math.LN10;
    const minCoordinate=Math.log(min)+Math.log1p(min/scale),maxCoordinate=Math.log(max)+Math.log1p(max/scale);
    if(shifted<=minCoordinate)return min;
    if(shifted>=maxCoordinate)return max;
    const target=Math.exp(shifted);
    const next=2*target/(1+Math.sqrt(1+4*target/scale));
    return clamp(next,min,max);
  }
  function effectiveNodes(cy,selected=cy.nodes(':selected')) {
    const nodes=cy.collection();
    selected.forEach(node=>{nodes.merge(node).merge(node.descendants());});
    return nodes;
  }
  function selectionStats(model,selectedIds) {
    const selected=new Set(selectedIds),children=new Map(),nodes=new Map(model.nodes.map(n=>[n.id,n])),members=new Set([...selected].filter(id=>nodes.has(id)));
    for(const [child,parent] of model.parents||[]){if(!children.has(parent))children.set(parent,[]);children.get(parent).push(child);}
    const queue=[...members];for(let i=0;i<queue.length;i++)for(const id of children.get(queue[i])||[])if(!members.has(id)){members.add(id);queue.push(id);}
    const countBy=(items,field)=>{const counts={};for(const item of items){const key=item[field]||'other';counts[key]=(counts[key]||0)+1;}return counts;};
    const participants=[...members].map(id=>nodes.get(id)).filter(Boolean),facts=participants.filter(n=>n.type!=='group'),groups=participants.filter(n=>n.type==='group');
    const internal=[],incoming=[],outgoing=[];
    for(const edge of model.relations){const from=members.has(edge.from),to=members.has(edge.to);if(from&&to)internal.push(edge);else if(from)outgoing.push(edge);else if(to)incoming.push(edge);}
    const selectedRelations=model.relations.filter(edge=>selected.has(edge.id));
    const aggregate=internal.filter(e=>Number.isFinite(e.count)),components=new Set(facts.map(n=>n.component).filter(Boolean));
    return {selectedCount:selected.size,nodeCount:facts.length,groupCount:groups.length,types:countBy(facts,'type'),components:components.size,
      entrypoints:facts.filter(n=>n.entrypoint).length,sourceCount:facts.filter(n=>n.source).length,
      selectedRelationCount:selectedRelations.length,selectedRelationTypes:countBy(selectedRelations,'type'),
      internalCount:internal.length,internalTypes:countBy(internal,'type'),incomingCount:incoming.length,outgoingCount:outgoing.length,
      incomingTypes:countBy(incoming,'type'),outgoingTypes:countBy(outgoing,'type'),
      aggregateCount:aggregate.length?aggregate.reduce((sum,e)=>sum+e.count,0):null,memberIds:[...members]};
  }
  function bind(cy,container,{motion=()=>{}}={}) {
    let gesture=null,frame=null,pendingStep=0,pendingAnchor=null,disposed=false;
    const win=container?.ownerDocument?.defaultView||window;
    const raf=typeof win?.requestAnimationFrame==='function'?win.requestAnimationFrame.bind(win):null;
    const caf=typeof win?.cancelAnimationFrame==='function'?win.cancelAnimationFrame.bind(win):null;
    const finish=()=>{gesture=null;if(container.style)container.style.cursor='';};
    const start=event=>{
      const mouse=event.originalEvent;if(mouse?.button!==2)return;
      gesture={x:mouse.clientX,y:mouse.clientY,pan:{...cy.pan()},moved:false};
      if(container.style)container.style.cursor='grabbing';mouse.preventDefault?.();
    };
    const move=event=>{
      if(!gesture)return;const mouse=event.originalEvent;if(!mouse)return;
      const dx=mouse.clientX-gesture.x,dy=mouse.clientY-gesture.y;
      if(!gesture.moved&&dx*dx+dy*dy<9)return;
      gesture.moved=true;motion();
      cy.pan({x:gesture.pan.x+dx,y:gesture.pan.y+dy});
      mouse.preventDefault?.();
    };
    const drag=()=>motion();
    const applyWheel=()=>{
      frame=null;
      if(disposed||!pendingStep||!cy.zoomingEnabled()){pendingStep=0;pendingAnchor=null;return;}
      const step=pendingStep,anchor=pendingAnchor;pendingStep=0;pendingAnchor=null;
      motion();cy.zoom({level:wheelZoom(cy.zoom(),step,cy.minZoom(),cy.maxZoom()),renderedPosition:anchor});
    };
    const wheel=event=>{
      if(gesture||!event.deltaY||!cy.zoomingEnabled())return;
      event.preventDefault();event.stopImmediatePropagation?.();
      const delta=event.deltaY;
      const pixels=event.deltaMode===1?delta*16:event.deltaMode===2?delta*cy.height():delta;
      pendingStep-=pixels/1000;
      const box=container.getBoundingClientRect();
      pendingAnchor={x:event.clientX-box.left,y:event.clientY-box.top};
      if(frame===null){if(raf)frame=raf(applyWheel);else applyWheel();}
    };
    cy.on('cxttapstart',start);cy.on('cxtdrag',move);cy.on('cxttapend',finish);
    cy.on('drag','node',drag);
    container.addEventListener?.('wheel',wheel,{passive:false,capture:true});
    const cancel=()=>finish();win.addEventListener?.('blur',cancel);
    return ()=>{disposed=true;finish();if(frame!==null){caf?.(frame);frame=null;}pendingStep=0;pendingAnchor=null;cy.off('cxttapstart',start);cy.off('cxtdrag',move);cy.off('cxttapend',finish);cy.off('drag','node',drag);container.removeEventListener?.('wheel',wheel,true);win.removeEventListener?.('blur',cancel);};
  }
  function groupLabels(cy,layer,escape) {
    let cache=null,signature='';
    return {
      invalidate(){cache=null;},
      render(){
        if(!layer||cy.destroyed())return;
        const zoom=cy.zoom();if(zoom<.55){if(signature!=='hidden'){layer.innerHTML='';signature='hidden';}return;}
        cache||=(cy.nodes(':parent').map(node=>{const box=node.boundingBox({includeLabels:false,includeOverlays:false});return {id:node.id(),title:node.data('full'),x:box.x1+12,y:box.y1+12,w:box.w-24};}));
        const pan=cy.pan(),width=cy.width(),height=cy.height();
        const visible=cache.map(item=>({...item,x:item.x*zoom+pan.x,y:item.y*zoom+pan.y,w:item.w*zoom})).filter(item=>item.x<width&&item.x+item.w>0&&item.y>=-20*zoom&&item.y<height);
        const next=JSON.stringify(visible.map(item=>[item.id,item.title]));
        if(next!==signature){layer.innerHTML=visible.map(item=>`<span class="k-group-label">${escape(item.title)}</span>`).join('');signature=next;}
        visible.forEach((item,index)=>{const style=layer.children[index].style;style.transform=`translate(${item.x}px,${item.y}px)`;style.maxWidth=item.w+'px';style.fontSize=15*zoom+'px';style.lineHeight=20*zoom+'px';});
      }
    };
  }
  function bindMenus(root) {
    const doc=root?.ownerDocument||window.document;
    if(!doc?.addEventListener)return ()=>{};
    const win=doc.defaultView||window;
    let active=null;
    const restore=()=>{if(active){active.panel.style.cssText=active.style;active=null;}};
    const fit=()=>{
      if(!active)return;
      const {menu,panel,summary}=active;
      if(!menu.open||menu.isConnected===false||root?.isConnected===false){restore();return;}
      const viewport=win.visualViewport,margin=8,gap=4;
      const width=viewport?.width||win.innerWidth||doc.documentElement?.clientWidth;
      const height=viewport?.height||win.innerHeight||doc.documentElement?.clientHeight;
      if(!width||!height)return;
      const left=(viewport?.offsetLeft||0)+margin,top=(viewport?.offsetTop||0)+margin;
      const right=left+Math.max(0,width-2*margin),bottom=top+Math.max(0,height-2*margin);
      const anchor=summary.getBoundingClientRect();
      Object.assign(panel.style,{position:'fixed',right:'auto',bottom:'auto',maxWidth:Math.max(0,right-left)+'px',maxHeight:Math.max(0,bottom-top)+'px'});
      const box=panel.getBoundingClientRect();
      const below=Math.max(0,bottom-Math.max(top,anchor.bottom+gap)),above=Math.max(0,Math.min(bottom,anchor.top-gap)-top);
      const upwards=box.height>below&&above>below,available=upwards?above:below;
      panel.style.maxHeight=available+'px';
      // Measure again after the height constraint: scrollbars can affect width.
      const fitted=panel.getBoundingClientRect();
      panel.style.left=clamp(anchor.right-fitted.width,left,Math.max(left,right-fitted.width))+'px';
      panel.style.top=clamp(upwards?anchor.top-gap-fitted.height:anchor.bottom+gap,top,Math.max(top,bottom-fitted.height))+'px';
    };
    const close=(target=null)=>{
      if(root?.isConnected===false)return;
      for(const menu of root?.querySelectorAll?.('details.k-graph-info[open]')||[]){
        if(target&&menu.contains?.(target))continue;
        menu.open=false;menu.removeAttribute?.('open');
      }
      if(active&&!active.menu.open)restore();
    };
    const toggle=event=>{
      const menu=event.target;
      if(!menu.matches?.('details.k-graph-info')||!root.contains?.(menu))return;
      if(!menu.open){if(active?.menu===menu)restore();return;}
      close(menu);
      const panel=menu.querySelector('.k-info-content'),summary=menu.querySelector('summary');
      if(!panel||!summary)return;
      if(active?.menu!==menu){restore();active={menu,panel,summary,style:panel.style.cssText};}
      fit();
    };
    const pointer=event=>close(event.target),click=event=>close(event.target),key=event=>{if(event.key==='Escape'&&(active||root.querySelectorAll('details.k-graph-info[open]').length)){event.preventDefault?.();close();}};
    doc.addEventListener('pointerdown',pointer,true);doc.addEventListener('click',click,true);doc.addEventListener('keydown',key,true);
    root.addEventListener?.('toggle',toggle,true);
    win.addEventListener?.('resize',fit);doc.addEventListener('scroll',fit,true);
    win.visualViewport?.addEventListener('resize',fit);win.visualViewport?.addEventListener('scroll',fit);
    // The root survives redraws, but its menus do not. Release removed panels.
    const observer=win.MutationObserver?new win.MutationObserver(fit):null;
    observer?.observe(root,{childList:true,subtree:true});
    return ()=>{restore();observer?.disconnect();doc.removeEventListener('pointerdown',pointer,true);doc.removeEventListener('click',click,true);doc.removeEventListener('keydown',key,true);doc.removeEventListener('scroll',fit,true);root.removeEventListener?.('toggle',toggle,true);win.removeEventListener?.('resize',fit);win.visualViewport?.removeEventListener('resize',fit);win.visualViewport?.removeEventListener('scroll',fit);};
  }
  window.ArchitectureCanvas={wheelZoom,effectiveNodes,selectionStats,bind,bindMenus,groupLabels};
})();
