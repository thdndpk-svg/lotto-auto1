#!/usr/bin/env python3
from __future__ import annotations

import csv
import subprocess
import sys
import threading
import traceback
from datetime import date
from io import StringIO
from pathlib import Path
from tkinter import BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from lotto_auto import (
    COMBO_FACTOR_LABELS,
    DEFAULT_COMBO_FACTORS,
    DEFAULT_NUMBER_FACTORS,
    NUMBER_FACTOR_LABELS,
    ComboScore,
    LottoAnalyzer,
    NumberScore,
    load_draws,
    parse_date,
    print_report,
)


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "data" / "lotto.csv"
REPORT_DIR = APP_DIR / "reports"


BALL_COLORS = {
    "yellow": "#F6C85F",
    "blue": "#5DADE2",
    "red": "#EC7063",
    "gray": "#AAB7B8",
    "green": "#58D68D",
}


def ball_color(number: int) -> str:
    if number <= 10:
        return BALL_COLORS["yellow"]
    if number <= 20:
        return BALL_COLORS["blue"]
    if number <= 30:
        return BALL_COLORS["red"]
    if number <= 40:
        return BALL_COLORS["gray"]
    return BALL_COLORS["green"]


def format_won(value: str | int | None) -> str:
    try:
        amount = int(value or 0)
    except ValueError:
        amount = 0
    return f"{amount:,}원" if amount else "-"


def format_count(value: str | int | None) -> str:
    try:
        count = int(value or 0)
    except ValueError:
        count = 0
    return f"{count:,}명" if count else "-"


def read_latest_row(path: Path) -> dict[str, str]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("CSV 데이터가 비어 있습니다.")
    return rows[-1]


class LottoDesktopApp:
    def __init__(self) -> None:
        self.root = Tk()
        self.root.title("Lotto Auto Analyzer")
        self.root.geometry("1180x760")
        self.root.minsize(1040, 660)
        self.root.configure(bg="#F5F7FB")

        self.target_date = StringVar(value=date.today().isoformat())
        self.candidates = StringVar(value="50000")
        self.seed = StringVar(value="18")
        self.status = StringVar(value="준비됨")
        self.latest_summary = StringVar(value="")
        self.last_report = ""

        self.number_factor_vars = {
            key: BooleanVar(value=key in DEFAULT_NUMBER_FACTORS)
            for key in NUMBER_FACTOR_LABELS
        }
        self.combo_factor_vars = {
            key: BooleanVar(value=key in DEFAULT_COMBO_FACTORS)
            for key in COMBO_FACTOR_LABELS
        }

        self._build_style()
        self._build_ui()
        self._load_latest_panel()
        self.root.after(350, self._bring_to_front)

    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", font=("Apple SD Gothic Neo", 12), background="#F5F7FB")
        style.configure("Title.TLabel", font=("Apple SD Gothic Neo", 24, "bold"), background="#F5F7FB", foreground="#18202A")
        style.configure("Subtle.TLabel", background="#F5F7FB", foreground="#657080")
        style.configure("Panel.TFrame", background="#FFFFFF", relief="flat")
        style.configure("Card.TFrame", background="#FFFFFF", relief="flat")
        style.configure("CardTitle.TLabel", font=("Apple SD Gothic Neo", 12, "bold"), background="#FFFFFF", foreground="#657080")
        style.configure("CardValue.TLabel", font=("Apple SD Gothic Neo", 18, "bold"), background="#FFFFFF", foreground="#18202A")
        style.configure("Primary.TButton", font=("Apple SD Gothic Neo", 13, "bold"), padding=(14, 9))
        style.configure("Tool.TButton", padding=(10, 7))
        style.configure("Treeview", rowheight=30, font=("Menlo", 12))
        style.configure("Treeview.Heading", font=("Apple SD Gothic Neo", 12, "bold"))
        style.configure("TCheckbutton", background="#FFFFFF")
        style.configure("TNotebook", background="#F5F7FB", borderwidth=0)
        style.configure("TNotebook.Tab", padding=(14, 8))

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root, padding=16)
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell)
        header.pack(fill="x")
        ttk.Label(header, text="Lotto Auto Analyzer", style="Title.TLabel").pack(side="left")
        ttk.Label(header, textvariable=self.status, style="Subtle.TLabel").pack(side="right")

        latest = ttk.Frame(shell, style="Panel.TFrame", padding=14)
        latest.pack(fill="x", pady=(14, 12))
        self.latest_card_frame = latest
        ttk.Label(latest, textvariable=self.latest_summary, style="CardValue.TLabel").grid(row=0, column=0, sticky="w")
        self.ball_frame = ttk.Frame(latest, style="Panel.TFrame")
        self.ball_frame.grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.prize_frame = ttk.Frame(latest, style="Panel.TFrame")
        self.prize_frame.grid(row=0, column=1, rowspan=2, sticky="e", padx=(20, 0))
        latest.columnconfigure(0, weight=1)

        body = ttk.Frame(shell)
        body.pack(fill="both", expand=True)

        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=14, width=320)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        sidebar.pack_propagate(False)

        self._build_settings(sidebar)
        self._build_factor_panel(sidebar)

        main = ttk.Frame(body)
        main.pack(side="left", fill="both", expand=True)

        action_row = ttk.Frame(main)
        action_row.pack(fill="x", pady=(0, 10))
        ttk.Button(action_row, text="분석 실행", style="Primary.TButton", command=self.run_analysis).pack(side="left")
        ttk.Button(action_row, text="리포트 저장", style="Tool.TButton", command=self.save_report).pack(side="left", padx=8)
        ttk.Button(action_row, text="데이터 갱신", style="Tool.TButton", command=self.refresh_data).pack(side="left")
        ttk.Button(action_row, text="폴더 열기", style="Tool.TButton", command=self.open_folder).pack(side="left", padx=8)
        self.progress = ttk.Progressbar(action_row, mode="indeterminate", length=170)
        self.progress.pack(side="right", padx=(10, 0))

        self.tabs = ttk.Notebook(main)
        self.tabs.pack(fill="both", expand=True)
        self._build_combo_tab()
        self._build_number_tab()
        self._build_report_tab()

    def _build_settings(self, parent: ttk.Frame) -> None:
        box = ttk.Frame(parent, style="Card.TFrame")
        box.pack(fill="x")
        ttk.Label(box, text="분석 설정", style="CardValue.TLabel").pack(anchor="w")
        self._field(box, "기준일", self.target_date)
        self._field(box, "후보 조합 수", self.candidates)
        self._field(box, "시드", self.seed)
        ttk.Label(
            box,
            text="후보수가 많을수록 오래 걸리지만 더 넓게 탐색합니다.",
            style="CardTitle.TLabel",
            wraplength=260,
        ).pack(anchor="w", pady=(8, 0))

    def _field(self, parent: ttk.Frame, label: str, variable: StringVar) -> None:
        ttk.Label(parent, text=label, style="CardTitle.TLabel").pack(anchor="w", pady=(12, 2))
        entry = ttk.Entry(parent, textvariable=variable)
        entry.pack(fill="x")

    def _build_factor_panel(self, parent: ttk.Frame) -> None:
        factors = ttk.Notebook(parent)
        factors.pack(fill="both", expand=True, pady=(14, 0))

        number_tab = ttk.Frame(factors, style="Card.TFrame", padding=10)
        combo_tab = ttk.Frame(factors, style="Card.TFrame", padding=10)
        factors.add(number_tab, text="번호 기법")
        factors.add(combo_tab, text="조합 필터")

        ttk.Label(number_tab, text="번호 점수에 반영", style="CardTitle.TLabel").pack(anchor="w")
        for key, label in NUMBER_FACTOR_LABELS.items():
            ttk.Checkbutton(number_tab, text=label, variable=self.number_factor_vars[key]).pack(anchor="w", pady=3)
        ttk.Button(number_tab, text="전체 선택", command=lambda: self._set_vars(self.number_factor_vars, True)).pack(fill="x", pady=(10, 4))
        ttk.Button(number_tab, text="전체 해제", command=lambda: self._set_vars(self.number_factor_vars, False)).pack(fill="x")

        ttk.Label(combo_tab, text="조합 점수에 반영", style="CardTitle.TLabel").pack(anchor="w")
        for key, label in COMBO_FACTOR_LABELS.items():
            ttk.Checkbutton(combo_tab, text=label, variable=self.combo_factor_vars[key]).pack(anchor="w", pady=3)
        ttk.Button(combo_tab, text="전체 선택", command=lambda: self._set_vars(self.combo_factor_vars, True)).pack(fill="x", pady=(10, 4))
        ttk.Button(combo_tab, text="전체 해제", command=lambda: self._set_vars(self.combo_factor_vars, False)).pack(fill="x")

    def _build_combo_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="추천 조합")
        columns = ("rank", "numbers", "score", "detail")
        self.combo_tree = ttk.Treeview(tab, columns=columns, show="headings")
        self.combo_tree.heading("rank", text="순위")
        self.combo_tree.heading("numbers", text="추천 번호")
        self.combo_tree.heading("score", text="점수")
        self.combo_tree.heading("detail", text="주요 점수")
        self.combo_tree.column("rank", width=60, anchor="center")
        self.combo_tree.column("numbers", width=210, anchor="center")
        self.combo_tree.column("score", width=90, anchor="center")
        self.combo_tree.column("detail", width=520, anchor="w")
        self.combo_tree.pack(fill="both", expand=True)

    def _build_number_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="번호 점수")
        columns = ("rank", "number", "score", "factors")
        self.number_tree = ttk.Treeview(tab, columns=columns, show="headings")
        self.number_tree.heading("rank", text="순위")
        self.number_tree.heading("number", text="번호")
        self.number_tree.heading("score", text="점수")
        self.number_tree.heading("factors", text="기법별 점수")
        self.number_tree.column("rank", width=60, anchor="center")
        self.number_tree.column("number", width=70, anchor="center")
        self.number_tree.column("score", width=90, anchor="center")
        self.number_tree.column("factors", width=660, anchor="w")
        self.number_tree.pack(fill="both", expand=True)

    def _build_report_tab(self) -> None:
        tab = ttk.Frame(self.tabs, padding=10)
        self.tabs.add(tab, text="상세 리포트")
        self.report_text = ScrolledText(tab, wrap="word", font=("Menlo", 12), padx=12, pady=12)
        self.report_text.pack(fill="both", expand=True)

    def _set_vars(self, vars_map: dict[str, BooleanVar], value: bool) -> None:
        for var in vars_map.values():
            var.set(value)

    def _load_latest_panel(self) -> None:
        try:
            row = read_latest_row(DATA_PATH)
            numbers = [int(row[f"n{i}"]) for i in range(1, 7)]
            bonus = int(row["bonus"])
            self.latest_summary.set(f"저번주 / 최신 {row['draw_no']}회  {row['date']}")
            self._draw_balls(numbers, bonus)
            self._draw_prizes(row)
        except Exception as exc:
            self.latest_summary.set(f"데이터를 읽지 못했습니다: {exc}")

    def _draw_balls(self, numbers: list[int], bonus: int) -> None:
        for child in self.ball_frame.winfo_children():
            child.destroy()
        for number in numbers:
            self._ball(self.ball_frame, number).pack(side="left", padx=(0, 7))
        ttk.Label(self.ball_frame, text="+", style="CardValue.TLabel").pack(side="left", padx=(3, 10))
        self._ball(self.ball_frame, bonus).pack(side="left")

    def _ball(self, parent: ttk.Frame, number: int) -> ttk.Label:
        label = ttk.Label(
            parent,
            text=f"{number:02d}",
            anchor="center",
            foreground="#111827",
            background=ball_color(number),
            font=("Menlo", 14, "bold"),
            padding=(10, 8),
        )
        return label

    def _draw_prizes(self, row: dict[str, str]) -> None:
        for child in self.prize_frame.winfo_children():
            child.destroy()
        headers = ("등수", "당첨자", "1인 당첨금")
        for col, text in enumerate(headers):
            ttk.Label(self.prize_frame, text=text, style="CardTitle.TLabel").grid(row=0, column=col, padx=8, sticky="e")
        for idx in range(1, 4):
            ttk.Label(self.prize_frame, text=f"{idx}등", style="CardTitle.TLabel").grid(row=idx, column=0, padx=8, pady=3, sticky="e")
            ttk.Label(self.prize_frame, text=format_count(row.get(f"rnk{idx}_winners")), style="CardValue.TLabel").grid(row=idx, column=1, padx=8, pady=3, sticky="e")
            ttk.Label(self.prize_frame, text=format_won(row.get(f"rnk{idx}_prize")), style="CardValue.TLabel").grid(row=idx, column=2, padx=8, pady=3, sticky="e")

    def selected_number_factors(self) -> list[str]:
        return [key for key, var in self.number_factor_vars.items() if var.get()]

    def selected_combo_factors(self) -> list[str]:
        return [key for key, var in self.combo_factor_vars.items() if var.get()]

    def run_analysis(self) -> None:
        self._run_in_thread(self._run_analysis_worker)

    def _run_analysis_worker(self) -> None:
        self._call_ui(self._start_busy, "분석 중...")
        try:
            target = parse_date(self.target_date.get())
            candidates = int(self.candidates.get())
            if candidates < 1000:
                raise ValueError("후보 조합 수는 1000 이상을 권장합니다.")
            seed_text = self.seed.get().strip()
            seed = int(seed_text) if seed_text else None
            number_factors = self.selected_number_factors()
            combo_factors = self.selected_combo_factors()
            if not number_factors:
                raise ValueError("번호 기법을 하나 이상 선택하세요.")
            if not combo_factors:
                raise ValueError("조합 필터를 하나 이상 선택하세요.")

            draws = load_draws(DATA_PATH)
            analyzer = LottoAnalyzer(draws)
            ranked, diagnostics = analyzer.number_scores(
                target=target,
                window=20,
                enabled_factors=number_factors,
            )
            combos = analyzer.generate_combinations(
                ranked,
                target=target,
                count=5,
                candidates=candidates,
                pool_size=30,
                window=20,
                seed=seed,
                combo_factors=combo_factors,
            )

            buffer = StringIO()
            print_report(DATA_PATH, target, analyzer, ranked, diagnostics, combos, top_numbers=15, output=buffer)
            self.last_report = buffer.getvalue()
            self._call_ui(self._render_results, ranked, combos, self.last_report)
            self._call_ui(self._stop_busy, "분석 완료")
        except Exception:
            self._call_ui(self.show_error, traceback.format_exc())

    def _render_results(self, ranked: list[NumberScore], combos: list[ComboScore], report: str) -> None:
        self.combo_tree.delete(*self.combo_tree.get_children())
        for idx, combo in enumerate(combos, 1):
            numbers = "  ".join(f"{n:02d}" for n in combo.numbers)
            detail = ", ".join(
                f"{COMBO_FACTOR_LABELS.get(k, k)} {v:+.1f}"
                for k, v in combo.parts.items()
                if k != "history_penalty"
            )
            self.combo_tree.insert("", "end", values=(idx, numbers, f"{combo.score:.2f}", detail))

        self.number_tree.delete(*self.number_tree.get_children())
        for idx, item in enumerate(ranked[:30], 1):
            factors = ", ".join(
                f"{NUMBER_FACTOR_LABELS.get(k, k)} {v:.1f}"
                for k, v in sorted(item.factors.items())
            )
            self.number_tree.insert("", "end", values=(idx, f"{item.number:02d}", f"{item.total:.2f}", factors))

        self.report_text.delete("1.0", "end")
        self.report_text.insert("end", report)
        self.tabs.select(0)

    def save_report(self) -> None:
        if not self.last_report:
            messagebox.showinfo("리포트 저장", "먼저 분석 실행을 눌러주세요.")
            return
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        default_name = f"analysis_{self.target_date.get()}.txt"
        path = filedialog.asksaveasfilename(
            title="리포트 저장",
            initialdir=str(REPORT_DIR),
            initialfile=default_name,
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return
        Path(path).write_text(self.last_report, encoding="utf-8")
        messagebox.showinfo("리포트 저장", f"저장했습니다:\n{path}")

    def refresh_data(self) -> None:
        self._run_in_thread(self._refresh_data_worker)

    def _refresh_data_worker(self) -> None:
        self._call_ui(self._start_busy, "데이터 갱신 중...")
        try:
            subprocess.run(
                [sys.executable, str(APP_DIR / "import_lotto_history_json.py")],
                cwd=str(APP_DIR),
                check=True,
                text=True,
                capture_output=True,
            )
            self._call_ui(self._load_latest_panel)
            self._call_ui(self._stop_busy, "데이터 갱신 완료")
            self._call_ui(messagebox.showinfo, "데이터 갱신", "로또 데이터를 갱신했습니다.")
        except Exception:
            self._call_ui(self.show_error, traceback.format_exc())

    def open_folder(self) -> None:
        try:
            subprocess.run(["open", str(APP_DIR)], check=False)
        except Exception as exc:
            messagebox.showerror("폴더 열기 실패", str(exc))

    def _start_busy(self, text: str) -> None:
        self.status.set(text)
        self.progress.start(10)

    def _stop_busy(self, text: str) -> None:
        self.progress.stop()
        self.status.set(text)

    def show_error(self, details: str) -> None:
        self.progress.stop()
        self.status.set("오류")
        self.report_text.delete("1.0", "end")
        self.report_text.insert("end", details)
        self.tabs.select(2)
        messagebox.showerror("오류", details.splitlines()[-1] if details else "알 수 없는 오류")

    def _bring_to_front(self) -> None:
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()
        self.root.attributes("-topmost", True)
        self.root.after(900, lambda: self.root.attributes("-topmost", False))

    def _run_in_thread(self, target) -> None:
        threading.Thread(target=target, daemon=True).start()

    def _call_ui(self, func, *args) -> None:
        self.root.after(0, lambda: func(*args))

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    app = LottoDesktopApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
