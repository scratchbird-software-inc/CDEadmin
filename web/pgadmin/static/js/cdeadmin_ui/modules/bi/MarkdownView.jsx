/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {Fragment, useMemo} from 'react';
import PropTypes from 'prop-types';
import {Box} from '../../primitives/Layout';
import {parseMarkdown} from './markdown';

function Inline({nodes}) {
  return nodes.map((node, index) => {
    switch(node.type) {
    case 'strong': return <strong key={index}><Inline nodes={node.children} /></strong>;
    case 'em': return <em key={index}><Inline nodes={node.children} /></em>;
    case 'code': return <Box component="code" key={index}
      sx={{fontFamily: 'monospace', bgcolor: 'action.hover', px: 0.5}}>{node.value}</Box>;
    case 'link': return <Box component="a" key={index} href={node.href} target="_blank"
      rel="noopener noreferrer" sx={{color: 'primary.main'}}><Inline nodes={node.children} /></Box>;
    default: return <Fragment key={index}>{node.value}</Fragment>;
    }
  });
}

Inline.propTypes = {nodes: PropTypes.array.isRequired};

const HEADING_SIZE = ['1.5rem', '1.25rem', '1.125rem', '1rem', '0.9375rem', '0.875rem'];

/**
 * Renders a text card. The Markdown is parsed into a tree and drawn with React
 * elements: HTML in the source is shown as text, never interpreted.
 */
export default function MarkdownView({markdown}) {
  const blocks = useMemo(() => parseMarkdown(markdown), [markdown]);
  return <Box data-cdeadmin-qa-key="bi.markdown" sx={{display: 'grid', gap: 1, minWidth: 0,
    overflowWrap: 'anywhere', fontSize: '0.875rem', color: 'text.primary'}}>
    {blocks.map((block, index) => {
      switch(block.type) {
      case 'heading': return <Box key={index} component={`h${Math.min(6, block.level + 1)}`}
        sx={{m: 0, fontSize: HEADING_SIZE[block.level - 1], fontWeight: 600}}>
        <Inline nodes={block.children} /></Box>;
      case 'list': return <Box key={index} component={block.ordered ? 'ol' : 'ul'} sx={{m: 0, pl: 3}}>
        {block.items.map((item, position) => <li key={position}><Inline nodes={item} /></li>)}
      </Box>;
      case 'quote': return <Box key={index} component="blockquote"
        sx={{m: 0, pl: 1.5, borderLeft: '3px solid', borderColor: 'divider', color: 'text.secondary'}}>
        <Inline nodes={block.children} /></Box>;
      case 'code': return <Box key={index} component="pre"
        sx={{m: 0, p: 1, overflow: 'auto', fontFamily: 'monospace', bgcolor: 'action.hover'}}>{block.value}</Box>;
      case 'rule': return <Box key={index} component="hr"
        sx={{width: '100%', border: 0, borderTop: '1px solid', borderColor: 'divider'}} />;
      default: return <Box key={index} component="p" sx={{m: 0}}><Inline nodes={block.children} /></Box>;
      }
    })}
  </Box>;
}

MarkdownView.propTypes = {markdown: PropTypes.string};
