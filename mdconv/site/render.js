import DOMPurify from './vendor/purify.js';

const allowedTags = ['p','br','hr','h1','h2','h3','h4','h5','h6','strong','em','del','s','b','i','u','blockquote','pre','code','ul','ol','li','table','thead','tbody','tfoot','tr','th','td','a','span','div','input','sup','sub','kbd','details','summary'];

export function safeFragment(html) {
  const fragment = DOMPurify.sanitize(html, {
    ALLOWED_TAGS:allowedTags,
    ALLOWED_ATTR:['href','title','class','type','checked','disabled','start','colspan','rowspan','align','open'],
    ALLOW_DATA_ATTR:false, ALLOW_ARIA_ATTR:false,
    RETURN_DOM_FRAGMENT:true, SANITIZE_NAMED_PROPS:true
  });
  for (const element of fragment.querySelectorAll('[class]')) {
    // Only the image description's presentation is retained from user markup.
    if (element.tagName === 'SPAN' && element.classList.contains('image-label')) element.className = 'image-label';
    else element.removeAttribute('class');
  }
  for (const link of fragment.querySelectorAll('a')) {
    const href = link.getAttribute('href') || '';
    if (!/^(?:https?:\/\/|mailto:|#)/i.test(href)) link.removeAttribute('href');
    if (link.hasAttribute('href')) {
      link.setAttribute('target','_blank');
      link.setAttribute('rel','noopener noreferrer');
      link.setAttribute('referrerpolicy','no-referrer');
    }
  }
  for (const input of fragment.querySelectorAll('input')) {
    input.setAttribute('type','checkbox');
    input.setAttribute('disabled','');
  }
  return fragment;
}

export function renderComparison(container,result) {
  const fragment = document.createDocumentFragment();
  if (!result.rows.length) {
    const empty = document.createElement('p'); empty.className = 'detail-note';
    empty.textContent = 'Both texts are empty. Paste or open text above to compare.';
    fragment.append(empty);
  }
  for (const row of result.rows) {
    const pair = document.createElement('div'); pair.className = 'diff-row';
    for (const cell of [row.left,row.right]) {
      const div = document.createElement('div'); div.className = 'diff-cell '+(cell?.type || 'empty');
      const lineNumber = document.createElement('span'); lineNumber.className = 'line-number';
      const sign = document.createElement('span'); sign.className = 'line-sign';
      if (cell) {
        lineNumber.textContent = cell.number;
        sign.textContent = cell.type === 'removed' ? '−' : cell.type === 'added' ? '+' : ' ';
        const content = document.createElement('span');
        if (cell.segments) for (const segment of cell.segments) {
          const node = document.createElement(segment.changed ? 'mark' : 'span');
          node.textContent = segment.text; content.append(node);
        }
        else content.textContent = cell.text || ' ';
        if (!cell.eol) {
          const end = document.createElement('span'); end.className = 'end-mark';
          end.textContent = '↵ No final newline'; content.append(end);
        }
        div.append(lineNumber,sign,content);
      } else {
        div.setAttribute('aria-label','No corresponding line');
        div.append(lineNumber,sign);
      }
      pair.append(div);
    }
    fragment.append(pair);
  }
  container.replaceChildren(fragment);
}

export function exportHTML(sanitisedHTML) {
  // Self-contained, inert document. No script or network resources are permitted.
  return '<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'+
    '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'; base-uri \'none\'; form-action \'none\'">'+
    '<meta name="referrer" content="no-referrer"><title>Markdown document</title>'+
    '<style>body{max-width:850px;margin:40px auto;padding:0 24px;font:16px/1.7 system-ui,sans-serif;color:#18222c;overflow-wrap:anywhere}pre{overflow:auto;padding:16px;background:#f1f4f2}code{font-family:monospace}table{border-collapse:collapse;display:block;overflow:auto}td,th{border:1px solid #ccd6d0;padding:8px}blockquote{border-left:3px solid #d2a33e;margin-left:0;padding-left:18px}img{display:none}</style></head><body>\n'+sanitisedHTML+'\n</body></html>\n';
}
