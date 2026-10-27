'use strict';
const fs = require('node:fs');
const init = require('./vendor/node_modules/pathkit-wasm/bin/pathkit.js');
const ID = [1,0,0,1,0,0];
function mul(a,b) {
  return [a[0]*b[0]+a[2]*b[1],a[1]*b[0]+a[3]*b[1],
    a[0]*b[2]+a[2]*b[3],a[1]*b[2]+a[3]*b[3],
    a[0]*b[4]+a[2]*b[5]+a[4],a[1]*b[4]+a[3]*b[5]+a[5]];
}
function matrix(value) {
  if (!value) return ID;
  const match = /^matrix\(([^)]+)\)$/.exec(value);
  if (!match) throw Error('Unsupported normalized transform: '+value);
  const nums = match[1].trim().split(/[ ,]+/).map(Number);
  if (nums.length!==6 || nums.some(v=>!Number.isFinite(v))) throw Error('Invalid transform.');
  return nums;
}

async function main() {
  const P = await init({wasmBinary:fs.readFileSync(__dirname+'/vendor/node_modules/pathkit-wasm/bin/pathkit.wasm')});
  const tree = JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
  const defs = new Map();
  function index(n) { if(n.a.id) defs.set(n.a.id,n); n.children.forEach(index); }
  index(tree);
  const empty = ()=>P.NewPath();
  const op = (a,b,kind)=>{ if(!a.op(b,P.PathOp[kind])) throw Error('Vector Boolean '+kind+' failed.'); return a; };
  const transformed = (p,m)=>{p.transform(m[0],m[2],m[4],m[1],m[3],m[5],0,0,1); return p;};
  const rect = (x,y,w,h)=>empty().rect(x,y,w,h);
  const layer = ()=>({ink:empty(),cover:empty()});
  const dispose = a=>{a.ink.delete();a.cover.delete();};
  function compose(a,b) {
    op(a.ink,b.cover,'DIFFERENCE'); op(a.ink,b.ink,'UNION'); op(a.cover,b.cover,'UNION');
    dispose(b); return a;
  }
  function crop(a,p) {op(a.ink,p,'INTERSECT');op(a.cover,p,'INTERSECT');p.delete();return a;}
  function ref(value) {
    const m=/^url\(#(.+)\)$/.exec(value||'');
    if(!m || !defs.has(m[1])) throw Error('Unresolved vector reference: '+value);
    return defs.get(m[1]);
  }
  function opacity(a,key) {
    const v=Number(a[key]??1);
    if(v!==0 && v!==1) throw Error('Partial opacity cannot be represented by a solid vector spline ('+key+').');
    return v;
  }
  function color(s,mode) {
    if(s==='none') return null;
    if(!/^#[0-9a-f]{6}$/i.test(s)) throw Error('Only solid black/white paints are supported; found '+s);
    if(mode==='alpha') return true;
    if(s.toLowerCase()!=='#000000' && s.toLowerCase()!=='#ffffff')
      throw Error('Gray/color paint cannot be represented exactly as a black/white spline.');
    return mode==='mask' ? s.toLowerCase()==='#ffffff' : s.toLowerCase()==='#000000';
  }
  function path(n,clip=false) {
    const p=P.FromSVGString(n.a.d||'');
    if(!p) throw Error('Invalid normalized SVG path.');
    p.setFillType((n.a[clip?'clip-rule':'fill-rule']||'nonzero')==='evenodd'?P.FillType.EVENODD:P.FillType.WINDING);
    return p;
  }
  function stroke(p,a) {
    // Skia's stroker uses a device-space tolerance. Expand in a larger vector
    // coordinate system so small SVG curves are not fitted at screen-pixel precision.
    const precision=128;
    transformed(p,[precision,0,0,precision,0,0]);
    const pattern=(a['stroke-dasharray']||'none');
    if(pattern!=='none') {
      let nums=pattern.trim().split(/[ ,]+/).map(v=>Number(v)*precision);
      if(nums.some(v=>!Number.isFinite(v)||v<0)) throw Error('Invalid stroke dash array.');
      if(nums.length%2) nums=nums.concat(nums);
      const total=nums.reduce((a,b)=>a+b,0);
      if(total>0) {
        const dashed=empty(); let offset=0;
        // Each on interval is one periodic dash; add disjoint open paths before stroking.
        for(let i=0;i<nums.length;i+=2) {
          const part=p.copy();
          if(!part.dash(nums[i],total-nums[i],Number(a['stroke-dashoffset']||0)*precision-offset)) throw Error('Stroke dash conversion failed.');
          dashed.addPath(part);part.delete();offset+=nums[i]+nums[i+1];
        }
        p.delete();p=dashed;
      }
    }
    const caps={butt:P.StrokeCap.BUTT,round:P.StrokeCap.ROUND,square:P.StrokeCap.SQUARE};
    const joins={miter:P.StrokeJoin.MITER,round:P.StrokeJoin.ROUND,bevel:P.StrokeJoin.BEVEL};
    if(!p.stroke({width:Number(a['stroke-width']||1)*precision,miter_limit:Number(a['stroke-miterlimit']||4),
      cap:caps[a['stroke-linecap']||'butt'],join:joins[a['stroke-linejoin']||'miter']})) throw Error('Stroke outline conversion failed.');
    return transformed(p,[1/precision,0,0,1/precision,0,0]);
  }
  function paint(n,m,mode) {
    const a=n.a; const result=layer();
    const order=(a['paint-order']||'fill stroke').split(' ');
    for(const kind of ['fill','stroke']) if(!order.includes(kind)) order.push(kind);
    for(const kind of order) {
      if(kind!=='fill' && kind!=='stroke') continue;
      const paintColor=a[kind]??(kind==='fill'?'#000000':'none');
      if(paintColor==='none' || !opacity(a,kind+'-opacity')) continue;
      const ink=color(paintColor,mode);
      let p=path(n);
      if(kind==='stroke') p=stroke(p,a);
      transformed(p,m);
      // Resolve self intersections and even-odd fills before combining with other paints.
      if(!p.simplify()) throw Error('Path fill simplification failed.');
      compose(result,{ink:ink?p.copy():empty(),cover:p});
    }
    return result;
  }
  function geometry(n,m=ID) {
    m=mul(m,matrix(n.a.transform));
    if(n.tag==='path') return transformed(path(n),m);
    const p=empty();
    for(const child of n.children) {
      if(child.tag==='defs') continue;
      const q=geometry(child,m);p.addPath(q);q.delete();
    }
    return p;
  }
  function bbox(n) {
    // Object bounding box before its own transform and before stroke expansion.
    const g=geometry({...n,a:{...n.a,transform:undefined}});
    const r=g.computeTightBounds();g.delete();
    return [r.fLeft,r.fTop,r.fRight-r.fLeft,r.fBottom-r.fTop];
  }
  function unitsMatrix(units,b) { return units==='objectBoundingBox'?[b[2],0,0,b[3],b[0],b[1]]:ID; }
  function clip(n,m,b,stack) {
    if(stack.has(n)) throw Error('Cyclic clip or mask reference.');
    stack=new Set(stack).add(n);
    m=mul(m,unitsMatrix(n.a.clipPathUnits||'userSpaceOnUse',b));
    m=mul(m,matrix(n.a.transform));
    const p=empty();
    for(const child of n.children) {
      let q;
      if(child.tag==='path') q=transformed(path(child,true),mul(m,matrix(child.a.transform)));
      else if(child.tag==='g') q=clip(child,m,b,stack);
      else throw Error('Unsupported clip geometry: '+child.tag);
      if(child.a['clip-path']) {const c=clip(ref(child.a['clip-path']),mul(m,matrix(child.a.transform)),bbox(child),stack);op(q,c,'INTERSECT');c.delete();}
      op(p,q,'UNION');q.delete();
    }
    if(n.a['clip-path']) {const q=clip(ref(n.a['clip-path']),m,b,stack);op(p,q,'INTERSECT');q.delete();}
    return p;
  }
  function mask(n,m,b,stack) {
    if(stack.has(n)) throw Error('Cyclic mask reference.');
    stack=new Set(stack).add(n);
    const content=mul(m,unitsMatrix(n.a.maskContentUnits||'userSpaceOnUse',b));
    const mode=n.a['mask-type']==='alpha'?'alpha':'mask';
    const a=children(n,content,mode,stack);
    const units=n.a.maskUnits||'objectBoundingBox';
    const vals=['x','y','width','height'].map((k,i)=>{
      const raw=n.a[k]??['-10%','-10%','120%','120%'][i];
      if(String(raw).endsWith('%')) return parseFloat(raw)/100*(units==='objectBoundingBox'?1:Number(tree.a[i%2?'height':'width']));
      return Number(raw);
    });
    const region=transformed(rect(...vals),mul(m,unitsMatrix(units,b)));
    crop(a,region);a.cover.delete();return a.ink;
  }
  function children(n,m,mode,stack) {
    const result=layer();
    for(const child of n.children) if(child.tag!=='defs') compose(result,visit(child,m,mode,stack));
    return result;
  }
  function visit(n,parent,mode,stack) {
    if(!opacity(n.a,'opacity')) return layer();
    const m=mul(parent,matrix(n.a.transform));
    if(n.a.filter) throw Error('SVG filters cannot be converted to exact vector outlines.');
    let result;
    if(n.tag==='path') result=paint(n,m,mode);
    else if(n.tag==='g'||n.tag==='svg') result=children(n,m,mode,stack);
    else throw Error('Unsupported vector element: '+n.tag+'. Convert it to paths first.');
    if(n.a['clip-path']) crop(result,clip(ref(n.a['clip-path']),m,bbox(n),stack));
    if(n.a.mask) crop(result,mask(ref(n.a.mask),m,bbox(n),stack));
    return result;
  }
  const result=visit(tree,ID,'normal',new Set());
  crop(result,rect(0,0,Number(tree.a.width),Number(tree.a.height)));
  fs.writeFileSync(process.argv[3],JSON.stringify({commands:result.ink.toCmds(),engine:'Skia PathKit 1.0.0 vector'}));
  dispose(result);
}
main().catch(error=>{console.error(error.stack||error.message);process.exit(1);});
