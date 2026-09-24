/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////



import { act, fireEvent, render, waitFor } from '@testing-library/react';
import ObjectBreadcrumbs from '../../../pgadmin/static/js/components/ObjectBreadcrumbs';
import pgAdmin from '../fake_pgadmin';
import { withBrowser } from '../genericFunctions';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import { TreeFake } from '../tree/tree_fake';

describe('ObjectBreadcrumbs', ()=>{

  beforeAll(()=>{
    jest.spyOn(usePreferences.getState(), 'getPreferencesForModule').mockReturnValue({
      breadcrumbs_enable: true,
      breadcrumbs_show_comment: true,
    });
    pgAdmin.Browser.tree = new TreeFake(pgAdmin.Browser);
  });

  it('not hovered', ()=>{
    let ThemedObjectBreadcrumbs = withBrowser(ObjectBreadcrumbs);
    let ctrl = render(<ThemedObjectBreadcrumbs />);
    expect(ctrl.container).toBeEmptyDOMElement();
  });

  it.each(['Tab', 'End', 'Escape', 'focusin'])(
    'dismisses hover information on %s without consuming navigation', async (key)=>{
      const ThemedObjectBreadcrumbs = withBrowser(ObjectBreadcrumbs);
      const ctrl = render(<ThemedObjectBreadcrumbs />);
      const hover = () => act(() => pgAdmin.Browser.Events.trigger(
        'pgadmin-browser:tree:hovered', {_metadata: {data: {}}}, {_type: 'object'}));
      hover();
      await waitFor(() => expect(ctrl.container).not.toBeEmptyDOMElement());
      const event = key === 'focusin' ? new Event('focusin', {bubbles: true}) :
        new KeyboardEvent('keydown', {key, bubbles: true, cancelable: true});
      fireEvent(document, event);
      expect(event.defaultPrevented).toBe(false);
      await waitFor(() => expect(ctrl.container).toBeEmptyDOMElement());
      hover();
      await waitFor(() => expect(ctrl.container).not.toBeEmptyDOMElement());
    });

  it('removes document handlers on unmount', () => {
    const add = jest.spyOn(document, 'addEventListener');
    const remove = jest.spyOn(document, 'removeEventListener');
    const ThemedObjectBreadcrumbs = withBrowser(ObjectBreadcrumbs);
    const ctrl = render(<ThemedObjectBreadcrumbs />);
    const registered = add.mock.calls.filter(([name, , capture]) =>
      ['keydown', 'focusin'].includes(name) && capture === true);
    ctrl.unmount();
    expect(registered).toHaveLength(2);
    registered.forEach((args) => expect(remove).toHaveBeenCalledWith(...args));
    add.mockRestore();
    remove.mockRestore();
  });

  it('hovered object with comment', async ()=>{
    let ThemedObjectBreadcrumbs = withBrowser(ObjectBreadcrumbs);
    let ctrl = render(<ThemedObjectBreadcrumbs />);
    pgAdmin.Browser.Events.trigger('pgadmin-browser:tree:hovered', {
      _metadata: {
        data: {
          description: 'some description'
        }
      },
    }, {
      _type: 'object',
    });

    await waitFor(()=>{
      expect(ctrl.container).not.toBeEmptyDOMElement();
      expect(ctrl.container.querySelector('[data-label="AccountTreeIcon"]')).toBeInTheDocument();
      expect(ctrl.container.querySelector('[data-label="CommentIcon"]')).toBeInTheDocument();
    }, {timeout: 500});
  });

  it('hovered object with no comment', async ()=>{
    let ThemedObjectBreadcrumbs = withBrowser(ObjectBreadcrumbs);
    let ctrl = render(<ThemedObjectBreadcrumbs />);

    pgAdmin.Browser.Events.trigger('pgadmin-browser:tree:hovered', {
      _metadata: {
        data: {}
      },
    }, {
      _type: 'object',
    });

    await waitFor(()=>{
      expect(ctrl.container).not.toBeEmptyDOMElement();
      expect(ctrl.container.querySelector('[data-label="AccountTreeIcon"]')).toBeInTheDocument();
      expect(ctrl.container.querySelector('[data-label="CommentIcon"]')).toBeNull();
    }, {timeout: 500});
  });
});
