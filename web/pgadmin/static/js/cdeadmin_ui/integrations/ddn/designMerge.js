// Native refresh reconciliation runs in the shared server conversion service.
export async function refreshDesign(post, baseline, draft, incoming) {
  const document = ({format, entry, view, files}) => ({format, entry, view, files});
  let result;
  try {result = await post({action: 'ddn_design_merge', request: {
    baseline: document(baseline), draft: document(draft), incoming: document(incoming),
  }});} catch (error) {
    throw new Error(error.response?.data?.errormsg || error.message || 'Design conversion failed.');
  }
  return {...draft, ...result};
}
