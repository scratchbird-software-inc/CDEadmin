import gettext from 'sources/gettext';

function sharedActionHints() {
  return {
    nav_first: gettext('Go to the first record'),
    nav_prev_page: gettext('Move back one page of records'),
    nav_prev_row: gettext('Go to the preceding record'),
    nav_next_row: gettext('Go to the following record'),
    nav_next_page: gettext('Move forward one page of records'),
    nav_last: gettext('Go to the last record'),
    bookmark_toggle: gettext('Add or remove a bookmark on the current record'),
    bookmark_prev: gettext('Go to the preceding bookmarked record'),
    bookmark_next: gettext('Go to the following bookmarked record'),
    insert_row: gettext('Open an empty form for a new record'),
    duplicate_row: gettext('Start a new record using values from the current record'),
    delete_row: gettext('Stage the current record for deletion'),
    commit: gettext('Commit pending changes to the database'),
    rollback: gettext('Discard uncommitted changes'),
    autocommit: gettext('Toggle automatic commit of changes'),
    export_data: gettext('Choose an export format and which data to include'),
    first_area: gettext('Choose the content in the upper or only display area'),
    second_area: gettext('Choose the content in the lower display area or turn it off'),
    first_presentation: gettext('Choose how rows appear in the upper or only display area'),
    second_presentation: gettext('Choose how rows appear in the lower display area'),
  };
}

export function dataViewerActionHints() {
  return {
    ...sharedActionHints(),
    locate_row: gettext('Scroll the current row into view'),
    jump_row: gettext('Go to a record by its row number'),
    set_null: gettext('Set the selected editable field to SQL NULL'),
    revert_row: gettext('Undo changes to the current row'),
    inspect_staged: gettext('Review the SQL for pending edits in the right drawer'),
    copy: gettext('Copy the selected data to the clipboard'),
    cut: gettext('Copy the selected cell value and clear it'),
    paste: gettext('Paste the clipboard value into the selected cell'),
    copy_special: gettext('Choose how to format selected data for the clipboard'),
    refresh: gettext('Reload rows from the database'),
    sort_loc: gettext('Choose whether the database or the local host sorts rows'),
    quick_find: gettext('Search for matching values in the data'),
    filter_builder: gettext('Build conditions to restrict the rows shown'),
    clear_filters: gettext('Remove active filters and sorting'),
    fetch_limits: gettext('Configure the maximum fetched rows and rows per page'),
    auto_fit: gettext('Resize columns to fit their content'),
    pin_col: gettext('Keep the selected column visible when scrolling horizontally'),
    col_selector: gettext('Choose which columns to show and their order'),
    reset_layout: gettext('Restore the default display settings'),
    import_data: gettext('Load a file into the staged row changes'),
    open_sql_editor: gettext('Open the browse query in the SQL Editor'),
    gen_insert_sql: gettext('Copy generated INSERT statements to the clipboard'),
    gen_update_sql: gettext('Copy generated UPDATE statements to the clipboard'),
  };
}

export function sqlEditorActionHints() {
  return {
    ...sharedActionHints(),
    result_set_menu: gettext('Choose which result set from the script to display'),
    explain: gettext('Request the database execution plan for the statement'),
    prepare_statement: gettext('Inspect the prepared statement and its input and output fields'),
    cancel: gettext('Request cancellation of the running SQL'),
    parameters: gettext('Enter values for the statement parameters'),
    terminator_menu: gettext('Choose the delimiter used to split SQL statements'),
    start_transaction: gettext('Choose options and start a database transaction'),
    prepare_transaction: gettext('Prepare the active transaction for later resolution'),
    snippets_drawer: gettext('Browse SQL snippets in the right drawer'),
    quick_queries: gettext('Browse and open named saved queries'),
    history_drawer: gettext('Browse previous SQL executions in the right drawer'),
    save_any: gettext('Save SQL as a file, a named query, or a snippet'),
    format_sql: gettext('Reformat the SQL text in the editor'),
    bool_menu: gettext('Choose how Boolean result values are displayed'),
    vb_inspector: gettext('Open the Visual Builder controls in the right drawer'),
    limits: gettext('Configure result fetch limits and page size'),
    conn_info: gettext('Inspect the database connection bound to this editor'),
    open_sql_file: gettext('Load SQL text from a file'),
    save_snippet_sel: gettext('Save the selected SQL as a tagged snippet'),
    save_bi_question: gettext('Save the current query as a BI question'),
    export_xlsx_ods: gettext('Export results as an Excel or OpenDocument spreadsheet'),
    export_pdf: gettext('Export results as a PDF report'),
  };
}
