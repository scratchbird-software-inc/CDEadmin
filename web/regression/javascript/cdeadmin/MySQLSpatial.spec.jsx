import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import Spatial from 'sources/Dialogs/MySQLSpatial';
import {withTheme} from '../fake_theme';
jest.mock('sources/cdeadmin_ui/integrations/ddn',() => ({DDNViewerSurface:() => <div data-testid="native-map" />}));
jest.mock('sources/cdeadmin_ui/integrations/ddn/library',() => ({loadDDNGeoLibraries:jest.fn(async () => ({}))}));
const Component=withTheme(Spatial);
const report={coverage:'bounded independent snapshot page',consistent_snapshot:true,identity:{server_uuid:'native'},rows:[
  {id:'row-0',state:'inspected',srid:'4326',validity:'valid',format:'mysql',raw_hex:'e610000001',raw_bytes:5,
    wkt_srs:'POINT(43 -79)',wkt_xy:'POINT(-79 43)',geojson:{type:'Point',coordinates:[-79,43]},
    map_geometry:{type:'Point',coordinates:[-79,43]},map_status:'native-X/Y'}],srs:{},tiles:'none',map_mode:'native',next_offset:null};
let height;
beforeEach(() => {height=window.innerHeight;window.innerHeight=2200;});
afterEach(() => {window.innerHeight=height;});
async function select(post) {
  fireEvent.change(screen.getByLabelText('Spatial database'),{target:{value:'db'}});
  fireEvent.change(screen.getByLabelText('Spatial table'),{target:{value:'t'}});
  fireEvent.click(screen.getByRole('button',{name:'Observe geometry columns'}));
  await waitFor(() => expect(post).toHaveBeenCalled());
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'Geometry or binary column'}));
  fireEvent.click(await screen.findByRole('option',{name:'g (geometry; SRID unrestricted)'}));
}
function response() {return jest.fn(async payload => payload.action==='mysql_spatial_columns' ? {
  fingerprint:'native-fingerprint',rows:[{COLUMN_NAME:'g',DATA_TYPE:'geometry',SRS_ID:null}],next_offset:null} : report);}

it('requires observed identity and private consent, then shows native axis text and map',async () => {
  const post=response();render(<Component post={post} databaseTargetId="registered" />);
  expect(post).not.toHaveBeenCalled();await select(post);
  expect(screen.getByRole('button',{name:'Inspect native geometry'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow private geometry inspection'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect native geometry'}));
  await screen.findByTestId('native-map');
  expect(post).toHaveBeenCalledWith({action:'mysql_spatial_read',request:expect.objectContaining({database_target_id:'registered',confirmed:true,fingerprint:'native-fingerprint',
    options:{format:'mysql',srid:'0',axis_order:'long-lat',map:'native',limit:25,offset:0,seconds:10}})});
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'Inspect spatial row'}));
  fireEvent.click(await screen.findByRole('option',{name:'row-0: inspected / native-X/Y'}));
  expect(screen.getByLabelText('WKT in native SRS order')).toHaveValue('POINT(43 -79)');
  expect(screen.getByLabelText('WKT X/Y (longitude/latitude for geographic SRS)')).toHaveValue('POINT(-79 43)');
  expect(screen.getByLabelText('Original native bytes (hex)')).toHaveValue('e610000001');
  fireEvent.click(screen.getByRole('button',{name:'Clear private inspection'}));
  expect(screen.queryByTestId('native-map')).toBeNull();expect(screen.queryByLabelText('Original native bytes (hex)')).toBeNull();
});

it('discards a late private geometry reply after target replacement',async () => {
  let finish;const base=response(),post=jest.fn(payload => payload.action==='mysql_spatial_read' ? new Promise(resolve => {finish=resolve;}) : base(payload));
  const mounted=render(<Component post={post} databaseTargetId="first" />);await select(post);
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow private geometry inspection'}));fireEvent.click(screen.getByRole('button',{name:'Inspect native geometry'}));
  mounted.rerender(<Component post={post} databaseTargetId="second" />);await act(async () => {finish(report);});
  expect(screen.queryByTestId('native-map')).toBeNull();expect(screen.getByRole('button',{name:'Inspect native geometry'})).toBeDisabled();
});

it('shows native errors without fabricating an empty successful map',async () => {
  const base=response(),post=jest.fn(payload => payload.action==='mysql_spatial_read' ? Promise.reject({response:{data:{errormsg:'Native read denied (1143)'}}}) : base(payload));
  render(<Component post={post} />);await select(post);fireEvent.click(screen.getByRole('checkbox',{name:'Allow private geometry inspection'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect native geometry'}));await screen.findByText('Native read denied (1143)');
  expect(screen.queryByTestId('native-map')).toBeNull();
});
