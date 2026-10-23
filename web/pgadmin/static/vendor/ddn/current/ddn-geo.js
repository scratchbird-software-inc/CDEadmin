/*! DDN 0.8.0 · GPL-2.0-or-later · modular runtime bundle: ddn-geo — Optional geographic module: map projections, GeoJSON ingestion, choropleth/symbol/outline rendering. Registers the "geo" kind (optional: visible placeholder when absent). */
(function () {
  'use strict';

  var h=typeof globalThis!=='undefined'?globalThis:this;if(!h.DDNLive)throw new Error('ddn-geo requires ddn-core.js to be loaded first');if(!h.DDNRender&&!h.__DDN_MODULE_REGISTRY__?.namespaces?.DDNRender)throw new Error('ddn-geo requires ddn-graph.js to be loaded first');if(h.DDNLive.VERSION!=="0.8.0")throw new Error('A different DDNLive runtime is already loaded. Load exactly one version.');if(h.DDNGeo)return;

  var pkg = {
    "version": "0.8.0"}
  ;

  /* SPDX-License-Identifier: GPL-2.0-or-later
   * Explicit cross-bundle module registry (B1-019, D6). One store per realm,
   * shared through globalThis so independently loaded runtime bundles (script
   * tags, CJS require, ESM import, vm contexts) find each other's namespaces.
   * Runtime modules never read host.* globals; bundle entries publish the
   * documented browser globals (DDNLive, DDNRender, …) from these namespaces.
   */
  const host$1=typeof globalThis==='object'&&globalThis?globalThis:{};
  const store=host$1.__DDN_MODULE_REGISTRY__||(host$1.__DDN_MODULE_REGISTRY__={namespaces:Object.create(null)});
  /* Register a module namespace. First publish wins: re-evaluating a bundle
   * (double load) never swaps instances underneath its siblings. Returns the
   * namespace other modules should use. */
  function publishNamespace(name,ns){
   const current=store.namespaces[name];
   if(current)return current;
   store.namespaces[name]=ns;
   return ns;
  }
  /* Required sibling namespace, resolved at module evaluation time. */
  function namespace(name){
   const ns=store.namespaces[name];
   if(!ns)throw new Error('DDN runtime namespace '+name+' is not loaded; load its bundle first.');
   return ns;
  }
  /* Optional sibling namespace for lazy cross-bundle composition (e.g. quality
   * renderers used by projections only when ddn-quality.js is present). */
  function optionalNamespace(name){
   return store.namespaces[name]||null;
  }

  /* SPDX-License-Identifier: GPL-2.0-or-later. Optional geographic module (B1-025):
   * pure-math projections (mercator, equirectangular, albers, equal-earth),
   * GeoJSON ingestion (Feature/FeatureCollection; Polygon/MultiPolygon/Point/
   * MultiPoint), and choropleth / symbol-map / outline rendering with record
   * provenance. Loaded only on demand; the engine renders a visible placeholder
   * plus a coded DDN-E010 diagnostic when this bundle is missing. */
  const D=namespace('DDN');
  const Data=namespace('DDNProjectionData');
  const R=namespace('DDNRender');
  const Text=namespace('DDNText');
  const Palette=namespace('DDNPalette');
  const esc=R.esc,f=n=>Number(n.toFixed(3)),q=D.quantity,clone=x=>JSON.parse(JSON.stringify(x));
  const rad=d=>d*Math.PI/180;

  /* ---------------------------------------------------------------- raw math
   * Each projection maps [lonRad, latRad] to projected units (y grows upwards);
   * fitting to the view box happens once per render in fitProjection. */
  const MERCATOR_MAX=85.051129;
  const projections={
   cartesian:(x,y)=>[x,y],
   mercator(lon,lat){
    const phi=Math.max(rad(-MERCATOR_MAX),Math.min(rad(MERCATOR_MAX),lat));
    return [lon,Math.log(Math.tan(Math.PI/4+phi/2))];
   },
   equirectangular:(lon,lat)=>[lon,lat],
   albers(lon,lat){ // Albers equal-area conic, standard parallels 29.5°/45.5°, origin at (0,0)
    const p1=rad(29.5),p2=rad(45.5),n=(Math.sin(p1)+Math.sin(p2))/2,C=Math.cos(p1)**2+2*n*Math.sin(p1);
    const rho=Math.sqrt(Math.max(0,C-2*n*Math.sin(lat)))/n,rho0=Math.sqrt(C)/n,th=n*lon;
    return [rho*Math.sin(th),rho0-rho*Math.cos(th)];
   },
   equalEarth(lon,lat){ // Šavrič et al. Equal Earth polynomial
    const A1=1.340264,A2=-0.081106,A3=0.000893,A4=0.003796,th=Math.asin(Math.sqrt(3)/2*Math.sin(lat)),t2=th*th;
    return [2*Math.sqrt(3)*lon*Math.cos(th)/(3*(A1+3*A2*t2+7*A3*t2*t2*t2+9*A4*t2*t2*t2*t2)),th*(A1+A2*t2+A3*t2*t2*t2+A4*t2*t2*t2*t2)];
   },
  };
  const METHODS=Object.keys(projections);

  /* ------------------------------------------------------------- GeoJSON in */
  function ingest(input,ErrorClass=D.DDNError,cartesian=false){
   const fail=(code,msg)=>{throw new ErrorClass(code,msg);};
   let doc=input;
   if(typeof doc==='string'){try{doc=JSON.parse(doc);}catch{fail('DDN-PJ144','Geography is not valid JSON');}}
   if(!doc||typeof doc!=='object')fail('DDN-PJ144','Geography must be a GeoJSON object');
   const raw=doc.type==='FeatureCollection'?doc.features:doc.type==='Feature'?[doc]:[{type:'Feature',properties:{},geometry:doc}];
   if(!Array.isArray(raw))fail('DDN-PJ144','GeoJSON FeatureCollection needs a features array');
   let pointCount=0;
   const expanded=[];
   const expand=(ft,depth=0)=>{
    if(depth>32||expanded.length>=500)fail('DDN-PJ147','Geometry exceeds 32 collection levels or 500 features');
    if(ft?.geometry?.type==='GeometryCollection'){
     if(!Array.isArray(ft.geometry.geometries))fail('DDN-PJ144','GeometryCollection needs geometries');
     ft.geometry.geometries.forEach((geometry,i)=>expand({...ft,id:String(ft.id??'collection')+'/'+i,geometry},depth+1));
    }else expanded.push(ft);
   };
   raw.forEach(ft=>expand(ft));
   const features=expanded.map((ft,i)=>{
    if(!ft||ft.type!=='Feature'||!ft.geometry)fail('DDN-PJ144','GeoJSON entry '+(i+1)+' is not a Feature with geometry');
    const g=ft.geometry;
    if(!['Polygon','MultiPolygon','Point','MultiPoint','LineString','MultiLineString'].includes(g.type))fail('DDN-PJ147','Unsupported GeoJSON geometry "'+g.type+'"; ddn-geo renders points, lines, polygons and collections');
    const check=(pt)=>{if(!Array.isArray(pt)||pt.length<2||!Number.isFinite(pt[0])||!Number.isFinite(pt[1]))fail('DDN-PJ146','GeoJSON coordinates must be finite [lon, lat] pairs');if(!cartesian&&(Math.abs(pt[0])>360||Math.abs(pt[1])>90))fail('DDN-PJ146','GeoJSON coordinate outside longitude/latitude range: ['+pt[0]+', '+pt[1]+']');};
    const walk=(c,depth=0)=>{if(!Array.isArray(c)||depth>32)fail('DDN-PJ144','Invalid or excessively nested coordinates');if(typeof c[0]==='number'){if(++pointCount>10000)fail('DDN-PJ147','Geography exceeds 10000 positions');check(c);return;}for(const x of c)walk(x,depth+1);};
    walk(g.coordinates);
    return {id:ft.id!==undefined?String(ft.id):undefined,name:ft.properties?.name??ft.properties?.NAME??'',properties:ft.properties||{},geometry:clone(g)};
   });
   return {type:'FeatureCollection',features};
  }

  /* -------------------------------------------------------- path generation */
  /* Longitude jumps over 180° mean the segment crosses the antimeridian; the
   * 110m asset is cut there, so breaking the path (M) keeps shapes streak-free. */
  function geoPath(geometry,project,{cartesian=false}={}){
   const seg=(a,b)=>!cartesian&&Math.abs(a[0]-b[0])>180;
   const ring=(pts,closed=true)=>{let d='';for(let i=0;i<pts.length;i++){const prev=i?pts[i-1]:null;d+=(i===0||seg(prev,pts[i])?'M':'L')+f(project(pts[i])[0])+' '+f(project(pts[i])[1]);}return d+(closed?'Z':'');};
   if(geometry.type==='LineString')return ring(geometry.coordinates,false);
   if(geometry.type==='MultiLineString')return geometry.coordinates.map(pts=>ring(pts,false)).join('');
   if(geometry.type==='Polygon')return geometry.coordinates.map(pts=>ring(pts)).join('');
   if(geometry.type==='MultiPolygon')return geometry.coordinates.map(poly=>poly.map(pts=>ring(pts)).join('')).join('');
   throw new D.DDNError('DDN-PJ147','geoPath renders Polygon and MultiPolygon geometry; "'+geometry.type+'" is a point type');
  }
  function pointsOf(geometry){
   if(geometry.type==='Point')return [geometry.coordinates];
   if(geometry.type==='MultiPoint')return geometry.coordinates;
   return [];
  }

  /* --------------------------------------------------- host geography store */
  const GEOGRAPHIES=new Map();
  function registerGeography(name,geojson){
   if(typeof name!=='string'||!name)throw new D.DDNError('DDN-PJ144','registerGeography needs a name and a GeoJSON document');
   GEOGRAPHIES.set(name,ingest(geojson));
  }
  function resolveGeography(p,ir){
   const src=p.geography;
   if(src===undefined)throw new D.DDNError('DDN-PJ144','Geo projection needs a geography: a registered name/URL or an inline @record holding GeoJSON');
   if(typeof src==='string'){
    const hit=GEOGRAPHIES.get(src);
    if(!hit)throw new D.DDNError('DDN-PJ144','Geography "'+src+'" is not registered in this host; call DDNGeo.registerGeography(name, geojson) first (the CLI pre-registers assets/geo/world-110m.json) or bind an inline @record');
    return hit;
   }
   const id=src&&src.$ref;
   const rec=id!==undefined&&ir.elements.find(n=>n.id===id);
   if(!rec)throw new D.DDNError('DDN-PJ144','Geography reference is outside the view data scope');
   return ingest(rec.properties.x_record??rec.properties.x_geojson,D.DDNError,p.method==='cartesian');
  }

  /* ------------------------------------------------------------------ render */
  const fmtNumber=n=>n!==0&&(Math.abs(n)>=1e9||Math.abs(n)<.01)?n.toExponential(3):new Intl.NumberFormat('en',{maximumFractionDigits:3}).format(n);
  const mix=(a,b,t)=>'#'+a.match(/[a-f0-9]{2}/gi).map((v,i)=>Math.round(parseInt(v,16)+(parseInt(b.match(/[a-f0-9]{2}/gi)[i],16)-parseInt(v,16))*t).toString(16).padStart(2,'0')).join('');
  const ramp=t=>mix('#E5F0FB','#225784',Math.max(0,Math.min(1,t)));

  function planGeo(ir){
   const p=ir.view.profiles.projection,byId=new Map(ir.elements.map(n=>[n.id,n])),shown=new Set(ir.view.selected);
   const fail=(code,msg,n)=>{throw new D.DDNError(code,msg,n?.source?.file||ir.view.source?.file,n?.source?.start||ir.view.source?.start);};
   const method=p.method===undefined?'mercator':p.method;
   if(!METHODS.includes(method))fail('DDN-PJ143','Unknown geo method "'+method+'"; use '+METHODS.join(', '));
   const mark=p.mark===undefined?({'geo.choropleth@1':'choropleth','geo.symbols@1':'symbol','geo.outline@1':'outline'})[p.profile]||'outline':p.mark;
   if(!['choropleth','symbol','outline'].includes(mark))fail('DDN-PJ143','Unknown geo mark "'+mark+'"; use choropleth, symbol or outline');
   const graticule=p.graticule===undefined?false:p.graticule;
   if(typeof graticule!=='boolean')fail('DDN-PJ143','graticule must be a boolean');
   const records=(p.records||[]).map(x=>{const id=typeof x==='string'?x:x?.$ref,n=byId.get(id);if(!n||!shown.has(n.id))fail('DDN-PJ007','Projection reference is outside its data scope: '+id);return n;});
   if(mark!=='outline'&&!records.length)fail('DDN-PJ009','Geo '+mark+' needs 1..500 explicit record references');
   const value=(n,key,code,label)=>{const v=Data.get(n,key);if(typeof v!=='number'||!Number.isFinite(v))fail(code,label+' must supply a finite number ('+key+')',n);return v;};
   const plan={kind:'geo',profile:p.profile,method,mark,graticule,records,unit:p.unit||'',sourceIds:records.map(n=>n.id)};
   if(mark==='choropleth'){
    if(typeof p.x!=='string'||typeof p.value!=='string')fail('DDN-PJ145','Choropleth binds x (region join key) and value (numeric measure)');
    const seen=new Set();
    plan.rows=records.map(n=>{
     const key=Data.get(n,p.x);if(typeof key!=='string'&&typeof key!=='number')fail('DDN-PJ145','Choropleth join key must be a scalar ('+p.x+')',n);
     const k=String(key);if(seen.has(k))fail('DDN-PJ148','Duplicate choropleth join key "'+k+'"',n);seen.add(k);
     return {node:n,key:k,value:value(n,p.value,'DDN-PJ145','Choropleth value')};
    });
   }
   if(mark==='symbol'){
    if(typeof p.x!=='string'||typeof p.y!=='string')fail('DDN-PJ146','Symbol map binds x (longitude) and y (latitude)');
    plan.dots=records.map(n=>{
     const lon=value(n,p.x,'DDN-PJ146','Symbol longitude'),lat=value(n,p.y,'DDN-PJ146','Symbol latitude');
     if(Math.abs(lon)>180||Math.abs(lat)>90)fail('DDN-PJ146','Symbol coordinate outside lon ±180 / lat ±90: ['+lon+', '+lat+']',n);
     const sz=p.size===undefined?undefined:value(n,p.size,'DDN-PJ146','Symbol size');
     return {node:n,lon,lat,size:sz};
    });
   }
   return plan;
  }

  /* Fit projected coordinates into the drawing box, preserving aspect ratio.
   * clamp [latMin, latMax] keeps conic fits usable on whole-world data: content
   * outside the clamp still renders (clipped to the drawing box) but does not
   * stretch the fit — a world albers is otherwise dominated by the pole arc. */
  function fitProjection(method,geography,dots,W,H,pad,clamp=[-90,90]){
   const raw=(lon,lat)=>method==='cartesian'?[lon,lat]:projections[method](rad(lon),rad(lat));
   let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
   const visit=pt=>{if(method!=='cartesian'&&(pt[1]<clamp[0]||pt[1]>clamp[1]))return;const [x,y]=raw(pt[0],pt[1]);x0=Math.min(x0,x);y0=Math.min(y0,y);x1=Math.max(x1,x);y1=Math.max(y1,y);};
   const walk=c=>{if(typeof c[0]==='number'){visit(c);return;}for(const x of c)walk(x);};
   for(const ft of geography.features)walk(ft.geometry.coordinates);
   for(const d of dots||[])visit([d.lon,d.lat]);
   if(!Number.isFinite(x0)){x0=-Math.PI;x1=Math.PI;y0=-Math.PI/2;y1=Math.PI/2;}
   const unit=method==='cartesian'?Math.max(Math.abs(x0),Math.abs(x1),Math.abs(y0),Math.abs(y1),1):1;
   x0/=unit;x1/=unit;y0/=unit;y1/=unit;
   const scale=Math.min((W-2*pad)/(x1-x0||1e-9),(H-2*pad)/(y1-y0||1e-9));
   const ox=(W-scale*(x1-x0))/2,oy=(H-scale*(y1-y0))/2;
   return pt=>{const [x,y]=raw(pt[0],pt[1]);return [ox+(x/unit-x0)*scale,H-(oy+(y/unit-y0)*scale)];};
  }
  const LAT_CLAMP={mercator:[-MERCATOR_MAX,MERCATOR_MAX],albers:[-60,85]};

  function render(ir,reg,glyphs='',options={}){
   const p=ir.view.profiles,pr=p.projection,plan=planGeo(ir),geography=resolveGeography(pr,ir);
   if(options.layoutState)throw new D.DDNError('DDN-PJ051','Retained graph positions cannot override data-bound projection coordinates');
   const t=Palette.themes[p.style.theme],s=q(p.style.font_size,16)/16,stats=Text.stats(),marks=[],diagnostics=[...ir.diagnostics],S=24*s;
   let body='',W=q(pr.width,1050),H=q(pr.height,620*s),smallest=11*s;
   const text=(x,y,value,size=13,weight=400,anchor='start')=>{const txt=String(value??'');Text.measure(txt,size*s,p.style.font,weight);smallest=Math.min(smallest,size*s);return `<text x="${f(x)}" y="${f(y)}" font-size="${size*s}" fill="${t.ink}" font-weight="${weight}" text-anchor="${anchor}">${esc(txt)}</text>`;};
   const lines=(ls,x,y,size=13,weight=400,anchor='start')=>ls.map((v,i)=>text(x,y+i*(size+6)*s,v,size,weight,anchor)).join('');
   const wrap=(str,w,size=13,weight=400)=>Text.wrap(str,w,size*s,p.style.font,weight);
   const line=(x,y,xx,yy,colour=t.rule,width=1,dash='')=>`<path d="M${f(x)} ${f(y)}L${f(xx)} ${f(yy)}" stroke="${colour}" stroke-width="${width}" fill="none"${dash?` stroke-dasharray="${dash}"`:''}/>`;
   const rect=(x,y,w,h,fill=t.surface,stroke=t.rule)=>R.rect(x,y,w,h,stroke,fill,p.style.look,ir.view.id+':'+x+':'+y,0,{...p.style,hachure:false});
   const group=(id,ids,content,box={},key)=>{const mid='mark:'+ir.view.id+':'+marks.length;marks.push({id:mid,sourceIds:ids,...box,...(key?{property:key}:{})});return `<g class="${R.cls('ddn-mark','ddn-mark-geo-'+plan.mark)}" data-id="${esc(id||ids[0]||'')}" data-source-ids="${esc(JSON.stringify(ids))}" data-projection-mark="${esc(mid)}"${key?` data-property="${esc(key)}"`:''} tabindex="0" role="group">${content}</g>`;};
   const latClamp=LAT_CLAMP[plan.method]||[-90,90];
   const project=fitProjection(plan.method,geography,plan.dots,W,H,Math.max(18*s,S),latClamp);
   const clipId='geo-clip-'+R.hash(ir.view.id);
   body+=`<clipPath id="${clipId}"><rect x="0" y="0" width="${f(W)}" height="${f(H)}"/></clipPath><g clip-path="url(#${clipId})">`;

   /* Graticule under everything else (10° grid, clamped to the fitted latitudes). */
   if(plan.graticule){
    const [latMin,latMax]=latClamp;let g='';
    for(let lon=-180;lon<=180;lon+=10){const pts=[];for(let lat=latMin;lat<=latMax;lat+=2)pts.push([lon,lat]);g+=`<path d="${pts.map((pt,i)=>(i?'L':'M')+f(project(pt)[0])+' '+f(project(pt)[1])).join('')}" stroke="${t.rule}" stroke-width="${lon===0?1:.5}" fill="none" opacity=".55"/>`;}
    for(let lat=-80;lat<=80;lat+=10){if(lat<latMin||lat>latMax)continue;const pts=[];for(let lon=-180;lon<=180;lon+=2)pts.push([lon,lat]);g+=`<path d="${pts.map((pt,i)=>(i?'L':'M')+f(project(pt)[0])+' '+f(project(pt)[1])).join('')}" stroke="${t.rule}" stroke-width="${lat===0?1:.5}" fill="none" opacity=".55"/>`;}
    body+=`<g class="ddn-graticule">${g}</g>`;
   }

   /* Base geography; choropleth fills join records to features by id or name. */
   let rowsByKey=null,domain=null;
   if(plan.mark==='choropleth'){
    rowsByKey=new Map(plan.rows.map(r=>[r.key,r]));
    const vs=plan.rows.map(r=>r.value);domain=[Math.min(...vs),Math.max(...vs)];
   }
   let matched=0;
   for(const ft of geography.features){
    if(!['Polygon','MultiPolygon','LineString','MultiLineString'].includes(ft.geometry.type))continue;
    let fill=t.surface,ids=[],rid=ft.id||ft.name,label=ft.name||ft.id||'region';
    if(rowsByKey){
     const row=rowsByKey.get(ft.id!==undefined?String(ft.id):'')||rowsByKey.get(ft.name);
     if(row){matched++;fill=ramp(domain[1]===domain[0]?.5:(row.value-domain[0])/(domain[1]-domain[0]));ids=[row.node.id];rid=row.node.id;label=ft.name+': '+fmtNumber(row.value)+(plan.unit?' '+plan.unit:'');}
    }
    const d=geoPath(ft.geometry,project,{cartesian:plan.method==='cartesian'});
    if(['LineString','MultiLineString'].includes(ft.geometry.type))fill='none';
    body+=group(rid,ids,`<path d="${d}" fill="${fill}" fill-rule="evenodd" stroke="${rowsByKey?t.rule:t.muted}" stroke-width="${rowsByKey?.8:1}"><title>${esc(label)}</title></path>`,{},rowsByKey?'value':undefined);
   }
   for(const ft of geography.features){
    if(!pointsOf(ft.geometry).length)continue;
    for(const pt of pointsOf(ft.geometry)){const [x,y]=project(pt);body+=group(ft.id||ft.name,[],`<circle cx="${f(x)}" cy="${f(y)}" r="${f(2.5*s)}" fill="${t.muted}"><title>${esc(ft.name||'point')}</title></circle>`);}
   }
   if(rowsByKey){
    const unmatchedFeatures=geography.features.filter(ft=>['Polygon','MultiPolygon'].includes(ft.geometry.type)&&!rowsByKey.get(ft.id!==undefined?String(ft.id):'')&&!rowsByKey.get(ft.name)).length;
    const unmatchedRecords=plan.rows.length-matched;
    if(unmatchedFeatures||unmatchedRecords)diagnostics.push({code:'DDN-PJW05',severity:'info',message:'Choropleth join: '+matched+' of '+plan.rows.length+' records matched a feature'+ (unmatchedRecords?'; '+unmatchedRecords+' record(s) have no matching feature':'')+(unmatchedFeatures?'; '+unmatchedFeatures+' feature(s) rendered neutral':'' )+'.'});
   }

   /* Symbol layer. */
   if(plan.mark==='symbol'){
    const sizes=plan.dots.map(d=>d.size).filter(v=>v!==undefined),sMax=sizes.length?Math.max(...sizes):0;
    for(const d of plan.dots){
     const [x,y]=project([d.lon,d.lat]),r=d.size===undefined?4*s:Math.max(2*s,Math.sqrt(d.size/sMax)*16*s);
     body+=group(d.node.id,[d.node.id],`<circle cx="${f(x)}" cy="${f(y)}" r="${f(r)}" fill="${t.accent}" fill-opacity=".62" stroke="${t.accent}" stroke-width="1.2"><title>${esc(d.node.name+(d.size!==undefined?': '+fmtNumber(d.size)+(plan.unit?' '+plan.unit:''):''))}</title></circle>`,{x:x-r,y:y-r,w:2*r,h:2*r},'value');
    }
   }

   /* Legend. B1-045: legend: off suppresses the choropleth ramp and the
    * symbol size key; auto/on keep today's always-when-data rule. */
   const legendOn=(p.chrome||{legend:'auto'}).legend!=='off';
   body+='</g>'; // end clipped map layer
   let ly=H-8*s;
   if(legendOn&&plan.mark==='choropleth'&&domain){
    const lw=Math.min(150*s,W/6);let lx=0;const lo=domain[0],hi=domain[1];
    for(let i=0;i<5;i++){const v0=lo+(hi-lo)*i/5,v1=lo+(hi-lo)*(i+1)/5;body+=rect(lx,ly-64*s,lw,14*s,ramp(i/4),t.rule)+text(lx+2*s,ly-40*s,fmtNumber(v0)+(i===4?' – '+fmtNumber(v1):''),11);lx+=lw+8*s;}
    if(plan.unit)body+=text(lx,ly-52*s,plan.unit,11,600);
   }
   if(legendOn&&plan.mark==='symbol'&&plan.dots.some(d=>d.size!==undefined)){
    const sizes=plan.dots.map(d=>d.size),sMax=Math.max(...sizes);let lx=0;
    for(const frac of [.25,.6,1]){const v=sMax*frac,r=Math.max(2*s,Math.sqrt(frac)*16*s);body+=`<circle cx="${f(lx+18*s)}" cy="${f(ly-56*s)}" r="${f(r)}" fill="none" stroke="${t.accent}" stroke-width="1.2"/>`+text(lx+18*s+r+5*s,ly-52*s,fmtNumber(v),11);lx+=2*r+70*s;}
   }
   body+=text(0,H-2*s,'Geographic projection: '+plan.method+' · '+geography.features.length+' features · positions derive from declared coordinates only',11);

   if(!Number.isFinite(W)||!Number.isFinite(H)||W>50000||H>50000)throw new D.DDNError('DDN-PJ060','Projection extent exceeds bounded publication budget');
   /* Page composition identical in shape to the data-bound projections.
    * B1-045 (D2): chrome toggles; defaults reproduce the pre-option page shape. */
   const chrome=p.chrome||{title:'on',footer:'on'},titleOn=chrome.title!=='off',footerOn=chrome.footer!=='off';
   const margin=q(p.publication.margin,32),titleLines=titleOn?wrap(ir.view.name,W,24,650):[],header=titleOn?Math.max(92*s,(titleLines.length*29+48)*s):0,footer=footerOn?46*s:0;
   let pageW=q(p.publication.width,1280),pageH=q(p.publication.height,800);if(['a4','letter'].includes(p.publication.size)){pageW=p.publication.size==='a4'?210*96/25.4:816;pageH=p.publication.size==='a4'?297*96/25.4:1056;if(p.publication.orientation==='landscape')[pageW,pageH]=[pageH,pageW];}
   /* 0.8 amendment (chapter 06, content scale): the drawing is scaled by
    * content_scale BEFORE the contain factor is computed, so contain and the
    * DDN071/DDN074 checks operate on the scaled result. */
   const contentScale=q(p.publication.content_scale,1);
   if(!Number.isFinite(contentScale)||contentScale<0.25||contentScale>4)throw new D.DDNError('DDN-PJ063','content_scale must be a finite ratio in [0.25, 4]');
   if(p.publication.size==='content'){pageW=W*contentScale+margin*2;pageH=H*contentScale+margin*2+header+footer;}
   const aw=pageW-2*margin,ah=pageH-2*margin-header-footer;if(aw<=0||ah<=0)throw new D.DDNError('DDN-PJ061','Page has no remaining drawing area');
   const scale=(p.publication.fit==='none'?1:Math.min(1,aw/(W*contentScale),ah/(H*contentScale)))*contentScale,min=q(p.publication.minimum_text,8*96/72),embed=p.publication.embedding_scale??1;
   if(!Number.isFinite(embed)||embed<=0||embed>4)throw new D.DDNError('DDN-PJ062','embedding_scale must be a positive finite value <= 4');
   const warnOrFail=(code,msg)=>{if(p.publication.overflow==='error')throw new D.DDNError(code,msg);diagnostics.push({code,severity:'warning',message:msg});};
   if(W*scale>aw+.01||H*scale>ah+.01)warnOrFail('DDN074','Projection exceeds publication page; use content size or a larger page');
   if(smallest*scale*embed<min-.001)warnOrFail('DDN071','Projection text would fall below the final publication minimum');
   const tx=margin+(aw-W*scale)/2,ty=margin+header;
   let out=`<?xml version="1.0" encoding="UTF-8"?>\n<svg class="${R.cls('ddn-svg','ddn-view-geo','ddn-profile-'+R.slug(plan.profile))}" xmlns="http://www.w3.org/2000/svg" width="${f(pageW)}" height="${f(pageH)}" viewBox="0 0 ${f(pageW)} ${f(pageH)}" role="img" aria-labelledby="projection-title projection-description" style="font-family:${esc(Text.FONTS[p.style.font])}"><title id="projection-title">${esc(ir.view.name)}</title><desc id="projection-description">${esc(plan.profile)}. Geographic projection (${plan.method}). Inspect marks to locate shared source definitions.</desc><rect width="100%" height="100%" fill="${t.background}"/>`;
   if(titleOn)out+=text(margin,margin+8*s,'DDN / 0.5 PROJECTION PREVIEW / '+plan.profile,11,600)+lines(titleLines,margin,margin+42*s,24,650);
   out+=`<g id="drawing" transform="translate(${f(tx)} ${f(ty)}) scale(${f(scale)})">`+rect(0,0,W,H,t.surface,t.rule)+body+'</g>';
   if(footerOn)out+=line(margin,pageH-margin-23*s,pageW-margin,pageH-margin-23*s)+text(margin,pageH-margin,'One model · source-bound occurrences · '+p.style.look+' / '+p.style.theme,11)+text(pageW-margin,pageH-margin,'geo',11,600,'end');
   out+='</svg>';
   const after=Text.stats(),estimated=after.estimated>stats.estimated;if(estimated){if(p.publication.metrics==='required')throw new D.DDNError('DDN077','Required measured fonts unavailable for projection');diagnostics.push({code:'DDN-TW01',severity:'warning',message:'Some projection text used estimated metrics. Browser-specific shaping is not certified.'});}
   const scene={width:pageW,height:pageH,smallestText:smallest,scale,origin:[tx,ty],nodes:[],routes:[],crossings:[],frames:[],subdiagrams:[],marks,projection:{kind:'geo',profile:plan.profile,sourceIds:plan.sourceIds,quantitative:plan.mark!=='outline'},drawingBounds:{x:0,y:0,w:W,h:H},drawingArea:{x:margin,y:margin+header,w:aw,h:ah},textMeasurement:{mode:estimated?'estimated':'measured',requestedFont:p.style.font}};
   return {svg:out,scene,diagnostics,_ir:ir};
  }

  const api$1={VERSION:'0.8.0',render,plan:planGeo,projections,ingest,geoPath,fitProjection,registerGeography,hasGeography:n=>GEOGRAPHIES.has(n),geographies:()=>[...GEOGRAPHIES.keys()]};
  publishNamespace('DDNGeo',api$1);

  /* SPDX-License-Identifier: GPL-2.0-or-later. ddn-geo bundle entry
   * (B1-025). Guards, optional geographic projection kind registration, browser globals. */

  const host = globalThis;
  if (!host.DDNLive) throw new Error('ddn-geo requires ddn-core.js to be loaded first');
  if (!host.DDNRender && !optionalNamespace('DDNRender')) throw new Error('ddn-geo requires ddn-graph.js to be loaded first');
  if (host.DDNLive.VERSION !== pkg.version) throw new Error('A different DDNLive runtime is already loaded. Load exactly one version.');
  if (!host.DDNGeo) {
    host.DDNGeo = api$1;
    const Engine = optionalNamespace('DDNEngine');
    Engine.registerProjectionRenderer('geo', api$1.render, { optional: true });
  }
  const api = host.DDNLive;
  if (typeof module === 'object' && module.exports) module.exports = api;
  const { VERSION, runtime, createWorkspace, registerWorkspace, mount, fromSnapshot, authoring, io, parse, profileCatalogue } = api;

})();
