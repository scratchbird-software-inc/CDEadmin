import {act, renderHook} from '@testing-library/react';
import useExecutionPolicy from '../../../pgadmin/tools/sqleditor/static/js/components/sections/useExecutionPolicy';

it('waits for acknowledgement, suppresses duplicate requests and never accepts failed policy changes', async () => {
  let resolve;
  const request = jest.fn(() => new Promise(done => { resolve = done; }));
  const onAccepted = jest.fn(), onError = jest.fn();
  const {result} = renderHook(() => useExecutionPolicy({request, onAccepted, onError, scope: 1}));
  let first;
  act(() => {first = result.current.change('auto_commit', true);});
  expect(result.current.pending).toBe(true);
  await act(async () => result.current.change('auto_commit', true));
  expect(request).toHaveBeenCalledTimes(1);
  expect(onAccepted).not.toHaveBeenCalled();
  await act(async () => {resolve({data: {data: {status: false}}}); await first;});
  expect(result.current.uncertain).toBe(true);
  expect(onAccepted).not.toHaveBeenCalled();
  expect(onError).toHaveBeenCalledTimes(1);
  request.mockResolvedValue({data: {data: {status: true}}});
  await act(async () => result.current.change('server_cursor', false));
  expect(result.current.uncertain).toBe(true);
  await act(async () => result.current.change('auto_commit', true));
  expect(result.current.uncertain).toBe(false);
  expect(onAccepted).toHaveBeenLastCalledWith('auto_commit', true);
});

it('ignores late replies after switching to another query-tool transaction', async () => {
  let resolve;
  const request = jest.fn(() => new Promise(done => {resolve = done;}));
  const onAccepted = jest.fn(), onError = jest.fn();
  const {result, rerender} = renderHook(({scope}) => useExecutionPolicy({request, onAccepted, onError, scope}), {initialProps: {scope: 1}});
  let first;
  act(() => {first = result.current.change('auto_commit', false);});
  rerender({scope: 2});
  await act(async () => {resolve({data: {data: {status: true}}}); await first;});
  expect(onAccepted).not.toHaveBeenCalled();
  expect(result.current.pending).toBe(false);
  expect(result.current.uncertain).toBe(false);
});
