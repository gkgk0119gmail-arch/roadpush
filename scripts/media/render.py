import sys, asyncio
from pathlib import Path
from playwright.async_api import async_playwright
html, outdir, w, h = Path(sys.argv[1]).resolve(), Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
ids = sys.argv[5].split(',')
transparent = len(sys.argv) > 6 and sys.argv[6] == 'alpha'
async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={'width': w, 'height': h})
        await pg.goto(html.as_uri()); await pg.wait_for_timeout(500)
        for i in ids:
            await pg.locator('#' + i).screenshot(path=str(outdir / f'{i}.png'), omit_background=transparent)
        await b.close()
asyncio.run(main())
