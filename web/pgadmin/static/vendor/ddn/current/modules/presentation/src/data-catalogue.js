export const chartProfileIds = Object.freeze(['basic', 'radar', 'funnel', 'quality', 'gauge', 'candlestick', 'treemap', 'sankey', 'histogram', 'density', 'qq', 'quantiledot', 'dotplot', 'boxplot', 'violin', 'beeswarm', 'topk', 'tidytree', 'radialtree', 'circlepack', 'sunburst', 'packedbubble', 'heatmap', 'densityheatmap', 'calendar', 'parallelcoords', 'wordcloud', 'arc', 'force', 'edgebundle'].map(name => `chart.${name}@1`));
export const geographyProfileIds = Object.freeze(['choropleth', 'symbols', 'outline'].map(name => `geo.${name}@1`));
export const surfaceProfileIds = Object.freeze([
    ...['raci', 'crud', 'relations', 'heatmap', 'bcg', 'ansoff', 'tows', 'storymap'].map(name => `matrix.${name}@1`),
    ...['basic', 'composed', 'journey', 'pyramid', 'venn'].map(name => `panels.${name}@1`),
    ...['bmc', 'lean', 'pest', 'pestle', 'porter5', 'empathy', 'scorecard'].map(name => `canvas.${name}@1`),
    'timeline.basic@1', 'decision.rules@1'
]);
export const dataProfileIds = Object.freeze([...chartProfileIds, ...surfaceProfileIds, ...geographyProfileIds]);
//# sourceMappingURL=data-catalogue.js.map