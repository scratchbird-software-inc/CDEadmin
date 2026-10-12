import {useEffect, useRef, useState} from 'react';
import {Alert, Box, Button, MenuItem, TextField} from '@mui/material';
import gettext from 'sources/gettext';
import GridNavigation from './GridNavigation';

const rowCount = page => (page?.rows || page?.documents || page?.records || []).length;

// Native continuations are consumed once. Backward navigation reads cached
// responses; no random access or transaction capabilities are inferred.
export default function useNativeRowPages(post) {
  const [pages, setPages] = useState([]), [index, setIndex] = useState(0);
  const [size, setSize] = useState(200), [maximum, setMaximum] = useState(1000);
  const cursor = useRef(null);
  const [error, setError] = useState('');
  const cancel = async () => {
    const retained = cursor.current;
    if (!retained) return;
    await retained.post({action: 'visual_admin_rows_cancel', request: {continuation: retained.token}});
    if (cursor.current === retained) cursor.current = null;
  };
  useEffect(() => () => {cancel().catch(() => {});}, [post]);
  const total = pages.reduce((count, page) => count + rowCount(page), 0);
  const valid = Number.isInteger(maximum) && maximum > 0 && maximum <= 100000;
  const read = async request => {
    if (!valid) throw new Error(gettext('Maximum rows must be between 1 and 100000.'));
    if (!request.continuation) await cancel();
    const remaining = maximum - (request.continuation ? total : 0);
    if (remaining <= 0) return;
    const response = await post({action: 'visual_admin_rows', request: {
      ...request, limit: Math.min(size, maximum),
    }});
    const key = ['rows', 'documents', 'records'].find(name => Array.isArray(response[name]));
    if (key && response[key].length > remaining) {
      response.prefetched_excess_rows = response[key].length - remaining;
      response[key] = response[key].slice(0, remaining);
      response.retrieval_limited = true;
    }
    cursor.current = response.continuation ? {post, token: response.continuation} : null;
    const loaded = request.continuation ? [...pages, response] : [response];
    if (loaded.reduce((count, page) => count + rowCount(page), 0) >= maximum && cursor.current) {
      await cancel(); response.continuation = null; response.retrieval_limited = true;
    }
    setPages(loaded); setIndex(loaded.length - 1);
  };
  const reset = () => {setPages([]); setIndex(0);};
  const clear = async () => {
    try {await cancel(); reset(); setError('');}
    catch (failure) {setError(failure?.message || gettext('Unable to close the cursor.'));}
  };
  const controls = (load, blocked=false) => <Box>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, my: 1}}>
      <TextField select size="small" label={gettext('Rows per page')} value={size}
        disabled={blocked || pages.length > 0} onChange={event => setSize(Number(event.target.value))}>
        {[25, 50, 100, 200, 500].map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}
      </TextField>
      <TextField type="number" size="small" label={gettext('Maximum rows retrieved')}
        value={maximum} disabled={blocked || pages.length > 0} error={!valid}
        inputProps={{min: 1, max: 100000}} onChange={event => setMaximum(Number(event.target.value))} />
    </Box>
    {pages.length > 0 && <GridNavigation page={index} pages={pages.length} busy={blocked}
      endKnown={!cursor.current} canNext={index < pages.length - 1 || Boolean(cursor.current)}
      onFirst={() => setIndex(0)} onPrevious={() => setIndex(index - 1)}
      onNext={() => index < pages.length - 1 ? setIndex(index + 1) : load(cursor.current.token)}
      onLast={() => setIndex(pages.length - 1)}>
      <span>{gettext('%s rows retained', total)}</span>
      <Button disabled={blocked} onClick={clear}>{gettext('Close result')}</Button>
      {pages.at(-1)?.retrieval_limited && <span>{gettext('Retrieval limit reached')}</span>}
      {pages.at(-1)?.prefetched_excess_rows > 0 && <span>{gettext('%s excess rows from the final native batch discarded', pages.at(-1).prefetched_excess_rows)}</span>}
    </GridNavigation>}
  </Box>;
  return {page: pages[index] || null, reset, read, controls, cancel,
    cursorOpen: Boolean(cursor.current), valid};
}
