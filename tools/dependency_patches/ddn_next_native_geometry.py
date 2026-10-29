"""Reviewed consumer patch, applied only to an isolated standalone DDN capture.

Extends the existing geography profile's declared method vocabulary and renderer
for native Cartesian, line and collection geometry. No grammar/API/default
change. See ddn-next-native-geometry.md; source checkout is never modified.
"""
import json
from pathlib import Path

CONTRACTS = 'docs/Weaver-Specifications/reference/planning/2026-10-property-codex'


def apply(root):
    root = Path(root)
    for name in ('ddn.schema.json', 'property-codex.json'):
        path = root / CONTRACTS / name
        value = json.loads(path.read_text())
        count = 0

        def visit(node):
            nonlocal count
            if isinstance(node, dict):
                choices = node.get('enum')
                if isinstance(choices, list) and 'mercator' in choices and 'equalEarth' in choices:
                    if 'cartesian' not in choices:
                        choices.append('cartesian')
                    count += 1
                for child in node.values():
                    visit(child)
            elif isinstance(node, list):
                for child in node:
                    visit(child)
        visit(value)
        if not count:
            raise RuntimeError('DDN geography contract changed; review the native geometry patch')
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    profiles = root / CONTRACTS / 'profile-contracts.json'
    data = json.loads(profiles.read_text())
    for key in ('geo.outline@1', 'geo.symbols@1', 'geo.choropleth@1'):
        rules = data[key]['profile_rules']
        rules.append('ScratchRobin reviewed native-geometry extension: cartesian projects finite x/y without geographic range checks or wrapping; outlines also accept LineString, MultiLineString and bounded GeometryCollection. Geographic methods retain longitude/latitude range checks. No tiles, routing, geocoding or spatial inference.')
    profiles.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    path = root / 'project/ddn/packages/presentation/src/data-geo.ts'
    text = path.read_text()
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise RuntimeError('DDN geography implementation changed; review native geometry patch: ' + old[:80])
        text = text.replace(old, new)
    replace('    const radians = Math.PI / 180', "    if (method === 'cartesian') return [longitude, -latitude];\n    const radians = Math.PI / 180")
    replace('    points: Coordinate[];\n}', '    points: Coordinate[];\n    lines: Coordinate[][];\n}')
    replace('function features(value: unknown): Feature[] {', 'function features(value: unknown, cartesian = false, depth = 0): Feature[] {\n    if (depth > 32) throw Error(\'Geometry collection nesting exceeds 32 levels.\');')
    replace('return array(json.features).flatMap(features);', 'return array(json.features).flatMap(child => features(child, cartesian, depth + 1));')
    replace("    if (type === 'Feature')", "    if (type === 'GeometryCollection') return array(json.geometries).flatMap(child => features(child, cartesian, depth + 1));\n    if (type === 'Feature')")
    replace("return [{ ...geometry(object(json.geometry)), id: String(json.id ?? object(json.properties).name ?? '') }];", "return features(json.geometry, cartesian, depth + 1).map(item => ({...item, id: String(json.id ?? object(json.properties).name ?? '')}));")
    replace("return [{ ...geometry(json), id: '' }];", "return [{ ...geometry(json, cartesian), id: '' }];")
    replace("function geometry(value: DataRecord): Omit<Feature, 'id'> {", "function geometry(value: DataRecord, cartesian: boolean): Omit<Feature, 'id'> {")
    replace('!finite(xy[0]) || !finite(xy[1]) || xy[0] < -180 || xy[0] > 180 || xy[1] < -90 || xy[1] > 90', '!finite(xy[0]) || !finite(xy[1]) || !cartesian && (xy[0] < -180 || xy[0] > 180 || xy[1] < -90 || xy[1] > 90)')
    replace("return { polygons: [], points: [coordinate(values)] };", "return { polygons: [], lines: [], points: [coordinate(values)] };")
    replace("return { polygons: [], points: values.map(coordinate) };", "return { polygons: [], lines: [], points: values.map(coordinate) };\n    const line = (value: unknown) => { const points = array(value).map(coordinate); if (points.length < 2) throw Error('A line requires at least two coordinates.'); return points; };\n    if (type === 'LineString') return {polygons: [], points: [], lines: [line(values)]};\n    if (type === 'MultiLineString') return {polygons: [], points: [], lines: values.map(line)};")
    replace("return { polygons: [values.map(ring)], points: [] };", "return { polygons: [values.map(ring)], points: [], lines: [] };")
    replace("return { polygons: values.map(p => array(p).map(ring)), points: [] };", "return { polygons: values.map(p => array(p).map(ring)), points: [], lines: [] };")
    replace("['mercator', 'equirectangular', 'albers', 'orthographic', 'equalEarth'].includes(method)", "['mercator', 'equirectangular', 'albers', 'orthographic', 'equalEarth', 'cartesian'].includes(method)")
    replace('geo = features(raw);', "geo = features(raw, method === 'cartesian');")
    replace('count += feature.points.length;', 'count += feature.points.length + feature.lines.reduce((total, line) => total + line.length, 0);')
    replace('polygon.flatMap(ring => splitAntimeridian(ring))', "polygon.flatMap(ring => method === 'cartesian' ? [ring] : splitAntimeridian(ring))")
    replace('const projected = geo.map', "const lineSegments = (line: Coordinate[]): Coordinate[][] => {\n        const result: Coordinate[][] = []; let segment: Coordinate[] = [];\n        for (const point of line) {\n            const previous = segment.at(-1);\n            if (method !== 'cartesian' && previous && Math.abs(point[0] - previous[0]) > 180) {\n                const longitude = point[0] + (point[0] > previous[0] ? -360 : 360), boundary = longitude > previous[0] ? 180 : -180;\n                const latitude = previous[1] + (point[1] - previous[1]) * (boundary - previous[0]) / (longitude - previous[0]);\n                segment.push([boundary, latitude]); result.push(segment); segment = [[-boundary, latitude]];\n            }\n            if (!projectCoordinate(point[0], point[1], method)) {if (segment.length) result.push(segment); segment = []; continue;}\n            segment.push(point);\n        }\n        if (segment.length) result.push(segment);\n        return result;\n    };\n    const projected = geo.map")
    replace('({ feature, polygons:', "({ feature, lines: feature.lines.flatMap(lineSegments).map(line => line.map(point => projectCoordinate(point[0], point[1], method)).filter((point): point is Coordinate => !!point)), polygons:")
    replace('[...g.polygons.flat(2), ...g.points]', '[...g.polygons.flat(2), ...g.lines.flat(), ...g.points]')
    replace('[...feature.polygons.flat(2), ...feature.points]', '[...feature.polygons.flat(2), ...feature.lines.flat(), ...feature.points]')
    replace('.filter(point => point[1] >= latitudeRange[0]! && point[1] <= latitudeRange[1]!)', ".filter(point => method === 'cartesian' || point[1] >= latitudeRange[0]! && point[1] <= latitudeRange[1]!)")
    replace('        for (const point of item.points)', "        for (const line of item.lines) primitives.push(path(pointsPath(line.map(screen)), '#8DA0B8', 'none', {'stroke-width': 1}));\n        for (const point of item.points)")
    replace('    if (settings.graticule) {', "    if (settings.graticule && method !== 'cartesian') {")
    replace('Math.abs(lon) > 180 || Math.abs(lat) > 90', "method !== 'cartesian' && (Math.abs(lon) > 180 || Math.abs(lat) > 90)")
    replace("    const projected = geo.map", """    // Scale Cartesian display coordinates before extents, preventing overflow
    // for finite native values near Number.MAX_VALUE. Authored data is intact.
    if (method === 'cartesian') {
        let scale = 1;
        for (const feature of geo) for (const point of [...feature.polygons.flat(2), ...feature.lines.flat(), ...feature.points]) scale = Math.max(scale, Math.abs(point[0]), Math.abs(point[1]));
        const normalized = (point: Coordinate): Coordinate => [point[0] / scale, point[1] / scale];
        geo = geo.map(feature => ({...feature, points: feature.points.map(normalized), lines: feature.lines.map(line => line.map(normalized)), polygons: feature.polygons.map(polygon => polygon.map(ring => ring.map(normalized)))}));
    }
    const projected = geo.map""")
    path.write_text(text)
    path = root / 'project/ddn/packages/viewer/src/core.ts'
    text = path.read_text()
    old = "svgElement(document, 'svg', { xmlns: NS, viewBox:"
    if text.count(old) != 1:
        raise RuntimeError('DDN SVG capture changed; review the namespace repair')
    # createElementNS already owns the namespace; XMLSerializer supplies xmlns.
    text = text.replace(old, "svgElement(document, 'svg', { viewBox:")
    old = "['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity'"
    if text.count(old) != 1:
        raise RuntimeError('DDN paint realization changed; review polygon hole preservation')
    path.write_text(text.replace(old, "['fill', 'fill-rule', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity'"))

    # Build-host portability only; the browser API and language are unchanged.
    path = root / 'tooling/workspace/run.mjs'
    text = path.read_text()
    text = text.replace("join(target,'node/bin/node')", "join(target,process.platform==='win32'?'node/node.exe':'node/bin/node')")
    text = text.replace('p.path.includes(`/project/${scope}/`)', 'p.path.replaceAll("\\\\","/").includes(`/project/${scope}/`)')
    text = text.replace("p.path.includes('/project/ddn/')", "p.path.replaceAll('\\\\','/').includes('/project/ddn/')")
    text = text.replace('p.includes(`/tests/${scope}/`)', 'p.replaceAll("\\\\","/").includes(`/tests/${scope}/`)')
    path.write_text(text)
