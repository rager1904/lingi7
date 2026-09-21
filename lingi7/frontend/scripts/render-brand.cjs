// Reproducible local export. Uses the bundled Playwright path supplied via NODE_PATH.
const fs = require('node:fs');
const path = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
(async () => {
  const output = path.resolve(__dirname, '../public/brand');
  const { logoSvg, phase, duration } = await import(pathToFileURL(path.join(output, 'logo-source.mjs')));
  fs.writeFileSync(path.join(output, 'l7.svg'), logoSvg());
  fs.writeFileSync(path.join(output, 'l7-animated.svg'), logoSvg({ animated: true }));
  fs.writeFileSync(path.join(output, 'l7-poster.svg'), logoSvg({ film: true }));
  fs.writeFileSync(path.join(output, 'l7-icon.svg'), logoSvg().replace('0 0 560 200', '188 24 162 158'));
  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
    await page.setContent('<canvas width="1280" height="720"></canvas>');
    const frames = Array.from({ length: 241 }, (_, i) => logoSvg({ progress: phase(i * duration / 240), film: true }));
    const data = await page.evaluate(async ({ frames }) => {
      const canvas = document.querySelector('canvas');
      const ctx = canvas.getContext('2d');
      const images = await Promise.all(frames.map(svg => new Promise((resolve, reject) => {
        const timer = setTimeout(() => reject(new Error('SVG image decode timed out')), 15000);
        const img = new Image(); img.onload = () => { clearTimeout(timer); resolve(img); };
        img.onerror = () => { clearTimeout(timer); reject(new Error('Invalid SVG frame')); };
        img.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(svg);
      })));
      ctx.drawImage(images[0], 0, 0);
      const stream = canvas.captureStream(30);
      const recorder = new MediaRecorder(stream, { mimeType: 'video/webm;codecs=vp9', videoBitsPerSecond: 2500000 });
      const chunks = [];
      recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
      const done = new Promise(resolve => { recorder.onstop = async () => resolve(Array.from(new Uint8Array(await new Blob(chunks).arrayBuffer()))); });
      recorder.start();
      const start = performance.now();
      await new Promise(resolve => {
        function draw(now) {
          const i = Math.min(240, Math.floor((now - start) / 8000 * 240));
          ctx.drawImage(images[i], 0, 0);
          if (now - start < 8000) setTimeout(() => draw(performance.now()), 1000 / 30); else resolve();
        }
        draw(performance.now());
      });
      recorder.stop(); stream.getTracks().forEach(track => track.stop());
      return done;
    }, { frames });
    fs.writeFileSync(path.join(output, 'lingi7-reveal.webm'), Buffer.from(data));
    for (const [name, progress] of [['compact', 0], ['expanded', 1]]) {
      await page.setContent(logoSvg({ progress, film: true }));
      await page.screenshot({ path: path.join(output, `${name}-preview.png`) });
    }
    console.log('Exported static/animated SVGs, poster, 8-second WebM and preview frames.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
