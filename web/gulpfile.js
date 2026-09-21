/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

'use strict';

const fs = require('fs');
const path = require('path');
const { series, watch } = require('gulp');
const sass = require('sass');

const themeScss = path.join(__dirname, 'pgadmin/static/css/theme.scss');
const themeCss = path.join(__dirname, 'pgadmin/static/css/theme.css');
const generatedBanner = '/* Generated from theme.scss by gulp. Do not edit. */\n\n';

function compileTheme(cb) {
  try {
    const result = sass.compile(themeScss, { style: 'expanded' });
    fs.writeFileSync(themeCss, generatedBanner + result.css);
    cb();
  } catch (err) {
    console.error(err.message || err);
    cb(err);
  }
}

function watchTheme() {
  watch(themeScss, compileTheme);
}

const watchTask = series(compileTheme, watchTheme);

module.exports = {
  theme: compileTheme,
  watch: watchTask,
  default: watchTask,
};
