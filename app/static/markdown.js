'use strict';
// Small local Markdown renderer. Raw HTML is always text, never inserted as HTML.
window.KenoMarkdown = (() => {
  const node = (tag, text) => { const el=document.createElement(tag); if(text!==undefined)el.textContent=text; return el; };
  function inline(parent, text, depth=0) {
    if(depth>4) { parent.append(document.createTextNode(text)); return; }
    const pattern=/(`[^`\n]{1,1000}`|\*\*[^*\n]{1,2000}\*\*|__[^_\n]{1,2000}__|\*[^*\n]{1,2000}\*|\[[^\]\n]{1,300}\]\([^\s)]{1,2000}\))/g;
    let start=0;
    for(const match of text.matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(start,match.index)));
      const value=match[0]; let child;
      if(value.startsWith('`')) child=node('code',value.slice(1,-1));
      else if(value.startsWith('**')||value.startsWith('__')) { child=node('strong');inline(child,value.slice(2,-2),depth+1); }
      else if(value.startsWith('*')) { child=node('em');inline(child,value.slice(1,-1),depth+1); }
      else {
        const split=value.indexOf(']('), label=value.slice(1,split), href=value.slice(split+2,-1);
        try { const url=new URL(href,window.location.href); if(!['https:','http:'].includes(url.protocol))throw Error();
          child=node('a',label);child.href=url.href;child.target='_blank';child.rel='noopener noreferrer';
        } catch { child=document.createTextNode(value); }
      }
      parent.append(child);start=match.index+value.length;
    }
    parent.append(document.createTextNode(text.slice(start)));
  }
  function cells(line) { return line.trim().replace(/^\|/,'').replace(/\|$/,'').split('|').map(value=>value.trim()); }
  function render(parent, text) {
    parent.replaceChildren(); const lines=String(text).slice(0,100000).split('\n');let index=0;
    while(index<lines.length) {
      const line=lines[index];
      if(!line.trim()) { index++;continue; }
      if(/^\s*```/.test(line)) {
        const pre=node('pre'),code=node('code'),language=line.trim().slice(3).trim().slice(0,30);let block=[];index++;
        while(index<lines.length&&!/^\s*```/.test(lines[index]))block.push(lines[index++]);
        if(index<lines.length)index++;code.textContent=block.join('\n');if(language)code.dataset.language=language;
        pre.append(code);parent.append(pre);continue;
      }
      const heading=line.match(/^(#{1,6})\s+(.+)$/);
      if(heading) { const el=node('h'+heading[1].length);inline(el,heading[2]);parent.append(el);index++;continue; }
      if(index+1<lines.length&&line.includes('|')&&/^\s*\|?\s*:?-{3,}/.test(lines[index+1])) {
        const wrap=node('div'),table=node('table'),head=node('thead'),body=node('tbody'),tr=node('tr');wrap.className='table-scroll';
        for(const value of cells(line)) { const th=node('th');inline(th,value);tr.append(th); }head.append(tr);index+=2;
        while(index<lines.length&&lines[index].includes('|')&&lines[index].trim()) { const row=node('tr');for(const value of cells(lines[index++])) { const td=node('td');inline(td,value);row.append(td); }body.append(row); }
        table.append(head,body);wrap.append(table);parent.append(wrap);continue;
      }
      const list=line.match(/^\s*(?:[-*+] |\d+\. )(.+)$/);
      if(list) {
        const ordered=/^\s*\d+\./.test(line),el=node(ordered?'ol':'ul');
        while(index<lines.length) { const match=lines[index].match(ordered?/^\s*\d+\. (.+)$/:/^\s*[-*+] (.+)$/);if(!match)break;
          const li=node('li');inline(li,match[1]);el.append(li);index++; }
        parent.append(el);continue;
      }
      if(/^>\s?/.test(line)) { const el=node('blockquote');inline(el,line.replace(/^>\s?/,''));parent.append(el);index++;continue; }
      const paragraph=node('p');inline(paragraph,line);parent.append(paragraph);index++;
    }
  }
  return {render};
})();
