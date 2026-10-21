"""Optional RDS via redsea (https://github.com/windytan/redsea).

Consumes a 57-kHz-containing WFM multiplex from the existing DSP, not
15-kHz speaker audio. No third-party binary distributed. Bounded queue and
separate writer/read threads avoid blocking the USB receive loop.
"""
from __future__ import annotations
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import threading
import numpy as np
from scipy import signal


class RDSStatus:
    def __init__(self):
        self.pi = ''
        self.ps = ''
        self.text = ''
        self.pty = ''

    def update(self, line):
        try:
            msg = json.loads(line) if isinstance(line,str) else line
        except (ValueError,TypeError):
            return False
        if not isinstance(msg,dict):
            return False
        old=(self.pi,self.ps,self.text,self.pty)
        self.pi = str(msg.get('pi') or self.pi)[:20]
        self.ps = str(msg.get('ps') or self.ps)[:20]
        self.text = str(msg.get('radiotext') or self.text)[:120]
        self.pty = str(msg.get('prog_type') or self.pty)[:45]
        return (self.pi,self.ps,self.text,self.pty)!=old

    def as_dict(self):
        return dict(pi=self.pi, ps=self.ps,text=self.text,pty=self.pty)


class RDSBridge:
    def __init__(self, executable, if_rate, callback, status_callback):
        self.executable=[str(part) for part in executable] if isinstance(executable,(list,tuple)) else str(executable)
        self.if_rate=int(round(if_rate))
        if self.if_rate < 130_000:
            raise ValueError('RDS vereist IF sample-rate minimaal 130 kHz')
        self.callback=callback
        self.status_callback=status_callback
        self.queue=queue.Queue(maxsize=6)
        self.closed=threading.Event()
        self.process=None
        self.dropped_blocks=0
        self.status=RDSStatus()
        self.threads=[]

    def start(self):
        flags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0
        command=list(self.executable) if isinstance(self.executable,list) else [self.executable]
        self.process=subprocess.Popen([*command,'--input','mpx','-r','171k'],
                         stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         bufsize=0,creationflags=flags,
                         cwd=str(Path(command[0]).resolve().parent) if Path(command[0]).is_file() else None)
        for name, fn in [('RDS-writer',self._writer),('RDS-reader',self._reader),('RDS-errors',self._errors)]:
            t=threading.Thread(target=fn,name=name,daemon=True)
            t.start();self.threads.append(t)
        return self

    def submit(self, mpx):
        if self.closed.is_set():
            return
        try:self.queue.put_nowait(np.asarray(mpx,dtype=np.float32).copy())
        except queue.Full:self.dropped_blocks+=1

    def _writer(self):
        gcd=math.gcd(self.if_rate,171_000)
        up,down=171_000//gcd,self.if_rate//gcd
        try:
            while not self.closed.is_set():
                try:mpx=self.queue.get(timeout=.1)
                except queue.Empty:continue
                out=signal.resample_poly(mpx,up,down)
                raw=(np.clip(out,-1,1)*32767).astype('<i2').tobytes()
                self.process.stdin.write(raw)
        except (BrokenPipeError,ValueError,OSError):
            if not self.closed.is_set():
                self.status_callback('RDS-decoder heeft de stream gesloten')

    def _reader(self):
        try:
            for raw in self.process.stdout:
                if self.closed.is_set():break
                if len(raw)>8192:continue
                if self.status.update(raw.decode('utf-8','replace').strip()):
                    self.callback(self.status.as_dict())
        except (OSError,ValueError):pass

    def _errors(self):
        try:
            for raw in self.process.stderr:
                if self.closed.is_set():break
                msg=raw.decode('utf-8','replace').strip()
                if msg and ('error' in msg.lower() or 'invalid' in msg.lower()):
                    self.status_callback('RDS: '+msg[:150])
        except (OSError,ValueError):pass

    def close(self):
        self.closed.set()
        if self.process:
            if self.process.poll() is None:
                self.process.terminate()
                try:self.process.wait(timeout=1)
                except subprocess.TimeoutExpired:self.process.kill()
            for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
                if stream:
                    try:stream.close()
                    except OSError:pass
