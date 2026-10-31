/*
 * Family render gate (design section 8): every populated engine × family form
 * renders in the shared ObjectEditor with its canonical tabs in skeleton order,
 * every field has a label and a typed control, and the SQL tab shows the
 * provider plan. The same test runs for every engine; nothing here names one.
 */
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Theme from 'sources/Theme';
import {ObjectEditor} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {BETA_ENGINES, FAMILIES, loadEngineBundle, loadFamilies, populatedForms} from './familyFixtures';

const CONTROLS = new Set(['text', 'number', 'boolean', 'select', 'multiselect', 'radio', 'password',
  'secret-reference', 'code', 'grid', 'keyvalue', 'privileges', 'reference', 'file']);

beforeEach(() => {
  window.innerHeight = 1200;
});

describe('family skeletons', () => {
  const families = loadFamilies();
  it.each(FAMILIES)('%s skeleton has unique, ordered tabs with a SQL preview where it mutates', (family) => {
    const skeleton = families[family];
    expect(skeleton).toBeDefined();
    const tabs = skeleton.tabs.map((tab) => tab.tab);
    expect(new Set(tabs).size).toBe(tabs.length);
    if(family !== 'server') expect(tabs).toContain('SQL');
  });
});

describe('engine bundles', () => {
  it.each(BETA_ENGINES)('%s resolves against the skeletons', (engine) => {
    const bundle = loadEngineBundle(engine);
    expect(bundle.engine).toBe(engine);
    for(const [family, form] of Object.entries(bundle.forms)) {
      const order = form.family_tabs;
      const positions = form.tabs.map((tab) => order.indexOf(tab.tab));
      expect(positions).toEqual([...positions].sort((a, b) => a - b));
      for(const tab of form.tabs) {
        for(const field of tab.fields) {
          expect(CONTROLS.has(field.control)).toBe(true);
          expect(field.label).toBeTruthy();
          expect(field.label).not.toMatch(/exact native/i);
        }
      }
      if(form.status === 'complete') expect(form.missing_required_tabs).toEqual([]);
      // Engine-object editors are one form per kind (design decision 15).
      expect(family).toBe(form.family === 'engine_object' ?
        `engine_object:${form.resource_kinds[0]}` : form.family);
    }
  });
});

describe('ObjectEditor renders every populated family form', () => {
  const cases = populatedForms();
  it('has forms to test', () => {
    expect(cases.length).toBeGreaterThan(20);
  });

  it.each(cases.map(([engine, family, form, bundle]) => [engine, family, form, bundle]))(
    '%s %s: canonical tabs, typed fields, SQL tab from the provider plan',
    async (engine, family, form) => {
      const plan = jest.fn(async () => ({plan_id: 'p1', plan_digest: 'd1', state: 'ready', execution_available: true,
        command_preview: {statements: [{source: `CREATE ${family.toUpperCase()} test`}]}}));
      const apply = jest.fn(async () => ({provider_result: {ok: true}}));
      render(<Theme><ObjectEditor form={form} mode="create" resourceKind={form.resource_kinds[0]} plan={plan} apply={apply}
        onClose={() => {}} autoPlan={false} /></Theme>);
      const tablist = screen.getByRole('tablist', {name: `${form.family_title} tabs`});
      const rendered = within(tablist).getAllByRole('tab').map((tab) => tab.textContent);
      // Tabs are a subset of the family skeleton, in skeleton order.
      const skeletonOrder = form.family_tabs.map((name) => name === 'Engine' ? (form.engine_tab_title || 'Engine') : name);
      const positions = rendered.map((label) => skeletonOrder.indexOf(label));
      expect(positions.every((position) => position >= 0)).toBe(true);
      expect(positions).toEqual([...positions].sort((a, b) => a - b));
      if(family !== 'server') expect(rendered).toContain('SQL');
      // Every field on every tab renders a labelled, typed control.
      for(const tab of form.tabs) {
        if(!tab.fields.length) continue;
        fireEvent.click(within(tablist).getByRole('tab', {name: tab.title}));
        const panel = screen.getByRole('tabpanel', {name: tab.title});
        for(const field of tab.fields) {
          if(field.modes && !field.modes.includes('create')) continue;
          if(field.visible_when) continue; // conditional fields are covered by descriptor logic tests
          // A tab with sections (Constraints) shows one at a time: open the field's section.
          const sections = within(panel).queryByRole('tablist', {name: `${tab.title} sections`});
          if(sections && field.group) fireEvent.click(within(sections).getByRole('tab', {name: field.group}));
          const control = panel.querySelector(`[data-cdeadmin-qa-key="object-editor.field.${field.field_id}"],` +
            `[data-cdeadmin-qa-key="object-editor.grid.${field.field_id}"],` +
            `[data-cdeadmin-qa-key="object-editor.keyvalue.${field.field_id}"]`);
          expect(control).not.toBeNull();
          expect(panel.textContent).toContain(field.label);
          expect(panel.textContent).not.toMatch(/Unsupported control/);
        }
      }
      if(family === 'server') return;
      // The SQL tab shows the provider plan for a draft that satisfies required fields.
      fireEvent.click(within(tablist).getByRole('tab', {name: 'SQL'}));
      const sqlPanel = screen.getByRole('tabpanel', {name: 'SQL'});
      if(within(sqlPanel).queryByRole('button', {name: 'Preview SQL'})) {
        fireEvent.click(within(sqlPanel).getByRole('button', {name: 'Preview SQL'}));
        await waitFor(() => expect(plan).toHaveBeenCalled());
        await waitFor(() => expect(sqlPanel.textContent).toContain(`CREATE ${family.toUpperCase()} test`));
      } else {
        // Required fields are empty, so the editor explains instead of planning (principle 5).
        expect(sqlPanel.textContent).toMatch(/required fields|Nothing to preview/);
        expect(plan).not.toHaveBeenCalled();
      }
    });
});
