import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import SourceValidation from '../../../pgadmin/tools/sqleditor/static/js/components/sections/SourceValidation';
import EventBus from 'sources/helpers/EventBus';
import {QUERY_TOOL_EVENTS} from '../../../pgadmin/tools/sqleditor/static/js/components/QueryToolConstants';
import {withTheme} from '../fake_theme';
const Component = withTheme(SourceValidation);
const result = {data: {data: {authority: 'postgresql-offline-grammar', grammar_valid: true,
  scope: 'PostgreSQL parser revision; no execution', diagnostics: []}}};

it('checks captured source without an execution event and clears stale diagnostics', async () => {
  const eventBus = new EventBus(), execute = jest.fn();
  eventBus.registerListener(QUERY_TOOL_EVENTS.TRIGGER_EXECUTION, execute);
  eventBus.registerListener(QUERY_TOOL_EVENTS.TRIGGER_GET_QUERY_CONTENT, callback => callback('SELECT 42'));
  const api = {post: jest.fn().mockResolvedValue(result)};
  render(<Component api={api} eventBus={eventBus} transId={7} />);
  fireEvent.click(screen.getByRole('button', {name: 'Check SQL source without executing'}));
  await screen.findByText('SQL grammar accepted');
  expect(api.post.mock.calls[0][1]).toEqual({source: 'SELECT 42'});
  expect(execute).not.toHaveBeenCalled();
  await act(async () => eventBus.fireEvent(QUERY_TOOL_EVENTS.QUERY_CHANGED));
  expect(screen.queryByText('SQL grammar accepted')).not.toBeInTheDocument();
});

it('does not display a late result in a different connection', async () => {
  let resolve;
  const eventBus = new EventBus();
  eventBus.registerListener(QUERY_TOOL_EVENTS.TRIGGER_GET_QUERY_CONTENT, callback => callback('SELECT 1'));
  const api = {post: jest.fn(() => new Promise(done => {resolve = done;}))};
  const {rerender} = render(<Component api={api} eventBus={eventBus} transId={7} />);
  fireEvent.click(screen.getByRole('button', {name: 'Check SQL source without executing'}));
  await waitFor(() => expect(api.post).toHaveBeenCalledTimes(1));
  rerender(<Component api={api} eventBus={eventBus} transId={8} />);
  await act(async () => resolve(result));
  expect(screen.queryByText('SQL grammar accepted')).not.toBeInTheDocument();
});
