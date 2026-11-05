/////////////////////////////////////////////////////////////
//
// Scratch notebook bar: rendering, commands, context, collapse, keyboard,
// menus, access keys and overflow.
//
//////////////////////////////////////////////////////////////

import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {NotebookBar} from 'sources/scratch_notebookbar';

const button = (id, extra={}) => ({id, label: id[0].toUpperCase() + id.slice(1),
  command: `cmd.${id}`, ...extra});

const MODEL = {
  tabs: [
    {id: 'home', label: 'Home', accessKey: 'H', groups: [
      {id: 'clipboard', label: 'Clipboard', priority: 9, controls: [
        button('cut', {size: 'large'}), button('copy')]},
      {id: 'font', label: 'Font', priority: 1, controls: [
        button('bold', {type: 'toggle'}),
        {id: 'size', type: 'select', label: 'Size', command: 'cmd.size',
          options: [{value: '10', label: '10'}, {value: '12', label: '12'}]},
        {id: 'colour', type: 'color', label: 'Colour', command: 'cmd.colour',
          palette: ['#112233', '#445566']},
      ]},
      {id: 'styles', label: 'Styles', priority: 0, controls: [
        {id: 'gallery', type: 'gallery', label: 'Styles', command: 'cmd.style',
          items: [{id: 'title', label: 'Title'}, {id: 'body', label: 'Body'}]},
      ]},
    ]},
    {id: 'insert', label: 'Insert', accessKey: 'I', groups: [
      {id: 'objects', label: 'Objects', controls: [
        {id: 'shape', type: 'menu', label: 'Shape', command: 'cmd.shape',
          items: [{id: 'square', label: 'Square'},
            {id: 'circle', label: 'Circle', command: 'cmd.circle'}]},
        {id: 'paste', type: 'split', label: 'Paste', command: 'cmd.paste',
          items: [{id: 'plain', label: 'Plain text'}]},
        button('table', {accessKey: 'T'}),
      ]},
    ]},
    {id: 'tabletools', label: 'Table', context: 'table', selectOnContext: true,
      groups: [{id: 'rows', label: 'Rows', controls: [button('row')]}]},
  ],
  quickAccess: [button('save', {shortcut: 'Ctrl+S'})],
};

function renderBar(props={}) {
  const onCommand = jest.fn();
  const view = render(<NotebookBar model={MODEL} onCommand={onCommand}
    label="Commands" {...props} />);
  return {...view, onCommand};
}

const tab = (name) => screen.getByRole('tab', {name});
const panel = () => screen.getByRole('tabpanel');

describe('NotebookBar', () => {
  it('renders tabs, a panel and the quick-access bar', () => {
    renderBar();
    expect(screen.getByRole('tablist', {name: 'Commands'})).toBeInTheDocument();
    expect(screen.getAllByRole('tab').map((item) => item.textContent))
      .toEqual(['Home', 'Insert']);
    expect(tab('Home')).toHaveAttribute('aria-selected', 'true');
    expect(panel()).toHaveAttribute('aria-labelledby', tab('Home').id);
    const quick = screen.getByRole('toolbar', {name: 'Quick access'});
    expect(within(quick).getByRole('button', {name: 'Save'}))
      .toHaveAttribute('title', 'Save (Ctrl+S)');
    expect(document.querySelectorAll('style[data-scratch-notebookbar]')).toHaveLength(1);
  });

  it('selects tabs and runs commands with their details', () => {
    const onSelectTab = jest.fn();
    const {onCommand, rerender} = renderBar({onSelectTab});
    fireEvent.click(within(panel()).getByRole('button', {name: 'Copy'}));
    expect(onCommand).toHaveBeenLastCalledWith('cmd.copy', {});
    const bold = within(panel()).getByRole('button', {name: 'Bold'});
    expect(bold).toHaveAttribute('aria-pressed', 'false');
    fireEvent.click(bold);
    expect(onCommand).toHaveBeenLastCalledWith('cmd.bold', {checked: true});
    rerender(<NotebookBar model={MODEL} onCommand={onCommand} onSelectTab={onSelectTab}
      state={{'cmd.bold': {checked: true}, 'cmd.copy': {enabled: false},
        'cmd.cut': {hidden: true}, 'cmd.size': {value: '12'}}} />);
    expect(within(panel()).getByRole('button', {name: 'Bold'}))
      .toHaveAttribute('aria-pressed', 'true');
    const copy = within(panel()).getByRole('button', {name: 'Copy'});
    expect(copy).toHaveAttribute('aria-disabled', 'true');
    onCommand.mockClear();
    fireEvent.click(copy);
    expect(onCommand).not.toHaveBeenCalled();
    expect(within(panel()).queryByRole('button', {name: 'Cut'})).not.toBeInTheDocument();
    fireEvent.change(within(panel()).getByRole('combobox', {name: 'Size'}),
      {target: {value: '10'}});
    expect(onCommand).toHaveBeenLastCalledWith('cmd.size', {value: '10'});
    fireEvent.click(tab('Insert'));
    expect(onSelectTab).toHaveBeenLastCalledWith('insert');
    expect(tab('Insert')).toHaveAttribute('aria-selected', 'true');
  });

  it('shows a contextual tab while its context is active and then returns', () => {
    const {rerender, onCommand} = renderBar();
    fireEvent.click(tab('Insert'));
    rerender(<NotebookBar model={MODEL} onCommand={onCommand} context="table" />);
    expect(tab('Table')).toHaveAttribute('aria-selected', 'true');
    rerender(<NotebookBar model={MODEL} onCommand={onCommand} context={[]} />);
    expect(screen.queryByRole('tab', {name: 'Table'})).not.toBeInTheDocument();
    expect(tab('Insert')).toHaveAttribute('aria-selected', 'true');
  });

  it('collapses to the tabs and peeks the panel until a command runs', () => {
    const onCollapsedChange = jest.fn();
    const {onCommand} = renderBar({onCollapsedChange});
    fireEvent.doubleClick(tab('Home'));
    expect(onCollapsedChange).toHaveBeenLastCalledWith(true);
    expect(screen.queryByRole('tabpanel')).not.toBeInTheDocument();
    fireEvent.click(tab('Insert'));
    expect(within(panel()).getByRole('button', {name: 'Table'})).toBeInTheDocument();
    fireEvent.click(within(panel()).getByRole('button', {name: 'Table'}));
    expect(onCommand).toHaveBeenLastCalledWith('cmd.table', {});
    expect(screen.queryByRole('tabpanel')).not.toBeInTheDocument();
    fireEvent.keyDown(tab('Insert'), {key: 'F1', ctrlKey: true});
    expect(onCollapsedChange).toHaveBeenLastCalledWith(false);
    expect(panel()).toBeInTheDocument();
  });

  it('moves through tabs and controls with the arrow keys', async () => {
    renderBar();
    act(() => tab('Home').focus());
    fireEvent.keyDown(tab('Home'), {key: 'ArrowRight'});
    expect(tab('Insert')).toHaveFocus();
    fireEvent.keyDown(tab('Insert'), {key: 'Enter'});
    expect(tab('Insert')).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(tab('Insert'), {key: 'ArrowDown'});
    const shape = within(panel()).getByRole('button', {name: 'Shape'});
    await waitFor(() => expect(shape).toHaveFocus());
    expect(shape).toHaveAttribute('tabindex', '0');
    fireEvent.keyDown(shape, {key: 'ArrowRight'});
    expect(within(panel()).getByRole('button', {name: 'Paste'})).toHaveFocus();
    fireEvent.keyDown(document.activeElement, {key: 'ArrowUp'});
    expect(tab('Insert')).toHaveFocus();
  });

  it('mirrors arrow keys right to left', () => {
    renderBar({dir: 'rtl'});
    act(() => tab('Home').focus());
    fireEvent.keyDown(tab('Home'), {key: 'ArrowLeft'});
    expect(tab('Insert')).toHaveFocus();
  });

  it('opens menus and split buttons with the keyboard and mouse', async () => {
    const {onCommand} = renderBar();
    fireEvent.click(tab('Insert'));
    const shape = within(panel()).getByRole('button', {name: 'Shape'});
    fireEvent.click(shape);
    const menu = await screen.findByRole('menu', {name: 'Shape'});
    expect(shape).toHaveAttribute('aria-expanded', 'true');
    const items = within(menu).getAllByRole('menuitem');
    await waitFor(() => expect(items[0]).toHaveFocus());
    fireEvent.keyDown(menu, {key: 'ArrowDown'});
    expect(items[1]).toHaveFocus();
    fireEvent.click(items[1]);
    expect(onCommand).toHaveBeenLastCalledWith('cmd.circle', {item: 'circle'});
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(shape).toHaveFocus();

    fireEvent.click(within(panel()).getByRole('button', {name: 'Paste'}));
    expect(onCommand).toHaveBeenLastCalledWith('cmd.paste', {});
    fireEvent.click(within(panel()).getByRole('button', {name: 'Paste options'}));
    const pasteMenu = await screen.findByRole('menu', {name: 'Paste'});
    fireEvent.keyDown(pasteMenu, {key: 'Escape'});
    expect(screen.queryByRole('menu')).not.toBeInTheDocument();
    expect(within(panel()).getByRole('button', {name: 'Paste options'})).toHaveFocus();
  });

  it('applies colours and gallery items', async () => {
    const {onCommand} = renderBar({state: {'cmd.colour': {value: '#112233'}}});
    fireEvent.click(within(panel()).getByRole('button', {name: 'Colour #112233'}));
    expect(onCommand).toHaveBeenLastCalledWith('cmd.colour', {value: '#112233'});
    fireEvent.click(within(panel()).getByRole('button', {name: 'Colour options'}));
    const palette = await screen.findByRole('menu', {name: 'Colour'});
    fireEvent.click(within(palette).getByRole('menuitemradio', {name: '#445566'}));
    expect(onCommand).toHaveBeenLastCalledWith('cmd.colour', {value: '#445566'});
    fireEvent.click(within(panel()).getByRole('radio', {name: 'Body'}));
    expect(onCommand).toHaveBeenLastCalledWith('cmd.style', {item: 'body'});
  });

  it('shows access-key hints on Alt and activates by typed keys', async () => {
    const {onCommand} = renderBar();
    const bar = screen.getByRole('region', {name: 'Commands'});
    fireEvent.keyDown(window, {key: 'Alt'});
    fireEvent.keyUp(window, {key: 'Alt'});
    expect(bar).toHaveAttribute('data-snb-access-keys', '1');
    expect(within(tab('Insert')).getByText('I')).toBeInTheDocument();
    expect(within(tab('Home')).getByText('H')).toBeInTheDocument();
    fireEvent.keyDown(bar, {key: 'i'});
    expect(tab('Insert')).toHaveAttribute('aria-selected', 'true');
    expect(bar).toHaveAttribute('data-snb-access-keys', '2');
    expect(within(within(panel()).getByRole('button', {name: 'Table'}))
      .getByText('T')).toBeInTheDocument();
    fireEvent.keyDown(bar, {key: 'Escape'});
    expect(bar).toHaveAttribute('data-snb-access-keys', '1');
    fireEvent.keyDown(bar, {key: 'i'});
    fireEvent.keyDown(bar, {key: 't'});
    expect(onCommand).toHaveBeenLastCalledWith('cmd.table', {});
    expect(bar).not.toHaveAttribute('data-snb-access-keys');
  });

  it('ignores Alt used with another key', () => {
    renderBar();
    fireEvent.keyDown(window, {key: 'Alt'});
    fireEvent.keyDown(window, {key: 'Shift', altKey: true});
    fireEvent.keyUp(window, {key: 'Alt'});
    expect(screen.getByRole('region', {name: 'Commands'}))
      .not.toHaveAttribute('data-snb-access-keys');
  });

  it.each([
    ['a click or drag', (target) => fireEvent.pointerDown(target, {altKey: true})],
    ['a mouse press', (target) => fireEvent.mouseDown(target, {altKey: true})],
    ['the wheel', (target) => fireEvent.wheel(target, {altKey: true})],
    ['leaving the window', () => fireEvent.blur(window)],
  ])('ignores Alt held during %s', (_name, interrupt) => {
    renderBar();
    const editor = document.createElement('div');
    document.body.appendChild(editor);
    fireEvent.keyDown(window, {key: 'Alt'});
    interrupt(editor);
    fireEvent.keyUp(window, {key: 'Alt'});
    expect(screen.getByRole('region', {name: 'Commands'}))
      .not.toHaveAttribute('data-snb-access-keys');
    editor.remove();
  });

  describe('overflow', () => {
    let resize;
    let widthDescriptor;
    beforeEach(() => {
      global.ResizeObserver = class {
        constructor(callback) { resize = callback; }
        observe() {}
        disconnect() {}
      };
      widthDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype,
        'offsetWidth');
      Object.defineProperty(HTMLElement.prototype, 'offsetWidth', {
        configurable: true,
        get() { return this.dataset?.snbGroup ? 200 : 0; },
      });
    });
    afterEach(() => {
      delete global.ResizeObserver;
      if(widthDescriptor) {
        Object.defineProperty(HTMLElement.prototype, 'offsetWidth', widthDescriptor);
      }
    });

    it('folds low-priority groups into More and unfolds when space returns', async () => {
      const {onCommand} = renderBar();
      act(() => resize([{contentRect: {width: 450}}]));
      const more = await within(panel()).findByRole('button', {name: 'More'});
      expect(within(panel()).queryByRole('group', {name: 'Styles'})).not.toBeInTheDocument();
      expect(within(panel()).getByRole('group', {name: 'Clipboard'})).toBeInTheDocument();
      fireEvent.click(more);
      const popup = await screen.findByRole('dialog', {name: 'More commands'});
      fireEvent.click(within(popup).getByRole('radio', {name: 'Title'}));
      expect(onCommand).toHaveBeenLastCalledWith('cmd.style', {item: 'title'});
      act(() => resize([{contentRect: {width: 900}}]));
      await waitFor(() => expect(within(panel()).queryByRole('button', {name: 'More'}))
        .not.toBeInTheDocument());
      expect(within(panel()).getByRole('group', {name: 'Styles'})).toBeInTheDocument();
    });
  });
});
