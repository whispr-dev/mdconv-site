import { normalise, validate, comparisonText } from './core.js';
import { safeFragment, renderComparison, exportHTML } from './render.js';

const $ = id => document.getElementById(id);
const sampleMarkdown = '# A little clarity.\n\nA place for **good ideas**, written simply.\n\n## The small things add up\n\n- Write in Markdown\n- Watch the preview update\n- Take your work with you\n\n> Less friction. More clarity.\n\n### Ready when you are\n\n```javascript\nconst message = "Hello, world.";\nconsole.log(message);\n```\n\n| One tool | Two useful modes |\n| --- | --- |\n| .md | Live Markdown preview |\n| .txt | Side-by-side text diff |\n\n- [x] Keep text in your browser\n- [ ] Make something worth sharing\n';
const samples = {original:'The small things add up.\nKeep the useful parts.\nMake it complicated.\nShip on Monday.\n',revised:'The small things add up.\nKeep the useful parts.\nMake it simple.\nShip on Tuesday.\nKeep improving.\n'};
let mode = 'md', worker, deadline, debounce, sequence = 0, html = '', result = null;
let toastTimer, undo = null, fileTarget = 'markdown';
const resultButtons = [...document.querySelectorAll('[data-result]')];

function toast(message) {
  $('toast').textContent = message; $('toast').classList.add('visible');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => $('toast').classList.remove('visible'),3500);
}
function stopWorker() {
  clearTimeout(deadline); worker?.terminate(); worker = null;
}
function busy(value) {
  for (const button of resultButtons) button.disabled = value;
  $('preview').setAttribute('aria-busy',String(value && mode === 'md'));
  $('diff-output').setAttribute('aria-busy',String(value && mode === 'txt'));
}
function failure(message) {
  stopWorker(); busy(true);
  $('preview').setAttribute('aria-busy','false'); $('diff-output').setAttribute('aria-busy','false');
  $('error').textContent = message; $('error').hidden = false;
  $('render-state').textContent = 'Preview unavailable'; $('diff-summary').textContent = 'Comparison unavailable';
  $('preview').replaceChildren(); $('diff-output').replaceChildren(); html = ''; result = null;
}
function updateCounts() {
  for (const [id,count] of [['markdown','md-count'],['original','original-count'],['revised','revised-count']]) {
    $(count).textContent = $(id).value.length.toLocaleString()+' characters';
  }
}
function schedule() {
  sequence++; clearTimeout(debounce); stopWorker(); busy(true); updateCounts();
  $('error').hidden = true;
  $('render-state').textContent = 'Updating…'; $('diff-summary').textContent = 'Comparing…';
  debounce = setTimeout(processText,140);
}
function processText() {
  const id = sequence;
  try {
    for (const key of mode === 'md' ? ['markdown'] : ['original','revised']) validate($(key).value);
    worker = new Worker(new URL('./worker.js',import.meta.url),{type:'module'});
    worker.onmessage = ({data}) => {
      if (data.id !== sequence || data.mode !== mode) return;
      stopWorker();
      if (data.error) return failure(data.error);
      try {
        if (mode === 'md') {
          $('preview').replaceChildren(safeFragment(data.result)); html = $('preview').innerHTML;
          if (!$('markdown').value) {
            const hint = document.createElement('p'); hint.className = 'detail-note'; hint.textContent = 'Start writing on the left. Your preview will appear here.';
            $('preview').append(hint);
          }
          $('render-state').textContent = 'Live · rendered locally';
        } else {
          result = data.result; renderComparison($('diff-output'),result);
          $('diff-summary').textContent = result.equal ? (result.rows.length ? 'Texts are identical' : 'Both texts are empty') : `${result.removed} removed · ${result.added} added`;
        }
        busy(false);
      } catch { failure('Could not display this result. Try a smaller selection.'); }
    };
    worker.onerror = event => { event.preventDefault(); if (id === sequence) failure('The local processor could not start. Reload the page, or check that your browser allows JavaScript workers.'); };
    deadline = setTimeout(() => { if (id === sequence) failure('Processing took too long. Use a smaller selection; your text is still in the editor.'); },3500);
    worker.postMessage({id,mode,markdown:$('markdown').value,original:$('original').value,revised:$('revised').value});
  } catch (error) { failure(error instanceof Error ? error.message : 'Could not process this text.'); }
}
function switchMode() {
  mode = $('mode').checked ? 'txt' : 'md';
  $('markdown-mode').hidden = mode !== 'md'; $('text-mode').hidden = mode !== 'txt';
  $('mode-name').textContent = mode === 'md' ? 'Markdown preview' : 'Text comparison';
  $('mode-description').textContent = mode === 'md' ? 'Write Markdown on the left. See it come alive on the right.' : 'Two versions. One clear view of what changed.';
  $('format-note').hidden = mode !== 'md';
  $('undo-clear').hidden = !undo || undo.mode !== mode;
  schedule();
}
async function copy(value) {
  try { await navigator.clipboard.writeText(value); toast('Copied to clipboard.'); }
  catch {
    // Older browsers / denied clipboard permission: selectable, in-tab fallback.
    const textarea = document.createElement('textarea'); textarea.value = value;
    textarea.setAttribute('aria-label','Text to copy'); document.body.append(textarea); textarea.select();
    let copied = false;
    try { copied = document.execCommand('copy'); } catch { /* Report failure below. */ }
    textarea.remove();
    toast(copied ? 'Copied to clipboard.' : 'Clipboard unavailable. Select the text, or use Download.');
  }
}
function download(content,name,type='text/plain') {
  const url = URL.createObjectURL(new Blob([content],{type:type+';charset=utf-8'}));
  const link = document.createElement('a'); link.href = url; link.download = name; document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url),1000);
}
function setValue(id,value) { $(id).value = value; }
function edits() { undo = null; $('undo-clear').hidden = true; schedule(); }
for (const id of ['markdown','original','revised']) {
  $(id).addEventListener('input',edits);
  $(id).addEventListener('keydown',event => {
    if (event.key === 'Tab' && !event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault(); const input = event.currentTarget;
      input.setRangeText('  ',input.selectionStart,input.selectionEnd,'end'); edits();
    }
    // Escape releases Tab from the editor, preserving keyboard navigation.
    if (event.key === 'Escape') $('mode').focus();
  });
}
$('mode').addEventListener('change',switchMode);
$('example').addEventListener('click',() => {
  undo = {mode, values:mode === 'md' ? {markdown:$('markdown').value} : {original:$('original').value,revised:$('revised').value}};
  if (mode === 'md') setValue('markdown',sampleMarkdown);
  else for (const key of ['original','revised']) setValue(key,samples[key]);
  $('undo-clear').hidden = false; $('undo-clear').textContent = 'Undo example'; schedule();
});
$('clear').addEventListener('click',() => {
  undo = {mode,values:Object.fromEntries((mode === 'md' ? ['markdown'] : ['original','revised']).map(id => [id,$(id).value]))};
  for (const id of Object.keys(undo.values)) setValue(id,'');
  $('undo-clear').hidden = false; $('undo-clear').textContent = 'Undo clear'; schedule();
});
$('undo-clear').addEventListener('click',() => {
  if (undo?.mode !== mode) return;
  for (const [id,value] of Object.entries(undo.values)) setValue(id,value);
  undo = null; $('undo-clear').hidden = true; schedule();
});
$('swap').addEventListener('click',() => {
  const original = $('original').value; setValue('original',$('revised').value); setValue('revised',original); edits();
});
for (const [button,id] of [['copy-md','markdown'],['copy-original','original'],['copy-revised','revised']]) $(button).addEventListener('click',() => copy($(id).value));
$('copy-text').addEventListener('click',() => copy($('markdown').value ? $('preview').innerText : ''));
$('copy-html').addEventListener('click',() => copy(html));
$('download-md').addEventListener('click',() => download($('markdown').value,'document.md','text/markdown'));
$('download-html').addEventListener('click',() => download(exportHTML(html),'document.html','text/html'));
$('download-diff').addEventListener('click',() => { if (result) download(comparisonText(result),'comparison.txt'); });
for (const [button,id] of [['open-md','markdown'],['open-original','original'],['open-revised','revised']]) $(button).addEventListener('click',() => {
  fileTarget = id; $('file-input').value = ''; $('file-input').click();
});
$('file-input').addEventListener('change',async () => {
  const file = $('file-input').files[0], target = fileTarget;
  if (!file) return;
  if (file.size > 1_000_000) return toast('File too large. Open a text file under 1 MB.');
  try {
    const text = new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
    if (text.includes('\0')) throw new Error('This looks like a binary file. Choose a UTF-8 text file.');
    validate(text); setValue(target,normalise(text)); edits(); toast('Opened locally. Nothing uploaded.');
  } catch (error) { toast(error instanceof TypeError ? 'Use a UTF-8 text file.' : error.message || 'Could not open that file.'); }
});
let scrolling = false;
for (const [from,to] of [[$('markdown'),$('preview')],[$('preview'),$('markdown')]]) from.addEventListener('scroll',() => {
  if (scrolling || !$('sync-scroll').checked) return;
  const distance = from.scrollHeight - from.clientHeight;
  scrolling = true; to.scrollTop = distance > 0 ? from.scrollTop / distance * (to.scrollHeight - to.clientHeight) : 0;
  requestAnimationFrame(() => { scrolling = false; });
},{passive:true});
$('privacy-open').addEventListener('click',() => $('privacy').showModal());
$('privacy-close').addEventListener('click',() => $('privacy').close());
$('privacy').addEventListener('click',event => { if (event.target === $('privacy')) {
  const bounds = $('privacy').getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) $('privacy').close();
}});
window.addEventListener('beforeunload',event => {
  const custom = ($('markdown').value && $('markdown').value !== sampleMarkdown) ||
    ($('original').value && $('original').value !== samples.original) || ($('revised').value && $('revised').value !== samples.revised);
  if (custom) { event.preventDefault(); event.returnValue = ''; }
});
setValue('markdown',sampleMarkdown); setValue('original',samples.original); setValue('revised',samples.revised);
// Browsers can restore checkbox state after a navigation; respect it on startup.
switchMode();
