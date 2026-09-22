"""Windows GUI and noninteractive entry point for NDS to CIA."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import queue
import sys
import threading

from generator import build_game
from prepare_native_banner import prepare

VERSION = '1.0.0'


def package_root():
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    return base/'bundle' if getattr(sys, 'frozen', False) else base/'dist-v2'


def state_root():
    return Path(os.environ.get('LOCALAPPDATA', Path.home()/'.local/share'))/'nds-to-cia'


@contextlib.contextmanager
def state_lock(state):
    """Serialize title-ID allocation across open converter windows."""
    state.mkdir(parents=True, exist_ok=True)
    with (state/'builder.lock').open('a+b') as lock:
        if lock.tell() == 0:
            lock.write(b'0'); lock.flush()
        lock.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise ValueError('Another conversion is using this profile. Wait for it to finish.') from error
        else:
            import fcntl
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == 'nt':
                lock.seek(0); msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def convert(rom, output, state, basic=False, title=None):
    if Path(output).suffix.lower() != '.cia':
        raise ValueError('Choose an output filename ending in .cia.')
    with state_lock(state):
        build_game(Path(rom), Path(output), title, package_root(), state/'native-assets',
                   basic, state/'title-ids.json')


class App:
    def __init__(self, root, state, initial_rom=None):
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        self.tk, self.ttk, self.dialog, self.message = tk, ttk, filedialog, messagebox
        self.root, self.state = root, state
        self.busy = False
        self.events = queue.Queue()
        root.title(f'NDS to CIA {VERSION}')
        root.geometry('720x480'); root.minsize(660,480)
        root.protocol('WM_DELETE_WINDOW', self.close)
        box = ttk.Frame(root, padding=24); box.pack(fill='both', expand=True)
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text='NDS to CIA', font=('Segoe UI',20,'bold')).grid(row=0,column=0,columnspan=3,sticky='w')
        ttk.Label(box,text='A self-contained HOME Menu title from your DS game dump.').grid(row=1,column=0,columnspan=3,sticky='w',pady=(4,20))
        self.rom = tk.StringVar(value=initial_rom or '')
        self.output = tk.StringVar(value=str(Path(initial_rom).with_suffix('.cia')) if initial_rom else '')
        for row,label,var,command in [(2,'DS game',self.rom,self.select_rom),(3,'Save CIA',self.output,self.select_output)]:
            ttk.Label(box,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=8)
            ttk.Entry(box,textvariable=var).grid(row=row,column=1,sticky='ew',pady=8)
            ttk.Button(box,text='Browse…',command=command).grid(row=row,column=2,padx=(8,0),pady=8)
        self.style=tk.StringVar(value='Native DS cartridge')
        ttk.Label(box,text='Banner').grid(row=4,column=0,sticky='w',pady=8)
        ttk.Combobox(box,textvariable=self.style,state='readonly',values=['Native DS cartridge','Simple icon']).grid(row=4,column=1,sticky='ew')
        self.import_button=ttk.Button(box,text='Banner setup…',command=self.setup)
        self.import_button.grid(row=4,column=2,padx=(8,0))
        self.status=tk.StringVar(value=self.ready_text())
        ttk.Label(box,textvariable=self.status,wraplength=640).grid(row=5,column=0,columnspan=3,sticky='w',pady=(18,8))
        self.progress=ttk.Progressbar(box,mode='indeterminate')
        self.progress.grid(row=6,column=0,columnspan=3,sticky='ew',pady=8)
        self.build_button=ttk.Button(box,text='Create CIA',command=self.build)
        self.build_button.grid(row=7,column=2,sticky='e',pady=8)
        ttk.Label(box,text='Install Bridge.cia once with FBI. First game launch prepares its files.',wraplength=480).grid(row=7,column=0,columnspan=2,sticky='w')
        root.after(100,self.poll)

    def ready_text(self):
        complete=all((self.state/'native-assets'/name).is_file() for name in ('BannerDS.bin','cbf_std.bcfnt'))
        return 'Native banner ready. Choose a DS game to begin.' if complete else 'One-time native banner setup is required. Simple icon mode works without system resources.'

    def select_rom(self):
        if self.busy:return
        value=self.dialog.askopenfilename(parent=self.root,title='Select your DS game dump',filetypes=[('DS game dumps','*.nds')])
        if value:
            self.rom.set(value);self.output.set(str(Path(value).with_suffix('.cia')))

    def select_output(self):
        if self.busy:return
        value=self.dialog.asksaveasfilename(parent=self.root,title='Save CIA',defaultextension='.cia',filetypes=[('CIA files','*.cia')],confirmoverwrite=False)
        if value:self.output.set(value)

    def run(self, work, success):
        if self.busy:return
        self.busy=True;self.build_button.state(['disabled']);self.import_button.state(['disabled'])
        self.progress.start(15);self.status.set('Working… Please keep this window open.')
        def worker():
            try:
                with contextlib.redirect_stdout(io.StringIO()):work()
                self.events.put((True,success))
            except Exception as error:self.events.put((False,str(error)))
        threading.Thread(target=worker,daemon=False).start()

    def poll(self):
        try:
            okay,text=self.events.get_nowait()
        except queue.Empty:pass
        else:
            self.busy=False;self.progress.stop();self.build_button.state(['!disabled']);self.import_button.state(['!disabled'])
            self.status.set(text if okay else 'Could not finish. Review the error and try again.')
            (self.message.showinfo if okay else self.message.showerror)('NDS to CIA',text,parent=self.root)
        self.root.after(100,self.poll)

    def build(self):
        rom,output=self.rom.get().strip(),self.output.get().strip()
        if not rom or not output:
            self.message.showerror('Choose files','Select a DS game and an output CIA.',parent=self.root);return
        basic=self.style.get()=='Simple icon'
        self.run(lambda:convert(rom,output,self.state,basic),f'Created {Path(output).name}. Install it using FBI after installing the one-time bridge.')

    def setup(self):
        if self.busy:return
        tk,ttk=self.tk,self.ttk
        window=tk.Toplevel(self.root);window.title('Native banner setup');window.transient(self.root);window.grab_set()
        frame=ttk.Frame(window,padding=20);frame.pack(fill='both',expand=True);frame.columnconfigure(1,weight=1)
        ttk.Label(frame,text='Import resources from your own console dumps.',font=('Segoe UI',12,'bold')).grid(row=0,column=0,columnspan=3,sticky='w')
        ttk.Label(frame,text='HOME Menu CIA + standard system font CIA. Encrypted CIAs also need boot9.bin.\nThe key dump is read for this import and is not copied into the app profile.',wraplength=600).grid(row=1,column=0,columnspan=3,sticky='w',pady=(8,14))
        values=[tk.StringVar() for _ in range(3)]
        for i,label in enumerate(['HOME Menu CIA','System font CIA','boot9.bin (if needed)']):
            ttk.Label(frame,text=label).grid(row=i+2,column=0,sticky='w',padx=(0,12),pady=6)
            ttk.Entry(frame,textvariable=values[i],width=48).grid(row=i+2,column=1,sticky='ew')
            def browse(index=i, title=label):
                path=self.dialog.askopenfilename(parent=window,title=title)
                if path:values[index].set(path)
            ttk.Button(frame,text='Browse…',command=browse).grid(row=i+2,column=2,padx=(8,0))
        def start():
            menu,font,key=[value.get().strip() for value in values]
            if not menu or not font:
                self.message.showerror('Missing dumps','Select the HOME Menu and system font CIAs.',parent=window);return
            window.destroy()
            self.run(lambda:prepare(Path(menu),Path(font),self.state/'native-assets',Path(key) if key else None),
                     'Native banner setup complete. You can now create CIAs with the original DS cartridge display.')
        ttk.Button(frame,text='Import resources',command=start).grid(row=5,column=2,pady=(16,0))

    def close(self):
        if self.busy:
            self.message.showinfo('Conversion in progress','Wait for the current operation to finish before closing.',parent=self.root)
        else:self.root.destroy()


def main(argv=None):
    parser=argparse.ArgumentParser(description='NDS to CIA '+VERSION)
    parser.add_argument('rom',nargs='?',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--basic-banner',action='store_true')
    parser.add_argument('--state-dir',type=Path,default=state_root())
    parser.add_argument('--report',type=Path)
    parser.add_argument('--self-test',action='store_true')
    args=parser.parse_args(argv)
    if args.self_test or args.output:
        report={'version':VERSION,'success':False}
        try:
            if args.self_test:
                import tkinter as tk
                from Cryptodome.Cipher import AES
                import pyctr
                root=tk.Tk();root.withdraw();app=App(root,args.state_dir);root.update();root.destroy()
                AES.new(bytes(16),AES.MODE_ECB).encrypt(bytes(16))
                required=['tools/makerom.exe','tools/bannertool.exe','data/launcher.elf','data/blank-logo.lz','assets/blank-logo-auth.json']
                if not all((package_root()/f).is_file() for f in required):raise ValueError('Packaged build components are missing')
                report['checks']=['tkinter-window','crypto-module','pyctr-import','embedded-build-tools']
            else:
                if not args.rom:raise ValueError('A DS dump is required')
                convert(args.rom,args.output,args.state_dir,args.basic_banner)
                report['output']=str(args.output)
            report['success']=True
        except Exception as error:report['error']=str(error)
        if args.report:
            args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2)+'\n')
        return 0 if report['success'] else 1
    import tkinter as tk
    root=tk.Tk();App(root,args.state_dir,str(args.rom) if args.rom else None);root.mainloop()
    return 0


if __name__=='__main__':
    # Windowed PyInstaller builds have no stdout/stderr handles.
    if sys.stdout is None:sys.stdout=io.StringIO()
    if sys.stderr is None:sys.stderr=io.StringIO()
    raise SystemExit(main())
