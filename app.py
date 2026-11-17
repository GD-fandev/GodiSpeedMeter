"""Windows coordinate speed meter with Korean/Japanese UI."""
import ctypes
import sys
import json
import math
import uuid
from datetime import datetime, timezone, timedelta
from diagnostics import review
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter import font as tkfont
from engine import Engine
from i18n import translate

ROOT=Path(__file__).resolve().parent
DATA_ROOT=Path(sys.executable).resolve().parent if getattr(sys,"frozen",False) else ROOT


class App:
    def __init__(self,root,engine_factory=Engine):
        self.root=root
        root.geometry('760x680')
        root.minsize(640,560)
        root.overrideredirect(True)
        root.attributes('-topmost',True)
        root.configure(bg='#d8b15a')
        self.events=queue.Queue()
        self.stop=threading.Event()
        self.request=0
        self.ready=False
        language='KOR'
        try:
            saved=json.loads((DATA_ROOT/'preferences.json').read_text(encoding='utf-8'))
            if saved.get('language') in ('KOR','JPN','ENG'):
                language=saved['language']
        except (OSError,ValueError,AttributeError):
            pass
        self.language=tk.StringVar(value=language)
        self.timeout=tk.StringVar(value='700')
        self.delay=tk.StringVar(value='0')
        self.status=tk.StringVar()
        self.result=tk.StringVar()
        self.live=tk.StringVar()
        self.status_state=('initializing',{})
        self.result_state=('result_empty',{})
        self.live_state=('live_empty',{})
        self.labels=[]
        self.history_count=0
        self.trial_values=[]
        self.records={}
        self.log_failure=""
        self.log_path=DATA_ROOT/"logs"/f"trials_{uuid.uuid4().hex[:12]}.jsonl"
        self.aggregate=tk.StringVar()
        self.compact_live=tk.StringVar()
        self.details_open=False
        self.wrap_widgets=[]
        self.style=ttk.Style(root)
        self.style.theme_use('clam')
        outer=ttk.Frame(root,style='Outer.TFrame',padding=1)
        outer.pack(fill='both',expand=True,padx=1,pady=1)
        title=ttk.Frame(outer,style='Header.TFrame',padding=(10,5))
        title.pack(fill='x')
        caption=ttk.Label(title,text='GodiSpeedMeter',style='Header.TLabel',cursor='fleur')
        caption.pack(side='left',fill='x',expand=True)
        for lang in ('KOR','JPN','ENG'):
            ttk.Radiobutton(title,text=lang,value=lang,variable=self.language,command=self.change_language).pack(side='left',padx=3)
        ttk.Button(title,text='×',width=3,command=self.close).pack(side='right',padx=(8,0))
        for widget in (title,caption):
            widget.bind('<ButtonPress-1>',self.begin_drag)
            widget.bind('<B1-Motion>',self.drag)
        box=ttk.Frame(outer,padding=(14,8))
        box.pack(fill='both',expand=True)
        self.label(box,'heading',style='Muted.TLabel').pack()
        ttk.Label(box,textvariable=self.result,style='Result.TLabel').pack(pady=(2,3))
        ttk.Label(box,textvariable=self.aggregate,style='Aggregate.TLabel').pack(pady=(0,6))
        ttk.Label(box,textvariable=self.compact_live,style='Muted.TLabel').pack()
        status_label=ttk.Label(box,textvariable=self.status,justify='center')
        status_label.pack(fill='x',pady=6)
        self.wrap_widgets.append(status_label)
        row=ttk.Frame(box); row.pack(pady=3)
        self.button(row,'start',self.start).pack(side='left',padx=3)
        self.button(row,'cancel',self.cancel).pack(side='left',padx=3)
        self.button(row,'clear_history',self.clear_history).pack(side='left',padx=3)
        self.button(row,'details',self.toggle_details).pack(side='left',padx=3)
        self.details=ttk.Frame(box,padding=(4,6))
        self.details_anchor=ttk.Frame(box)
        self.details_anchor.pack(fill='x')
        row=ttk.Frame(self.details); row.pack()
        for key,var in [('timeout',self.timeout),('delay',self.delay)]:
            self.label(row,key).pack(side='left',padx=4)
            ttk.Entry(row,textvariable=var,width=7).pack(side='left')
        diagnostics=ttk.Label(self.details,textvariable=self.live,justify='center',style='Muted.TLabel')
        diagnostics.pack(fill='x',pady=5)
        self.wrap_widgets.append(diagnostics)
        heading=ttk.Frame(box); heading.pack(fill='x',pady=(8,4))
        self.label(heading,'history').pack(side='left')
        self.label(heading,'mean_hint',style='Muted.TLabel').pack(side='right')
        actions=ttk.Frame(box); actions.pack(fill='x',pady=(0,4))
        self.button(actions,'trial_details',self.show_trial).pack(side='left',padx=2)
        self.button(actions,'toggle_include',self.toggle_selected).pack(side='left',padx=2)
        table=ttk.Frame(box); table.pack(fill='both',expand=True)
        table.rowconfigure(0,weight=1); table.columnconfigure(0,weight=1)
        self.history=ttk.Treeview(table,columns=('number','cells','seconds','average','max_gap','max_lag','quality','included'),show='headings',height=5)
        for col,width in [('number',65),('cells',110),('seconds',150),('average',160),('max_gap',145),('max_lag',145),('quality',130),('included',130)]:
            self.history.column(col,width=width,minwidth=width,anchor='center',stretch=True)
        self.history.grid(row=0,column=0,sticky='nsew')
        scrollbar=ttk.Scrollbar(table,orient='vertical',command=self.history.yview)
        scrollbar.grid(row=0,column=1,sticky='ns')
        horizontal=ttk.Scrollbar(table,orient='horizontal',command=self.history.xview)
        horizontal.grid(row=1,column=0,sticky='ew')
        self.history.configure(yscrollcommand=scrollbar.set,xscrollcommand=horizontal.set)
        self.history.bind('<Double-1>',lambda event:self.show_trial())
        self.history.tag_configure('review',foreground='#ffc26a')
        self.history.tag_configure('excluded',foreground='#958b7d')
        footer=ttk.Frame(outer,padding=(10,3)); footer.pack(side='bottom',fill='x',before=box)
        self.label(footer,'overlay_hint',style='Muted.TLabel').pack(side='left')
        grip=ttk.Label(footer,text='◢',cursor='size_nw_se',style='Aggregate.TLabel')
        grip.pack(side='right')
        grip.bind('<ButtonPress-1>',self.begin_resize)
        grip.bind('<B1-Motion>',self.resize)
        root.bind('<Configure>',self.on_configure)
        root.after(100,self.exclude_capture)
        self.render()
        self.engine=engine_factory(ROOT/'models',self.events)
        self.hotkey_thread=threading.Thread(target=self.hotkeys,daemon=True)
        self.hotkey_thread.start()
        root.after(20,self.poll)
        root.protocol('WM_DELETE_WINDOW',self.close)

    def label(self,parent,key,**options):
        widget=ttk.Label(parent,**options)
        self.labels.append((widget,key))
        return widget

    def button(self,parent,key,command):
        widget=ttk.Button(parent,command=command)
        self.labels.append((widget,key))
        return widget

    def text(self,key,**values):
        return translate(self.language.get(),key,**values)

    def render(self):
        self.root.title(self.text('title'))
        font={'KOR':'Malgun Gothic','JPN':'Yu Gothic UI','ENG':'Segoe UI'}[self.language.get()]
        self.style.configure('.',font=(font,10),background='#2a2118',foreground='#fff1c9')
        self.style.configure('TFrame',background='#2a2118')
        self.style.configure('Outer.TFrame',background='#17130f')
        self.style.configure('Header.TFrame',background='#5a4932')
        self.style.configure('Header.TLabel',background='#5a4932',foreground='#ffe09a',font=(font,10,'bold'))
        self.style.configure('Muted.TLabel',foreground='#bda982')
        self.style.configure('Result.TLabel',foreground='#ffe09a',font=(font,25,'bold'))
        self.style.configure('Aggregate.TLabel',foreground='#d8b15a',font=(font,12,'bold'))
        self.style.configure('TButton',background='#3b3022',foreground='#fff1c9',padding=(7,5),borderwidth=1)
        self.style.map('TButton',background=[('active','#6b5537')])
        self.style.configure('TRadiobutton',background='#5a4932',foreground='#fff1c9')
        self.style.map('TRadiobutton',background=[('active','#6b5537')])
        self.style.configure('TEntry',fieldbackground='#17130f',foreground='#fff1c9',insertcolor='#fff1c9')
        metrics=tkfont.Font(root=self.root,family=font,size=10)
        self.style.configure('Treeview',background='#17130f',fieldbackground='#17130f',foreground='#fff1c9',
                             rowheight=metrics.metrics('linespace')+12,borderwidth=0)
        self.style.configure('Treeview.Heading',background='#5a4932',foreground='#ffe09a',font=(font,10),padding=(6,7))
        self.style.map('Treeview',background=[('selected','#6b5537')],foreground=[('selected','#fff8df')])
        self.style.map('Treeview.Heading',background=[('active','#6b5537')])
        for widget,key in self.labels:
            widget.configure(text=self.text(key))
        for var,state in [(self.status,self.status_state),(self.result,self.result_state),(self.live,self.live_state)]:
            var.set(self.text(state[0],**state[1]))
        if self.log_failure:
            self.status.set(self.status.get()+'\n'+self.text('log_error',detail=self.log_failure))
        self.refresh_rows()
        self.aggregate.set(self.text('all_mean',count=len(self.trial_values),value=math.fsum(self.trial_values)/len(self.trial_values))
                           if self.trial_values else self.text('all_mean_empty'))
        self.compact_live.set(self.text('live_compact',**self.live_state[1]) if self.live_state[0]=='live' else self.text('live_empty'))
        for col in self.history['columns']:
            self.history.heading(col,text=self.text(col))

    def clear_history(self):
        self.write_log({"event":"clear_history"})
        self.records.clear()
        self.trial_values.clear()
        self.history_count=0
        for item in self.history.get_children(): self.history.delete(item)
        if self.result_state[0]!='result_running': self.result_state=('result_empty',{})
        self.render()

    def write_log(self, payload):
        try:
            self.log_path.parent.mkdir(parents=True,exist_ok=True)
            data=dict(payload,logged_at=datetime.now(timezone(timedelta(hours=9))).isoformat())
            with self.log_path.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(data,ensure_ascii=False)+'\n')
        except OSError as exc:
            self.log_failure=str(exc)

    def add_record(self, measurement, diagnostics=None):
        m=measurement
        average=None if m.error else m.average_ms
        cells=sum(n for _,n in m.kept)
        seconds=sum(t for t,_ in m.kept)/1000
        reasons=review(average,cells,m.kept,diagnostics,self.trial_values)
        self.history_count+=1
        record=dict(number=self.history_count,average=average,cells=cells,seconds=seconds,
                    included=average is not None,diagnostics=diagnostics,reasons=reasons,
                    intervals=list(m.kept),error=m.error,
                    settings=dict(timeout_ms=self.timeout.get(),extra_wait_ms=self.delay.get()))
        item=self.history.insert('',0)
        self.records[item]=record
        if average is not None:self.trial_values.append(average)
        self.write_log(dict(event='trial',record=record))
        return item

    def refresh_rows(self):
        for item,record in self.records.items():
            d=record['diagnostics'] or {}
            values=(record['number'],record['cells'],f"{record['seconds']:.2f}",
                    '—' if record['average'] is None else f"{record['average']:.3f}",
                    '—' if not d else f"{d['max_gap_ms']:.2f}",
                    '—' if not d else f"{d['max_lag_ms']:.2f}",
                    self.text('review_required' if record['reasons'] else 'no_flags'),
                    self.text('yes' if record['included'] else 'no'))
            self.history.item(item,values=values,tags=('excluded' if not record['included'] else 'review' if record['reasons'] else 'normal',))

    def toggle_selected(self):
        for item in self.history.selection():
            record=self.records.get(item)
            if record is None or record['average'] is None:continue
            record['included']=not record['included']
            self.write_log(dict(event='inclusion',number=record['number'],included=record['included']))
        self.trial_values[:]=[r['average'] for r in self.records.values() if r['included'] and r['average'] is not None]
        self.render()

    def show_trial(self):
        selected=self.history.selection()
        if not selected or selected[0] not in self.records:return
        record=self.records[selected[0]]
        d=record['diagnostics']
        lines=[self.text('trial_number',number=record['number']),
               self.text('included')+': '+self.text('yes' if record['included'] else 'no')]
        if record['average'] is not None:lines.append(self.text('result_value',value=record['average']))
        if d:
            for field,key in [('mean_gap_ms','mean_gap'),('max_gap_ms','max_gap'),('max_lag_ms','max_lag'),
                              ('max_ocr_ms','max_ocr'),('max_backlog','peak_queue'),('ocr_calls','ocr_count'),('ocr_failures','ocr_failed')]:
                value=d.get(field,0)
                lines.append(f"{self.text(key)}: {value:.3f}" if field.endswith('_ms') else f"{self.text(key)}: {value}")
        lines.extend(['',self.text('review_note')])
        lines.extend('• '+self.text('reason_'+reason) for reason in record['reasons'])
        if not record['reasons']:lines.append(self.text('no_flags'))
        lines.extend(['',self.text('scope_note'),''])
        if d:
            lines.append(self.text('event_list'))
            for event in d.get('events',[]):
                lines.append(f"+{event['at_seconds']:.3f}s  {self.text('event_'+event['kind'])}: {event['ms']:.2f}ms")
        lines.extend(['',self.text('log_location'),str(self.log_path)])
        window=tk.Toplevel(self.root)
        window.title(self.text('trial_details')); window.geometry('740x620')
        window.attributes('-topmost',True)
        body=ttk.Frame(window,padding=12); body.pack(fill='both',expand=True)
        text=tk.Text(body,wrap='char',bg='#17130f',fg='#fff1c9',insertbackground='#fff1c9',font=({'KOR':'Malgun Gothic','JPN':'Yu Gothic UI','ENG':'Segoe UI'}[self.language.get()],10))
        scroll=ttk.Scrollbar(body,command=text.yview)
        scroll.pack(side='right',fill='y'); text.pack(fill='both',expand=True)
        text.configure(yscrollcommand=scroll.set)
        text.insert('1.0','\n'.join(lines)); text.configure(state='disabled')

    def toggle_details(self):
        self.details_open=not self.details_open
        if self.details_open:
            self.details.pack(before=self.details_anchor,fill='x')
            self.root.geometry(f'{self.root.winfo_width()}x{max(740,self.root.winfo_height())}')
        else:
            self.details.pack_forget()

    def begin_drag(self,event):
        self.drag_origin=(event.x_root,event.y_root,self.root.winfo_x(),self.root.winfo_y())

    def drag(self,event):
        x,y,left,top=self.drag_origin
        from ctypes import wintypes
        user=ctypes.windll.user32
        user.GetParent.argtypes=[wintypes.HWND]; user.GetParent.restype=wintypes.HWND
        user.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.UINT]
        hwnd=user.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        user.SetWindowPos(hwnd,None,left+event.x_root-x,top+event.y_root-y,0,0,0x0015)

    def begin_resize(self,event):
        self.resize_origin=(event.x_root,event.y_root,self.root.winfo_width(),self.root.winfo_height())

    def resize(self,event):
        x,y,width,height=self.resize_origin
        self.root.geometry(f'{max(640,width+event.x_root-x)}x{max(560,height+event.y_root-y)}')

    def on_configure(self,event):
        if event.widget is self.root:
            for widget in self.wrap_widgets: widget.configure(wraplength=max(250,event.width-44))

    def exclude_capture(self):
        from ctypes import wintypes
        user=ctypes.windll.user32
        user.GetParent.argtypes=[wintypes.HWND]; user.GetParent.restype=wintypes.HWND
        user.SetWindowDisplayAffinity.argtypes=[wintypes.HWND,wintypes.DWORD]
        hwnd=user.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        self.capture_excluded=bool(user.SetWindowDisplayAffinity(hwnd,0x11))

    def change_language(self):
        self.render()
        try:
            (DATA_ROOT/'preferences.json').write_text(json.dumps({'language':self.language.get()}),encoding='utf-8')
        except OSError:
            pass

    def hotkeys(self):
        user=ctypes.windll.user32
        previous=False
        while not self.stop.wait(.005):
            down=bool(user.GetAsyncKeyState(0x11)&0x8000 and user.GetAsyncKeyState(0x46)&0x8000)
            if down and not previous:
                self.events.put((None,'hotkey',{}))
            previous=down

    def start(self):
        if not self.ready:
            return
        try:
            timeout,delay=float(self.timeout.get()),float(self.delay.get())
            if not all(map(math.isfinite,(timeout,delay))) or not 50<=timeout<=60000 or not 0<=delay<=1000:
                raise ValueError
        except ValueError:
            messagebox.showerror(self.text('settings_error'),self.text('settings_detail'))
            return
        self.request+=1
        self.result_state=('result_running',{})
        self.status_state=('searching',{})
        self.live_state=('live_empty',{})
        self.engine.commands.put((self.request,'start',timeout/1000,delay/1000))
        self.render()

    def cancel(self):
        self.request+=1
        self.engine.commands.put((self.request,'cancel'))
        self.result_state=('result_empty',{})
        self.status_state=('cancelled',{})
        self.render()

    def poll(self):
        dirty=False
        try:
            while True:
                request,kind,data=self.events.get_nowait()
                if kind=='hotkey':
                    self.start(); continue
                if kind=='ready':
                    self.ready=True
                    if self.request==0: self.status_state=('ready',{})
                elif kind=='fatal':
                    self.ready=False
                    self.status_state=('fatal',data)
                    self.result_state=('result_invalid',{})
                elif request!=self.request:
                    continue
                elif kind=='discarded':
                    self.write_log(dict(event='discarded',**data))
                elif kind=='status':
                    code=data.pop('code')
                    self.status_state=(code,data)
                    if code in ('overflow','reader_error'):
                        self.result_state=('result_invalid',{})
                elif kind=='live':
                    self.live_state=('live',data)
                elif kind=='done':
                    m=data['measurement']
                    self.add_record(m,data.get('diagnostics'))
                    if m.error:
                        self.result_state=('result_invalid',{})
                        self.status_state=(m.error,{})
                    elif m.average_ms is None:
                        self.result_state=('result_short',{})
                        self.status_state=('insufficient',{})
                    else:
                        cells=sum(n for _,n in m.kept)
                        seconds=sum(t for t,_ in m.kept)/1000
                        self.result_state=('result_value',{'value':m.average_ms})
                        self.status_state=('complete',dict(intervals=len(m.kept),cells=cells,seconds=seconds))

                dirty=True
        except queue.Empty:
            pass
        if dirty: self.render()
        if not self.stop.is_set(): self.root.after(20,self.poll)

    def close(self):
        self.stop.set()
        self.engine.close()
        self.root.destroy()


if __name__=='__main__':
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    if '--self-test' in sys.argv:
        from packaged_check import run
        run(Path(sys.argv[sys.argv.index('--self-test')+1]))
    else:
        App(tk.Tk()).root.mainloop()
