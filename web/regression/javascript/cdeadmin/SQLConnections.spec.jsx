import {withTheme} from '../fake_theme';
import {useState} from 'react';
import {act, fireEvent, render, screen} from '@testing-library/react';
import SQLConnections, {activateSQLConnection, registerSQLConnection, removeSQLConnections} from '../../../pgadmin/static/js/cdeadmin_ui/editors/SQLConnections';
function Draft() {const [value,setValue]=useState('');return <input aria-label="draft" value={value} onChange={e=>setValue(e.target.value)} />;}
it('shows the complete query-tool layout before any connection is selected', () => {
  const Component = withTheme(SQLConnections); render(<Component />);
  expect(screen.getByRole('button', {name: 'Run'})).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Commit'})).toBeDisabled();
  expect(screen.getByRole('button', {name: 'Rollback'})).toBeDisabled();
  expect(screen.getByRole('tab', {name: 'Data Output'})).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByLabelText('Statement metrics')).toHaveTextContent('Buffered rows: 0');
  fireEvent.click(screen.getByRole('tab', {name: 'Messages'}));
  expect(screen.getByRole('tabpanel', {name: 'Messages'})).toHaveTextContent('No connection selected.');
});

it('switches active connections without unmounting drafts or recreating their sessions', () => {
  Object.defineProperty(window, 'innerHeight', {configurable:true,value:1000});
  activateSQLConnection({id:'firebird-a',label:'Firebird / A',content:<Draft />});
  activateSQLConnection({id:'mysql-b',label:'MySQL / B',content:<Draft />});
  const Component=withTheme(SQLConnections);render(<Component />);
  const inputs=screen.getAllByLabelText('draft');
  fireEvent.change(inputs[1],{target:{value:'uncommitted draft'}});
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'Active connection'}));
  fireEvent.click(screen.getByRole('option',{name:'Firebird / A'}));
  expect(inputs[0]).toBeVisible();expect(inputs[1]).not.toBeVisible();
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'Active connection'}));
  fireEvent.click(screen.getByRole('option',{name:'MySQL / B'}));
  expect(screen.getAllByLabelText('draft')[1]).toBe(inputs[1]);
  expect(inputs[1]).toHaveValue('uncommitted draft');
});

it('lists explorer connections before opening SQL and removes only the disconnected server', () => {
  const open = jest.fn(() => activateSQLConnection({id:'explorer',serverId:7,label:'Explorer database',content:<Draft />}));
  registerSQLConnection({id:'explorer',serverId:7,label:'Explorer database',open});
  const Component=withTheme(SQLConnections);render(<Component />);
  expect(open).not.toHaveBeenCalled();
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'Active connection'}));
  fireEvent.click(screen.getByRole('option',{name:'Explorer database'}));
  expect(open).toHaveBeenCalledTimes(1);
  act(() => removeSQLConnections(7));
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'Active connection'}));
  expect(screen.queryByRole('option',{name:'Explorer database'})).not.toBeInTheDocument();
  expect(screen.getByRole('option',{name:'Firebird / A'})).toBeInTheDocument();
});

it('disconnects one PostgreSQL database without removing its sibling connection', () => {
  registerSQLConnection({id:'pg-a',serverId:18,databaseTargetId:'postgresql-database:10',engine:'PostgreSQL',label:'A'});
  registerSQLConnection({id:'pg-b',serverId:18,databaseTargetId:'postgresql-database:11',engine:'PostgreSQL',label:'B'});
  removeSQLConnections(18, 'postgresql-database:10');
  const Component=withTheme(SQLConnections);render(<Component />);
  fireEvent.mouseDown(screen.getByRole('combobox', {name:'Active connection'}));
  expect(screen.queryByRole('option',{name:'PostgreSQL — A'})).not.toBeInTheDocument();
  expect(screen.getByRole('option',{name:'PostgreSQL — B'})).toBeInTheDocument();
});
