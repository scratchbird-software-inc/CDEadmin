const webpack = require('webpack');
const config = require('./webpack.config.js')[0];
config.entry = { 'security.pages': 'security.pages' };
config.watch = true;
webpack(config, (err, stats) => {
  if (err) {
    console.error(err);
    return;
  }
  const info = stats.toJson({ all: false, errors: true, warnings: true, assets: true });
  if (stats.hasErrors()) {
    console.error(stats.toString({ colors: false, chunks: false, modules: false, errors: true }));
    return;
  }
  const asset = (info.assets || []).find((item) => item.name === 'security.pages.js');
  console.log(stats.hasWarnings() ? 'compiled with warnings' : 'compiled successfully');
  if (asset) console.log('security.pages.js emitted=' + asset.emitted + ' size=' + asset.size);
});
