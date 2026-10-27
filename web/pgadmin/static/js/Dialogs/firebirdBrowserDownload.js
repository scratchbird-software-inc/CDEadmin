import {startBrowserFileDownload} from './browserFileDownload';

// Native form navigation gives the browser download manager the response.
// No fetch().blob(), object URL, filesystem picker or complete-file buffering.
export function startFirebirdBrowserDownload(url, payload) {
  return startBrowserFileDownload(url,payload,{action:'firebird_file_download',prefix:'firebird',title:'Firebird file download'});
}
