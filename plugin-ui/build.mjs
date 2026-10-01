import { build } from 'esbuild';
import { mkdir, copyFile, writeFile, readFile } from 'node:fs/promises';
import { dirname, resolve, parse } from 'node:path';
import { fileURLToPath } from 'node:url';
const root=dirname(fileURLToPath(import.meta.url));
const out=resolve(root,'../src/codex_eval_lab/ui');
await mkdir(out,{recursive:true});
const bundled=new Set();
for(const entry of ['app','standalone','calibration']){
 const result=await build({absWorkingDir:root,entryPoints:[resolve(root,`src/${entry}.js`)],outfile:resolve(out,`${entry}.js`),bundle:true,format:'iife',platform:'browser',target:['es2020'],minify:true,legalComments:'eof',metafile:true});
 for(const input of Object.keys(result.metafile.inputs))if(input.includes('node_modules/'))bundled.add(resolve(root,input));
}
await copyFile(resolve(root,'src/review.css'),resolve(out,'review.css'));
await copyFile(resolve(root,'src/review.html'),resolve(out,'review.html'));
await copyFile(resolve(root,'src/calibration.html'),resolve(out,'calibration.html'));
const packages=new Map();
for(const input of bundled){let dir=dirname(input);while(dir!==root&&dir!==parse(dir).root){try{const pkg=JSON.parse(await readFile(resolve(dir,'package.json'),'utf8'));if(pkg.name){packages.set(pkg.name,{...pkg,path:dir});break;}}catch{}dir=dirname(dir);}}
let notices='Bundled browser UI third-party notices. Versions are pinned by plugin-ui/package-lock.json.\nPackage metadata license labels are informational; the complete upstream license text follows each label.\n';
for(const [name,pkg]of [...packages.entries()].sort()){
 let license='';for(const file of ['LICENSE','LICENSE.txt','LICENSE.md','LICENSE-MIT']){try{license=await readFile(resolve(pkg.path,file),'utf8');break;}catch{}}
 if(!license)throw Error(`Missing bundled license for ${name}`);
 notices+=`\n${'='.repeat(72)}\n${name} ${pkg.version} (package metadata: ${pkg.license||'see license'})\n${'='.repeat(72)}\n${license}\n`;
}
await writeFile(resolve(out,'THIRD_PARTY_NOTICES.txt'),notices);
