"""Read-only inspector checks on the owned seeded Firebird fixture."""

from types import SimpleNamespace

from selenium.webdriver.common.by import By

from tools.cdeadmin_firebird_admin_mapping_gate import (
    _create_client, _resources, _route_arguments,
)
from tools.cdeadmin_firebird_seeded_transaction_gate import _load_profile
from tools.cdeadmin_ui_evidence import expand, named_tree_item


CASES = (
    ('Tables', 'table', 'CUSTOMERS'),
    ('Tables', 'table', 'ASSETS'),
    ('Views', 'view', 'OPEN_WORK_ORDERS'),
    ('Sequences', 'sequence', 'INSPECTION_NUMBER'),
)


def native_expectations(profiles):
    import firebird.driver as driver
    route = _load_profile(profiles)
    password = route.pop('password')
    _create_client(SimpleNamespace(acquire_secret=None))
    connection = driver.connect(password=password,
                                **_route_arguments(route, driver))
    try:
        resources = _resources(connection, {'route': route})
        result = {}
        for _group, kind, name in CASES:
            resource = next(item for item in resources if
                            item['resource_kind'] == kind and
                            item['display_name'] == name)
            ddl = resource['native'].get('ddl')
            if not isinstance(ddl, str) or not ddl.strip():
                raise RuntimeError(f'Native DDL is absent for {name}')
            columns = []
            if kind in ('table', 'view'):
                cursor = connection.cursor()
                cursor.execute(
                    'SELECT TRIM(RDB$FIELD_NAME) FROM RDB$RELATION_FIELDS '
                    'WHERE RDB$RELATION_NAME = ? ORDER BY RDB$FIELD_POSITION',
                    (name,))
                columns = [row[0] for row in cursor.fetchall()]
                cursor.close()
                if not columns:
                    raise RuntimeError(f'Native columns are absent for {name}')
            result[name] = {'ddl': ddl, 'columns': columns}
        return result
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def verify(driver, wait, options, capture):
    expected = native_expectations(options.profiles)
    print('Inspector database state:', driver.execute_async_script("""
      const done = arguments[arguments.length - 1];
      const tree = window.pgAdmin.Browser.tree;
      const item = tree.selected();
      const data = tree.itemData(item);
      const app = window.pgAdmin;
      const headers = {[app.csrf_token_header]: app.csrf_token};
      fetch(data.children_url, {headers}).then(r => r.json())
      .then(body => done({
        type: data._type, childCount: item.children?.length,
        groups: body.data?.map(value => value.label), error: body.errormsg
      })).catch(e => done({error: String(e)}));
    """), flush=True)
    collapsed = driver.find_elements(
        By.CSS_SELECTOR,
        f'button[aria-label="Collapse {options.database}"]')
    if collapsed:
        collapsed[-1].click()
    expand(wait, options.database)
    capture('object-database-expanded')
    results = []

    def inspector():
        return driver.find_element(
            By.CSS_SELECTOR, 'aside[aria-label="Inspector"]')

    def section(label, section_id):
        control = wait.until(lambda _browser: next(iter(
            inspector().find_elements(By.CSS_SELECTOR, '[role="combobox"]')
        ), None))
        control.click()
        try:
            item = wait.until(lambda browser: next((
                option for option in browser.find_elements(
                    By.CSS_SELECTOR, '[role="option"]')
                if option.is_displayed() and
                ' '.join(option.text.split()) == label), None))
        except Exception:
            capture('object-section-selection-failed')
            print('Inspector section choices:', [
                option.text for option in driver.find_elements(
                    By.CSS_SELECTOR, '[role="option"]')
                if option.is_displayed()], flush=True)
            raise
        item.click()
        return wait.until(lambda _browser: next(iter(
            inspector().find_elements(
                By.CSS_SELECTOR,
                f'[aria-label="{section_id} object section"]')
        ), None))

    for group, kind, name in CASES:
        reveal_tree_item(driver, wait, group)
        expand(wait, group)
        reveal_tree_item(driver, wait, name).click()
        wait.until(lambda _browser: name in inspector().text and
                   not inspector().find_elements(
                       By.CSS_SELECTOR,
                       '[aria-label="Loading object properties"]'))
        panel = section('Creation statement (DDL)', 'ddl')
        wait.until(lambda _browser:
                   panel.get_attribute('textContent') == expected[name]['ddl'])
        capture(f'object-{name}-ddl')
        if expected[name]['columns']:
            panel = section('Columns', 'columns')
            wait.until(lambda _browser: all(
                column in panel.text for column in expected[name]['columns']))
            capture(f'object-{name}-columns')
        results.append({'name': name, 'kind': kind,
                        'exact_provider_ddl_rendered': True,
                        'native_column_names': expected[name]['columns']})
    return results


def reveal_tree_item(driver, wait, label):
    """Scroll the virtual navigator so offscreen rows can be mounted."""
    scroll_script = """
      const root = document.querySelector('[role="tree"]');
      const scroll = root && [root, ...root.querySelectorAll('*')].find(
        node => node.scrollHeight > node.clientHeight &&
          /auto|scroll/.test(getComputedStyle(node).overflowY));
      if (scroll) scroll.scrollTop = arguments[0] === 'reset' ? 0 :
        scroll.scrollTop + Math.max(40, scroll.clientHeight * .65);
    """
    driver.execute_script(scroll_script, 'reset')

    def find(browser):
        item = named_tree_item(browser, label)
        if item:
            browser.execute_script(
                'arguments[0].scrollIntoView({block:"nearest",'
                'inline:"nearest"})', item)
            return item
        browser.execute_script(scroll_script, 'next')
        return None

    return wait.until(find)
