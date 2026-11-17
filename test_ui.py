import queue
import tempfile
import json
from pathlib import Path
import tkinter as tk
import unittest
from unittest.mock import patch
from app import App
from measurement import Measurement


class FakeEngine:
    def __init__(self,*args): self.commands=queue.Queue()
    def close(self): pass


class InterfaceTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk(); self.root.withdraw()
        with patch.object(App,'hotkeys',return_value=None):
            self.app=App(self.root,engine_factory=FakeEngine)
        self.temp=tempfile.TemporaryDirectory()
        self.app.log_path=Path(self.temp.name)/'trials.jsonl'
        self.app.language.set('KOR'); self.app.render()
        self.app.ready=True
    def tearDown(self):
        self.app.close()
        self.temp.cleanup()
    def test_language_switch_reformats_current_result_and_history_headers(self):
        self.app.result_state=('result_value',{'value':235.8})
        self.app.status_state=('complete',dict(intervals=5,cells=5,seconds=1.179))
        self.app.language.set('JPN'); self.app.render()
        self.assertEqual(self.app.result.get(),'235.800 ms/マス')
        self.assertIn('区間',self.app.status.get())
        self.assertEqual(self.app.history.heading('cells')['text'],'有効マス数')
        self.app.language.set('KOR'); self.app.render()
        self.assertEqual(self.app.result.get(),'235.800 ms/칸')
    def test_cancel_ignores_previous_session_result(self):
        self.app.start(); old=self.app.request
        self.app.cancel()
        self.app.events.put((old,'done',{'measurement':Measurement()}))
        self.app.poll()
        self.assertEqual(self.app.result_state[0],'result_empty')
        self.assertEqual(self.app.status_state[0],'cancelled')
    def test_completed_run_adds_history_and_survives_language_switch(self):
        self.app.start()
        m=Measurement()
        for point,t in [((0,0),0),((1,0),.1),((2,0),.3),((3,0),.5),((4,0),.7),((4,0),1.5)]: m.observe(point,t)
        self.app.events.put((self.app.request,'done',{'measurement':m})); self.app.poll()
        self.assertEqual(len(self.app.history.get_children()),1)
        self.app.language.set('JPN'); self.app.render()
        self.assertEqual(self.app.result.get(),'200.000 ms/マス')
    def test_all_attempts_mean_and_clear_during_active_run(self):
        self.app.trial_values.extend([238.105,238.012])
        self.app.history_count=2
        self.app.history.insert('',0,values=(1,71,'16.90','238.012'))
        self.app.render()
        self.assertIn('2회',self.app.aggregate.get())
        self.assertIn(f'{(238.105+238.012)/2:.3f}',self.app.aggregate.get())
        self.app.start()
        request=self.app.request
        self.app.clear_history()
        self.assertEqual(self.app.request,request)
        self.assertEqual(self.app.result_state[0],'result_running')
        self.assertEqual(self.app.history_count,0)
        self.assertFalse(self.app.trial_values)
        self.assertFalse(self.app.history.get_children())
        self.assertIn('0회',self.app.aggregate.get())
    def test_more_than_twenty_successes_retained_and_equal_weighted(self):
        for i in range(25):
            self.app.start()
            m=Measurement()
            m.intervals=[(200+i,1),(300,1)]
            self.app.events.put((self.app.request,'done',{'measurement':m}))
            self.app.poll()
        self.assertEqual(len(self.app.history.get_children()),25)
        self.assertEqual(len(self.app.trial_values),25)
        self.assertIn('212.000',self.app.aggregate.get())
    def test_overlay_and_font_sized_rows(self):
        from tkinter import font as tkfont
        self.assertTrue(self.root.overrideredirect())
        self.root.update_idletasks()
        line=tkfont.Font(root=self.root,family='Malgun Gothic',size=10).metrics('linespace')
        self.assertGreaterEqual(int(self.app.style.lookup('Treeview','rowheight')),line+8)

    def test_broadcast_window_is_capturable_after_show_and_remap(self):
        import ctypes
        from ctypes import wintypes
        user=ctypes.windll.user32
        user.GetWindowDisplayAffinity.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        for _ in range(2):
            self.root.deiconify(); self.root.update()
            hwnd=user.GetAncestor(self.root.winfo_id(),2)
            affinity=wintypes.DWORD()
            self.assertTrue(user.GetWindowDisplayAffinity(hwnd,ctypes.byref(affinity)))
            self.assertEqual(affinity.value,0)
            style=user.GetWindowLongW(hwnd,-20)
            self.assertFalse(style & 0x80,'OBS excludes tool windows')
            self.assertTrue(style & 0x40000)
            self.assertTrue(self.root.overrideredirect())
            self.assertTrue(self.root.attributes('-topmost'))
            self.root.withdraw(); self.root.update()

    def test_record_details_exclusion_restore_and_log(self):
        from diagnostics import Diagnostics
        m=Measurement(); m.intervals=[(238,1)]*72
        d=Diagnostics(); d.capture(0); d.capture(.3)
        item=self.app.add_record(m,d.snapshot())
        self.app.render()
        self.assertIn('capture_severe',self.app.records[item]['reasons'])
        self.assertEqual(self.app.trial_values,[238])
        self.app.history.selection_set(item)
        self.app.toggle_selected(); self.assertEqual(self.app.trial_values,[])
        self.assertFalse(self.app.records[item]['included'])
        self.app.toggle_selected(); self.assertEqual(self.app.trial_values,[238])
        events=[json.loads(line) for line in self.app.log_path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([e['event'] for e in events],['trial','inclusion','inclusion'])
        self.assertEqual(events[0]['record']['diagnostics']['max_gap_ms'],300)
        self.app.clear_history()
        self.assertFalse(self.app.records)
        self.assertTrue(self.app.log_path.exists())

    def test_all_error_states_render_in_both_languages(self):
        for language in ('KOR','JPN','ENG'):
            self.app.language.set(language)
            for code in ('no_game','no_hud','foreground','overflow','reader_error','unreadable','direction','diagonal'):
                self.app.status_state=(code,{})
                self.app.render()
                self.assertTrue(self.app.status.get())

if __name__=='__main__': unittest.main()
