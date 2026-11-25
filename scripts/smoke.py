"""Exercise the starter scene with real browser input; disconnect the web export after loading."""
import argparse
import io
from pathlib import Path
from playwright.sync_api import sync_playwright
from PIL import Image


def check(url,backend,touch,channel,picture):
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel=channel,headless=True)
        try:
            context=browser.new_context(viewport={"width":900,"height":500},is_mobile=touch,has_touch=touch)
            page=context.new_page()
            errors, sockets=[],[]
            def page_error(exc):
                errors.append(str(exc))
                print("Browser error:",exc,flush=True)
            page.on("pageerror",page_error)
            page.on("console",lambda msg: print(msg.type,msg.text[:400],flush=True) if msg.type in ("warning","error","log") else None)
            page.on("websocket",lambda ws:sockets.append(ws.url))
            page.goto(url,wait_until="domcontentloaded")
            page.wait_for_function("window.threeGame?.snapshot()?.tick>0 && parseInt(document.querySelector('#fps').textContent)>0",timeout=60000)
            snap=lambda:page.evaluate("threeGame.snapshot()")
            start=snap()
            assert start["backend"]==backend,start
            if backend=="wasm":
                assert not sockets,sockets
                context.set_offline(True)
            else:
                assert any("/poses?" in uri for uri in sockets),sockets
            if touch:
                cdp=context.new_cdp_session(page)
                def point(sel,idx,dx=0):
                    r=page.locator(sel).bounding_box()
                    return {"id":idx,"x":r["x"]+r["width"]/2+dx,"y":r["y"]+r["height"]/2}
                stick=point("#stick",1,35)
                cdp.send("Input.dispatchTouchEvent",{"type":"touchStart","touchPoints":[stick]})
                page.wait_for_timeout(120)
                cdp.send("Input.dispatchTouchEvent",{"type":"touchStart","touchPoints":[stick,point("#jump",2)]})
            else:
                page.keyboard.down("d")
                page.keyboard.down("Space")
            page.wait_for_function("p=>threeGame.snapshot().position[0]>p[0]+.15 && threeGame.snapshot().position[1]>p[1]+.25",
                                   arg=start["position"],timeout=3000)
            if touch:
                cdp.send("Input.dispatchTouchEvent",{"type":"touchEnd","touchPoints":[]})
                page.locator("#fullscreen").tap()
                page.wait_for_function("!!document.fullscreenElement")
            else:
                page.keyboard.up("Space")
                page.keyboard.up("d")
            page.wait_for_function("p=>Math.abs(threeGame.snapshot().position[1]-p[1])<.03",arg=start["position"],timeout=4000)
            png=page.screenshot(path=str(picture) if picture else None)
            im=Image.open(io.BytesIO(png)).convert("RGB")
            w,h=im.size
            colors=im.crop((w//4,h//4,3*w//4,3*h//4)).getcolors(w*h)
            assert len([c for n,c in colors if n>20])>=3,"Blank game canvas"
            assert snap()["tick"]>start["tick"] and not errors,errors
            print("PASS",backend,"touch" if touch else "keyboard",snap(),page.locator("#fps").inner_text())
        finally:
            browser.close()


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("url")
    p.add_argument("--backend",choices=("native","wasm"),required=True)
    p.add_argument("--touch",action="store_true")
    p.add_argument("--channel",default=None,help="For example chrome. Default: Playwright Chromium.")
    p.add_argument("--screenshot",type=Path)
    a=p.parse_args()
    check(a.url,a.backend,a.touch,a.channel,a.screenshot)
