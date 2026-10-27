'use strict';
// Parse/normalize only. No render(), pixels, or tracing in the import pipeline.
const fs = require('node:fs');
const {Resvg} = require('./vendor/node_modules/@resvg/resvg-js');
try {
  const renderer = new Resvg(fs.readFileSync(process.argv[2]), {
    font: {loadSystemFonts:true}, dpi:96, logLevel:'warn'
  });
  fs.writeFileSync(process.argv[3], renderer.toString());
} catch (error) { console.error(error.message); process.exit(1); }
