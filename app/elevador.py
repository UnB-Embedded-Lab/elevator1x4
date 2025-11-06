#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Elevador GUI (COM apenas) - v3.2 (aproveitamento de espaço)
- Plots mais altos (height ~1.9), usando fill="both", expand=True
- Margens internas reduzidas (subplots_adjust)
- Mantém correções contra corte de rótulos (constrained_layout, labelpad, tick_params)
- Janela 820x720 (ideal 1366x768)
"""
from collections import deque
from datetime import datetime
import os
import csv
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import serial
import serial.tools.list_ports

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

BAUDRATE = 19200
LINE_END = b"\\r"
POLL_MS = 50
PLOT_INTERVAL_MS = 300
MAX_POINTS = 600

MOTOR_ESTADOS = {0: "Parado", 2: "Descendo", 3: "Subindo"}

def listar_com_ports_only():
    ports = []
    for p in serial.tools.list_ports.comports():
        dev = (p.device or "").upper()
        if dev.startswith("COM"):
            ports.append(p.device)
    return ports

class RealTimePlots:
    def __init__(self, parent):
        self.times = deque(maxlen=MAX_POINTS)
        self.pos   = deque(maxlen=MAX_POINTS)
        self.vel   = deque(maxlen=MAX_POINTS)
        self.temp  = deque(maxlen=MAX_POINTS)

        self.frm = ttk.Frame(parent)
        self.frm.pack(fill="both", expand=True, padx=6, pady=6)

        height = 1.9  # melhor aproveitamento vertical

        # Posição
        self.fig_pos = Figure(figsize=(4,height), dpi=90, constrained_layout=True)
        self.ax_pos = self.fig_pos.add_subplot(111)
        self.ax_pos.set_title("Posição (mm)")
        self.ax_pos.set_ylabel("mm", labelpad=6)
        self.ax_pos.grid(True)
        self.ax_pos.tick_params(axis='x', labelsize=8)
        self.ax_pos.tick_params(axis='y', labelsize=8)
        self.fig_pos.subplots_adjust(left=0.10, right=0.99, top=0.90, bottom=0.18)
        self.line_pos, = self.ax_pos.plot([], [])
        self.canvas_pos = FigureCanvasTkAgg(self.fig_pos, master=self.frm)
        self.canvas_pos.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=1)

        # Velocidade
        self.fig_vel = Figure(figsize=(4,height), dpi=90, constrained_layout=True)
        self.ax_vel = self.fig_vel.add_subplot(111)
        self.ax_vel.set_title("Velocidade (mm/s)")
        self.ax_vel.set_ylabel("mm/s", labelpad=6)
        self.ax_vel.grid(True)
        self.ax_vel.tick_params(axis='x', labelsize=8)
        self.ax_vel.tick_params(axis='y', labelsize=8)
        self.fig_vel.subplots_adjust(left=0.10, right=0.99, top=0.90, bottom=0.18)
        self.line_vel, = self.ax_vel.plot([], [])
        self.canvas_vel = FigureCanvasTkAgg(self.fig_vel, master=self.frm)
        self.canvas_vel.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=1)

        # Temperatura
        self.fig_temp = Figure(figsize=(4,height), dpi=90, constrained_layout=True)
        self.ax_temp = self.fig_temp.add_subplot(111)
        self.ax_temp.set_title("Temperatura (°C)")
        self.ax_temp.set_ylabel("°C", labelpad=6)
        self.ax_temp.grid(True)
        self.ax_temp.tick_params(axis='x', labelsize=8)
        self.ax_temp.tick_params(axis='y', labelsize=8)
        self.fig_temp.subplots_adjust(left=0.10, right=0.99, top=0.90, bottom=0.18)
        self.line_temp, = self.ax_temp.plot([], [])
        self.canvas_temp = FigureCanvasTkAgg(self.fig_temp, master=self.frm)
        self.canvas_temp.get_tk_widget().pack(fill="both", expand=True, padx=4, pady=1)

    def append(self, t, p, v, te):
        self.times.append(t); self.pos.append(p); self.vel.append(v); self.temp.append(te)

    def refresh(self):
        if not self.times:
            return
        xs = list(range(len(self.times)))
        self.line_pos.set_data(xs, list(self.pos))
        self.ax_pos.relim(); self.ax_pos.autoscale_view(); self.canvas_pos.draw_idle()

        self.line_vel.set_data(xs, list(self.vel))
        self.ax_vel.relim(); self.ax_vel.autoscale_view(); self.canvas_vel.draw_idle()

        self.line_temp.set_data(xs, list(self.temp))
        self.ax_temp.relim(); self.ax_temp.autoscale_view(); self.canvas_temp.draw_idle()


class ElevadorGUI:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("Elevador")
        self.master.geometry("820x720")
        for candidate in ("unb.ico", "unb.png", "unb.jpg"):
            if os.path.exists(candidate):
                try:
                    if candidate.endswith(".ico"):
                        self.master.iconbitmap(candidate)
                    else:
                        self.master.iconphoto(False, tk.PhotoImage(file=candidate))
                except Exception:
                    pass
                break

        self.ser = None
        self.buffer = bytearray()
        self.csv_file = None
        self.csv_writer = None
        self.logging_enabled = tk.BooleanVar(value=False)

        # Top bar
        top = ttk.Frame(master); top.pack(fill="x", padx=6, pady=6)
        ttk.Label(top, text="Porta COM:").pack(side="left")
        self.cmb = ttk.Combobox(top, width=20, state="readonly")
        self._update_com_list()
        self.cmb.pack(side="left", padx=4)
        ttk.Button(top, text="Atualizar", command=self._update_com_list).pack(side="left", padx=4)
        self.btn_connect = ttk.Button(top, text="Conectar", command=self._toggle_connection)
        self.btn_connect.pack(side="left", padx=6)

        # Status
        self.var_status = tk.StringVar(value="Desconectado")
        ttk.Label(master, textvariable=self.var_status, relief="sunken", anchor="w").pack(fill="x", padx=6, pady=2)

        # Indicadores
        indic = ttk.Frame(master); indic.pack(fill="x", padx=6, pady=2)
        self.var_andar=tk.StringVar(value="-"); self.var_dest=tk.StringVar(value="-"); self.var_motor=tk.StringVar(value="-")
        self.var_pos=tk.StringVar(value="-"); self.var_vel=tk.StringVar(value="-"); self.var_temp=tk.StringVar(value="-")
        def mk(lbl,var):
            f=ttk.Frame(indic); f.pack(side="left", padx=4)
            ttk.Label(f,text=lbl).pack(); ttk.Label(f,textvariable=var,font=("Arial",10,"bold")).pack()
        mk("Andar (A)",self.var_andar); mk("Destino (D)",self.var_dest); mk("Motor (M)",self.var_motor)
        mk("Pos (mm)",self.var_pos); mk("Vel (mm/s)",self.var_vel); mk("Temp (°C)",self.var_temp)

        # Envio $OD\r
        sendf = ttk.LabelFrame(master, text="Enviar $OD\\r (O=0..3 D=0..3)")
        sendf.pack(fill="x", padx=6, pady=4)
        self.var_origem = tk.IntVar(value=0); self.var_destino = tk.IntVar(value=1)
        ttk.Label(sendf,text="Origem").pack(side="left", padx=2); ttk.Spinbox(sendf, from_=0,to=3,textvariable=self.var_origem,width=4).pack(side="left")
        ttk.Label(sendf,text="Destino").pack(side="left", padx=2); ttk.Spinbox(sendf, from_=0,to=3,textvariable=self.var_destino,width=4).pack(side="left")
        ttk.Button(sendf, text="Enviar $OD", command=self._enviar_od).pack(side="left", padx=6)
        for d in range(4):
            ttk.Button(sendf, text=f"-> {d}", command=lambda dd=d: self._enviar_rapido(dd)).pack(side="left", padx=2)

        # Logging CSV
        logf = ttk.Frame(master); logf.pack(fill="x", padx=6, pady=2)
        ttk.Checkbutton(logf, text="Gravar CSV", variable=self.logging_enabled, command=self._toggle_csv).pack(side="left")
        self.lbl_csv = ttk.Label(logf, text=""); self.lbl_csv.pack(side="left", padx=6)

        # Plots
        self.plots = RealTimePlots(master)

        # Timers
        self.master.after(POLL_MS, self._poll_serial)
        self.master.after(PLOT_INTERVAL_MS, self._plot_timer)

    # --------- COM handling ----------
    def _update_com_list(self):
        ports = listar_com_ports_only()
        self.cmb["values"] = ports
        if ports:
            try: self.cmb.current(0)
            except Exception: self.cmb.set(ports[0])
        else:
            self.cmb.set("")

    def _toggle_connection(self):
        if self.ser is None:
            self._connect()
        else:
            self._disconnect()

    def _connect(self):
        port = self.cmb.get()
        if not port:
            messagebox.showwarning("Porta COM", "Nenhuma COM selecionada. Clique em Atualizar para listar as COM disponíveis.")
            return
        try:
            self.ser = serial.Serial(port=port, baudrate=BAUDRATE, timeout=0.0, write_timeout=1.0)
            self.btn_connect.configure(text="Desconectar")
            self.var_status.set(f"Conectado em {port} @ {BAUDRATE}")
        except Exception as e:
            self.ser = None
            messagebox.showerror("Erro", f"Falha ao abrir {port}: {e}")

    def _disconnect(self):
        try:
            if self.ser:
                self.ser.close()
        finally:
            self.ser = None
            self.btn_connect.configure(text="Conectar")
            self.var_status.set("Desconectado")

    # --------- Envio/Recepção ----------
    def _enviar_od(self):
        if not self.ser:
            messagebox.showwarning("Serial", "Conecte primeiro.")
            return
        o = int(self.var_origem.get()); d = int(self.var_destino.get())
        if not (0<=o<=3 and 0<=d<=3):
            messagebox.showwarning("Valores", "Origem/Destino devem estar entre 0 e 3.")
            return
        frame = f"${o}{d}\\r".encode("ascii")
        try:
            self.ser.write(frame)
            self.var_status.set(f"Enviado: {frame!r}")
        except Exception as e:
            messagebox.showerror("Erro", f"Falha no envio: {e}")

    def _enviar_rapido(self, d):
        try:
            o = int(self.var_andar.get())
        except Exception:
            o = 0
        self.var_origem.set(o); self.var_destino.set(d)
        self._enviar_od()

    def _poll_serial(self):
        try:
            if self.ser and self.ser.is_open:
                while True:
                    chunk = self.ser.read(256)
                    if not chunk:
                        break
                    self.buffer.extend(chunk)
                # processa por CR
                while True:
                    idx = self.buffer.find(LINE_END)
                    if idx < 0:
                        break
                    line = bytes(self.buffer[:idx])
                    del self.buffer[:idx+1]
                    self._process_line(line)
        except Exception as e:
            self._disconnect()
            self.var_status.set(f"Erro na serial: {e}")
        finally:
            self.master.after(POLL_MS, self._poll_serial)

    def _process_line(self, line: bytes):
        try:
            txt = line.decode("ascii", errors="ignore").strip()
        except Exception:
            return
        if not txt:
            return
        if txt.startswith("$"):
            payload = txt[1:]
        else:
            payload = txt
        parts = [p.strip() for p in payload.split(",")]
        if len(parts) != 6:
            self.var_status.set(f"Recebido (ignorado): {txt}")
            return
        try:
            A = int(parts[0]); D = int(parts[1]); M = int(parts[2]); H = int(parts[3])
            VV = float(parts[4]); TT = float(parts[5])
        except Exception:
            return
        # Indicadores
        self.var_andar.set(str(A)); self.var_dest.set(str(D))
        self.var_motor.set(MOTOR_ESTADOS.get(M, f"Desconhecido ({M})"))
        self.var_pos.set(str(H)); self.var_vel.set(f"{VV:.1f}"); self.var_temp.set(f"{TT:.1f}")
        # Plots
        t = datetime.now().timestamp()
        self.plots.append(t, H, VV, TT)
        # CSV
        if self.logging_enabled.get() and self.csv_writer:
            now = datetime.now().isoformat(timespec="milliseconds")
            self.csv_writer.writerow([now, A, D, M, H, f"{VV:.1f}", f"{TT:.1f}"])

    def _toggle_csv(self):
        if self.logging_enabled.get():
            p = filedialog.asksaveasfilename(title="Salvar CSV", defaultextension=".csv",
                                             filetypes=[("CSV","*.csv")],
                                             initialfile=f"elevador_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv")
            if not p:
                self.logging_enabled.set(False); return
            try:
                self.csv_file = open(p,"w",newline="",encoding="utf-8")
                self.csv_writer = csv.writer(self.csv_file)
                self.csv_writer.writerow(["timestamp","A","D","M","pos_mm","vel_mms","temp_C"])
            except Exception as e:
                messagebox.showerror("CSV", f"Erro ao abrir arquivo: {e}")
                self.logging_enabled.set(False)
        else:
            try:
                if self.csv_file: self.csv_file.close()
            finally:
                self.csv_file = None; self.csv_writer = None

    def _plot_timer(self):
        try:
            self.plots.refresh()
        except Exception as e:
            print("Plot error:", e)
        finally:
            self.master.after(PLOT_INTERVAL_MS, self._plot_timer)


def main():
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    app = ElevadorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
