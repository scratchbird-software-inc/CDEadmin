// Data-only DDN publications; identifiers are adapter-owned, values are quoted.
const quoted = (value) => JSON.stringify(String(value ?? 'Unavailable').trim());

export function dashboardPanelFiles(panels, title, moduleName) {
  const records = panels.flatMap((panel) => panel.rows.map((row, index) =>
    `record ${panel.id}_${index} ${quoted(row[0])} { x_record: { ` +
    `value: ${quoted(row[1])}, unit: ${quoted(row[2] ?? '')}, ` +
    `rate: ${quoted(row[3] ?? '')} }; }`)).join('\n');
  const views = panels.map((panel) => `view ${panel.id} ${quoted(panel.title)} {
    data: [@observations];
    projection { kind: table; profile: "table.records@1";
      records: [${panel.rows.map((_, index) => `@observations.${panel.id}_${index}`).join(', ')}];
      columns: [{key: "name", label: "Measure"}, {key: "x_record.value", label: "Value"},
        {key: "x_record.unit", label: "Unit / meaning"}, {key: "x_record.rate", label: "Per second"}];
    }
    publication { size: content; fit: none; }
  }`).join('\n');
  return {'dashboard.ddn': `ddn "0.5"; module ${quoted(moduleName)};
    data observations { ${records} }
    ${views}
    view dashboard ${quoted(title)} {
      data: [@observations];
      projection { kind: panels; profile: "panels.composed@1"; columns: 2;
        panels: [${panels.map((panel, index) => `{id: ${quoted(panel.id)}, title: ${quoted(panel.title)}, row: ${Math.floor(index / 2)}, column: ${index % 2}, view: @${panel.id}}`).join(', ')}];
      }
      publication { size: content; fit: none; }
    }`};
}
