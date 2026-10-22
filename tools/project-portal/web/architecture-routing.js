/* SVG overlay for compound and self edges that Cytoscape cannot route natively. */
(() => {
  'use strict';
  const SVG='http://www.w3.org/2000/svg';
  const edgeId=edge=>String(edge.id());
  function special(edge) {
    if(!edge||!edge.source||!edge.target)return false;
    const source=edge.source(),target=edge.target();
    if(!source.length||!target.length||source.id()===target.id())return true;
    return source.ancestors().contains(target)||target.ancestors().contains(source);
  }
  const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
  function box(node) {
    return node.boundingBox({includeLabels:false,includeOverlays:false});
  }
  function topPort(node,index,count) {
    const b=box(node);
    const margin=Math.min(18,Math.max(6,(b.x2-b.x1)*.12)),slot=(index+1)/(count+1);
    return {x:clamp(b.x1+margin+(b.x2-b.x1-margin*2)*slot,b.x1+margin,b.x2-margin),y:b.y1};
  }
  function pathFor(edge,slots) {
    const source=edge.source(),target=edge.target(),sb=box(source),tb=box(target);
    const same=source.id()===target.id();
    if(same){
      const slot=(slots.sourceIndex+1)/(slots.sourceCount+1),height=sb.y2-sb.y1,y1=sb.y1+height*(.1+.2*slot),y2=sb.y1+height*(.7+.2*slot),p={x:sb.x2,y:y1},q={x:sb.x2,y:y2},offset=Math.max(18,(sb.x2-sb.x1)*(.35+.35*slot));
      return {start:p,end:q,c2:{x:q.x+offset,y:q.y},d:`M ${p.x} ${p.y} C ${p.x+offset} ${p.y}, ${q.x+offset} ${q.y}, ${q.x} ${q.y}`};
    }
    const sp=topPort(source,slots.sourceIndex,slots.sourceCount),tp=topPort(target,slots.targetIndex,slots.targetCount);
    const dx=tp.x-sp.x,dy=tp.y-sp.y;
    // A monotone cubic stays within its endpoint rectangle: no overshoot,
    // native compound petals, or change of shape when the camera zooms.
    const c1={x:sp.x+dx*.1,y:sp.y+dy/3},c2={x:tp.x-dx*.1,y:sp.y+dy*2/3};
    return {start:sp,end:tp,c2,d:`M ${sp.x} ${sp.y} C ${c1.x} ${c1.y}, ${c2.x} ${c2.y}, ${tp.x} ${tp.y}`};
  }
  function mount(cy,container,{select=()=>{},hover=()=>{}}={}) {
    if(!cy||!container||!container.ownerDocument)return ()=>{};
    const doc=container.ownerDocument,svg=doc.createElementNS(SVG,'svg'),svgGroup=doc.createElementNS(SVG,'g');
    svg.setAttribute('aria-hidden','true');svg.style.position='absolute';svg.style.inset='0';svg.style.width='100%';svg.style.height='100%';svg.style.overflow='visible';svg.style.pointerEvents='none';
    if(!container.style.position)container.style.position='relative';svg.appendChild(svgGroup);container.appendChild(svg);
    let disposed=false;const originalOpacity=new Map(),originalEvents=new Map(),edges=()=>cy.edges().filter(special).sort((a,b)=>edgeId(a).localeCompare(edgeId(b)));
    // Incoming and outgoing relations share one slot budget. Reverse edges
    // therefore get distinct ports rather than lying on exactly the same path.
    const makeSlots=list=>{const source=new Map();for(const edge of list)for(const id of new Set([edge.source().id(),edge.target().id()])){if(!source.has(id))source.set(id,[]);source.get(id).push(edge);}return {source,target:source};};
    const render=()=>{if(disposed)return;const pan=cy.pan(),zoom=cy.zoom();svgGroup.setAttribute('transform',`translate(${pan.x} ${pan.y}) scale(${zoom})`);
      while(svgGroup.firstChild)svgGroup.removeChild(svgGroup.firstChild);
      const list=edges(),groups=makeSlots(list);
      for(const edge of list){
        const sourceGroup=groups.source.get(edge.source().id())||[],targetGroup=groups.target.get(edge.target().id())||[];
        const geometry=pathFor(edge,{sourceIndex:sourceGroup.indexOf(edge),sourceCount:sourceGroup.length,targetIndex:targetGroup.indexOf(edge),targetCount:targetGroup.length});
        const group=doc.createElementNS(SVG,'g'),path=doc.createElementNS(SVG,'path');
        const selected=edge.selected(),color=edge.data('type')==='imports'?'#ce8fb8':edge.data('type')==='contains'?'#b49cde':edge.data('type')==='extends'||edge.data('type')==='implements'||edge.data('type')==='inherits'?'#5eb6a2':edge.data('type')==='uses'||edge.data('type')==='depends-on'?'#6ea6d8':'#d7a756';
        group.dataset.edgeId=edgeId(edge);path.setAttribute('d',geometry.d);path.setAttribute('fill','none');path.setAttribute('stroke',color);path.setAttribute('stroke-width',selected?'3':'1.8');path.setAttribute('stroke-dasharray',edge.data('provenance')==='authored'?'6 4':'');path.setAttribute('opacity',selected?'1':'.86');path.style.pointerEvents='stroke';
        const hit=doc.createElementNS(SVG,'path');hit.setAttribute('d',geometry.d);hit.setAttribute('fill','none');hit.setAttribute('stroke','transparent');hit.setAttribute('stroke-width','14');hit.style.pointerEvents='stroke';
        hit.addEventListener('click',event=>{event.stopPropagation();select(edge);});hit.addEventListener('pointerenter',()=>{path.setAttribute('stroke-width','3');hover(edge,true);});hit.addEventListener('pointerleave',()=>{path.setAttribute('stroke-width',edge.selected()?'3':'1.8');hover(edge,false);});
        const vx=geometry.end.x-geometry.c2.x,vy=geometry.end.y-geometry.c2.y,vl=Math.max(1,Math.hypot(vx,vy)),size=10;
        const arrow=doc.createElementNS(SVG,'polygon');arrow.setAttribute('points',`${geometry.end.x},${geometry.end.y} ${geometry.end.x-vx/vl*size-vy/vl*size*.55},${geometry.end.y-vy/vl*size+vx/vl*size*.55} ${geometry.end.x-vx/vl*size+vy/vl*size*.55},${geometry.end.y-vy/vl*size-vx/vl*size*.55}`);arrow.setAttribute('fill',color);arrow.setAttribute('opacity',selected?'1':'.86');
        group.append(path,arrow,hit);svgGroup.appendChild(group);
        if(!originalOpacity.has(edgeId(edge)))originalOpacity.set(edgeId(edge),edge.style('opacity'));
        if(!originalEvents.has(edgeId(edge)))originalEvents.set(edgeId(edge),edge.style('events'));
        edge.style('opacity',0);edge.style('events','no');
      }
    };
    const frame=typeof requestAnimationFrame==='function'?requestAnimationFrame:(fn=>setTimeout(fn,16)),cancel=typeof cancelAnimationFrame==='function'?cancelAnimationFrame:clearTimeout;
    let pending=false,frameId=null;
    const rerender=()=>{if(disposed||pending)return;pending=true;frameId=frame(()=>{pending=false;frameId=null;if(!disposed)render();});};
    cy.on('position pan zoom resize select unselect',rerender);render();
    const cleanup=()=>{if(disposed)return;disposed=true;if(frameId!==null)cancel(frameId);cy.off('position pan zoom resize select unselect',rerender);while(svgGroup.firstChild)svgGroup.removeChild(svgGroup.firstChild);svg.remove();for(const edge of cy.edges().filter(special)){const value=originalOpacity.get(edgeId(edge));if(value!==undefined)edge.style('opacity',value);const events=originalEvents.get(edgeId(edge));if(events!==undefined)edge.style('events',events);}};
    cleanup.render=render;return cleanup;
  }
  window.ArchitectureRouting={special,mount};
})();
