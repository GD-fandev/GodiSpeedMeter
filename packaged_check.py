"""Opt-in packaged runtime smoke check: --self-test REPORT.json."""
import json
from pathlib import Path
import traceback


def run(report_path):
    report={}
    app=None
    try:
        import tkinter as tk
        from PIL import Image,ImageDraw,ImageFont
        from paddle_ocr_backend import PaddleOcrBackend
        from auto_ui.geometry import sprite
        from desktop_capture import DesktopCapture
        from app import App,ROOT,DATA_ROOT
        from i18n import TEXT
        report['bundled_assets']=bool(sprite(69).size and sprite(210).size)
        im=Image.new('RGB',(220,55),'black')
        ImageDraw.Draw(im).text((10,8),'123:456',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',32),fill='white')
        report['ocr']=PaddleOcrBackend(ROOT/'models').recognize_coordinates(im)
        assert report['ocr']=='123:456'
        capture=DesktopCapture()
        try:
            image,_=capture.capture_client((0,0,100,50))
            report['capture_size']=list(image.size)
        finally:capture.close()
        root=tk.Tk();root.withdraw()
        app=App(root)
        for language in ('KOR','JPN','ENG'):
            app.language.set(language);app.render();root.update_idletasks()
            assert root.title()=='GodiSpeedMeter · Ctrl+F'
            assert set(TEXT[language])==set(TEXT['KOR'])
        assert app.engine.ready.wait(20),'Engine initialization timed out'
        report['engine_ready']=True
        # Exercise the real mapped EXE window, not just Python-level settings.
        import ctypes
        import time
        from ctypes import wintypes
        from PIL import ImageGrab
        root.geometry('+40+40');root.deiconify();root.update()
        user=ctypes.windll.user32
        hwnd=user.GetAncestor(root.winfo_id(),2)
        user.GetWindowDisplayAffinity.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        affinity=wintypes.DWORD()
        assert user.GetWindowDisplayAffinity(hwnd,ctypes.byref(affinity))
        report['capture_affinity']=affinity.value
        assert affinity.value==0
        report['obs_toolwindow']=bool(user.GetWindowLongW(hwnd,-20)&0x80)
        assert not report['obs_toolwindow']
        marker=tk.Canvas(root,width=24,height=24,bg='#12ab34',highlightthickness=0)
        marker.place(x=20,y=20);root.update()
        captured=False
        for _ in range(20):
            root.update();time.sleep(.1)
            x,y=marker.winfo_rootx()+12,marker.winfo_rooty()+12
            pixel=ImageGrab.grab(bbox=(x,y,x+1,y+1),include_layered_windows=True).convert('RGB').getpixel((0,0))
            if pixel==(18,171,52):
                captured=True
                break
        report['window_visible_in_screenshot']=captured
        assert captured,'Application window missing from desktop screenshot'
        marker.destroy()
        report['languages']=list(TEXT)
        report['data_next_to_exe']=DATA_ROOT!=ROOT
        report['ok']=True
    except Exception:
        report['ok']=False
        report['error']=traceback.format_exc()
    finally:
        if app:app.close()
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not report['ok']:raise SystemExit(1)
