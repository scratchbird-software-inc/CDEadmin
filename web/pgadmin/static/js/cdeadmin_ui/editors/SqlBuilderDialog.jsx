/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

/*
 * Visual SQL builder (owner direction 2026-11-06, option b; SQLite and
 * DuckDB first, 2026-11-08). Opened from the SQL tab; writes a query into
 * the editor and runs nothing. Every option is shown; the ones this
 * connection lacks are disabled with the reason the engine declares. The
 * server writes the SQL and refuses unavailable options again.
 */

import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Box} from '../primitives/Layout';
import {Button} from '../primitives/Button';
import {TextField, NumberField} from '../primitives/Field';
import {Checkbox, Select} from '../primitives/Choice';
import {MultiSelect} from '../primitives/AdvancedControls';
import {Dialog} from '../overlays/Dialog';
import FormReference from '../navigation/FormReference';
import {
  AGGREGATES, BuilderDraftError, COMPARISONS, GROUPINGS, JOIN_TYPES, SET_OPERATORS,
  available, columnChoices, columnResolver, cteSource, emptyColumn, emptyCondition,
  emptyCte, emptyDraft, emptyJoin, emptyOrder, emptySelect, outputColumns,
  relationSource, toModel, unavailableReason,
} from './sqlBuilderModel';

function requestError(error) {
  return error?.response?.data?.errormsg || error?.message || 'The SQL builder request failed.';
}

function replaceAt(list, index, value) {
  return list.map((item, position) => position === index ? value : item);
}

function removeAt(list, index) {
  return list.filter((_item, position) => position !== index);
}

/* A menu choice the connection lacks: disabled, and labelled with the
 * reason. */
function gated(options, id, label) {
  return available(options, id) ? {disabled: false, label} :
    {disabled: true, label: `${label} (${unavailableReason(options, id)})`};
}

/* A field the connection lacks: disabled, with the reason as helper text. */
function gatedField(options, id) {
  return available(options, id) ? {disabled: false} :
    {disabled: true, helperText: unavailableReason(options, id)};
}

function Section({title, children}) {
  return <Box component="fieldset" sx={{border: '1px solid', borderColor: 'divider', m: 0, mb: 1,
    p: 1, display: 'grid', gap: 1, minWidth: 0}}>
    <Box component="legend" sx={{px: 0.5, fontWeight: 600}}>{title}</Box>
    {children}
  </Box>;
}
Section.propTypes = {title: PropTypes.node, children: PropTypes.node};

function Row({children}) {
  return <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap',
    '& > .MuiFormControl-root': {minWidth: 140}}}>{children}</Box>;
}
Row.propTypes = {children: PropTypes.node};

function GatedButton({options, option, onClick, children, disabled=false}) {
  const reason = option ? unavailableReason(options, option) : '';
  return <Button size="small" disabled={disabled || Boolean(reason)} onClick={onClick}
    title={reason || undefined}>{children}{reason ? ` (${reason})` : ''}</Button>;
}
GatedButton.propTypes = {options: PropTypes.object, option: PropTypes.string,
  onClick: PropTypes.func, children: PropTypes.node, disabled: PropTypes.bool};

/* A chosen value the sources no longer offer (an alias or CTE was renamed)
 * stays visible, marked, so the form never hides what it will write. */
function withStale(choices, values, describe) {
  const stale = values.filter((value) => value && !choices.some((item) => item.value === value));
  return [...choices, ...stale.map((value) => ({value, label: `${describe(value)} (no longer available)`}))];
}

function refLabel(value) {
  try {
    return JSON.parse(value).join('.');
  } catch {
    return value;
  }
}

function ColumnPicker({label, value, choices, onChange}) {
  return <Select size="small" label={label} value={value}
    options={withStale(choices, [value], refLabel)} onChange={onChange} />;
}

function SourcePicker({label, value, sources, onChange}) {
  return <Select size="small" label={label} value={value}
    options={withStale(sources, [value], (stale) => stale.replace(/^(rel|cte):/, ''))}
    onChange={onChange} />;
}
SourcePicker.propTypes = {label: PropTypes.string, value: PropTypes.string,
  sources: PropTypes.array, onChange: PropTypes.func};
ColumnPicker.propTypes = {label: PropTypes.string, value: PropTypes.string,
  choices: PropTypes.array, onChange: PropTypes.func};

function ColumnsPicker({label, value, choices, onChange, disabled=false, helperText}) {
  const offered = withStale(choices, value, refLabel);
  const selected = offered.filter((item) => value.includes(item.value));
  return <MultiSelect label={label} options={offered} value={selected} disabled={disabled}
    helperText={helperText} isOptionEqualToValue={(a, b) => a.value === b.value}
    onChange={(next) => onChange(next.map((item) => item.value))} size="small"
    sx={{minWidth: 260, flex: '1 1 260px'}} />;
}
ColumnsPicker.propTypes = {label: PropTypes.string, value: PropTypes.array, choices: PropTypes.array,
  onChange: PropTypes.func, disabled: PropTypes.bool, helperText: PropTypes.node};

/* A column, an aggregate, or a value. */
function OperandEditor({label, operand, onChange, choices, options, kinds}) {
  const set = (patch) => onChange({...operand, ...patch});
  const kindOptions = [
    {value: 'column', label: 'Column'},
    {value: 'aggregate', ...gated(options, 'aggregate', 'Aggregate')},
    {value: 'text', label: 'Text value'},
    {value: 'number', label: 'Number value'},
    {value: 'null', label: 'NULL'},
    {value: 'all', label: 'All columns (*)'},
  ].filter((item) => kinds.includes(item.value));
  return <Row>
    <Select size="small" label={`${label} kind`} value={operand.kind} options={kindOptions}
      onChange={(kind) => set({kind, star: kind === 'aggregate' ? operand.star || !operand.column : operand.star})} />
    {operand.kind === 'column' &&
      <ColumnPicker label={label} value={operand.column} choices={choices} onChange={(column) => set({column})} />}
    {operand.kind === 'aggregate' && <>
      <Select size="small" label={`${label} function`} value={operand.func}
        options={AGGREGATES.map((name) => ({value: name, label: name}))}
        onChange={(func) => set({func, star: func === 'count' ? operand.star : false})} />
      {operand.func === 'count' && <Checkbox label="All rows (*)" checked={operand.star}
        onChange={(star) => set({star, distinct: star ? false : operand.distinct})} />}
      {!operand.star && <ColumnPicker label={`${label} argument`} value={operand.column} choices={choices}
        onChange={(column) => set({column})} />}
      {!operand.star && <Checkbox label={gated(options, 'aggregate.distinct', 'Distinct values').label}
        disabled={!available(options, 'aggregate.distinct')} checked={operand.distinct}
        onChange={(distinct) => set({distinct})} />}
    </>}
    {(operand.kind === 'text' || operand.kind === 'number') &&
      <TextField size="small" label={`${label} value`} value={operand.value}
        type={operand.kind === 'number' ? 'number' : 'text'}
        onChange={(event) => set({value: event.target.value})} />}
  </Row>;
}
OperandEditor.propTypes = {label: PropTypes.string, operand: PropTypes.object, onChange: PropTypes.func,
  choices: PropTypes.array, options: PropTypes.object, kinds: PropTypes.array};

function ConditionEditor({label, condition, onChange, choices, options, leftKinds, onRemove}) {
  const unary = condition.op === 'IS NULL' || condition.op === 'IS NOT NULL';
  return <Box sx={{display: 'grid', gap: 0.5, borderLeft: '2px solid', borderColor: 'divider', pl: 1}}>
    <OperandEditor label={`${label} left`} operand={condition.left} choices={choices} options={options}
      kinds={leftKinds} onChange={(left) => onChange({...condition, left})} />
    <Row>
      <Select size="small" label={`${label} comparison`} value={condition.op}
        options={COMPARISONS.map((op) => ({value: op, label: op}))}
        onChange={(op) => onChange({...condition, op})} />
      {onRemove && <Button size="small" onClick={onRemove}>Remove</Button>}
    </Row>
    {!unary && <OperandEditor label={`${label} right`} operand={condition.right} choices={choices}
      options={options} kinds={['column', 'text', 'number']}
      onChange={(right) => onChange({...condition, right})} />}
  </Box>;
}
ConditionEditor.propTypes = {label: PropTypes.string, condition: PropTypes.object, onChange: PropTypes.func,
  choices: PropTypes.array, options: PropTypes.object, leftKinds: PropTypes.array, onRemove: PropTypes.func};

function ConditionList({title, label, group, onChange, choices, options, option, leftKinds, newLeft}) {
  return <Section title={title}>
    {group.items.length > 1 && <Select size="small" label={`${label} combine`} value={group.combine}
      options={[{value: 'all', label: 'All must hold (AND)'},
        {value: 'any', ...gated(options, 'where.or', 'Any may hold (OR)')}]}
      onChange={(combine) => onChange({...group, combine})} />}
    {group.items.map((item, index) => <ConditionEditor key={item.key} label={`${label} ${index + 1}`}
      condition={item} choices={choices} options={options} leftKinds={leftKinds}
      onChange={(next) => onChange({...group, items: replaceAt(group.items, index, next)})}
      onRemove={() => onChange({...group, items: removeAt(group.items, index)})} />)}
    <Box><GatedButton options={options} option={option}
      onClick={() => onChange({...group, items: [...group.items, emptyCondition(newLeft)]})}>
      Add condition</GatedButton></Box>
  </Section>;
}
ConditionList.propTypes = {title: PropTypes.string, label: PropTypes.string, group: PropTypes.object,
  onChange: PropTypes.func, choices: PropTypes.array, options: PropTypes.object, option: PropTypes.string,
  leftKinds: PropTypes.array, newLeft: PropTypes.string};

function JoinEditor({label, join, onChange, onRemove, sources, columnsOf, choices, options}) {
  const set = (patch) => onChange({...join, ...patch});
  const shared = (columnsOf(join.source) || []).map((name) => ({value: name, label: name}));
  const plain = join.type === 'cross' || join.type === 'natural';
  return <Box sx={{display: 'grid', gap: 0.5, borderLeft: '2px solid', borderColor: 'divider', pl: 1}}>
    <Row>
      <Select size="small" label={`${label} type`} value={join.type}
        options={JOIN_TYPES.map((item) => ({value: item.value, ...gated(options, `join.${item.value}`, item.label)}))}
        onChange={(type) => set({type})} />
      <SourcePicker label={`${label} source`} value={join.source} sources={sources}
        onChange={(source) => set({source, using: []})} />
      <TextField size="small" label={`${label} alias`} value={join.alias}
        onChange={(event) => set({alias: event.target.value})} />
      <Button size="small" onClick={onRemove}>Remove</Button>
    </Row>
    {!plain && <Row>
      <Select size="small" label={`${label} match`} value={join.mode}
        options={[{value: 'on', label: 'ON condition'},
          {value: 'using', ...gated(options, 'join.using', 'USING shared columns')}]}
        onChange={(mode) => set({mode})} />
    </Row>}
    {!plain && join.mode === 'on' && <ConditionEditor label={`${label} ON`} condition={join.on}
      choices={choices} options={options} leftKinds={['column']} onChange={(on) => set({on})} />}
    {!plain && join.mode === 'using' && <ColumnsPicker label={`${label} USING`} value={join.using}
      choices={shared} onChange={(using) => set({using})} />}
  </Box>;
}
JoinEditor.propTypes = {label: PropTypes.string, join: PropTypes.object, onChange: PropTypes.func,
  onRemove: PropTypes.func, sources: PropTypes.array, columnsOf: PropTypes.func,
  choices: PropTypes.array, options: PropTypes.object};

function GroupEditor({label, group, onChange, choices, options}) {
  const set = (patch) => onChange({...group, ...patch});
  // Every grouping needs GROUP BY itself as well as its own option.
  const choice = (item) => {
    const missing = [...new Set(['group_by', item.option])]
      .find((id) => !available(options, id));
    return {value: item.value, ...(item.option && missing ? gated(options, missing, item.label) :
      {disabled: false, label: item.label})};
  };
  return <Section title="Grouping">
    <Select size="small" label={`${label} grouping`} value={group.kind}
      options={GROUPINGS.map(choice)} onChange={(kind) => set({kind})} />
    {['columns', 'rollup', 'cube'].includes(group.kind) && <ColumnsPicker label={`${label} grouping columns`}
      value={group.columns} choices={choices} onChange={(columns) => set({columns})} />}
    {group.kind === 'grouping_sets' && <>
      {group.sets.map((columns, index) => <Row key={`${label}-set-${index}`}>
        <ColumnsPicker label={`${label} grouping set ${index + 1}`} value={columns} choices={choices}
          helperText={columns.length ? undefined : 'An empty set is the grand total.'}
          onChange={(next) => set({sets: replaceAt(group.sets, index, next)})} />
        <Button size="small" onClick={() => set({sets: removeAt(group.sets, index)})}>Remove</Button>
      </Row>)}
      <Box><Button size="small" onClick={() => set({sets: [...group.sets, []]})}>Add grouping set</Button></Box>
    </>}
  </Section>;
}
GroupEditor.propTypes = {label: PropTypes.string, group: PropTypes.object, onChange: PropTypes.func,
  choices: PropTypes.array, options: PropTypes.object};

function SelectEditor({label, select, onChange, scope}) {
  const {options, sources, columnsOf} = scope;
  const set = (patch) => onChange({...select, ...patch});
  const choices = useMemo(() => columnChoices(select, columnsOf), [select, columnsOf]);
  return <Box sx={{display: 'grid', gap: 1}}>
    <Section title="FROM">
      <Row>
        <SourcePicker label={`${label} FROM`} value={select.source} sources={sources}
          onChange={(source) => set({source})} />
        <TextField size="small" label={`${label} alias`} value={select.alias}
          onChange={(event) => set({alias: event.target.value})} />
      </Row>
      {select.joins.map((join, index) => <JoinEditor key={join.key} label={`${label} join ${index + 1}`}
        join={join} sources={sources} columnsOf={columnsOf} choices={choices} options={options}
        onChange={(next) => set({joins: replaceAt(select.joins, index, next)})}
        onRemove={() => set({joins: removeAt(select.joins, index)})} />)}
      <Box><GatedButton options={options} disabled={!JOIN_TYPES.some((item) => available(options, `join.${item.value}`))}
        onClick={() => set({joins: [...select.joins, emptyJoin(select.source)]})}>Add join</GatedButton></Box>
    </Section>
    <Section title="Columns">
      <Row>
        <Checkbox label={gated(options, 'distinct', 'DISTINCT').label} checked={select.distinct}
          disabled={!available(options, 'distinct')} onChange={(distinct) => set({distinct})} />
        <ColumnsPicker label={`${label} DISTINCT ON`} value={select.distinctOn} choices={choices}
          {...gatedField(options, 'distinct_on')} onChange={(distinctOn) => set({distinctOn})} />
      </Row>
      {select.columns.length === 0 && <Box component="small" sx={{color: 'text.secondary'}}>
        No columns chosen: every column (*) is read.</Box>}
      {select.columns.map((column, index) => <Row key={column.key}>
        <OperandEditor label={`${label} column ${index + 1}`} operand={column} choices={choices}
          options={options} kinds={['column', 'aggregate', 'text', 'number', 'null', 'all']}
          onChange={(next) => set({columns: replaceAt(select.columns, index, {...column, ...next})})} />
        {column.kind !== 'all' && <TextField size="small" label={`${label} column ${index + 1} alias`}
          value={column.alias} onChange={(event) => set({columns: replaceAt(select.columns, index,
            {...column, alias: event.target.value})})} />}
        <Button size="small" onClick={() => set({columns: removeAt(select.columns, index)})}>Remove</Button>
      </Row>)}
      <Box><Button size="small" onClick={() => set({columns: [...select.columns, emptyColumn()]})}>
        Add column</Button></Box>
    </Section>
    <ConditionList title="WHERE" label={`${label} condition`} group={select.where} choices={choices}
      options={options} option="where" leftKinds={['column']} newLeft="column"
      onChange={(where) => set({where})} />
    <GroupEditor label={label} group={select.group} choices={choices} options={options}
      onChange={(group) => set({group})} />
    <ConditionList title="HAVING" label={`${label} HAVING`} group={select.having} choices={choices}
      options={options} option="having" leftKinds={['aggregate', 'column']} newLeft="aggregate"
      onChange={(having) => set({having})} />
  </Box>;
}
SelectEditor.propTypes = {label: PropTypes.string, select: PropTypes.object, onChange: PropTypes.func,
  scope: PropTypes.object};

function CompoundEditor({label, compound, onChange, scope}) {
  const {options, columnsOf} = scope;
  const set = (patch) => onChange({...compound, ...patch});
  const firstOperator = SET_OPERATORS.find((item) => available(options, `set.${item.value}`));
  // ORDER BY: a single SELECT orders by its columns; a set operation by
  // the names of its result columns.
  const orderChoices = useMemo(() => {
    const names = outputColumns(compound, columnsOf).map((name) =>
      ({value: JSON.stringify([name]), label: name}));
    if(compound.selects.length > 1) return names;
    const qualified = columnChoices(compound.selects[0], columnsOf);
    return [...qualified, ...names.filter((item) => !qualified.some((other) => other.value === item.value))];
  }, [compound, columnsOf]);
  return <Box sx={{display: 'grid', gap: 1}}>
    {compound.selects.map((select, index) => <Box key={select.key} sx={{display: 'grid', gap: 1}}>
      {index > 0 && <Row>
        <Select size="small" label={`${label} set operation ${index}`} value={compound.operators[index - 1]}
          options={SET_OPERATORS.map((item) => ({value: item.value,
            ...gated(options, `set.${item.value}`, item.label)}))}
          onChange={(operator) => set({operators: replaceAt(compound.operators, index - 1, operator)})} />
        <Button size="small" onClick={() => set({selects: removeAt(compound.selects, index),
          operators: removeAt(compound.operators, index - 1)})}>Remove this SELECT</Button>
      </Row>}
      <SelectEditor label={compound.selects.length > 1 ? `${label} SELECT ${index + 1}` : label}
        select={select} scope={scope}
        onChange={(next) => set({selects: replaceAt(compound.selects, index, next)})} />
    </Box>)}
    <Box><GatedButton options={options} disabled={!firstOperator}
      onClick={() => set({selects: [...compound.selects, emptySelect(compound.selects[0].source)],
        operators: [...compound.operators, firstOperator.value]})}>
      Add SELECT (UNION, INTERSECT, EXCEPT)</GatedButton></Box>
    <Section title="ORDER BY, LIMIT and OFFSET">
      {compound.order.map((item, index) => <Row key={item.key}>
        <OperandEditor label={`${label} order ${index + 1}`} operand={item.operand} choices={orderChoices}
          options={options} kinds={['column', 'aggregate']}
          onChange={(operand) => set({order: replaceAt(compound.order, index, {...item, operand})})} />
        <Select size="small" label={`${label} order ${index + 1} direction`} value={item.direction}
          options={[{value: 'asc', label: 'Ascending'}, {value: 'desc', label: 'Descending'}]}
          onChange={(direction) => set({order: replaceAt(compound.order, index, {...item, direction})})} />
        <Select size="small" label={`${label} order ${index + 1} NULLs`}
          value={item.nulls} {...gatedField(options, 'order_by.nulls')}
          options={[{value: '', label: 'Engine default'}, {value: 'first', label: 'NULLS FIRST'},
            {value: 'last', label: 'NULLS LAST'}]}
          onChange={(nulls) => set({order: replaceAt(compound.order, index, {...item, nulls})})} />
        <Button size="small" onClick={() => set({order: removeAt(compound.order, index)})}>Remove</Button>
      </Row>)}
      <Box><GatedButton options={options} option="order_by"
        onClick={() => set({order: [...compound.order, emptyOrder()]})}>Add sort column</GatedButton></Box>
      <Row>
        <NumberField size="small" label={`${label} LIMIT`} value={compound.limit}
          {...gatedField(options, 'limit')} inputProps={{min: 0, step: 1}}
          onChange={(event) => set({limit: event.target.value})} />
        <NumberField size="small" label={`${label} OFFSET`} value={compound.offset}
          inputProps={{min: 0, step: 1}} {...(available(options, 'offset') ?
            {disabled: !String(compound.limit).trim(), helperText: 'OFFSET needs LIMIT.'} :
            gatedField(options, 'offset'))}
          onChange={(event) => set({offset: event.target.value})} />
      </Row>
    </Section>
  </Box>;
}
CompoundEditor.propTypes = {label: PropTypes.string, compound: PropTypes.object, onChange: PropTypes.func,
  scope: PropTypes.object};

function sourceOptions(relations, ctes) {
  return [...relations.map((item) => ({value: relationSource(item.path),
    label: `${item.path.join('.')} (${item.kind})`})),
  ...ctes.map((cte) => ({value: cteSource(cte.name), label: `${cte.name} (WITH)`}))];
}

export default function SqlBuilderDialog({open, onClose, post, onInsert}) {
  const [info, setInfo] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [draft, setDraft] = useState(null);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState('');
  const [busy, setBusy] = useState(false);
  // The dialog shows errors above the form; after a click at the bottom of
  // a long form, bring the message into view.
  const top = useRef(null);
  useEffect(() => {
    if(error || loadError) top.current?.scrollIntoView?.({block: 'nearest'});
  }, [error, loadError]);
  useEffect(() => {
    if(!open) return undefined;
    let active = true;
    setInfo(null); setLoadError(''); setError(''); setPreview('');
    post({action: 'sql_builder', request: {operation: 'options'}})
      .then((result) => {
        if(!active) return;
        setInfo(result);
        const first = result?.relations?.[0];
        setDraft(emptyDraft(first ? relationSource(first.path) : ''));
      })
      .catch((failure) => {if(active) setLoadError(requestError(failure));});
    return () => {active = false;};
  }, [open]);
  const options = info?.options || {};
  const relations = info?.relations || [];
  const ctes = draft?.ctes || [];
  const columnsOf = useMemo(() => columnResolver(relations, ctes), [relations, ctes]);
  const scopeFor = (visible) => ({options, columnsOf, sources: sourceOptions(relations, visible)});
  const named = ctes.filter((cte) => cte.name.trim());
  const write = async () => {
    setError('');
    let model;
    try {
      model = toModel(draft);
    } catch(failure) {
      setError(failure instanceof BuilderDraftError ? failure.message :
        `The form could not be read: ${failure.message}`);
      return null;
    }
    setBusy(true);
    try {
      return await post({action: 'sql_builder', request: {operation: 'source', model}});
    } catch(failure) {
      setError(requestError(failure));
      return null;
    } finally {
      setBusy(false);
    }
  };
  const showPreview = async () => {
    const written = await write();
    if(written) setPreview(written.source);
  };
  const insert = async () => {
    const written = await write();
    if(!written) return;
    onInsert({source: written.source, languageProfile: written.language_profile});
    onClose();
  };
  const setCte = (index, next) => setDraft((current) => ({...current, ctes: replaceAt(current.ctes, index, next)}));
  return <Dialog open={open} title="Build a query" size="large" busy={busy}
    onClose={() => !busy && onClose()} validationError={error || loadError}
    actions={<>
      <Button disabled={busy} onClick={onClose}>Cancel</Button>
      <Button disabled={busy || !draft} onClick={showPreview}>Preview SQL</Button>
      <Button intent="primary" loading={busy} disabled={!draft} onClick={insert}>Insert into editor</Button>
    </>}>
    <div ref={top} />
    <FormReference formKey="sql-builder" />
    {!info && !loadError && <Box component="p">Reading this connection&apos;s options and tables…</Box>}
    {info && draft && <Box sx={{display: 'grid', gap: 1}}>
      <Box component="p" sx={{m: 0}}>
        The query is written in this connection&apos;s SQL and put in the editor; nothing is run.
        Options this connection lacks are disabled with the reason
        {info.runtime_version ? ` (runtime ${info.runtime_version})` : ''}.
      </Box>
      <Box component="details" aria-label="Options for this connection">
        <summary>Options for this connection</summary>
        <Box component="ul" sx={{m: 0, pl: 3}}>
          {Object.entries(options).map(([id, entry]) => <Box component="li" key={id}
            data-option={id} data-available={entry.available ? 'true' : 'false'}
            sx={{color: entry.available ? 'text.primary' : 'text.disabled'}}>
            {entry.label}{entry.available ? '' : ` — ${entry.reason}`}
          </Box>)}
        </Box>
      </Box>
      {relations.length === 0 && <Box component="p" sx={{m: 0}}>
        This connection&apos;s catalog lists no tables or views.</Box>}
      <Section title="WITH (common table expressions)">
        <Checkbox label={gated(options, 'cte.recursive', 'RECURSIVE').label} checked={draft.recursive}
          disabled={!available(options, 'cte.recursive') || ctes.length === 0}
          onChange={(recursive) => setDraft((current) => ({...current, recursive}))} />
        {ctes.map((cte, index) => {
          // A CTE reads the ones before it; a recursive one also reads itself.
          const visible = named.filter((other, position) => position < index ||
            (draft.recursive && other.key === cte.key));
          return <Box key={cte.key} sx={{display: 'grid', gap: 1, borderLeft: '3px solid',
            borderColor: 'primary.main', pl: 1}}>
            <Row>
              <TextField size="small" required label={`CTE ${index + 1} name`} value={cte.name}
                onChange={(event) => setCte(index, {...cte, name: event.target.value})} />
              <TextField size="small" label={`CTE ${index + 1} column names`} value={cte.columns}
                helperText="Optional, separated by commas."
                onChange={(event) => setCte(index, {...cte, columns: event.target.value})} />
              <Select size="small" label={`CTE ${index + 1} materialization`}
                value={cte.materialized} {...gatedField(options, 'cte.materialized')}
                options={[{value: '', label: 'Engine decides'}, {value: 'yes', label: 'MATERIALIZED'},
                  {value: 'no', label: 'NOT MATERIALIZED'}]}
                onChange={(materialized) => setCte(index, {...cte, materialized})} />
              <Button size="small" onClick={() => setDraft((current) => ({...current,
                ctes: removeAt(current.ctes, index),
                recursive: current.ctes.length > 1 && current.recursive}))}>Remove</Button>
            </Row>
            <CompoundEditor label={cte.name.trim() || `CTE ${index + 1}`} compound={cte.query}
              scope={scopeFor(visible)} onChange={(query) => setCte(index, {...cte, query})} />
          </Box>;
        })}
        <Box><GatedButton options={options} option="cte"
          onClick={() => setDraft((current) => ({...current, ctes: [...current.ctes,
            emptyCte(`cte${current.ctes.length + 1}`, current.query.selects[0].source)]}))}>
          Add common table expression</GatedButton></Box>
      </Section>
      <Section title="Query">
        <CompoundEditor label="Query" compound={draft.query} scope={scopeFor(named)}
          onChange={(query) => setDraft((current) => ({...current, query}))} />
      </Section>
      {preview && <Box component="pre" aria-label="SQL preview" sx={{m: 0, p: 1, border: '1px solid',
        borderColor: 'divider', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{preview}</Box>}
    </Box>}
  </Dialog>;
}

SqlBuilderDialog.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  post: PropTypes.func.isRequired,
  onInsert: PropTypes.func.isRequired,
};
