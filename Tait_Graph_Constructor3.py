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
        self.root.title("Planar Multigrapher: Domain-Locked Edition")

        # --- Logic State ---
        self.modes = ["VERTEX", "EDGE", "ROUTE/EDIT", "YAJIMA-KINOSHITA-3"]
        self.current_mode_idx = 0
        self.nodes = []
        self.edges = []
        self.history = []
        self.selected_node = None
        self.active_node = None  # For Vertex Mode only
        self.active_edge = None  # For Route/Edit Mode only
        self.default_type = "+"
        self.yk3_edge_indices = []

        self.setup_menus()

        # --- UI Setup ---
        self.toolbar = tk.Frame(root, bg="#f0f0f0", bd=1, relief=tk.RAISED)
        self.toolbar.pack(side=tk.TOP, fill=tk.X)
        self.btn_mode = tk.Button(self.toolbar, text="MODE: VERTEX", width=25, command=self.cycle_mode)
        self.btn_mode.pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(self.toolbar, text="Auto-Layout", command=self.relax_graph).pack(side=tk.LEFT, padx=5)

        self.status_label = tk.Label(root, text="VERTEX MODE: Click node to highlight/drag | Click canvas to add",
                                     bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas = tk.Canvas(root, width=800, height=600, bg="white")
        self.canvas.pack(pady=10)

        # --- Bindings ---
        self.canvas.bind("<Button-1>", self.handle_press)
        self.canvas.bind("<B1-Motion>", self.handle_drag)
        self.canvas.bind("<ButtonRelease-1>", self.handle_release)
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Control-n>", lambda e: self.new_graph())
        self.root.bind("<Escape>", lambda e: self.cancel_selection())
        self.root.bind("t", lambda e: self.toggle_edge_type())
        self.root.bind("d", lambda e: self.delete_element())
        self.root.bind("<space>", lambda e: self.cycle_mode())

    def setup_menus(self):
        self.menubar = tk.Menu(self.root)
        file_m = tk.Menu(self.menubar, tearoff=0)
        file_m.add_command(label="New", command=self.new_graph, accelerator="Ctrl+N")
        file_m.add_command(label="Save", command=self.save_graph)
        file_m.add_command(label="Load", command=self.load_graph)
        file_m.add_separator()
        file_m.add_command(label="Export PDF", command=self.export_to_pdf)
        self.menubar.add_cascade(label="File", menu=file_m)

        edit_m = tk.Menu(self.menubar, tearoff=0)
        edit_m.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        self.menubar.add_cascade(label="Edit", menu=edit_m)

        self.action_menu = tk.Menu(self.menubar, tearoff=0)
        self.action_menu.add_command(label="Delete Highlighted", command=self.delete_element, accelerator="D")
        self.action_menu.add_command(label="Toggle Edge Sign", command=self.toggle_edge_type, accelerator="T")
        self.menubar.add_cascade(label="Actions", menu=self.action_menu)
        self.root.config(menu=self.menubar)

    def update_menu_state(self):
        m = self.modes[self.current_mode_idx]
        if (m == "VERTEX" and self.active_node is not None) or (m == "ROUTE/EDIT" and self.active_edge is not None):
            self.action_menu.entryconfig("Delete Highlighted", state="normal")
        else:
            self.action_menu.entryconfig("Delete Highlighted", state="disabled")

        if m == "ROUTE/EDIT" and self.active_edge is not None:
            self.action_menu.entryconfig("Toggle Edge Sign", state="normal")
        else:
            self.action_menu.entryconfig("Toggle Edge Sign", state="disabled")

    def cycle_mode(self):
        self.current_mode_idx = (self.current_mode_idx + 1) % len(self.modes)
        self.active_node = self.active_edge = self.selected_node = None
        self.yk3_edge_indices = []
        mode_name = self.modes[self.current_mode_idx]
        self.btn_mode.config(text=f"MODE: {mode_name}")

        tips = {
            "VERTEX": "VERTEX MODE: Click node to highlight/drag | Click canvas to add",
            "EDGE": "EDGE MODE: Connect two nodes",
            "ROUTE/EDIT": "ROUTE MODE: Click edge midpoint to highlight/curve",
            "YAJIMA-KINOSHITA-3": "YK3 MODE: Select 3 edges for triangle move"
        }
        self.status_label.config(text=tips[mode_name])
        self.update_menu_state()
        self.refresh_canvas()

    def handle_press(self, event):
        m = self.modes[self.current_mode_idx]
        ni = self.find_closest_node(event.x, event.y)
        ei = self.find_closest_edge_control(event.x, event.y)

        if m == "VERTEX":
            self.active_edge = None
            if ni is not None:
                self.active_node = ni
            else:
                self.save_state()
                self.nodes.append([event.x, event.y, None])
                self.active_node = len(self.nodes) - 1
        elif m == "EDGE" and ni is not None:
            if self.selected_node is None:
                self.selected_node = ni
            else:
                self.attempt_add_edge(self.selected_node, ni)
                self.selected_node = None
        elif m == "ROUTE/EDIT":
            self.active_node = None
            self.active_edge = ei  # Can ONLY select edge here
        elif m == "YAJIMA-KINOSHITA-3":
            if ei is not None and ei not in self.yk3_edge_indices:
                self.yk3_edge_indices.append(ei)
                if len(self.yk3_edge_indices) == 3: self.perform_yk3_move()

        self.update_menu_state()
        self.refresh_canvas()

    def handle_drag(self, event):
        m = self.modes[self.current_mode_idx]
        if m == "VERTEX" and self.active_node is not None:
            node = self.nodes[self.active_node]
            dx, dy = event.x - node[0], event.y - node[1]
            node[0], node[1] = event.x, event.y
            # Move control points half-way to maintain curve relative to move
            for e in self.edges:
                if e["u"] == self.active_node or e["v"] == self.active_node:
                    e["cx"] += dx / 2;
                    e["cy"] += dy / 2
        elif m == "ROUTE/EDIT" and self.active_edge is not None:
            self.edges[self.active_edge]["cx"], self.edges[self.active_edge]["cy"] = event.x, event.y
        self.refresh_canvas()

    def handle_release(self, _):
        pass  # Keep selection active for menu actions

    def delete_element(self):
        m = self.modes[self.current_mode_idx]
        self.save_state()
        if m == "VERTEX" and self.active_node is not None:
            idx = self.active_node
            # CASCADE DELETE: Remove all incident edges
            self.edges = [e for e in self.edges if e["u"] != idx and e["v"] != idx]
            # Shift indices for all other edges
            for e in self.edges:
                if e["u"] > idx: e["u"] -= 1
                if e["v"] > idx: e["v"] -= 1
            self.nodes.pop(idx)
            self.active_node = None
        elif m == "ROUTE/EDIT" and self.active_edge is not None:
            self.edges.pop(self.active_edge)
            self.active_edge = None

        self.update_menu_state()
        self.refresh_canvas()

    def toggle_edge_type(self):
        if self.modes[self.current_mode_idx] == "ROUTE/EDIT" and self.active_edge is not None:
            self.save_state()
            e = self.edges[self.active_edge]
            e["type"] = "-" if e["type"] == "+" else "+"
            self.refresh_canvas()

    def refresh_canvas(self):
        self.canvas.delete("all")
        m = self.modes[self.current_mode_idx]

        # Draw Edges
        for i, e in enumerate(self.edges):
            n1, n2 = self.nodes[e["u"]], self.nodes[e["v"]]
            is_active_edge = (m == "ROUTE/EDIT" and i == self.active_edge)
            is_yk = (m == "YAJIMA-KINOSHITA-3" and i in self.yk3_edge_indices)

            color = "green" if is_yk else ("orange" if is_active_edge else ("blue" if e["type"] == "+" else "red"))
            width = 4 if (is_active_edge or is_yk) else 2

            self.canvas.create_line(n1[0], n1[1], e["cx"], e["cy"], n2[0], n2[1],
                                    fill=color, dash=(None if e["type"] == "+" else (4, 4)),
                                    width=width, smooth=True)
            if m in ["ROUTE/EDIT", "YAJIMA-KINOSHITA-3"]:
                self.canvas.create_oval(e["cx"] - 5, e["cy"] - 5, e["cx"] + 5, e["cy"] + 5, fill=color)

        # Draw Nodes
        for i, n in enumerate(self.nodes):
            is_active_node = (m == "VERTEX" and i == self.active_node)
            is_selected = (m == "EDGE" and i == self.selected_node)

            fill = "yellow" if (is_active_node or is_selected) else "black"
            self.canvas.create_oval(n[0] - 8, n[1] - 8, n[0] + 8, n[1] + 8, fill=fill, outline="white")

    # --- Core Helpers ---
    def calculate_offset(self, u, v, count):
        n1, n2 = self.nodes[u], self.nodes[v]
        mid_x, mid_y = (n1[0] + n2[0]) / 2, (n1[1] + n2[1]) / 2
        if count == 0: return mid_x, mid_y
        dx, dy = n2[0] - n1[0], n2[1] - n1[1]
        dist = math.hypot(dx, dy)
        if dist == 0: return mid_x, mid_y
        px, py = -dy / dist, dx / dist
        magnitude = 40 * ((count + 1) // 2)
        direction = -1 if count % 2 == 0 else 1
        return mid_x + (px * magnitude * direction), mid_y + (py * magnitude * direction)

    def attempt_add_edge(self, u, v):
        self.save_state()
        pair = tuple(sorted((u, v)))
        count = sum(1 for e in self.edges if tuple(sorted((e["u"], e["v"]))) == pair)
        cx, cy = self.calculate_offset(u, v, count)
        self.edges.append({"u": u, "v": v, "type": self.default_type, "cx": cx, "cy": cy})

    def find_closest_node(self, x, y):
        for i, n in enumerate(self.nodes):
            if math.hypot(x - n[0], y - n[1]) < 15: return i
        return None

    def find_closest_edge_control(self, x, y):
        for i, e in enumerate(self.edges):
            if math.hypot(x - e["cx"], y - e["cy"]) < 20: return i
        return None

    def save_state(self):
        self.history.append({"nodes": copy.deepcopy(self.nodes), "edges": copy.deepcopy(self.edges)})
        if len(self.history) > 50: self.history.pop(0)

    def undo(self):
        if self.history:
            s = self.history.pop();
            self.nodes, self.edges = s["nodes"], s["edges"]
            self.refresh_canvas()

    def relax_graph(self):
        if not self.nodes: return
        self.save_state()
        G = nx.Graph()
        G.add_nodes_from(range(len(self.nodes)))
        for e in self.edges: G.add_edge(e["u"], e["v"])
        pos = nx.spring_layout(G, k=2.0)
        for i, p in pos.items():
            self.nodes[i][0], self.nodes[i][1] = p[0] * 300 + 400, p[1] * 250 + 300
        counts = {}
        for e in self.edges:
            pair = tuple(sorted((e["u"], e["v"])))
            c = counts.get(pair, 0)
            e["cx"], e["cy"] = self.calculate_offset(e["u"], e["v"], c)
            counts[pair] = c + 1
        self.refresh_canvas()

    def perform_yk3_move(self):
        idx_list = self.yk3_edge_indices
        e1, e2, e3 = [self.edges[i] for i in idx_list]
        v_sets = [set([e["u"], e["v"]]) for e in [e1, e2, e3]]
        all_v = v_sets[0] | v_sets[1] | v_sets[2]
        if len(all_v) != 3 or len(set([e["type"] for e in [e1, e2, e3]])) == 1:
            messagebox.showerror("Error", "Invalid Triangle or Signs.")
            self.yk3_edge_indices = []
            return
        self.save_state()
        a = list(v_sets[0] & v_sets[2])[0]
        b = list(v_sets[0] & v_sets[1])[0]
        c = list(v_sets[1] & v_sets[2])[0]
        dx = sum(self.nodes[v][0] for v in [a, b, c]) / 3
        dy = sum(self.nodes[v][1] for v in [a, b, c]) / 3
        self.nodes.append([dx, dy, None])
        new_v = len(self.nodes) - 1
        new_configs = [(a, e2["type"]), (b, e3["type"]), (c, e1["type"])]
        for old_i in sorted(idx_list, reverse=True): self.edges.pop(old_i)
        for v_end, old_type in new_configs:
            new_type = "-" if old_type == "+" else "+"
            self.edges.append({"u": v_end, "v": new_v, "type": new_type, "cx": (self.nodes[v_end][0] + dx) / 2,
                               "cy": (self.nodes[v_end][1] + dy) / 2})
        self.yk3_edge_indices = []
        self.refresh_canvas()

    def cancel_selection(self):
        self.yk3_edge_indices = []; self.active_node = self.active_edge = None; self.refresh_canvas()

    def new_graph(self):
        self.nodes, self.edges, self.history = [], [], []; self.refresh_canvas()

    def save_graph(self):
        fp = filedialog.asksaveasfilename(defaultextension=".json")
        if fp:
            with open(fp, 'w') as f: json.dump({"nodes": self.nodes, "edges": self.edges}, f)

    def load_graph(self):
        fp = filedialog.askopenfilename()
        if fp:
            with open(fp, 'r') as f: d = json.load(f)
            self.nodes, self.edges = d["nodes"], d["edges"];
            self.refresh_canvas()

    def export_to_pdf(self):
        fp = filedialog.asksaveasfilename(defaultextension=".pdf")
        if fp:
            self.canvas.postscript(file="tmp.ps", colormode='color')
            Image.open("tmp.ps").save(fp, "PDF");
            os.remove("tmp.ps")


if __name__ == "__main__":
    root = tk.Tk();
    app = GraphDrawer(root);
    root.mainloop()