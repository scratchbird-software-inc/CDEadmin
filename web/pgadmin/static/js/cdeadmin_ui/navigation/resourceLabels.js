// Labels describe the native target; resource IDs remain selection authority.
export function administrationResourceLabel(resource) {
  const native = resource.extensions?.postgresql?.native;
  if (typeof native?.sql_identity === 'string' && native.sql_identity) {
    return native.sql_identity;
  }
  if (native?.schema && native?.name) {
    const quote = value => '"' + String(value).replaceAll('"', '""') + '"';
    if (resource.resource_kind === 'operator' && native.right_type) {
      return `${quote(native.schema)}.${native.name} (${native.left_type || 'NONE'}, ${native.right_type})`;
    }
    const name = `${quote(native.schema)}.${quote(native.name)}`;
    return typeof native.identity_arguments === 'string' ?
      `${name} (${native.identity_arguments || '*'})` : name;
  }
  return resource.display_name;
}
