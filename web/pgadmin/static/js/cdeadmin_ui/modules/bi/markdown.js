/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * A deliberately small Markdown reader for text cards. It produces a plain
 * tree (never HTML): headings, paragraphs, bullet and numbered lists, block
 * quotes, fenced code, rules, and inline strong, emphasis, code and links.
 * Raw HTML is not recognised and stays literal text; images are shown as
 * their alt text; a link is kept only for http, https and mailto addresses.
 * MarkdownView renders the tree with React elements, so no string is ever
 * interpreted as markup.
 */

const MAX_DEPTH = 4;

export function safeHref(url) {
  const value = String(url ?? '').trim();
  return /^(https?:|mailto:)[^\s<>"]+$/i.test(value) ? value : null;
}

const INLINE_SOURCE = [
  '!\\[([^\\]]*)\\]\\(([^)]*)\\)', // 1,2 image: kept as alt text
  '(`+)([^`]|[^`][\\s\\S]*?[^`])\\3(?!`)', // 3,4 code
  '\\*\\*([^*]+?)\\*\\*', // 5
  '__([^_]+?)__', // 6
  '\\*([^*\\s][^*]*?)\\*', // 7
  '(?<![A-Za-z0-9])_([^_\\s][^_]*?)_(?![A-Za-z0-9])', // 8
  '\\[([^\\]]+)\\]\\(([^)\\s]*)(?:\\s+"[^"]*")?\\)', // 9,10 link
].join('|');

/** Inline nodes of one run of text. */
export function parseInline(text, depth = 0) {
  const nodes = [];
  const source = String(text ?? '');
  let last = 0;
  const push = (value) => { if(value) nodes.push({type: 'text', value}); };
  // A fresh expression per call: nested calls must not share lastIndex with this loop.
  const inline = new RegExp(INLINE_SOURCE, 'g');
  let match = inline.exec(source);
  while(match) {
    push(source.slice(last, match.index));
    const nested = (inner) => depth < MAX_DEPTH ? parseInline(inner, depth + 1) : [{type: 'text', value: inner}];
    if(match[1] !== undefined) push(match[1]);
    else if(match[3] !== undefined) nodes.push({type: 'code', value: match[4]});
    else if(match[5] !== undefined || match[6] !== undefined) {
      nodes.push({type: 'strong', children: nested(match[5] ?? match[6])});
    } else if(match[7] !== undefined || match[8] !== undefined) {
      nodes.push({type: 'em', children: nested(match[7] ?? match[8])});
    } else {
      const href = safeHref(match[10]);
      if(href) nodes.push({type: 'link', href, children: nested(match[9])});
      else push(match[0]);
    }
    last = match.index + match[0].length;
    match = inline.exec(source);
  }
  push(source.slice(last));
  return nodes;
}

const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const BULLET = /^\s{0,3}[-*+]\s+(.*)$/;
const NUMBERED = /^\s{0,3}\d{1,9}[.)]\s+(.*)$/;
const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
const FENCE = /^\s{0,3}(```+|~~~+)/;
const QUOTE = /^\s{0,3}>\s?(.*)$/;

/** Block nodes of a Markdown document. */
export function parseMarkdown(text) {
  const lines = String(text ?? '').replace(/\r\n?/g, '\n').split('\n');
  const blocks = [];
  let index = 0;
  const startsBlock = (line) => HEADING.test(line) || BULLET.test(line) || NUMBERED.test(line) ||
    RULE.test(line) || FENCE.test(line) || QUOTE.test(line);
  while(index < lines.length) {
    const line = lines[index];
    if(!line.trim()) { index += 1; continue; }
    const fence = FENCE.exec(line);
    if(fence) {
      const code = [];
      index += 1;
      while(index < lines.length && !lines[index].trim().startsWith(fence[1][0].repeat(3))) {
        code.push(lines[index]);
        index += 1;
      }
      index += 1;
      blocks.push({type: 'code', value: code.join('\n')});
      continue;
    }
    const heading = HEADING.exec(line);
    if(heading) {
      blocks.push({type: 'heading', level: heading[1].length, children: parseInline(heading[2])});
      index += 1;
      continue;
    }
    if(RULE.test(line)) { blocks.push({type: 'rule'}); index += 1; continue; }
    const list = BULLET.test(line) ? BULLET : NUMBERED.test(line) ? NUMBERED : null;
    if(list) {
      const items = [];
      while(index < lines.length && list.test(lines[index])) {
        items.push(parseInline(list.exec(lines[index])[1]));
        index += 1;
      }
      blocks.push({type: 'list', ordered: list === NUMBERED, items});
      continue;
    }
    if(QUOTE.test(line)) {
      const quoted = [];
      while(index < lines.length && QUOTE.test(lines[index])) {
        quoted.push(QUOTE.exec(lines[index])[1]);
        index += 1;
      }
      blocks.push({type: 'quote', children: parseInline(quoted.join(' '))});
      continue;
    }
    const paragraph = [];
    while(index < lines.length && lines[index].trim() && !(paragraph.length && startsBlock(lines[index]))) {
      paragraph.push(lines[index].trim());
      index += 1;
    }
    blocks.push({type: 'paragraph', children: parseInline(paragraph.join(' '))});
  }
  return blocks;
}
