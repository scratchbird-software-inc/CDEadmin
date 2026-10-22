import {useMemo, useState} from 'react';
import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Alert, Box, Button, Typography} from '@mui/material';
import {mysqlPlanText, parseMySQLPlan} from './mysqlQueryPlan';

function PlanNode({id, graph, selected, onSelect}) {
  const node = graph.nodes[id];
  const [expanded, setExpanded] = useState(true);
  return <Box component="li" role="treeitem" aria-label={node.label}
    aria-selected={selected === id} aria-expanded={node.children.length ? expanded : undefined}
    sx={{listStyle: 'none', position: 'relative', my: 1,
      '&:before': {content: '""', position: 'absolute', width: 18, left: -18, top: 20, borderTop: 1, borderColor: 'divider'}}}>
    <Box sx={{display: 'flex', alignItems: 'flex-start', gap: .5}}>
      {node.children.length > 0 && <Button size="small" sx={{minWidth: 28}} aria-label={expanded ? gettext('Collapse operator') : gettext('Expand operator')}
        onClick={() => setExpanded(value => !value)}>{expanded ? '−' : '+'}</Button>}
      <Box component="button" onClick={() => onSelect(id)}
        aria-label={gettext('Inspect operator %s', id + 1)}
        sx={{textAlign: 'left', p: 1, border: 1, borderRadius: 1, color: 'text.primary',
          bgcolor: selected === id ? 'action.selected' : 'background.paper',
          borderColor: selected === id ? 'primary.main' : 'divider', maxWidth: 780,
          cursor: 'pointer', overflowWrap: 'anywhere', font: 'inherit'}}>
        <Typography component="span" sx={{fontWeight: 600}}>{node.label}</Typography>
        <Typography component="span" sx={{display: 'block', fontSize: '.8rem', color: 'text.secondary'}}>
          {node.actual ? gettext('Native actual measurements') : gettext('Native plan structure / estimates')}
        </Typography>
        {node.facts.filter(fact => /cost|rows|time|loops|access_type|table_name|key$|native estimates|native actuals/.test(fact.name)).slice(0, 8)
          .map(fact => <Box key={fact.name} sx={{fontSize: '.8rem', whiteSpace: 'pre-wrap'}}>{fact.name}: {fact.value}</Box>)}
      </Box>
    </Box>
    {node.children.length > 0 && expanded && <Box component="ul" role="group"
      sx={{pl: 2.25, ml: 2, borderLeft: 1, borderColor: 'divider'}}>
      {node.children.map(child => <PlanNode key={child} id={child} graph={graph} selected={selected} onSelect={onSelect} />)}
    </Box>}
  </Box>;
}
PlanNode.propTypes = {id: PropTypes.number.isRequired, graph: PropTypes.object.isRequired,
  selected: PropTypes.number, onSelect: PropTypes.func.isRequired};

export default function MySQLQueryPlan({rendered, analyzeRequested=false, pending=false, failed=false}) {
  const source = mysqlPlanText(rendered);
  const graph = useMemo(() => parseMySQLPlan(source), [source]);
  const [selected, setSelected] = useState(0);
  const node = graph.nodes?.[selected] || graph.nodes?.[0];
  return <Box aria-label={gettext('MySQL query plan')} sx={{mt: 1, minWidth: 0}}>
    <Alert severity="info">{analyzeRequested ?
      gettext('EXPLAIN ANALYZE was requested and executes the statement on the selected SQL session. A displayed plan does not establish commit or rollback.') :
      gettext('Native optimizer estimates are shown as reported. Costs are not elapsed milliseconds; links follow the native plan nesting.')}</Alert>
    {(pending || failed || rendered?.page?.next_cursor) && <Alert severity="warning">
      {gettext('This execution or result delivery is incomplete, failed, or awaiting observation. Returned plan text does not establish successful completion.')}
    </Alert>}
    {graph.available ? <>
      <Typography component="h4">{graph.format} · {graph.nodes.length} {gettext('native plan nodes')}</Typography>
      <Box sx={{display: 'grid', gridTemplateColumns: {xs: '1fr', lg: 'minmax(0, 3fr) minmax(230px, 2fr)'}, gap: 1}}>
        <Box sx={{overflow: 'auto', maxHeight: 620, border: 1, borderColor: 'divider', borderRadius: 1, p: 1}}>
          <Box component="ul" role="tree" aria-label={gettext('Native MySQL operator graph')} sx={{m: 0, pl: 2}}>
            {graph.roots.map(id => <PlanNode key={id} id={id} graph={graph} selected={node?.id}
              onSelect={setSelected} />)}
          </Box>
        </Box>
        <Box aria-label={gettext('Selected native operator')} sx={{overflow: 'auto', maxHeight: 620}}>
          <Typography component="h4">{node?.label}</Typography>
          <Box component="code">{node?.path}</Box>
          <Box component="dl" sx={{m: 0}}>{node?.facts.map((fact, index) =>
            <Box key={index} sx={{my: 1}}><Box component="dt" sx={{fontWeight: 600}}>{fact.name}</Box>
              <Box component="dd" sx={{m: 0, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{fact.value}</Box></Box>)}
          </Box>
        </Box>
      </Box>
    </> : <Alert severity="info">{gettext('Graphical presentation is unavailable.')} {graph.reason} {gettext('The original result remains available.')}</Alert>}
    {source !== null && <Box component="details" sx={{mt: 1}}>
      <Box component="summary">{gettext('Original native plan text')}</Box>
      <Box component="pre" aria-label={gettext('Original MySQL plan text')}
        sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 460, overflow: 'auto'}}>{source}</Box>
    </Box>}
  </Box>;
}
MySQLQueryPlan.propTypes = {rendered: PropTypes.object, analyzeRequested: PropTypes.bool,
  pending: PropTypes.bool, failed: PropTypes.bool};
