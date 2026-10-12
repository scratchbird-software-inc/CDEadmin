import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import NativeNavigation from '../../../pgadmin/static/js/cdeadmin_ui/navigation/NativeNavigation';
import LanguageSourceEditor from '../../../pgadmin/static/js/cdeadmin_ui/editors/LanguageSourceEditor';

const node = (id, label, kind, children=[], section=null) => ({id,label,kind,children,section,form_reference:'SR-F-000085'});

test('binds real table children and opens owner sections, with numbered missing destinations', () => {
  const open=jest.fn();
  const design={engine_id:'test',root:node('r','Engine','engine',[
    node('t','<table>','table',[node('i','Indexes','folder',[],'indexes')]),
    node('x','Missing native form','extension'),
  ])};
  render(<NativeNavigation design={design} resources={[{resource_id:'t1',resource_kind:'table',display_name:'orders'}]}
    catalog={{objects:[{resource_kind:'table'}]}} onOpen={open} onOperation={jest.fn()} onRefresh={jest.fn()} />);
  fireEvent.click(screen.getByText('Indexes'));
  expect(open).toHaveBeenCalledWith(expect.objectContaining({resource_id:'t1'}),'indexes','Indexes');
  fireEvent.click(screen.getByText('Missing native form'));
  expect(screen.getAllByLabelText('Form reference').some(e=>e.textContent==='SR-F-000085')).toBe(true);
});

test('validates through the retained language session without executing source', async () => {
  const post=jest.fn().mockResolvedValue({grammar_valid:null,scope:'lexical',diagnostics:[]});
  render(<LanguageSourceEditor language={{language_profile:'postgresql-sql'}} source="SELECT 1" onChange={jest.fn()}
    post={post} ensureSession={async ()=>'s1'} databaseTargetId="db1" onScriptLock={jest.fn()} />);
  fireEvent.click(screen.getByText('Check source'));
  await waitFor(()=>expect(post).toHaveBeenCalledWith({action:'source_validate',session_id:'s1',source:'SELECT 1',database_target_id:'db1'}));
  expect(await screen.findByText(/not certified/)).toBeInTheDocument();
});

test('resumes the same retained plan after an unavailable observation', async () => {
  const plan={plan_id:'p1',state:'ready',revision:0,statements:[{ordinal:1,source:'SELECT 1'}]};
  const post=jest.fn().mockResolvedValueOnce(plan)
    .mockResolvedValueOnce({...plan,state:'waiting',revision:1,occurrence_id:'o1',observation_unavailable:true})
    .mockResolvedValueOnce({...plan,state:'complete',revision:2,occurrence_id:null});
  const lock=jest.fn();
  render(<LanguageSourceEditor language={{language_profile:'postgresql-sql',tooling:{script_framing:true}}}
    source="SELECT 1" onChange={jest.fn()} post={post} ensureSession={async ()=>'s1'} onScriptLock={lock} />);
  fireEvent.click(screen.getByText('Preview script'));
  await waitFor(()=>expect(screen.getByText('Run / resume retained script')).toBeEnabled());
  fireEvent.click(screen.getByText('Run / resume retained script'));
  await screen.findByText(/Observation unavailable/);
  expect(lock).toHaveBeenLastCalledWith(true);
  fireEvent.click(screen.getByText('Run / resume retained script'));
  await waitFor(()=>expect(lock).toHaveBeenLastCalledWith(false));
  expect(post.mock.calls.filter(([p])=>p.action==='native_script_prepare')).toHaveLength(1);
  expect(post.mock.calls[2][0]).toEqual(expect.objectContaining({action:'native_script_advance',plan_id:'p1',revision:1}));
});
