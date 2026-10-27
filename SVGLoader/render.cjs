'use strict';
const fs = require('node:fs');
const path = require('node:path');
const {Resvg} = require('./vendor/node_modules/@resvg/resvg-js');

function resolveImages(renderer, filename) {
  for (const href of renderer.imagesToResolve()) {
    if (/^https?:/i.test(href)) throw new Error('Download linked images locally before importing: '+href);
    const local = href.startsWith('file:') ? require('node:url').fileURLToPath(href)
      : path.resolve(path.dirname(filename), decodeURIComponent(href));
    renderer.resolveImage(href, fs.readFileSync(local));
  }
}
const [filename, output, edgeText='8192'] = process.argv.slice(2);
const svg = fs.readFileSync(filename);
const options = {font:{loadSystemFonts:true}, logLevel:'warn', dpi:96};
const probe = new Resvg(svg, options);
const nativeWidth = probe.width, nativeHeight = probe.height;
if (!(nativeWidth>0 && nativeHeight>0)) throw new Error('SVG has no valid viewport.');
const edge = Math.max(256,Math.min(8192,Number(edgeText)));
const renderer = new Resvg(svg, {...options,fitTo:{mode:nativeWidth>=nativeHeight?'width':'height',value:edge}});
resolveImages(renderer, filename);
const rendered = renderer.render();
if (output.endsWith('.png')) { fs.writeFileSync(output,rendered.asPng()); process.exit(0); }
const width = rendered.width, height=rendered.height;
const pixels=rendered.pixels;
// Potrace uses native uint32 words on Windows, MSB first within each scanline.
const stride=Math.ceil(width/32), packed=Buffer.alloc(stride*height*4);
for (let y=0;y<height;y++) {
  for(let word=0;word<stride;word++) {
    let bits=0;
    for(let k=0;k<32;k++) {
      const x=word*32+k;
      if(x>=width) break;
      const i=(y*width+x)*4, alpha=pixels[i+3]/255;
      const luminance=(0.2126*pixels[i]+0.7152*pixels[i+1]+0.0722*pixels[i+2])*alpha+255*(1-alpha);
      if(luminance<127.5) bits=(bits | (0x80000000>>>k))>>>0;
    }
    packed.writeUInt32LE(bits,y*stride*4+word*4);
  }
}
fs.writeFileSync(output,packed);
fs.writeFileSync(output+'.json',JSON.stringify({width,height,stride,nativeWidth,nativeHeight}));
