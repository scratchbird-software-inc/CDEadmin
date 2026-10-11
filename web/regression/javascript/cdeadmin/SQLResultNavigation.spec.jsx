import {useState} from 'react';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {ResultControls} from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';

const page = (offset, next_cursor) => ({descriptor: {result_id: 'r', export_formats: []},
  page: {offset, next_cursor, page_size: 2}, view_model: {rows: [{n: offset}]}});
function Harness({post}) {
  const [result, setResult] = useState(page(0, 'next'));
  return <><span>offset {result.page.offset}</span><ResultControls rendered={result}
    history={[]} post={post} onRendered={setResult} setBusy={()=>{}} setError={()=>{}} bufferRows={2} /></>;
}
it('revisits bounded server pages without executing SQL or consuming a native continuation', async () => {
  const post = jest.fn(async ({request}) => request.cursor ? page(2, null) : page(0, 'next'));
  render(<Harness post={post} />);
  expect(screen.getByRole('button', {name: /Last page/})).toBeDisabled();
  fireEvent.click(screen.getByRole('button', {name: 'Next result page'}));
  await screen.findByText('offset 2');
  await waitFor(() => expect(screen.getByRole('button', {name: 'First page'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name: 'First page'}));
  await screen.findByText('offset 0');
  await waitFor(() => expect(screen.getByRole('button', {name: 'Last page'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name: 'Last page'}));
  await screen.findByText('offset 2');
  await waitFor(() => expect(post).toHaveBeenCalledTimes(3));
  expect(post.mock.calls.map(([request]) => request)).toEqual([
    {action: 'result_page', request: {result_id: 'r', cursor: 'next', page_size: 2}},
    {action: 'result_page', request: {result_id: 'r', cursor: null, page_size: 2}},
    {action: 'result_page', request: {result_id: 'r', cursor: 'next', page_size: 2}},
  ]);
});
