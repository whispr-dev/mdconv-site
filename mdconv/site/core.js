import { marked } from './vendor/marked.js';
import { diffLines } from './vendor/diff/diff/line.js';
import { diffChars } from './vendor/diff/diff/character.js';

export const MAX_CHARACTERS = 250_000;
export const MAX_LINES = 5_000;
export const normalise = text => text.replace(/\r\n?/g, '\n');
export const escapeHTML = text => text.replace(/[&<>"']/g, value => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[value]));

export function validate(text) {
  if (typeof text !== 'string') throw new Error('Input must be text.');
  if (text.length > MAX_CHARACTERS) throw new Error('Use a smaller selection: the limit is 250,000 characters per input. Your text has not been truncated.');
  if (normalise(text).split('\n').length > MAX_LINES) throw new Error('Use a smaller selection: the limit is 5,000 lines per input. Your text has not been truncated.');
}

// Images become text before HTML parsing, avoiding even an attempted image fetch.
marked.use({gfm:true, breaks:false, renderer:{
  image({text}) { return `<span class="image-label">[Image: ${escapeHTML(text || 'no description')}]</span>`; }
}});

export function markdownHTML(text) {
  validate(text);
  return marked.parse(normalise(text).replace(/^\uFEFF/, ''));
}

export function splitLines(value) {
  if (!value) return [];
  const parts = value.split('\n');
  const hasFinalNewline = value.endsWith('\n');
  if (hasFinalNewline) parts.pop();
  return parts.map((text,index) => ({text, eol:index < parts.length - 1 || hasFinalNewline}));
}

function segments(left, right) {
  if (left === undefined || right === undefined || left.length + right.length > 4_000) return null;
  return diffChars(left, right, {timeout:20,maxEditLength:1_000}) || null;
}

export function compareTexts(original, revised) {
  validate(original); validate(revised);
  original = normalise(original); revised = normalise(revised);
  const changes = diffLines(original, revised, {timeout:800,maxEditLength:6_000});
  if (!changes) throw new Error('This comparison is too complex. Compare a smaller section of the text.');
  const rows = [];
  let oldNumber = 0, newNumber = 0, added = 0, removed = 0, inlineBudget = 100_000;
  const cell = (line, type, number) => line ? {...line, type, number} : null;
  for (let i = 0; i < changes.length; i++) {
    const change = changes[i];
    if (!change.added && !change.removed) {
      for (const line of splitLines(change.value)) rows.push({left:cell(line,'same',++oldNumber),right:cell(line,'same',++newNumber)});
      continue;
    }
    const deleted = [], inserted = [];
    while (i < changes.length && (changes[i].added || changes[i].removed)) {
      const part = changes[i];
      (part.removed ? deleted : inserted).push(...splitLines(part.value));
      i++;
    }
    i--;
    removed += deleted.length; added += inserted.length;
    for (let j = 0; j < Math.max(deleted.length,inserted.length); j++) {
      const left = cell(deleted[j],'removed',deleted[j] ? ++oldNumber : null);
      const right = cell(inserted[j],'added',inserted[j] ? ++newNumber : null);
      if (left && right) {
        inlineBudget -= left.text.length + right.text.length;
        const pieces = inlineBudget >= 0 ? segments(left.text,right.text) : null;
        if (pieces) {
          left.segments = pieces.filter(p => !p.added).map(p => ({text:p.value,changed:!!p.removed}));
          right.segments = pieces.filter(p => !p.removed).map(p => ({text:p.value,changed:!!p.added}));
        }
      }
      rows.push({left,right});
    }
  }
  return {rows, added, removed, equal:original === revised};
}

export function comparisonText(result) {
  const lines = ['Text comparison — mdconv.site',`${result.removed} removed line(s), ${result.added} added line(s)`,'Line endings normalised to LF.',''];
  for (const row of result.rows) {
    if (row.left?.type === 'same') {
      lines.push('  '+row.left.text);
      if (!row.left.eol) lines.push('  [No final newline]');
    } else {
      for (const [cell,sign] of [[row.left,'-'],[row.right,'+']]) {
        if (!cell) continue;
        lines.push(sign+' '+cell.text);
        if (!cell.eol) lines.push(sign+' [No final newline]');
      }
    }
  }
  return lines.join('\n')+'\n';
}
