const fs = require('fs');
const path = require('path');

function ensureDirSync(dir) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

function tryCopy(srcPaths, dest) {
  for (const srcPath of srcPaths) {
    const fullSrc = path.resolve(srcPath);
    if (fs.existsSync(fullSrc)) {
      ensureDirSync(path.dirname(dest));
      fs.copyFileSync(fullSrc, dest);
      console.log(`Copied ${fullSrc} -> ${dest}`);
      return true;
    }
  }
  console.warn(`WARN: None of the candidate paths exist for destination ${dest}`);
  return false;
}

// run from webapp/
const mappings = [
  {
    src: [
      'node_modules/jquery/dist/jquery.min.js'
    ],
    dest: 'static/vendor/jquery/jquery.min.js'
  },
  {
    src: [
      'node_modules/bootstrap/dist/css/bootstrap.min.css'
    ],
    dest: 'static/vendor/bootstrap/css/bootstrap.min.css'
  },
  {
    src: [
      'node_modules/bootstrap/dist/css/bootstrap-theme.min.css'
    ],
    dest: 'static/vendor/bootstrap/css/bootstrap-theme.min.css'
  },
  {
    src: [
      'node_modules/bootstrap/dist/js/bootstrap.min.js'
    ],
    dest: 'static/vendor/bootstrap/js/bootstrap.min.js'
  },
  {
    // opensheetmusicdisplay path may vary between versions
    src: [
      'node_modules/opensheetmusicdisplay/build/opensheetmusicdisplay.min.js',
      'node_modules/opensheetmusicdisplay/dist/opensheetmusicdisplay.min.js',
      'node_modules/opensheetmusicdisplay/opensheetmusicdisplay.min.js'
    ],
    dest: 'static/vendor/opensheetmusicdisplay/opensheetmusicdisplay.min.js'
  }
];

for (const m of mappings) {
  const destPath = path.resolve(m.dest);
  const srcCandidates = m.src.map(p => path.resolve(p));
  tryCopy(srcCandidates, destPath);
}
