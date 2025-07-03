import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import datetime
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import requests
import time
import webbrowser
from collections import deque

matplotlib.use("TkAgg")
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

def get_stock_data(stock_code):
    code = stock_code.strip()
    if code.startswith('1.') or code.startswith('0.'):
        secid = code
    elif code.startswith(('6', '9')):
        secid = f"1.{code}"
    elif code.startswith(('0', '3')):
        secid = f"0.{code}"
    else:
        secid = code
    url = "https://push2.eastmoney.com/api/qt/stock/get"
    params = {
        "ut": "fa5fd1943c7b386f1734de892508f7",
        "invt": 2,
        "fltt": 2,
        "fields": "f2,f3,f4,f5,f6,f7,f8,f9,f10,f12,f14,f15,f16,f17,f18,f20,f21,f23,f62,f128,f43,f57,f58,f59,f60,f61",
        "secid": secid
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://finance.eastmoney.com/",
    }
    try:
        response = requests.get(url, params=params, headers=headers, timeout=4)
        response.raise_for_status()
        data = response.json()
        if data.get("data"):
            d = data["data"]
            price = d.get("f2")
            if price is not None:
                price = float(price)
            elif d.get("f43") is not None:
                price = float(d.get("f43"))
            else:
                price = None
            prev_close = d.get("f18")
            if prev_close is not None:
                prev_close = float(prev_close)
            elif d.get("f60") is not None:
                prev_close = float(d.get("f60"))
            else:
                prev_close = None
            stock_info = {
                "code": d.get("f12") or d.get("f57"),
                "name": d.get("f14") or d.get("f58"),
                "price": price,
                "change_percent": d.get("f3"),
                "change": d.get("f4"),
                "volume": d.get("f5"),
                "amount": d.get("f6"),
                "high": d.get("f15"),
                "low": d.get("f16"),
                "open": d.get("f17"),
                "prev_close": prev_close,
                "market": d.get("f59"),
            }
            return stock_info
        else:
            return None
    except requests.RequestException:
        return None

def ai_select_stocks(input_prompt):
    return ["600519", "600036", "000858", "601318"]

class ToolTip(object):
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.show_tip)
        self.widget.bind("<Leave>", self.hide_tip)

    def show_tip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, _cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 60
        y = y + cy + self.widget.winfo_rooty() + 30
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(
            tw, text=self.text, justify=tk.LEFT,
            background="#ffffe0", relief=tk.SOLID, borderwidth=1,
            font=("tahoma", "10", "normal"))
        label.pack(ipadx=1)

    def hide_tip(self, event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()

class AIStockSelectorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI智能选股与行情监控（东方财富API优化）")
        self.root.geometry("1300x860")

        self.selected_stocks = []
        self.warning_params = []
        self.price_history = [deque(maxlen=2880) for _ in range(4)]
        self.warning_triggered = [False]*4

        self.start_time = None
        self.last_plot_range = 180

        self._build_gui()
        self.update_thread = None
        self.running = False

    def _build_gui(self):
        mainf = ttk.Frame(self.root)
        mainf.pack(padx=8, pady=8, fill=tk.BOTH, expand=True)

        # 手工股票输入区
        manualf = ttk.Labelframe(mainf, text="股票代码手动输入", padding=6)
        manualf.pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Label(manualf, text="请输入4个股票代码（用逗号分隔），如600519,600036,000858,601318，或直接点击AI选股:").grid(row=0, column=0, sticky="w")
        manual_input_frame = ttk.Frame(manualf)
        manual_input_frame.grid(row=1, column=0, sticky="w")
        self.manual_stock_var = tk.StringVar()
        self.manual_stock_entry = ttk.Entry(manual_input_frame, textvariable=self.manual_stock_var, width=85)
        self.manual_stock_entry.grid(row=0, column=0, sticky="w")
        self.manual_input_btn = ttk.Button(manual_input_frame, text="确定", command=self.manual_input_action)
        self.manual_input_btn.grid(row=0, column=1, padx=8)
        self.manual_tip_label = ttk.Label(
            manualf,
            text="您需要输入四个股票代码，以逗号分隔，或者直接点击AI选股，由AI为您智能推荐四只股票。",
            foreground="blue"
        )
        self.manual_tip_label.grid(row=2, column=0, sticky="w")

        # 选股区
        stockf = ttk.Labelframe(mainf, text="智能策略选股", padding=6)
        stockf.pack(side=tk.TOP, fill=tk.X, pady=2)
        ttk.Label(stockf, text="AI选股输入提示:").grid(row=0, column=0)
        self.ai_prompt_var = tk.StringVar(value="帮我优选沪深A股价值成长股4只")
        self.ai_prompt_entry = ttk.Entry(stockf, textvariable=self.ai_prompt_var, width=60)
        self.ai_prompt_entry.grid(row=0, column=1, padx=4)
        self.ai_select_btn = ttk.Button(stockf, text="AI选股", command=self.ai_select_stocks_action)
        self.ai_select_btn.grid(row=0, column=2, padx=3)
        ToolTip(self.ai_select_btn,
            "请复制左边框内这段提示词到您常用的实时大模型对话框中，建议deepseek,豆包，火山引擎，阿里千问")
        ttk.Label(stockf, text="当前监控股票:").grid(row=1, column=0, pady=4)
        self.stocks_label = ttk.Label(stockf, text="", font=("Consolas", 12, "bold"))
        self.stocks_label.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)

        # 报警区
        warnf = ttk.Labelframe(mainf, text="预警设置（最多监控4只）", padding=6)
        warnf.pack(side=tk.TOP, fill=tk.X, pady=2)
        self.warn_entries = []
        for i in range(4):
            ttk.Label(warnf, text=f"股票{i+1}:").grid(row=i, column=0)
            stock_var = tk.StringVar()
            setattr(self, f"stock_{i}_var", stock_var)
            stock_entry = ttk.Entry(warnf, textvariable=stock_var, width=12)
            stock_entry.grid(row=i, column=1)
            up_var = tk.DoubleVar(value=10)
            down_var = tk.DoubleVar(value=2)
            up_pct_var = tk.DoubleVar(value=20)
            down_pct_var = tk.DoubleVar(value=15)
            ttk.Label(warnf, text="高于:").grid(row=i, column=2)
            up_entry = ttk.Entry(warnf, textvariable=up_var, width=8)
            up_entry.grid(row=i, column=3)
            ttk.Label(warnf, text="低于:").grid(row=i, column=4)
            down_entry = ttk.Entry(warnf, textvariable=down_var, width=8)
            down_entry.grid(row=i, column=5)
            ttk.Label(warnf, text="3天涨幅%≥").grid(row=i, column=6)
            up_pct_entry = ttk.Entry(warnf, textvariable=up_pct_var, width=6)
            up_pct_entry.grid(row=i, column=7)
            ttk.Label(warnf, text="3天跌幅%≥").grid(row=i, column=8)
            down_pct_entry = ttk.Entry(warnf, textvariable=down_pct_var, width=6)
            down_pct_entry.grid(row=i, column=9)
            self.warn_entries.append((stock_var, up_var, down_var, up_pct_var, down_pct_var))
        ttk.Button(warnf, text="开始监控", command=self.start_monitor).grid(row=0, column=10, rowspan=2, padx=6)
        ttk.Button(warnf, text="停止监控", command=self.stop_monitor).grid(row=2, column=10, rowspan=2, padx=6)

        out_frame = ttk.Frame(mainf)
        out_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.fig, self.axes = plt.subplots(2, 2, figsize=(13, 7))
        plt.subplots_adjust(hspace=0.35)
        self.canvas = FigureCanvasTkAgg(self.fig, master=out_frame)
        self.canvas.get_tk_widget().pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        rightf = ttk.Frame(out_frame)
        rightf.pack(side=tk.LEFT, fill=tk.Y, padx=4)
        ttk.Label(rightf, text="行情&预警日志:").pack(anchor="w", pady=(0, 4))
        self.log_box = scrolledtext.ScrolledText(rightf, width=40, height=37, font=("Consolas", 11))
        self.log_box.pack(fill=tk.BOTH, expand=True)
        ttk.Button(rightf, text="清空日志", command=lambda: self.log_box.delete(1.0, tk.END)).pack(pady=2)

    def manual_input_action(self):
        manual_codes = self.manual_stock_var.get().strip()
        if manual_codes:
            code_list = [c.strip() for c in manual_codes.split(",") if c.strip()]
            if len(code_list) != 4:
                messagebox.showinfo("股票代码数量不符", "您需要输入四个股票代码，以逗号分隔。")
                return
            for i, code in enumerate(code_list):
                getattr(self, f"stock_{i}_var").set(code)
            self.stocks_label.config(text=" | ".join(code_list))
        else:
            messagebox.showinfo("提示", "请输入四个股票代码后点击确定，或者直接点击AI选股。")

    def ai_select_stocks_action(self):
        webbrowser.open("https://yuanbao.tencent.com/")
        stocks = ai_select_stocks(self.ai_prompt_var.get().strip())
        for i, s in enumerate(stocks):
            getattr(self, f"stock_{i}_var").set(s)
        self.stocks_label.config(text=" | ".join(stocks))

    def start_monitor(self):
        manual_codes = self.manual_stock_var.get().strip()
        if manual_codes:
            code_list = [c.strip() for c in manual_codes.split(",") if c.strip()]
            if len(code_list) != 4:
                messagebox.showinfo("股票代码数量不符", "您需要输入四个股票代码，以逗号分隔。")
                return
            stocks = code_list
            self.stocks_label.config(text=" | ".join(stocks))
            for i, code in enumerate(stocks):
                getattr(self, f"stock_{i}_var").set(code)
        else:
            codes = [self.warn_entries[i][0].get().strip() for i in range(4)]
            if not all(codes):
                messagebox.showinfo(
                    "请选择股票", 
                    "您需要输入四个股票代码，以逗号分隔，或者直接点击AI选股，由AI为您智能推荐四只股票。"
                )
                return
            stocks = codes
            self.stocks_label.config(text=" | ".join(stocks))

        self.selected_stocks = []
        self.warning_params = []
        for i in range(4):
            stock = self.warn_entries[i][0].get().strip()
            if stock:
                self.selected_stocks.append(stock)
                self.warning_params.append((
                    self.warn_entries[i][1].get(),
                    self.warn_entries[i][2].get(),
                    self.warn_entries[i][3].get(),
                    self.warn_entries[i][4].get(),
                ))
        self.running = True
        self.warning_triggered = [False]*4
        self.price_history = [deque(maxlen=2880) for _ in range(4)]
        self.start_time = time.time()
        self.last_plot_range = 180
        self.log_box.insert(tk.END, f"\n>>> 启动实时行情监控...\n")
        if not self.update_thread or not self.update_thread.is_alive():
            self.update_thread = threading.Thread(target=self.monitor_loop, daemon=True)
            self.update_thread.start()

    def stop_monitor(self):
        self.running = False
        self.log_box.insert(tk.END, f"\n>>> 已停止行情监控。\n")

    def monitor_loop(self):
        while self.running:
            try:
                now = datetime.datetime.now()
                elapsed = time.time() - self.start_time if self.start_time else 0
                if elapsed < 180:
                    plot_range = 180
                    sleep_interval = 1
                else:
                    plot_range = 2880
                    sleep_interval = 5

                for idx, stock in enumerate(self.selected_stocks):
                    stock_info = get_stock_data(stock)
                    if not stock_info:
                        self.log_box.insert(tk.END, f"[{now:%H:%M:%S}] {stock} 无法获取数据\n")
                        continue
                    name = stock_info.get("name") or "未知"
                    code = stock_info.get("code") or stock
                    last_price = stock_info.get("price")
                    try:
                        last_price = float(last_price)
                    except Exception:
                        last_price = None
                    if last_price is not None:
                        self.price_history[idx].append((now, last_price))
                    ax = self.axes[idx//2][idx%2]
                    ax.clear()
                    ph = self.price_history[idx]
                    if ph:
                        if len(ph) > plot_range:
                            ph_window = list(ph)[-plot_range:]
                        else:
                            ph_window = list(ph)
                        times = [t.strftime("%H:%M:%S") for t, p in ph_window]
                        prices = [float(p) for t, p in ph_window]
                        ax.plot(times, prices, label=f"{name}({code})", color='b', marker='o', markersize=2)
                        ax.set_title(f"{name}({code})")
                        ax.set_xlabel("时间")
                        ax.set_ylabel("价格")
                        ax.tick_params(axis='x', labelsize=8, rotation=45)
                        ax.legend()
                    msg = ""
                    up, down, up_pct, down_pct = self.warning_params[idx]
                    if (last_price is not None) and (up > 0) and (last_price >= up) and (not self.warning_triggered[idx]):
                        msg += f"▲ {name} 最新价 {last_price:.2f} >= 预警高价{up}\n"
                        self.warning_triggered[idx] = True
                    if (last_price is not None) and (down > 0) and (last_price <= down) and (not self.warning_triggered[idx]):
                        msg += f"▼ {name} 最新价 {last_price:.2f} <= 预警低价{down}\n"
                        self.warning_triggered[idx] = True
                    if (last_price is not None) and len(self.price_history[idx]) >= 180:
                        price3ago = float(self.price_history[idx][-180][1])
                        pct = (float(last_price)-price3ago)/price3ago*100
                        if (up_pct > 0) and (pct >= up_pct) and (not self.warning_triggered[idx]):
                            msg += f"▲ {name} 3天涨幅{pct:.2f}% ≥ {up_pct}%\n"
                            self.warning_triggered[idx] = True
                        if (down_pct > 0) and (pct <= -abs(down_pct)) and (not self.warning_triggered[idx]):
                            msg += f"▼ {name} 3天跌幅{pct:.2f}% ≤ {down_pct}%\n"
                            self.warning_triggered[idx] = True
                    if msg:
                        self.log_box.insert(tk.END, f"[{now:%H:%M:%S}] {msg}")
                    else:
                        self.warning_triggered[idx] = False
                self.canvas.draw()
            except Exception as e:
                self.log_box.insert(tk.END, f"[异常]{e}\n")
            for _ in range(int(sleep_interval*10)):
                if not self.running:
                    break
                time.sleep(0.1)

if __name__ == "__main__":
    root = tk.Tk()
    app = AIStockSelectorApp(root)
    root.mainloop()