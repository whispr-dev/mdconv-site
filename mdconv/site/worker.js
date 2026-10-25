import { markdownHTML, compareTexts } from './core.js';
self.onmessage = ({data}) => {
  const {id,mode,markdown,original,revised} = data;
  try {
    const result = mode === 'md' ? markdownHTML(markdown) : compareTexts(original,revised);
    self.postMessage({id,mode,result});
  } catch (error) {
    self.postMessage({id,mode,error:error instanceof Error ? error.message : 'Could not process that text.'});
  }
};
