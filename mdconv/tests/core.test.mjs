import test from 'node:test';
import assert from 'node:assert/strict';
import {compareTexts,comparisonText,markdownHTML,normalise,splitLines,validate,MAX_CHARACTERS} from '../site/core.js';

const reconstruct = (result,side) => result.rows.map(row => row[side] ? row[side].text+(row[side].eol ? '\n' : '') : '').join('');
for (const [name,left,right] of [
  ['both empty','',''],['identical','a\nb\n','a\nb\n'],['insert','a\nc\n','a\nb\nc\n'],
  ['delete','a\nb\nc','a\nc'],['replace','red\nblue\n','green\nblue\n'],
  ['all added','','hello\n\n'],['all removed','hello\n\n',''],
  ['trailing newline','hello','hello\n'],['blank line','','\n'],
  ['CRLF','hello\r\nworld\r\n','hello\nworld\n'],
  ['whitespace','a b\n\tindent\n','a  b\n  indent\n'],
  ['unicode','🐺 café\n古い\n','🐺 cafés\n新しい\n'],
  ['literal HTML','<script>alert(1)</script>','<img src=x onerror=alert(2)>']
]) test(`diff retains both complete inputs: ${name}`,() => {
  const result=compareTexts(left,right);
  assert.equal(reconstruct(result,'left'),normalise(left));
  assert.equal(reconstruct(result,'right'),normalise(right));
  assert.equal(result.equal,normalise(left)===normalise(right));
  const oldNumbers=result.rows.flatMap(row=>row.left?[row.left.number]:[]);
  const newNumbers=result.rows.flatMap(row=>row.right?[row.right.number]:[]);
  assert.deepEqual(oldNumbers,oldNumbers.map((_,index)=>index+1));
  assert.deepEqual(newNumbers,newNumbers.map((_,index)=>index+1));
  for(const row of result.rows) for(const side of ['left','right']) if(row[side]?.segments)
    assert.equal(row[side].segments.map(s=>s.text).join(''),row[side].text);
});
test('random comparisons preserve ordering, characters and line boundaries',()=>{
  let seed=81623;
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/2**32;};
  const make=()=>Array.from({length:Math.floor(random()*15)},()=>['a','b','','  ','🐺','<x>'][Math.floor(random()*6)]).join('\n');
  for(let i=0;i<250;i++){
    const left=make(),right=make(),r=compareTexts(left,right);
    assert.equal(reconstruct(r,'left'),left);assert.equal(reconstruct(r,'right'),right);
  }
});
test('line and inline change accounting',()=>{
  const r=compareTexts('keep\ncat\ndelete\n','keep\ncar\n');
  assert.equal(r.removed,2);assert.equal(r.added,1);
  assert(r.rows.some(row=>row.left?.segments?.some(segment=>segment.changed)));
});
test('export marks a missing final newline and empty results honestly',()=>{
  assert.match(comparisonText(compareTexts('a','a\n')),/No final newline/);
  assert.match(comparisonText(compareTexts('','')),/0 removed line\(s\), 0 added/);
});
test('input limits reject without truncating',()=>{
  assert.throws(()=>validate('a'.repeat(MAX_CHARACTERS+1)),/not been truncated/);
  assert.throws(()=>validate('\n'.repeat(5000)),/5,000 lines/);
  assert.doesNotThrow(()=>validate('a'.repeat(MAX_CHARACTERS)));
  assert.deepEqual(splitLines('\n'),[{text:'',eol:true}]);
});
test('GFM includes tables, tasks, emphasis and literal fenced code',()=>{
  const html=markdownHTML('# Heading\n\n**strong**\n\n| a | b |\n| - | - |\n| 1 | 2 |\n\n- [x] done\n\n```html\n<script>hello()</script>\n```');
  for(const expression of [/<h1>Heading/,/<strong>strong/,/<table>/,/<input checked="" disabled="" type="checkbox">/,/&lt;script&gt;hello\(\)&lt;\/script&gt;/]) assert.match(html,expression);
});
test('Markdown images never emit image tags and escape their description',()=>{
  const html=markdownHTML('![private image](https://example.com/tracker.png)\n\n![<img src=x>](https://example.com/x)');
  assert.doesNotMatch(html,/<img|tracker\.png/);
  assert.match(html,/Image: private image/);assert.match(html,/&lt;img src=x&gt;/);
});
