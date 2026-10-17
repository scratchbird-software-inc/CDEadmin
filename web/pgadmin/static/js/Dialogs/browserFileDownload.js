import pgAdmin from 'sources/pgadmin';

// Form navigation streams to the browser download manager without a whole-file
// JavaScript Blob or a filesystem picker.
export function startBrowserFileDownload(url,payload,{action,prefix,title}) {
  const endpoint=new URL(url,window.location.href);
  if(endpoint.origin!==window.location.origin)throw new Error('Invalid download origin.');
  const frame=document.createElement('iframe');
  frame.name=prefix+'-download-'+window.crypto.randomUUID();frame.hidden=true;frame.title=title;
  const form=document.createElement('form');
  form.method='POST';form.action=endpoint.href;form.target=frame.name;form.hidden=true;
  for(const [name,value] of Object.entries({action,csrf_token:pgAdmin.csrf_token,payload:JSON.stringify(payload)})) {
    const input=document.createElement('input');input.type='hidden';input.name=name;input.value=value;form.appendChild(input);
  }
  document.body.append(frame,form);
  try {form.submit();}
  catch(error) {frame.remove();throw error;}
  finally {form.remove();}
  return () => frame.remove();
}
