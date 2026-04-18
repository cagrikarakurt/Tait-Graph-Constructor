import tkinter as tk
from tkinter import messagebox, filedialog
import networkx as nx
import math
import json
import copy
import os
from PIL import Image


class GraphDrawer:
    def __init__(self, root):
        self.root = root
        self.root.title("Planar Multigrapher: Multi-Page Edition")

        # --- Multi-Page State ---
        self.pages = [self.create_empty_page()]
        self.current_page_idx = 0

        # --- Mode State ---
        self.modes = ["VERTEX", "EDGE", "ROUTE/EDIT", "YAJIMA-KINOSHITA-3"]
        self.current_mode_idx = 0
        self.selected_node = None
        self.active_node = None
        self.active_edge = None
        self.default_type = "+"
        self.yk3_edge_indices = []

        self.setup_ui()
        self.setup_menus()

        # --- Bindings ---
        self.root.bind("<Left>", lambda e: self.prev_page())
        self.root.bind("<Right>", lambda e: self.next_page())
        self.canvas.bind("<Button-1>", self.handle_press)
        self.canvas.bind("<B1-Motion>", self.handle_drag)
        self.canvas.bind("<ButtonRelease-1>", self.handle_release)
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-n>", lambda e: self.new_graph())
        self.root.bind("<Escape>", lambda e: self.cancel_selection())
        self.root.bind("t", lambda e: self.toggle_edge_type())
        self.root.bind("d", lambda e: self.delete_element())
        self.root.bind("<space>", lambda e: self.cycle_mode())

        self.refresh_canvas()

    def create_empty_page(self):
        return {"nodes": [], "edges": [], "history": []}

    def setup_ui(self):
        self.toolbar = tk.Frame(self.root, bg="#f0f0f0", bd=1, relief=tk.RAISED)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)

        self.btn_mode = tk.Button(self.toolbar, text="MODE: VERTEX", width=18, command=self.cycle_mode)
        self.btn_mode.pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(self.toolbar, text="Auto-Layout", command=self.relax_graph).pack(side=tk.LEFT, padx=5)

        tk.Label(self.toolbar, text="|  Page:", bg="#f0f0f0").pack(side=tk.LEFT, padx=2)
        tk.Button(self.toolbar, text="<", command=self.prev_page).pack(side=tk.LEFT)
        self.page_var = tk.StringVar(value="1/1")
        self.page_entry = tk.Entry(self.toolbar, textvariable=self.page_var, width=8, justify='center',
                                   state='readonly')
        self.page_entry.pack(side=tk.LEFT, padx=2)
        tk.Button(self.toolbar, text=">", command=self.next_page).pack(side=tk.LEFT)

        tk.Button(self.toolbar, text="+ Add Page", command=self.add_page, bg="#d4edda").pack(side=tk.LEFT, padx=5)
        tk.Button(self.toolbar, text="- Delete Page", command=self.delete_page, bg="#f8d7da").pack(side=tk.LEFT, padx=5)

        self.status_label = tk.Label(self.root, text="Ready", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas = tk.Canvas(self.root, width=800, height=600, bg="white")
        self.canvas.pack(pady=10)

    def setup_menus(self):
        self.menubar = tk.Menu(self.root)
        file_m = tk.Menu(self.menubar, tearoff=0)
        file_m.add_command(label="New Project", command=self.new_graph, accelerator="Ctrl+N")
        file_m.add_command(label="Save Project", command=self.save_graph)
        file_m.add_command(label="Load Project", command=self.load_graph)
        file_m.add_separator()
        file_m.add_command(label="Export All to PDF", command=self.export_to_pdf)
        self.menubar.add_cascade(label="File", menu=file_m)

        act_m = tk.Menu(self.menubar, tearoff=0)
        act_m.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        act_m.add_command(label="Delete Element", command=self.delete_element, accelerator="D")
        act_m.add_command(label="Toggle Sign", command=self.toggle_edge_type, accelerator="T")
        self.menubar.add_cascade(label="Actions", menu=act_m)
        self.root.config(menu=self.menubar)

    def add_page(self):
        new_page = copy.deepcopy(self.pages[self.current_page_idx])
        new_page["history"] = []
        self.pages.insert(self.current_page_idx + 1, new_page)
        self.current_page_idx += 1
        self.refresh_canvas()

    def delete_page(self):
        if len(self.pages) <= 1:
            messagebox.showwarning("Warning", "You must have at least one page.")
            return
        if messagebox.askyesno("Confirm Delete", "Permanently delete the current page?"):
            self.pages.pop(self.current_page_idx)
            if self.current_page_idx >= len(self.pages):
                self.current_page_idx = len(self.pages) - 1
            self.refresh_canvas()

    def next_page(self):
        if self.current_page_idx < len(self.pages) - 1:
            self.current_page_idx += 1;
            self.refresh_canvas()

    def prev_page(self):
        if self.current_page_idx > 0:
            self.current_page_idx -= 1;
            self.refresh_canvas()

    @property
    def current_data(self):
        return self.pages[self.current_page_idx]

    def save_state(self):
        p = self.current_data
        p["history"].append({"nodes": copy.deepcopy(p["nodes"]), "edges": copy.deepcopy(p["edges"])})
        if len(p["history"]) > 50: p["history"].pop(0)

    def undo(self):
        p = self.current_data
        if p["history"]:
            s = p["history"].pop();
            p["nodes"], p["edges"] = s["nodes"], s["edges"];
            self.refresh_canvas()

    def handle_press(self, event):
        m = self.modes[self.current_mode_idx]
        p = self.current_data
        ni, ei = self.find_closest_node(event.x, event.y), self.find_closest_edge_control(event.x, event.y)
        if m == "VERTEX":
            if ni is not None:
                self.active_node = ni
            else:
                self.save_state(); p["nodes"].append([event.x, event.y, None]); self.active_node = len(p["nodes"]) - 1
        elif m == "EDGE" and ni is not None:
            if self.selected_node is None:
                self.selected_node = ni
            else:
                self.attempt_add_edge(self.selected_node, ni); self.selected_node = None
        elif m == "ROUTE/EDIT":
            self.active_edge = ei
        elif m == "YAJIMA-KINOSHITA-3":
            if ei is not None and ei not in self.yk3_edge_indices:
                self.yk3_edge_indices.append(ei)
                if len(self.yk3_edge_indices) == 3: self.perform_yk3_move()
        self.refresh_canvas()

    def handle_drag(self, event):
        m = self.modes[self.current_mode_idx]
        p = self.current_data
        if m == "VERTEX" and self.active_node is not None:
            node = p["nodes"][self.active_node]
            dx, dy = event.x - node[0], event.y - node[1]
            node[0], node[1] = event.x, event.y
            for e in p["edges"]:
                if e["u"] == self.active_node or e["v"] == self.active_node:
                    e["cx"] += dx / 2;
                    e["cy"] += dy / 2
        elif m == "ROUTE/EDIT" and self.active_edge is not None:
            p["edges"][self.active_edge]["cx"], p["edges"][self.active_edge]["cy"] = event.x, event.y
        self.refresh_canvas()

    def handle_release(self, _):
        pass

    def delete_element(self):
        m, p = self.modes[self.current_mode_idx], self.current_data
        self.save_state()
        if m == "VERTEX" and self.active_node is not None:
            idx = self.active_node
            p["edges"] = [e for e in p["edges"] if e["u"] != idx and e["v"] != idx]
            for e in p["edges"]:
                if e["u"] > idx: e["u"] -= 1
                if e["v"] > idx: e["v"] -= 1
            p["nodes"].pop(idx);
            self.active_node = None
        elif m == "ROUTE/EDIT" and self.active_edge is not None:
            p["edges"].pop(self.active_edge);
            self.active_edge = None
        self.refresh_canvas()

    def refresh_canvas(self):
        self.canvas.delete("all");
        m, p = self.modes[self.current_mode_idx], self.current_data
        self.page_var.set(f"{self.current_page_idx + 1} / {len(self.pages)}")
        for i, e in enumerate(p["edges"]):
            n1, n2 = p["nodes"][e["u"]], p["nodes"][e["v"]]
            is_active_edge, is_yk = (m == "ROUTE/EDIT" and i == self.active_edge), (
                        m == "YAJIMA-KINOSHITA-3" and i in self.yk3_edge_indices)
            color = "green" if is_yk else ("orange" if is_active_edge else ("blue" if e["type"] == "+" else "red"))
            self.canvas.create_line(n1[0], n1[1], e["cx"], e["cy"], n2[0], n2[1], fill=color,
                                    dash=(None if e["type"] == "+" else (4, 4)),
                                    width=(4 if (is_active_edge or is_yk) else 2), smooth=True)
            if m in ["ROUTE/EDIT", "YAJIMA-KINOSHITA-3"]: self.canvas.create_oval(e["cx"] - 5, e["cy"] - 5, e["cx"] + 5,
                                                                                  e["cy"] + 5, fill=color)
        for i, n in enumerate(p["nodes"]):
            fill = "yellow" if (m == "VERTEX" and i == self.active_node) or (
                        m == "EDGE" and i == self.selected_node) else "black"
            self.canvas.create_oval(n[0] - 8, n[1] - 8, n[0] + 8, n[1] + 8, fill=fill, outline="white")

    def save_graph(self):
        fp = filedialog.asksaveasfilename(defaultextension=".json")
        if fp:
            clean = [{"nodes": p["nodes"], "edges": p["edges"]} for p in self.pages]
            with open(fp, 'w') as f: json.dump(clean, f)

    def load_graph(self):
        fp = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if fp:
            with open(fp, 'r') as f:
                data = json.load(f)
                self.pages = [{"nodes": p["nodes"], "edges": p["edges"], "history": []} for p in data]
            self.current_page_idx = 0;
            self.refresh_canvas()

    def export_to_pdf(self):
        fp = filedialog.asksaveasfilename(defaultextension=".pdf")
        if not fp: return
        pdf_pages, original_idx = [], self.current_page_idx
        try:
            for i in range(len(self.pages)):
                self.current_page_idx = i;
                self.refresh_canvas();
                self.root.update()
                self.canvas.postscript(file="tmp.ps", colormode='color')
                pdf_pages.append(Image.open("tmp.ps").convert("RGB"));
                os.remove("tmp.ps")
            if pdf_pages: pdf_pages[0].save(fp, save_all=True, append_images=pdf_pages[1:])
            messagebox.showinfo("Export", "Multi-page PDF exported.")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))
        finally:
            self.current_page_idx = original_idx; self.refresh_canvas()

    def find_closest_node(self, x, y):
        for i, n in enumerate(self.current_data["nodes"]):
            if math.hypot(x - n[0], y - n[1]) < 15: return i
        return None

    def find_closest_edge_control(self, x, y):
        for i, e in enumerate(self.current_data["edges"]):
            if math.hypot(x - e["cx"], y - e["cy"]) < 20: return i
        return None

    def cycle_mode(self):
        self.current_mode_idx = (self.current_mode_idx + 1) % len(self.modes)
        self.active_node = self.active_edge = self.selected_node = None;
        self.yk3_edge_indices = []
        self.btn_mode.config(text=f"MODE: {self.modes[self.current_mode_idx]}");
        self.refresh_canvas()

    def new_graph(self):
        if messagebox.askyesno("New", "Reset all?"): self.pages = [
            self.create_empty_page()]; self.current_page_idx = 0; self.refresh_canvas()

    def attempt_add_edge(self, u, v):
        self.save_state();
        p = self.current_data;
        pair = tuple(sorted((u, v)))
        count = sum(1 for e in p["edges"] if tuple(sorted((e["u"], e["v"]))) == pair)
        n1, n2 = p["nodes"][u], p["nodes"][v];
        mx, my = (n1[0] + n2[0]) / 2, (n1[1] + n2[1]) / 2
        cx, cy = mx, my
        if count > 0:
            dx, dy = n2[0] - n1[0], n2[1] - n1[1];
            dist = math.hypot(dx, dy)
            if dist > 0: px, py = -dy / dist, dx / dist; mag = 40 * ((count + 1) // 2); d = -1 if count % 2 == 0 else 1
            cx, cy = mx + (px * mag * d), my + (py * mag * d)
        p["edges"].append({"u": u, "v": v, "type": self.default_type, "cx": cx, "cy": cy})

    def relax_graph(self):
        p = self.current_data;
        self.save_state();
        G = nx.Graph()
        G.add_nodes_from(range(len(p["nodes"])));
        [G.add_edge(e["u"], e["v"]) for e in p["edges"]]
        pos = nx.spring_layout(G, k=2.0)
        for i, pt in pos.items(): p["nodes"][i][0], p["nodes"][i][1] = pt[0] * 300 + 400, pt[1] * 250 + 300
        self.refresh_canvas()

    def perform_yk3_move(self):
        p = self.current_data;
        idxs = self.yk3_edge_indices;
        es = [p["edges"][i] for i in idxs];
        vs = [set([e["u"], e["v"]]) for e in es];
        all_v = vs[0] | vs[1] | vs[2]
        if len(all_v) != 3 or len(set([e["type"] for e in es])) == 1: messagebox.showerror("Error",
                                                                                           "Check Triangle/Signs"); self.yk3_edge_indices = []; return
        self.save_state();
        a, b, c = list(vs[0] & vs[2])[0], list(vs[0] & vs[1])[0], list(vs[1] & vs[2])[0]
        dx, dy = sum(p["nodes"][v][0] for v in [a, b, c]) / 3, sum(p["nodes"][v][1] for v in [a, b, c]) / 3
        p["nodes"].append([dx, dy, None]);
        dv = len(p["nodes"]) - 1;
        cfgs = [(a, es[1]["type"]), (b, es[2]["type"]), (c, es[0]["type"])]
        [p["edges"].pop(i) for i in sorted(idxs, reverse=True)]
        for v_e, ot in cfgs: p["edges"].append(
            {"u": v_e, "v": dv, "type": ("-" if ot == "+" else "+"), "cx": (p["nodes"][v_e][0] + dx) / 2,
             "cy": (p["nodes"][v_e][1] + dy) / 2})
        self.yk3_edge_indices = [];
        self.refresh_canvas()

    def cancel_selection(self):
        self.yk3_edge_indices = []; self.active_node = self.active_edge = None; self.refresh_canvas()

    def toggle_edge_type(self):
        if self.modes[self.current_mode_idx] == "ROUTE/EDIT" and self.active_edge is not None:
            self.save_state();
            e = self.current_data["edges"][self.active_edge];
            e["type"] = "-" if e["type"] == "+" else "+";
            self.refresh_canvas()


if __name__ == "__main__":
    root = tk.Tk();
    app = GraphDrawer(root);
    root.mainloop()