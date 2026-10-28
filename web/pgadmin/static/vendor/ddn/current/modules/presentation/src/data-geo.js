import { array, object, str, num, pathValue, refKey } from './model.js';
import { matrixEncoding } from './data-encoding.js';
import { DataScene, finite, extent, ellipse, path, pointsPath, colors, label, numberLabel } from './data-common.js';
export function projectCoordinate(longitude, latitude, method) {
    if (method === 'cartesian')
        return [longitude, -latitude];
    const radians = Math.PI / 180, lambda = longitude * radians, phi = latitude * radians;
    if (method === 'equirectangular')
        return [lambda, -phi];
    if (method === 'mercator')
        return [lambda, -Math.log(Math.tan(Math.PI / 4 + Math.max(-85.05112878, Math.min(85.05112878, latitude)) * radians / 2))];
    // Equal Earth spherical forward equations (Savric et al.; PROJ eqearth).
    // https://proj.org/en/stable/operations/projections/eqearth.html
    if (method === 'equalEarth') {
        const theta = Math.asin(Math.sqrt(3) / 2 * Math.sin(phi)), t2 = theta * theta, t6 = t2 * t2 * t2, t8 = t6 * t2;
        return [2 * Math.sqrt(3) * lambda * Math.cos(theta) / (3 * (1.340264 - .243318 * t2 + .006251 * t6 + .034164 * t8)), -theta * (1.340264 - .081106 * t2 + .000893 * t6 + .003796 * t8)];
    }
    if (method === 'orthographic') {
        if (Math.cos(phi) * Math.cos(lambda) < -1e-10)
            return;
        return [Math.cos(phi) * Math.sin(lambda), -Math.sin(phi)];
    }
    if (method === 'albers') {
        const p1 = 29.5 * radians, p2 = 45.5 * radians, n = (Math.sin(p1) + Math.sin(p2)) / 2, c = Math.cos(p1) ** 2 + 2 * n * Math.sin(p1), rho = Math.sqrt(Math.max(0, c - 2 * n * Math.sin(phi))) / n, rho0 = Math.sqrt(c) / n;
        return [rho * Math.sin(n * lambda), rho * Math.cos(n * lambda) - rho0];
    }
    return;
}
/** Split a geographic ring at the antimeridian before screen projection. */
export function splitAntimeridian(ring) {
    if (ring.length < 3)
        return [];
    const unwrapped = [ring[0]];
    for (const p of ring.slice(1)) {
        let lon = p[0], previous = unwrapped.at(-1)[0];
        while (lon - previous > 180)
            lon -= 360;
        while (lon - previous < -180)
            lon += 360;
        unwrapped.push([lon, p[1]]);
    }
    const clip = (points, boundary, lower) => {
        const result = [];
        for (let i = 0; i < points.length; i++) {
            const a = points[i], b = points[(i + 1) % points.length], ain = lower ? a[0] >= boundary : a[0] <= boundary, bin = lower ? b[0] >= boundary : b[0] <= boundary;
            if (ain)
                result.push(a);
            if (ain !== bin) {
                const t = (boundary - a[0]) / (b[0] - a[0]);
                result.push([boundary, a[1] + (b[1] - a[1]) * t]);
            }
        }
        return result;
    };
    const result = [];
    for (const offset of [-720, -360, 0, 360, 720]) {
        const moved = unwrapped.map(p => [p[0] + offset, p[1]]), clipped = clip(clip(moved, -180, true), 180, false);
        if (clipped.length >= 3)
            result.push(clipped);
    }
    return result;
}
function features(value, cartesian = false, depth = 0) {
    if (depth > 32)
        throw Error('Geometry collection nesting exceeds 32 levels.');
    const json = object(value), type = str(json.type);
    if (type === 'FeatureCollection')
        return array(json.features).flatMap(child => features(child, cartesian, depth + 1));
    if (type === 'GeometryCollection')
        return array(json.geometries).flatMap(child => features(child, cartesian, depth + 1));
    if (type === 'Feature')
        return features(json.geometry, cartesian, depth + 1).map(item => ({ ...item, id: String(json.id ?? object(json.properties).name ?? '') }));
    return [{ ...geometry(json, cartesian), id: '' }];
}
function geometry(value, cartesian) {
    const coordinate = (value) => {
        const xy = array(value);
        if (!finite(xy[0]) || !finite(xy[1]) || !cartesian && (xy[0] < -180 || xy[0] > 180 || xy[1] < -90 || xy[1] > 90))
            throw new Error('GeoJSON longitude/latitude must be finite and within range.');
        return [xy[0], xy[1]];
    };
    const type = str(value.type), values = array(value.coordinates);
    if (type === 'Point')
        return { polygons: [], lines: [], points: [coordinate(values)] };
    if (type === 'MultiPoint')
        return { polygons: [], lines: [], points: values.map(coordinate) };
    const line = (value) => { const points = array(value).map(coordinate); if (points.length < 2)
        throw Error('A line requires at least two coordinates.'); return points; };
    if (type === 'LineString')
        return { polygons: [], points: [], lines: [line(values)] };
    if (type === 'MultiLineString')
        return { polygons: [], points: [], lines: values.map(line) };
    const ring = (values) => {
        const points = array(values).map(coordinate);
        if (points.length < 4 || points[0][0] !== points.at(-1)[0] || points[0][1] !== points.at(-1)[1])
            throw new Error('GeoJSON polygon rings must be closed with at least four coordinates.');
        return points;
    };
    if (type === 'Polygon')
        return { polygons: [values.map(ring)], points: [], lines: [] };
    if (type === 'MultiPolygon')
        return { polygons: values.map(p => array(p).map(ring)), points: [], lines: [] };
    throw new Error(`Unsupported GeoJSON geometry ${type}.`);
}
function clipHemisphere(ring) {
    const visible = (p) => Math.cos(p[1] * Math.PI / 180) * Math.cos(p[0] * Math.PI / 180) >= 0, result = [];
    for (let i = 0; i < ring.length; i++) {
        const a = ring[i], b = ring[(i + 1) % ring.length], ain = visible(a), bin = visible(b);
        if (ain)
            result.push(a);
        if (ain !== bin) {
            let low = 0, high = 1;
            for (let iteration = 0; iteration < 40; iteration++) {
                const t = (low + high) / 2, p = [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
                if (visible(p) === ain)
                    low = t;
                else
                    high = t;
            }
            const t = (low + high) / 2;
            result.push([a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]);
        }
    }
    return result;
}
export function drawGeo(scene, supplied) {
    const settings = scene.settings, method = str(settings.method, 'mercator'), profile = str(scene.view.record.profile), mark = str(settings.mark, profile === 'geo.symbols@1' ? 'symbol' : profile === 'geo.choropleth@1' ? 'choropleth' : 'outline'), geography = str(settings.geography);
    if (!['mercator', 'equirectangular', 'albers', 'orthographic', 'equalEarth', 'cartesian'].includes(method)) {
        scene.issue(`Unsupported geographic projection ${method}.`);
        return;
    }
    // Resolve the declaring file first: included files may repeat asset names.
    if (!['outline', 'symbol', 'choropleth'].includes(mark)) {
        scene.issue('Geographic marks are outline, symbol or choropleth.');
        return;
    }
    let geographyFile = scene.view.file, geographyName = geography;
    if (geography.startsWith('[')) {
        try {
            const reference = JSON.parse(geography);
            if (Array.isArray(reference) && reference.length === 2 && reference.every(part => typeof part === 'string'))
                [geographyFile, geographyName] = reference;
        }
        catch { /* A malformed reference remains unresolved below. */ }
    }
    else if (geography.includes('::')) {
        const delimiter = geography.lastIndexOf('::');
        geographyFile = geography.slice(0, delimiter);
        geographyName = geography.slice(delimiter + 2);
    }
    const source = scene.all.find(record => record.file === geographyFile && (record.ref.id === geographyName || record.record.name === geographyName || record.owner === 'asset' && record.record.path === geographyName));
    const asset = source?.owner === 'asset' ? source : undefined;
    let raw = source ? supplied?.get(refKey(source.ref)) : undefined;
    if (raw === undefined && asset)
        raw = asset.record.bytes;
    if (raw === undefined && source)
        raw = pathValue(source.record, 'metadata.x_record.geography');
    if (raw === undefined)
        raw = supplied?.get(geography);
    if (raw === undefined && geography.trim().startsWith('{'))
        raw = geography;
    if (typeof raw === 'string') {
        try {
            raw = JSON.parse(raw);
        }
        catch {
            scene.issue('Geography must be valid supplied GeoJSON.');
            return;
        }
    }
    if (!raw) {
        scene.issue('Declared geography is unavailable; supply local GeoJSON.');
        return;
    }
    let geo;
    try {
        geo = features(raw, method === 'cartesian');
    }
    catch (error) {
        scene.issue(String(error));
        return;
    }
    let count = 0;
    geo.forEach(feature => { count += feature.points.length + feature.lines.reduce((total, line) => total + line.length, 0); feature.polygons.forEach(polygon => polygon.forEach(ring => count += ring.length)); });
    if (count > 100000) {
        scene.issue('Geography exceeds 100,000 coordinates.');
        return;
    }
    const lineSegments = (line) => {
        const result = [];
        let segment = [];
        for (const point of line) {
            const previous = segment.at(-1);
            if (method !== 'cartesian' && previous && Math.abs(point[0] - previous[0]) > 180) {
                const longitude = point[0] + (point[0] > previous[0] ? -360 : 360), boundary = longitude > previous[0] ? 180 : -180;
                const latitude = previous[1] + (point[1] - previous[1]) * (boundary - previous[0]) / (longitude - previous[0]);
                segment.push([boundary, latitude]);
                result.push(segment);
                segment = [[-boundary, latitude]];
            }
            if (!projectCoordinate(point[0], point[1], method)) {
                if (segment.length)
                    result.push(segment);
                segment = [];
                continue;
            }
            segment.push(point);
        }
        if (segment.length)
            result.push(segment);
        return result;
    };
    // Scale Cartesian display coordinates before extents, preventing overflow
    // for finite native values near Number.MAX_VALUE. Authored data is intact.
    if (method === 'cartesian') {
        let scale = 1;
        for (const feature of geo)
            for (const point of [...feature.polygons.flat(2), ...feature.lines.flat(), ...feature.points])
                scale = Math.max(scale, Math.abs(point[0]), Math.abs(point[1]));
        const normalized = (point) => [point[0] / scale, point[1] / scale];
        geo = geo.map(feature => ({ ...feature, points: feature.points.map(normalized), lines: feature.lines.map(line => line.map(normalized)), polygons: feature.polygons.map(polygon => polygon.map(ring => ring.map(normalized))) }));
    }
    const projected = geo.map(feature => ({ feature, lines: feature.lines.flatMap(lineSegments).map(line => line.map(point => projectCoordinate(point[0], point[1], method)).filter((point) => !!point)), polygons: feature.polygons.map(polygon => polygon.flatMap(ring => method === 'cartesian' ? [ring] : splitAntimeridian(ring)).map(ring => method === 'orthographic' ? clipHemisphere(ring) : ring).map(ring => ring.map(p => projectCoordinate(p[0], p[1], method)).filter((p) => !!p))), points: feature.points.map(p => projectCoordinate(p[0], p[1], method)).filter((p) => !!p) })), allPoints = projected.flatMap(g => [...g.polygons.flat(2), ...g.lines.flat(), ...g.points]);
    if (!allPoints.length) {
        scene.issue('No supplied geometry is visible in this projection.');
        return;
    }
    const latitudeRange = method === 'mercator' ? [-85.05112878, 85.05112878] : method === 'albers' ? [-60, 85] : [-90, 90];
    const fitPoints = geo.flatMap(feature => [...feature.polygons.flat(2), ...feature.lines.flat(), ...feature.points]).filter(point => method === 'cartesian' || point[1] >= latitudeRange[0] && point[1] <= latitudeRange[1]).map(point => projectCoordinate(point[0], point[1], method)).filter((point) => !!point);
    const fitted = fitPoints.length ? fitPoints : allPoints;
    const xd = extent(fitted.map(p => p[0])), yd = extent(fitted.map(p => p[1])), fit = Math.min((scene.bounds.width - 80) / (xd[1] - xd[0]), (scene.bounds.height - 110) / (yd[1] - yd[0])), dx = scene.bounds.x + (scene.bounds.width - (xd[1] - xd[0]) * fit) / 2, dy = scene.bounds.y + 30 + (scene.bounds.height - 100 - (yd[1] - yd[0]) * fit) / 2, screen = (point) => [dx + (point[0] - xd[0]) * fit, dy + (point[1] - yd[0]) * fit];
    const data = mark === 'outline' ? [] : scene.data(), xKey = str(settings.x, mark === 'symbol' ? 'longitude' : 'region'), yKey = str(settings.y, mark === 'symbol' ? 'latitude' : str(settings.value, 'value')), matches = new Map();
    if (mark === 'choropleth') {
        for (const datum of data) {
            const key = String(valueAtGeo(datum.values, xKey)), value = valueAtGeo(datum.values, yKey);
            if (matches.has(key) || !finite(value)) {
                scene.issue('Choropleth keys must be unique with finite values.');
                return;
            }
            matches.set(key, datum);
        }
    }
    const domain = extent(data.map(d => valueAtGeo(d.values, yKey)).filter(finite)), geographicColor = matrixEncoding({ domain: { min: domain[0], max: domain[1] } }, domain);
    const geographicStart = scene.result.entries.length;
    for (const item of projected) {
        const datum = matches.get(item.feature.id), value = datum ? valueAtGeo(datum.values, yKey) : undefined, primitives = [];
        if (mark === 'choropleth' && !datum)
            scene.issue(`No record matches feature ${item.feature.id || '(unnamed)'}.`, 'DDN-GEO-UNMATCHED', 'warning');
        for (const polygon of item.polygons)
            primitives.push(path(polygon.map(ring => pointsPath(ring.map(screen), true)).join(''), mark === 'choropleth' ? '#D5DFEB' : '#8DA0B8', finite(value) ? geographicColor(value) : '#FFFFFF', { 'fill-rule': 'evenodd', 'stroke-width': mark === 'choropleth' ? .8 : 1 }));
        for (const line of item.lines)
            primitives.push(path(pointsPath(line.map(screen)), '#8DA0B8', 'none', { 'stroke-width': 1 }));
        for (const point of item.points) {
            const p = screen(point);
            primitives.push(ellipse(p[0], p[1], 3, '#94a3b8'));
        }
        scene.add(`${item.feature.id || 'Geographic feature'}${finite(value) ? `: ${value}` : ''}`, scene.bounds, primitives, datum?.source ?? asset ?? scene.view, datum?.contributors ?? [asset?.ref ?? scene.view.ref]);
    }
    if (mark === 'choropleth')
        for (const [key, datum] of matches)
            if (!geo.some(feature => feature.id === key))
                scene.issue(`Record ${key} has no geographic feature.`, 'DDN-GEO-UNMATCHED', 'warning', datum.source.ref);
    if (settings.graticule && method !== 'cartesian') {
        const primitives = [];
        for (let longitude = -180; longitude <= 180; longitude += 10) {
            const points = [];
            for (let latitude = -80; latitude <= 80; latitude += 2) {
                const p = projectCoordinate(longitude, latitude, method);
                if (p)
                    points.push(screen(p));
            }
            if (points.length)
                primitives.push(path(pointsPath(points), '#94a3b8', 'none', { 'stroke-opacity': .4, 'stroke-width': .5 }));
        }
        for (let latitude = -80; latitude <= 80; latitude += 10) {
            let segment = [];
            for (let longitude = -180; longitude <= 180; longitude += 2) {
                const p = projectCoordinate(longitude, latitude, method);
                if (p)
                    segment.push(screen(p));
                else if (segment.length) {
                    primitives.push(path(pointsPath(segment), '#94a3b8', 'none', { 'stroke-opacity': .4, 'stroke-width': .5 }));
                    segment = [];
                }
            }
            if (segment.length)
                primitives.push(path(pointsPath(segment), '#94a3b8', 'none', { 'stroke-opacity': .4, 'stroke-width': .5 }));
        }
        scene.add('Graticule', scene.bounds, primitives);
        const graticule = scene.result.entries.pop();
        scene.result.entries.splice(geographicStart, 0, graticule);
    }
    if (mark === 'choropleth')
        scene.intensity(domain, str(settings.unit), scene.bounds.x + 64, scene.bounds.y + 18, value => geographicColor(value));
    const maximumSize = Math.max(...data.map(datum => settings.size ? valueAtGeo(datum.values, str(settings.size)) : 16).filter(finite), 0) || 1;
    if (mark === 'symbol')
        for (const datum of data) {
            const lon = valueAtGeo(datum.values, xKey), lat = valueAtGeo(datum.values, yKey), size = settings.size ? valueAtGeo(datum.values, str(settings.size)) : 16;
            if (!finite(lon) || !finite(lat) || method !== 'cartesian' && (Math.abs(lon) > 180 || Math.abs(lat) > 90) || !finite(size) || size < 0) {
                scene.issue('Geographic symbols require valid lon/lat and nonnegative finite size.');
                continue;
            }
            const coordinate = projectCoordinate(lon, lat, method);
            if (!coordinate)
                continue;
            const p = screen(coordinate), radius = settings.size ? 16 * Math.sqrt(size / maximumSize) : 4;
            scene.add(`${lon}, ${lat}`, { x: p[0] - radius, y: p[1] - radius, width: radius * 2, height: radius * 2 }, [ellipse(p[0], p[1], radius, colors[0], { 'fill-opacity': .65 })], datum.source, datum.contributors);
        }
    if (mark === 'symbol' && settings.size) {
        const primitives = [];
        for (const [i, value] of [maximumSize / 4, maximumSize / 2, maximumSize].entries()) {
            const x = scene.bounds.x + 50 + i * 100, y = scene.bounds.y + 20;
            primitives.push(ellipse(x, y, 16 * Math.sqrt(value / maximumSize), colors[0], { 'fill-opacity': .65 }), label(numberLabel(value), x + 22, y + 4, 11));
        }
        scene.add('Symbol area scale', { x: scene.bounds.x + 30, y: scene.bounds.y + 2, width: 320, height: 36 }, primitives);
    }
    scene.caption(`${method}; ${geo.length} geographic features${mark === 'symbol' ? settings.size ? '; symbol area encodes ' + str(settings.size, 'size').split('.').at(-1) : '; symbols mark supplied coordinates' : mark === 'choropleth' ? '; color encodes value; unmatched features are neutral' : '; outlines are geographic boundaries'}.`);
}
function valueAtGeo(value, key) { return Object.hasOwn(value, key) ? value[key] : pathValue(value, key); }
//# sourceMappingURL=data-geo.js.map